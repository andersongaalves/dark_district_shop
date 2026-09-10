from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.security import get_current_user
from database import get_db
from models.atendimento import Conversation
from schemas.atendimento import ChatHistory, ConversationStatus, ConversationUpdate
from services import conversation_service
from services.customer_service import SupportError

router = APIRouter(prefix="/admin/conversations", tags=["Atendimento administrativo"],
                   dependencies=[Depends(get_current_user)])


@router.get("")
def list_conversations(status: ConversationStatus | None = None, db: Session = Depends(get_db)):
    return conversation_service.list_conversations(db, status)


@router.get("/{conversation_id}/messages", response_model=ChatHistory)
def get_messages(conversation_id: UUID, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, str(conversation_id))
    if not conversation:
        raise SupportError("Conversa não encontrada.", 404)
    return conversation_service.history(db, conversation)


@router.patch("/{conversation_id}")
def update_conversation(conversation_id: UUID, data: ConversationUpdate, db: Session = Depends(get_db)):
    return conversation_service.change_status(db, str(conversation_id), data.status)
