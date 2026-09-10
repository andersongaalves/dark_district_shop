"""Adapt authenticated visitor input to the shared conversation pipeline."""
from services import conversation_service


def receive_message(db, conversation, data):
    return conversation_service.receive(db, conversation, str(data.message_id), data.message)
