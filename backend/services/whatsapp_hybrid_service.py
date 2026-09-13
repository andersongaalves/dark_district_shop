"""Durable hybrid workflow. Webhook persistence never waits for LLM or Meta."""
import logging
from sqlalchemy import select, update
from core.config import settings
from database import SessionLocal
from models.atendimento import Conversation, ChannelIdentity, DeliveryJob, Message, utc_now
from services.customer_service import resolve_whatsapp
from services.whatsapp_human_service import WELCOME_TEXT
from services import delivery_service as delivery, whatsapp_ai_service as ai, attendant_notification_service as notifications
from integrations.whatsapp.client import send_text, WhatsAppDeliveryError

logger = logging.getLogger(__name__)


def queue(db, c, key, purpose, payload, *, kind="outbound"):
    key = "hybrid:" + key
    if db.scalar(select(DeliveryJob.id).where(DeliveryJob.external_id == key)):
        return
    identity = db.get(ChannelIdentity, c.identity_id)
    phone, recipient = identity.external_id.split(":", 1)
    db.add(DeliveryJob(kind=kind, external_id=key, conversation_id=c.id,
        routing_key=identity.external_id, payload={"purpose": purpose, "cycle": c.cycle,
        "version": c.version, "phone_number_id": phone, "recipient": recipient, **payload}))
    db.flush()


def outbound(db, c, key, text, purpose, timestamp, products=None):
    message = Message(conversation_id=c.id, sender="assistant", external_id="hybrid:" + key,
                      content=text, extra_data={"cycle": c.cycle, "delivery_status": "pending"})
    db.add(message)
    db.flush()
    queue(db, c, key, purpose, {"text": text, "timestamp": timestamp, "message_id": message.id,
                               "products": products or []})


def handoff(db, c, reason, source, *, transition=True):
    if c.status == "WAITING_HUMAN":
        return
    c.status = "WAITING_HUMAN"
    c.handoff_reason = reason
    c.version += 1
    c.updated_at = utc_now()
    key = f"handoff:{c.id}:{c.cycle}:{c.version}"
    c.context = {**(c.context or {}), "handoff_event": c.version}
    timestamp = (source.extra_data or {}).get("received_timestamp", utc_now().timestamp())
    if transition:
        outbound(db, c, key, ai.PURCHASE_TEXT if reason == "PURCHASE_INTENT" else ai.HANDOFF_TEXT,
                 "handoff", timestamp)
    identity = db.get(ChannelIdentity, c.identity_id)
    customer = identity.external_id.split(":", 1)[-1]
    if customer != settings.WHATSAPP_ATTENDANT_NUMBER:
        queue(db, c, key + ":notify", "notification", {"customer": customer, "reason": reason,
              "excerpt": source.content[:300]})
    logger.info("ai_handoff_created conversation_id=%s reason=%s", c.id, reason)


def receive_messages(db, incoming_messages):
    for incoming in incoming_messages:
        c = resolve_whatsapp(db, incoming.external_identity)
        c = db.scalar(select(Conversation).where(Conversation.id == c.id).with_for_update().execution_options(populate_existing=True))
        if db.scalar(select(Message.id).where(Message.conversation_id == c.id,
            Message.sender == "customer", Message.external_id == incoming.message_id)):
            db.commit()
            continue
        first = not db.scalar(select(Message.id).where(Message.conversation_id == c.id).limit(1))
        reopened = c.status == "CLOSED"
        if first:
            c.ai_mode = settings.WHATSAPP_AI_DEFAULT_MODE
        if incoming.sender == settings.WHATSAPP_ATTENDANT_NUMBER:
            c.ai_mode = "OFF"  # Attendant messages cannot trigger a notification loop.
        if reopened:
            c.cycle += 1
            logger.info("conversation_reopened conversation_id=%s cycle=%s", c.id, c.cycle)
        if first or reopened:
            c.context = {}
            c.handoff_reason = None
            c.failure_count = 0
            c.processing_token = None
            c.processing_until = None
            c.status = "AI" if c.ai_mode == "AUTO" else "HUMAN"  # human mode enters handoff below
        c.version += 1
        c.updated_at = utc_now()
        source = Message(conversation_id=c.id, sender="customer", external_id=incoming.message_id,
            content=incoming.text, extra_data={"cycle": c.cycle, "received_timestamp": incoming.timestamp})
        db.add(source)
        db.flush()
        db.execute(update(DeliveryJob).where(DeliveryJob.routing_key == incoming.external_identity,
            DeliveryJob.status == "pending", ~DeliveryJob.external_id.startswith("hybrid:")).values(status="cancelled", error_code="legacy_queue"))
        if first or reopened:
            outbound(db, c, f"welcome:{c.id}:{c.cycle}", WELCOME_TEXT, "greeting", incoming.timestamp)
            if c.ai_mode != "AUTO":
                handoff(db, c, "HUMAN_REQUESTED", source, transition=False)
        if c.status == "AI" and c.ai_mode == "AUTO":
            reason = ai.reason_for(source.content)
            if reason:
                handoff(db, c, reason, source)
            else:
                queue(db, c, f"auto:{c.id}:{source.id}", "auto", {"source_id": source.id}, kind="inbound")
        db.commit()


def process_auto(job, sessions):
    with sessions() as db:
        c = db.get(Conversation, job.conversation_id)
        source = db.get(Message, job.payload["source_id"])
        if not c or not source or c.status != "AI" or c.ai_mode != "AUTO" or c.cycle != job.payload["cycle"]:
            delivery._finish(job, "cancelled", session_factory=sessions)
            return
        latest = db.scalar(select(Message.id).where(Message.conversation_id == c.id, Message.sender == "customer")
                           .order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
        if latest != source.id:
            delivery._finish(job, "cancelled", session_factory=sessions)
            return
        version, conversation_id = c.version, c.id
        incoming = ai.agent_input(db, c, source)
        db.rollback()
        reason = None
        try:
            result = ai.ai_agent.respond(db, incoming)
            if result.type == "error":
                reason = "AI_FAILURE"
            elif result.handoff:
                reason = "HUMAN_REQUESTED"
            elif result.message.startswith(("Não entendi bem", "Essa informação precisa", "Não consegui")):
                reason = "LOW_CONFIDENCE"
        except Exception:
            reason = "AI_FAILURE"
        db.rollback()
        c = db.scalar(select(Conversation).where(Conversation.id == conversation_id).with_for_update().execution_options(populate_existing=True))
        owned = db.scalar(select(DeliveryJob.id).where(*delivery._ownership(job)))
        if not owned:
            return
        valid = c and c.version == version and c.status == "AI" and c.ai_mode == "AUTO"
        if valid:
            source = db.get(Message, job.payload["source_id"])
            if reason:
                handoff(db, c, reason, source)
            else:
                c.context = result.context
                from channels.whatsapp_channel import render_text
                outbound(db, c, f"reply:{source.id}", render_text(result), "auto",
                         source.extra_data["received_timestamp"], [p.model_dump(mode="json") for p in result.products])
        db.execute(update(DeliveryJob).where(*delivery._ownership(job)).values(status="sent" if valid else "cancelled", locked_at=None))
        db.commit()


def process_outbound(job, sessions):
    # Serialize dispatch against claim/close/mode changes. Only bounded Meta IO
    # holds this row lock; LLM generation always happens outside transactions.
    with sessions() as db:
        c = db.scalar(select(Conversation).where(Conversation.id == job.conversation_id).with_for_update())
        if not db.scalar(select(DeliveryJob.id).where(*delivery._ownership(job))):
            return
        p = job.payload
        purpose = p["purpose"]
        valid = c and c.cycle == p["cycle"] and c.status != "CLOSED" and p["phone_number_id"] == settings.WHATSAPP_PHONE_NUMBER_ID
        if purpose == "auto":
            valid = valid and c.status == "AI" and c.ai_mode == "AUTO" and c.version == p["version"]
        if purpose in {"handoff", "notification"}:
            valid = valid and c.status == "WAITING_HUMAN" and c.handoff_reason == p.get("reason", c.handoff_reason)
            valid = valid and (c.context or {}).get("handoff_event") == p["version"]
            # New messages in WAITING do not invalidate this one handoff event.
        if purpose != "notification":
            valid = valid and delivery._within_reply_window(p)
        status, metadata = "cancelled", {}
        if valid:
            try:
                if purpose == "notification":
                    meta_id = notifications.deliver(db, p)
                else:
                    body = delivery._current_outbound_text(db, p)
                    meta_id = send_text(p["recipient"], body)
                    if body != p["text"] and p.get("message_id"):
                        db.get(Message, p["message_id"]).content = body
                status, metadata = "sent", {"meta_message_id": meta_id}
                logger.info("%s conversation_id=%s", "attendant_notification_sent" if purpose == "notification" else "ai_auto_reply_sent", c.id)
            except WhatsAppDeliveryError as error:
                status = "uncertain" if error.uncertain else "failed"
                metadata = {"error_code": error.code}
            except Exception:
                status, metadata = "uncertain", {"error_code": "send_unknown"}
        db.execute(update(DeliveryJob).where(*delivery._ownership(job)).values(status=status, locked_at=None,
            error_code=metadata.get("error_code"), payload={**p, **metadata}, updated_at=utc_now()))
        if p.get("message_id"):
            db.execute(update(Message).where(Message.id == p["message_id"]).values(
                extra_data={"cycle": p["cycle"], "delivery_status": status, **metadata}))
        db.commit()


def run_once(session_factory=SessionLocal):
    if not settings.AI_WHATSAPP_ENABLED or not settings.WHATSAPP_ENABLED:
        return False
    job = delivery.claim_next(session_factory, prefix="hybrid:")
    if not job:
        return False
    try:
        if job.kind == "inbound":
            process_auto(job, session_factory)
        else:
            process_outbound(job, session_factory)
    except Exception:
        if job.kind == "inbound" and job.attempts >= settings.DELIVERY_MAX_ATTEMPTS:
            with session_factory() as db:
                c = db.scalar(select(Conversation).where(Conversation.id == job.conversation_id).with_for_update())
                source = db.get(Message, job.payload.get("source_id"))
                if c and source and c.status == "AI" and c.ai_mode == "AUTO":
                    handoff(db, c, "AI_FAILURE", source)
                    db.commit()
        delivery._finish(job, "uncertain" if job.kind == "outbound" else "pending" if job.attempts < settings.DELIVERY_MAX_ATTEMPTS else "failed",
                         error_code="hybrid_processing_error", session_factory=session_factory)
    return True
