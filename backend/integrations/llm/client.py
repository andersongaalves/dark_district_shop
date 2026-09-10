"""One bounded planning call; commercial text is never taken from the model."""

import json
import logging
from time import monotonic

import httpx

from core.config import settings
from integrations.llm.provider import DisabledProvider, Plan, ProviderUnavailable, ToolCall

logger = logging.getLogger(__name__)
MAX_PROVIDER_RESPONSE_BYTES = 128 * 1024


class OpenAICompatibleProvider:
    enabled = True

    def __init__(self, *, config=None, transport=None):
        self.config = config or settings
        self.transport = transport

    def plan(self, messages: list[dict], tools: list[dict]) -> Plan:
        config = self.config
        secret = config.LLM_API_KEY.get_secret_value()
        if not secret or not config.LLM_MODEL:
            raise ProviderUnavailable("O atendimento por IA ainda não está configurado.")
        started = monotonic()
        payload = {
            "model": config.LLM_MODEL,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "max_completion_tokens": config.LLM_MAX_OUTPUT_TOKENS,
        }
        try:
            with httpx.Client(timeout=config.LLM_TIMEOUT_SECONDS, follow_redirects=False,
                              transport=self.transport) as client:
                with client.stream("POST", str(config.LLM_BASE_URL).rstrip("/") + "/chat/completions",
                                   headers={"Authorization": f"Bearer {secret}"}, json=payload) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        if monotonic() - started > config.LLM_TIMEOUT_SECONDS:
                            raise ProviderUnavailable("O serviço de IA excedeu o tempo de resposta.")
                        content.extend(chunk)
                        if len(content) > MAX_PROVIDER_RESPONSE_BYTES:
                            raise ProviderUnavailable("Resposta do serviço de IA excedeu o limite.")
            data = json.loads(content)
            calls = data["choices"][0]["message"].get("tool_calls") or []
            if not isinstance(calls, list) or len(calls) > config.LLM_MAX_TOOL_CALLS:
                raise ValueError("Invalid tool call count")
            parsed = []
            for call in calls:
                if call.get("type") != "function":
                    raise ValueError("Unsupported call type")
                function = call["function"]
                arguments = json.loads(function["arguments"])
                name = function["name"]
                if not isinstance(arguments, dict) or not isinstance(name, str) or len(name) > 80:
                    raise ValueError("Invalid function call")
                parsed.append(ToolCall(name=name, arguments=arguments))
            usage = data.get("usage") or {}
            tokens = usage.get("total_tokens")
            logger.info("llm_plan duration_ms=%d calls=%d total_tokens=%s",
                        (monotonic() - started) * 1000, len(parsed),
                        tokens if isinstance(tokens, int) and tokens >= 0 else "unknown")
            return Plan(calls=parsed)
        except ProviderUnavailable:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, AttributeError):
            logger.warning("llm_plan_failed duration_ms=%d", (monotonic() - started) * 1000)
            raise ProviderUnavailable("O serviço de IA está indisponível no momento.") from None


def get_provider():
    if settings.LLM_PROVIDER == "disabled":
        return DisabledProvider()
    if settings.LLM_PROVIDER in {"openai", "openai_compatible"}:
        return OpenAICompatibleProvider()
    raise ProviderUnavailable("Provedor de IA não configurado.")
