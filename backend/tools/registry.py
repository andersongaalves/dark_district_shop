"""The model only receives the approved read-only catalog and FAQ functions."""

from dataclasses import dataclass
import logging
from time import monotonic

from pydantic import ValidationError

from tools.catalog_tools import (
    CategoryArguments, ColorArguments, ProductArguments, SearchArguments,
    SizeArguments, StockArguments, ToolResult, lookup, search,
)
from tools.faq_tools import FAQArguments, consult_faq

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tool:
    arguments: type
    handler: object
    description: str


REGISTRY = {
    "buscar_produto": Tool(SearchArguments, search, "Busca peças disponíveis por texto, ID e filtros combinados."),
    "listar_produtos": Tool(SearchArguments, search, "Lista uma pequena seleção do catálogo disponível."),
    "consultar_estoque": Tool(StockArguments, lookup, "Consulta variantes e quantidades reais de um produto conhecido."),
    "consultar_preco": Tool(ProductArguments, lookup, "Consulta preço original e oferta vigente de um produto conhecido."),
    "buscar_por_categoria": Tool(CategoryArguments, search, "Busca peças disponíveis de uma categoria."),
    "buscar_por_tamanho": Tool(SizeArguments, search, "Busca peças com estoque no tamanho informado."),
    "buscar_por_cor": Tool(ColorArguments, search, "Busca peças com estoque na cor informada."),
    "consultar_faq": Tool(FAQArguments, consult_faq,
        "Consulta respostas oficiais sobre compra pelo WhatsApp, entrega no endereço, prazo de devolução e região atendida. "
        "Selecione compra, entrega, devolucao ou atendimento; null retorna todos. Entrega explica as regras de frete; a cotação exige endereço na seleção de itens. Não informa prazo de entrega, "
        "formas de pagamento, condições extras de devolução nem confirma cidades específicas não cadastradas."),
}


def _strict_schema(schema):
    """OpenAI strict function schemas require every property, nullable if optional."""
    schema = dict(schema)
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        schema["required"] = list(schema.get("properties", {}))
    schema.pop("default", None)
    for key, value in list(schema.items()):
        if isinstance(value, dict):
            schema[key] = _strict_schema(value)
        elif isinstance(value, list):
            schema[key] = [_strict_schema(item) if isinstance(item, dict) else item for item in value]
    return schema


def definitions() -> list[dict]:
    return [{"type": "function", "function": {
        "name": name, "description": tool.description,
        "parameters": _strict_schema(tool.arguments.model_json_schema()), "strict": True,
    }} for name, tool in REGISTRY.items()]


def execute(db, name: str, arguments: dict) -> ToolResult:
    tool = REGISTRY.get(name)
    if tool is None:
        # Do not echo attacker-provided tool names or arguments into logs/replies.
        logger.warning("catalog_tool_rejected reason=unknown_tool")
        return ToolResult(error="Ferramenta indisponível.")
    try:
        validated = tool.arguments.model_validate(arguments)
    except ValidationError:
        logger.warning("catalog_tool_rejected tool=%s reason=invalid_arguments", name)
        return ToolResult(error="Parâmetros inválidos para a consulta.")
    started = monotonic()
    result = tool.handler(db, validated)
    logger.info("catalog_tool tool=%s duration_ms=%d results=%d", name,
                (monotonic() - started) * 1000, len(result.products) + len(result.faqs))
    return result
