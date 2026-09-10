"""Translate official Meta payloads without coupling the agent to Meta."""

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from schemas.atendimento import AgentResponse


class InvalidWebhook(ValueError):
    pass


class UnexpectedAccount(InvalidWebhook):
    pass


@dataclass(frozen=True)
class IncomingText:
    phone_number_id: str
    sender: str
    message_id: str
    text: str
    timestamp: int

    @property
    def external_identity(self) -> str:
        return f"{self.phone_number_id}:{self.sender}"


def parse_messages(payload: dict, *, waba_id: str, phone_number_id: str,
                   max_message_length: int) -> list[IncomingText]:
    """Keep only validated, incoming text; delivery receipts never become prompts."""
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        raise InvalidWebhook("Objeto de webhook inválido.")
    entries = payload.get("entry", [])
    if not isinstance(entries, list) or len(entries) > 100:
        raise InvalidWebhook("Entradas de webhook inválidas.")
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise InvalidWebhook("Entrada de webhook inválida.")
        if str(entry.get("id", "")) != waba_id:
            raise UnexpectedAccount("Conta de webhook inesperada.")
        changes = entry.get("changes", [])
        if not isinstance(changes, list) or len(changes) > 100:
            raise InvalidWebhook("Alterações de webhook inválidas.")
        for change in changes:
            if not isinstance(change, dict):
                raise InvalidWebhook("Alteração de webhook inválida.")
            if change.get("field") != "messages":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                raise InvalidWebhook("Conteúdo de webhook inválido.")
            metadata = value.get("metadata", {})
            if not isinstance(metadata, dict) or str(metadata.get("phone_number_id", "")) != phone_number_id:
                raise UnexpectedAccount("Número de webhook inesperado.")
            messages = value.get("messages", [])
            if not isinstance(messages, list) or len(messages) > 100:
                raise InvalidWebhook("Mensagens de webhook inválidas.")
            for message in messages:
                if not isinstance(message, dict):
                    raise InvalidWebhook("Mensagem de webhook inválida.")
                if message.get("type") != "text":
                    continue
                sender, message_id = message.get("from"), message.get("id")
                body = message.get("text", {})
                body = body.get("body") if isinstance(body, dict) else None
                if (not isinstance(sender, str) or not re.fullmatch(r"[0-9]{5,20}", sender)
                    or not isinstance(message_id, str) or not 1 <= len(message_id) <= 200
                    or not isinstance(body, str) or not body.strip() or "\x00" in body):
                    raise InvalidWebhook("Campos de mensagem inválidos.")
                try:
                    timestamp = int(message["timestamp"])
                except (KeyError, ValueError, TypeError, OverflowError):
                    raise InvalidWebhook("Horário de mensagem inválido.") from None
                if not 0 < timestamp <= datetime.now(timezone.utc).timestamp() + 300:
                    raise InvalidWebhook("Horário de mensagem inválido.")
                if len(body) > max_message_length:
                    # The entire batch is rejected; never silently change a customer's prompt.
                    raise InvalidWebhook("Mensagem excede o limite de texto.")
                result.append(IncomingText(phone_number_id, sender, message_id, body.strip(), timestamp))
                if len(result) > 100:
                    raise InvalidWebhook("Lote de mensagens excede o limite.")
    return result


def render_text(response: AgentResponse) -> str:
    """Text and product links supported by Cloud API, bounded to one message."""
    chunks = [response.message]
    for product in response.products:
        value = f"R$ {product.effective_price:.2f}".replace(".", ",")
        block = f"{product.title}\n{value}\n{product.url}"
        if len("\n\n".join([*chunks, block])) > 4000:
            break
        chunks.append(block)
    return "\n\n".join(chunks)[:4096]
