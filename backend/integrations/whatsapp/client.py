"""A small Cloud API client with explicit delivery ambiguity handling."""

import re

import httpx

from core.config import settings


class WhatsAppDeliveryError(Exception):
    def __init__(self, code: str, *, retryable: bool = False, uncertain: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.uncertain = uncertain


def send_text(recipient: str, text: str, *, http_client=None) -> str:
    """Send once. Do not retry ambiguous requests: Meta does not promise idempotence."""
    token = settings.WHATSAPP_ACCESS_TOKEN.get_secret_value()
    phone = settings.WHATSAPP_PHONE_NUMBER_ID
    version = settings.WHATSAPP_GRAPH_VERSION
    if (not settings.WHATSAPP_ENABLED or not token
        or not re.fullmatch(r"[0-9]+", phone)
        or not re.fullmatch(r"v[0-9]+\.[0-9]+", version)):
        raise WhatsAppDeliveryError("whatsapp_unconfigured")
    if not re.fullmatch(r"[0-9]{5,20}", recipient) or not text or len(text) > 4096:
        raise WhatsAppDeliveryError("invalid_outbound")
    owned = http_client is None
    client = http_client or httpx.Client(timeout=settings.WHATSAPP_HTTP_TIMEOUT_SECONDS,
                                         follow_redirects=False)
    try:
        try:
            response = client.post(
                f"https://graph.facebook.com/{version}/{phone}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"messaging_product": "whatsapp", "recipient_type": "individual",
                      "to": recipient, "type": "text", "text": {"preview_url": False, "body": text}},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise WhatsAppDeliveryError("whatsapp_connection", retryable=True) from None
        except httpx.RequestError:
            raise WhatsAppDeliveryError("whatsapp_delivery_unknown", uncertain=True) from None
        if response.status_code == 429:
            raise WhatsAppDeliveryError("whatsapp_rate_limited", retryable=True)
        if response.status_code >= 500:
            raise WhatsAppDeliveryError("whatsapp_delivery_unknown", uncertain=True)
        if not 200 <= response.status_code < 300:
            # Never include Meta's error body: it can contain recipient information.
            raise WhatsAppDeliveryError(f"whatsapp_http_{response.status_code}")
        try:
            message_id = response.json()["messages"][0]["id"]
            if not isinstance(message_id, str) or not message_id:
                raise ValueError
        except (ValueError, KeyError, IndexError, TypeError):
            raise WhatsAppDeliveryError("whatsapp_delivery_unknown", uncertain=True) from None
        return message_id
    finally:
        if owned:
            client.close()
