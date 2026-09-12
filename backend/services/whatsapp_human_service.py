"""Persist human WhatsApp conversations and reserve one initial greeting.

The reservation commits before network IO. A duplicate webhook never retries a
send, including when Meta's acceptance or the final database commit is uncertain.
No agent, catalog tool, DeliveryJob consumer or background process is involved.
"""
from dataclasses import dataclass
import logging

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from integrations.whatsapp.client import send_text, WhatsAppDeliveryError
from models.atendimento import Conversation, DeliveryJob, Message, utc_now
from services.customer_service import resolve_whatsapp

logger = logging.getLogger(__name__)
WELCOME_ID = "whatsapp:initial-human-greeting:v1"
WELCOME_TEXT = ("Olá! 🖤 Recebemos sua mensagem.\n\n"
                "Em breve, um atendente da Dark District entrará em contato com você.\n\n"
                "Obrigado pela preferência.\nDark District — Vista o seu lado obscuro.")


@dataclass(frozen=True)
class Greeting:
    message_id: str
    recipient: str


def persist_messages(db, messages):
    """Durably store the whole parsed batch before the API starts sending."""
    greetings = []
    added = 0
    for incoming in messages:
        conversation = resolve_whatsapp(db, incoming.external_identity)
        conversation = db.scalar(select(Conversation).where(Conversation.id == conversation.id)
                                 .with_for_update().execution_options(populate_existing=True))
        # Freeze old AI outbox entries for this identity during the transition.
        db.execute(update(DeliveryJob).where(DeliveryJob.routing_key == incoming.external_identity,
            DeliveryJob.status == "pending").values(status="cancelled", error_code="human_only"))
        duplicate = db.scalar(select(Message.id).where(Message.conversation_id == conversation.id,
            Message.external_id == incoming.message_id, Message.sender == "customer"))
        if duplicate:
            db.commit()
            continue
        if conversation.status != "HUMAN":
            conversation.status = "WAITING_HUMAN"
        conversation.version += 1
        conversation.processing_token = None
        conversation.processing_until = None
        conversation.updated_at = utc_now()
        has_history = db.scalar(select(Message.id).where(Message.conversation_id == conversation.id).limit(1))
        try:
            db.add(Message(conversation_id=conversation.id, external_id=incoming.message_id,
                           sender="customer", content=incoming.text,
                           extra_data={"received_timestamp": incoming.timestamp}))
            greeting = None
            if not has_history:
                within_window = -300 <= utc_now().timestamp() - incoming.timestamp < 24 * 60 * 60
                greeting = Message(conversation_id=conversation.id, external_id=WELCOME_ID,
                    sender="assistant", content=WELCOME_TEXT,
                    extra_data={"automation": "initial_human_greeting",
                                "delivery_status": "sending" if within_window else "cancelled",
                                "error_code": None if within_window else "reply_window_expired"})
                db.add(greeting)
            db.flush()
            greeting_id = greeting.id if greeting is not None and within_window else None
            db.commit()
        except IntegrityError:
            db.rollback()
            # Concurrent duplicate events are harmless. Other integrity failures
            # must reach Meta so persistence can be retried.
            if db.scalar(select(Message.id).where(Message.conversation_id == conversation.id,
                Message.external_id == incoming.message_id, Message.sender == "customer")) is None:
                raise
            db.rollback()
            continue
        added += 1
        if greeting_id:
            greetings.append(Greeting(greeting_id, incoming.sender))
    logger.info("whatsapp_messages_persisted count=%s greetings=%s", added, len(greetings))
    return greetings


def send_greetings(db, greetings, *, sender=None):
    for greeting in greetings:
        metadata = {"automation": "initial_human_greeting"}
        try:
            meta_id = (sender or send_text)(greeting.recipient, WELCOME_TEXT)
            metadata.update(delivery_status="sent", meta_message_id=meta_id)
        except WhatsAppDeliveryError as error:
            metadata.update(delivery_status="uncertain" if error.uncertain else "failed", error_code=error.code)
        except Exception:
            metadata.update(delivery_status="uncertain", error_code="send_unknown")
        try:
            db.execute(update(Message).where(Message.id == greeting.message_id).values(extra_data=metadata))
            db.commit()
        except Exception:
            db.rollback()
            # The incoming message and greeting reservation are already committed.
            logger.error("whatsapp_greeting_result_unrecorded message_id=%s", greeting.message_id)
            continue
        logger.info("whatsapp_greeting_finished message_id=%s status=%s error_code=%s",
                    greeting.message_id, metadata["delivery_status"], metadata.get("error_code"))


def receive_messages(db, messages):
    greetings = persist_messages(db, messages)
    send_greetings(db, greetings)
