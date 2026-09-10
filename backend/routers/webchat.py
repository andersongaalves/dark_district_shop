from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from channels.web_channel import receive_message
from core.config import settings
from database import get_db
from schemas.atendimento import ChatHistory, ChatMessageCreate, ChatReply, ChatSession
from services import conversation_service, customer_service
from services.customer_service import SupportError

router = APIRouter(prefix="/api/chat", tags=["Atendimento Web"])
bearer = HTTPBearer(auto_error=False)


def enabled():
    if not settings.CHAT_ENABLED:
        raise SupportError("O atendimento está indisponível no momento.", 503)


def web_conversation(request: Request, db: Session = Depends(get_db),
                     credentials: HTTPAuthorizationCredentials | None = Depends(bearer), _=Depends(enabled)):
    conversation = customer_service.authenticate_web(db, credentials.credentials if credentials else "")
    if request.method == "POST" and request.app.state.chat_session_limiter.retry_after(conversation.id) is not None:
        raise SupportError("Muitas mensagens. Aguarde um minuto antes de tentar novamente.", 429)
    return conversation


@router.post("/sessions", response_model=ChatSession, status_code=201, dependencies=[Depends(enabled)])
def create_session(db: Session = Depends(get_db)):
    return customer_service.create_web_session(db)


@router.post("/messages", response_model=ChatReply)
def send_message(data: ChatMessageCreate, conversation=Depends(web_conversation), db: Session = Depends(get_db)):
    return receive_message(db, conversation, data)


@router.get("/messages", response_model=ChatHistory)
def get_messages(conversation=Depends(web_conversation), db: Session = Depends(get_db)):
    return conversation_service.history(db, conversation)


@router.delete("/session", status_code=204)
def delete_session(conversation=Depends(web_conversation), db: Session = Depends(get_db)):
    customer_service.delete_web_session(db, conversation)
    return Response(status_code=204)
