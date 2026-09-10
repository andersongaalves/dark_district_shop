"""Persistent inbox/outbox jobs with bounded retries and short transactions.

An ambiguous outbound request is quarantined instead of resent. This provides
deduplicated event handling without pretending the external API is exactly-once.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from channels.whatsapp_channel import IncomingText, render_text
from core.config import settings
from database import SessionLocal
from integrations.whatsapp.client import WhatsAppDeliveryError, send_text
from models.atendimento import Conversation, DeliveryJob

logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


def event_key(kind: str, phone: str, message_id: str) -> str:
    digest = hashlib.sha256(f"{phone}:{message_id}".encode()).hexdigest()
    return f"wa:{kind}:{digest}"


def enqueue_inbound(db, messages: list[IncomingText]) -> int:
    added = 0
    for message in messages:
        external_id = event_key("in", message.phone_number_id, message.message_id)
        try:
            with db.begin_nested():
                db.add(DeliveryJob(kind="inbound", channel="whatsapp", external_id=external_id,
                                   routing_key=message.external_identity,
                                   payload=asdict(message), status="pending", attempts=0,
                                   available_at=utcnow()))
                db.flush()
            added += 1
        except IntegrityError:
            # Only the known unique event is a harmless duplicate; other failures
            # must reach Meta as a failed request, so it can retry persistence.
            if db.scalar(select(DeliveryJob.id).where(DeliveryJob.external_id == external_id)) is None:
                raise
    db.commit()
    return added


@dataclass(frozen=True)
class ClaimedJob:
    id: str
    kind: str
    external_id: str
    payload: dict
    conversation_id: str | None
    attempts: int
    locked_at: datetime


def _ownership(job):
    return (DeliveryJob.id == job.id, DeliveryJob.status == "processing",
            DeliveryJob.locked_at == job.locked_at)


def ready_jobs_query(now):
    """Only the oldest unfinished job for each identity may acquire a lease.

    A retry scheduled in the future still blocks later messages for that person;
    unrelated identities can continue. PostgreSQL workers skip locked candidates.
    """
    earlier = aliased(DeliveryJob)
    preceding_job = exists(select(earlier.id).where(
        earlier.routing_key == DeliveryJob.routing_key,
        earlier.status.in_(("pending", "processing")),
        or_(earlier.created_at < DeliveryJob.created_at,
            and_(earlier.created_at == DeliveryJob.created_at, earlier.id < DeliveryJob.id)),
    ))
    return select(DeliveryJob).where(
        DeliveryJob.status == "pending", DeliveryJob.available_at <= now,
        DeliveryJob.channel == "whatsapp", ~preceding_job,
    ).order_by(DeliveryJob.created_at, DeliveryJob.id).with_for_update(skip_locked=True).limit(1)


def claim_next(session_factory=SessionLocal) -> ClaimedJob | None:
    now = utcnow()
    stale = now - timedelta(seconds=settings.DELIVERY_LEASE_SECONDS)
    with session_factory() as db:
        # If the process died during a send, delivery is unknown. Never resend it
        # automatically. Inbound processing is safe to repeat by message ID.
        db.execute(update(DeliveryJob).where(
            DeliveryJob.status == "processing", DeliveryJob.locked_at < stale,
            DeliveryJob.kind == "outbound",
        ).values(status="uncertain", error_code="worker_interrupted", locked_at=None, updated_at=now))
        db.execute(update(DeliveryJob).where(
            DeliveryJob.status == "processing", DeliveryJob.locked_at < stale,
            DeliveryJob.kind == "inbound", DeliveryJob.attempts < settings.DELIVERY_MAX_ATTEMPTS,
        ).values(status="pending", available_at=now, locked_at=None, updated_at=now))
        db.execute(update(DeliveryJob).where(
            DeliveryJob.status == "processing", DeliveryJob.locked_at < stale,
            DeliveryJob.kind == "inbound", DeliveryJob.attempts >= settings.DELIVERY_MAX_ATTEMPTS,
        ).values(status="failed", error_code="attempts_exhausted", locked_at=None, updated_at=now))
        candidate = db.scalar(ready_jobs_query(now))
        if candidate is None:
            db.commit()
            return None
        job = ClaimedJob(candidate.id, candidate.kind, candidate.external_id,
                         dict(candidate.payload), candidate.conversation_id, candidate.attempts + 1, now)
        claimed = db.execute(update(DeliveryJob).where(
            DeliveryJob.id == candidate.id, DeliveryJob.status == "pending",
        ).values(status="processing", attempts=job.attempts, locked_at=now, updated_at=now))
        db.commit()
        return job if claimed.rowcount else None


def _finish(job, status, *, error_code=None, session_factory=SessionLocal, extra_payload=None):
    values = {"status": status, "error_code": error_code, "locked_at": None, "updated_at": utcnow()}
    if status == "pending":
        values["available_at"] = utcnow() + timedelta(seconds=min(60, 5 * 2 ** job.attempts))
    if extra_payload:
        values["payload"] = {**job.payload, **extra_payload}
    with session_factory() as db:
        db.execute(update(DeliveryJob).where(*_ownership(job)).values(**values))
        db.commit()
    logger.info("whatsapp_job_finished job_id=%s status=%s error_code=%s", job.id, status, error_code)


def _within_reply_window(payload):
    try:
        age = utcnow().timestamp() - int(payload["timestamp"])
        return -300 <= age < 24 * 60 * 60
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _process_inbound(job, session_factory, receiver):
    if not _within_reply_window(job.payload):
        _finish(job, "cancelled", error_code="reply_window_expired", session_factory=session_factory)
        return
    message = IncomingText(**job.payload)
    with session_factory() as db:
        reply = receiver(db, external_id=message.external_identity,
                         message_id=message.message_id, text=message.text)
        # A receiver owns its processing commits. Close any read transaction before
        # the next phase; rendering does not perform network calls.
        db.commit()
    body = render_text(reply)
    should_send = bool(body and reply.type != "silent" and reply.status != "HUMAN"
                       and (reply.status == "AI" or reply.type == "handoff"))
    with session_factory() as db:
        done = db.execute(update(DeliveryJob).where(*_ownership(job)).values(
            status="sent", conversation_id=reply.conversation_id,
            source_message_id=reply.message_id, locked_at=None, error_code=None, updated_at=utcnow()))
        if not done.rowcount:
            db.rollback()
            return
        if should_send:
            key = event_key("out", message.phone_number_id, message.message_id)
            if db.scalar(select(DeliveryJob.id).where(DeliveryJob.external_id == key)) is None:
                db.add(DeliveryJob(
                    kind="outbound", channel="whatsapp", external_id=key, status="pending", attempts=0,
                    routing_key=message.external_identity,
                    conversation_id=reply.conversation_id, source_message_id=reply.message_id,
                    available_at=utcnow(), payload={
                        "recipient": message.sender, "phone_number_id": message.phone_number_id,
                        "text": body, "timestamp": message.timestamp,
                        "allow_waiting": reply.type == "handoff",
                        "products": [product.model_dump(mode="json") for product in reply.products],
                    },
                ))
        db.commit()
    logger.info("whatsapp_inbound_processed job_id=%s conversation_id=%s", job.id, reply.conversation_id)


def _process_outbound(job, session_factory, sender):
    if not _within_reply_window(job.payload):
        _finish(job, "cancelled", error_code="reply_window_expired", session_factory=session_factory)
        return
    if job.payload.get("phone_number_id") != settings.WHATSAPP_PHONE_NUMBER_ID:
        _finish(job, "cancelled", error_code="account_changed", session_factory=session_factory)
        return
    with session_factory() as db:
        owned = db.scalar(select(DeliveryJob.id).where(*_ownership(job)))
        body = _current_outbound_text(db, job.payload)
        state = db.scalar(select(Conversation.status).where(Conversation.id == job.conversation_id))
        allowed = state == "AI" or (state == "WAITING_HUMAN" and job.payload.get("allow_waiting") is True)
        # Release the database connection before calling the external API.
        db.rollback()
    if not owned:
        return
    if not allowed:
        _finish(job, "cancelled", error_code="human_handoff", session_factory=session_factory)
        return
    external_id = sender(job.payload["recipient"], body)
    _finish(job, "sent", session_factory=session_factory, extra_payload={"meta_message_id": external_id})


def _current_outbound_text(db, payload):
    """A delayed reply must not repeat prices or inventory that changed in queue."""
    snapshots = payload.get("products", [])
    if not snapshots:
        return payload["text"]
    from services.produtos import listar_produtos
    from tools.catalog_tools import serialize_product
    products = listar_produtos(db, product_ids=[product["id"] for product in snapshots], limit=len(snapshots))
    current = {product.id: serialize_product(product).model_dump(mode="json") for product in products}
    if any(current.get(product["id"]) != product for product in snapshots):
        return ("O catálogo mudou desde a consulta. Envie sua busca novamente para eu conferir "
                "os valores e a disponibilidade atuais.")
    return payload["text"]


def run_once(*, session_factory=SessionLocal, receiver=None, sender=None) -> bool:
    """Process one job; sessions are never shared across threads or HTTP requests."""
    if not settings.WHATSAPP_ENABLED:
        return False
    if receiver is None:
        from services.conversation_service import receive_whatsapp
        receiver = receive_whatsapp
    job = claim_next(session_factory)
    if job is None:
        return False
    try:
        if job.kind == "inbound":
            _process_inbound(job, session_factory, receiver)
        elif job.kind == "outbound":
            _process_outbound(job, session_factory, sender or send_text)
        else:
            _finish(job, "failed", error_code="invalid_job_kind", session_factory=session_factory)
    except WhatsAppDeliveryError as exc:
        status = "uncertain" if exc.uncertain else (
            "pending" if exc.retryable and job.attempts < settings.DELIVERY_MAX_ATTEMPTS else "failed")
        _finish(job, status, error_code=exc.code, session_factory=session_factory)
    except HTTPException as exc:
        retryable = exc.status_code in (409, 429) or exc.status_code >= 500
        status = "pending" if retryable and job.attempts < settings.DELIVERY_MAX_ATTEMPTS else "failed"
        _finish(job, status, error_code="conversation_unavailable", session_factory=session_factory)
    except Exception:
        # Exception text/traceback may embed provider requests or customer text.
        status = "uncertain" if job.kind == "outbound" else (
            "pending" if job.attempts < settings.DELIVERY_MAX_ATTEMPTS else "failed")
        _finish(job, status, error_code="processing_error", session_factory=session_factory)
    return True
