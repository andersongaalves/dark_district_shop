"""WhatsApp notification transport; other notification transports can be added here."""
from sqlalchemy import select, func
from core.config import settings
from integrations.whatsapp.client import send_template, send_text, WhatsAppDeliveryError
from models.atendimento import Conversation, ChannelIdentity, Message, utc_now
from services.customer_service import aware


def deliver(db, payload):
    recipient = settings.WHATSAPP_ATTENDANT_NUMBER
    if not recipient or recipient == payload["customer"] or recipient == settings.WHATSAPP_BUSINESS_PHONE_NUMBER:
        raise WhatsAppDeliveryError("attendant_unconfigured")
    link = settings.STOREFRONT_URL.rstrip("/") + "/admin/#atendimento"
    parameters = [payload["customer"], payload["reason"], " ".join(payload["excerpt"].split())[:300], link]
    if settings.WHATSAPP_ATTENDANT_TEMPLATE:
        return send_template(recipient, settings.WHATSAPP_ATTENDANT_TEMPLATE,
                             settings.WHATSAPP_ATTENDANT_TEMPLATE_LANGUAGE, parameters)
    last = db.scalar(select(func.max(Message.created_at)).join(Conversation).join(
        ChannelIdentity, Conversation.identity_id == ChannelIdentity.id).where(
        ChannelIdentity.external_id == f"{settings.WHATSAPP_PHONE_NUMBER_ID}:{recipient}", Message.sender == "customer"))
    timestamp = db.scalar(select(func.max(Message.extra_data["received_timestamp"].as_integer())).join(Conversation).join(
        ChannelIdentity, Conversation.identity_id == ChannelIdentity.id).where(
        ChannelIdentity.external_id == f"{settings.WHATSAPP_PHONE_NUMBER_ID}:{recipient}", Message.sender == "customer"))
    if not last or not -300 <= utc_now().timestamp() - (timestamp or aware(last).timestamp()) < 86400:
        raise WhatsAppDeliveryError("attendant_template_required")
    return send_text(recipient, "🖤 Novo atendimento — Dark District\n\nCliente: " + parameters[0]
                     + "\nMotivo: " + parameters[1] + "\n\nÚltima mensagem:\n" + parameters[2]
                     + "\n\nAguardando atendimento humano.\nPainel: " + link)
