"""Signed WhatsApp messages go to human support with one initial greeting."""

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from channels.whatsapp_channel import InvalidWebhook, UnexpectedAccount, parse_messages
from core.config import settings
from database import get_db
from services.whatsapp_human_service import receive_messages

router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp"])


def require_webhook_configuration():
    if (not settings.WHATSAPP_ENABLED or not settings.WHATSAPP_VERIFY_TOKEN.get_secret_value()
        or not settings.META_APP_SECRET.get_secret_value()
        or not settings.WHATSAPP_WABA_ID or not settings.WHATSAPP_PHONE_NUMBER_ID):
        raise HTTPException(status_code=503, detail="Canal WhatsApp indisponível.")


@router.get("", response_class=PlainTextResponse)
def verify_webhook(
    mode: str = Query(default="", alias="hub.mode", max_length=30),
    token: str = Query(default="", alias="hub.verify_token", max_length=500),
    challenge: str = Query(default="", alias="hub.challenge", max_length=200),
):
    require_webhook_configuration()
    if mode != "subscribe" or not hmac.compare_digest(
        token.encode(), settings.WHATSAPP_VERIFY_TOKEN.get_secret_value().encode()
    ) or not challenge:
        raise HTTPException(status_code=403, detail="Verificação de webhook inválida.")
    return challenge


@router.post("")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    require_webhook_configuration()
    body = await request.body()
    expected = "sha256=" + hmac.new(settings.META_APP_SECRET.get_secret_value().encode(),
                                     body, hashlib.sha256).hexdigest()
    provided = request.headers.get("x-hub-signature-256", "")
    if not hmac.compare_digest(expected.encode(), provided.encode()):
        raise HTTPException(status_code=403, detail="Assinatura de webhook inválida.")
    try:
        payload = json.loads(body)
        messages = parse_messages(payload, waba_id=settings.WHATSAPP_WABA_ID,
                                  phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
                                  business_phone_number=settings.WHATSAPP_BUSINESS_PHONE_NUMBER,
                                  max_message_length=settings.CHAT_MAX_MESSAGE_LENGTH)
    except UnexpectedAccount:
        raise HTTPException(status_code=403, detail="Conta de webhook inesperada.") from None
    except (InvalidWebhook, ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Evento de webhook inválido.") from None
    await run_in_threadpool(receive_messages, db, messages)
    return {"received": True}
