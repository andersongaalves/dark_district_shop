from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from core.security import get_current_user
from database import get_db
from models.atendimento import Conversation
from schemas.atendimento import ConversationStatus, ConversationUpdate, ChatMessageCreate
from models.atendimento import Channel
from models.usuario import Usuario
from services import whatsapp_inbox_service as inbox
from services import conversation_service
from services.customer_service import SupportError

def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/admin/conversations", tags=["Atendimento administrativo"],
                   dependencies=[Depends(get_current_user), Depends(private_response)])


@router.get("")
def list_conversations(status: ConversationStatus | None = None, channel: Channel | None = None,
                       limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
                       db: Session = Depends(get_db)):
    if channel == Channel.WHATSAPP:
        return inbox.list_inbox(db, status, limit, offset)
    return conversation_service.list_conversations(db, status)


@router.get("/{conversation_id}/messages")
def get_messages(conversation_id: UUID, limit: int = Query(50, ge=1, le=100),
                 before: UUID | None = None, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, str(conversation_id))
    if not conversation:
        raise SupportError("Conversa não encontrada.", 404)
    if conversation.channel == "whatsapp":
        return inbox.get_messages(db, str(conversation_id), limit, str(before) if before else None)
    return conversation_service.history(db, conversation)


@router.post("/{conversation_id}/claim")
def claim(conversation_id: UUID, db: Session = Depends(get_db), admin: Usuario = Depends(get_current_user)):
    return inbox.set_status(db, str(conversation_id), "HUMAN", admin.id)


@router.post("/{conversation_id}/close")
def close(conversation_id: UUID, db: Session = Depends(get_db), admin: Usuario = Depends(get_current_user)):
    return inbox.set_status(db, str(conversation_id), "CLOSED", admin.id)


@router.post("/{conversation_id}/messages")
def send_message(conversation_id: UUID, data: ChatMessageCreate, db: Session = Depends(get_db),
                 admin: Usuario = Depends(get_current_user)):
    return inbox.send_manual(db, str(conversation_id), str(data.message_id), data.message, admin.id)


@router.patch("/{conversation_id}")
def update_conversation(conversation_id: UUID, data: ConversationUpdate, db: Session = Depends(get_db)):
    return conversation_service.change_status(db, str(conversation_id), data.status)
