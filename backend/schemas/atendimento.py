from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.atendimento import Channel, ConversationStatus, Sender
from schemas.produto import ProdutoResponse


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class HistoryEntry(StrictModel):
    sender: Sender
    content: str = Field(max_length=6000)


class AgentInput(StrictModel):
    channel: Channel
    conversation_id: str
    customer_id: str
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryEntry] = Field(default_factory=list, max_length=40)
    context: dict[str, Any] = Field(default_factory=dict)


class ChatProduct(ProdutoResponse):
    url: str


class ChatAction(StrictModel):
    type: Literal["human_handoff"] = "human_handoff"
    label: str = "Falar com uma pessoa"


class AgentResponse(StrictModel):
    message: str = Field(max_length=6000)
    type: Literal["message", "product_results", "handoff", "error", "silent"] = "message"
    products: list[ChatProduct] = Field(default_factory=list, max_length=10)
    actions: list[ChatAction] = Field(default_factory=list, max_length=3)
    handoff: bool = False
    context: dict[str, Any] = Field(default_factory=dict, exclude=True)


class ChatReply(AgentResponse):
    conversation_id: str
    status: ConversationStatus
    message_id: str


class ChatMessageCreate(StrictModel):
    message_id: UUID
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value):
        value = value.strip()
        if not value or "\x00" in value:
            raise ValueError("Digite uma mensagem válida.")
        return value


class ChatSession(StrictModel):
    session_id: str
    conversation_id: str
    expires_at: datetime


class StoredMessage(StrictModel):
    id: str
    external_id: str | None = None
    sender: Sender
    content: str
    created_at: datetime
    response: AgentResponse | None = None

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class ChatHistory(StrictModel):
    conversation_id: str
    status: ConversationStatus
    messages: list[StoredMessage]


class ConversationUpdate(StrictModel):
    status: ConversationStatus
