from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FAQTopic = Literal["compra", "entrega", "devolucao", "atendimento"]


class FAQItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: FAQTopic
    question: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=1200)
