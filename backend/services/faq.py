"""Approved store information shared by the public FAQ and every agent channel."""
from functools import lru_cache
from pathlib import Path
import re
import unicodedata

from pydantic import TypeAdapter

from schemas.faq import FAQItem, FAQTopic

FAQ_FILE = Path(__file__).resolve().parents[1] / "content" / "faq.json"


@lru_cache(maxsize=1)
def _items() -> tuple[FAQItem, ...]:
    items = TypeAdapter(list[FAQItem]).validate_json(FAQ_FILE.read_text(encoding="utf-8"))
    if len({item.id for item in items}) != len(items):
        raise ValueError("O FAQ contém tópicos repetidos.")
    return tuple(items)


def list_faq(topic: FAQTopic | None = None) -> list[FAQItem]:
    return [item for item in _items() if topic is None or item.id == topic]


def match_faq(message: str) -> list[FAQItem]:
    """Resolve common policy questions without paying for a model call.

    This only selects published answers. It does not authorize a refund, infer
    delivery prices/times, or confirm a city/address outside the published region.
    """
    parts = [part.strip() for part in re.split(r"[?;\n]+", message) if part.strip()]
    if len(parts) > 1:
        topics = {item.id for part in parts for item in match_faq(part)}
        return [item for item in list_faq() if item.id in topics]
    text = "".join(char for char in unicodedata.normalize("NFKD", message.lower())
                   if not unicodedata.combining(char))
    returns = bool(re.search(r"\b(devolucoes|devolucao|devolver|devolvo)\b", text))
    # Missing commercial details need staff confirmation, not an invented policy.
    if re.search(r"\b(taxa|taxas|custa|custo|valor|gratis|gratuito|gratuita|etiqueta|defeito|garantia|lavada|usada|reembolso|estorno|troca|trocar|correios|retirada)\b", text):
        return []
    topics = set()
    if returns:
        topics.add("devolucao")
    if (re.search(r"\b(onde|quais cidades|que cidades|regiao|area|juazeiro)\b", text) and re.search(
        r"\b(atend\w*|entreg\w*|envia\w*|cobertura|regiao|juazeiro)\b", text)) or re.search(
        r"\b(atend\w*|entreg\w*|envia\w*)\s+(em|para)\b", text):
        topics.add("atendimento")
    if not returns and re.search(r"\b(entrega|entregue|entregador|entregas|entregam|frete|delivery|enviam|manda)\b", text):
        if re.search(r"\b(prazo|quando|demora|horario|horarios|dias|amanha|hoje)\b|quanto tempo|que horas", text):
            return []
        if re.search(r"\b(endereco|casa)\b", text):
            topics.discard("atendimento")
        if "atendimento" not in topics and (re.search(r"\b(como|endereco|casa|entregador|entregue|delivery|fazem)\b", text)
                                             or re.fullmatch(r"\s*entregas?[\s?!.,]*", text)):
            topics.add("entrega")
    if re.search(r"\b(compra|compras|comprar|compro|pedido|pedidos|pedir|finalizar)\b", text) and re.search(
        r"\b(como|funciona|funcionam|processo|passos|finalizo|finalizar)\b", text):
        topics.add("compra")
    if re.fullmatch(r"\s*(faq|perguntas frequentes)[\s?!.,]*", text):
        return list_faq()
    return [item for item in list_faq() if item.id in topics]
