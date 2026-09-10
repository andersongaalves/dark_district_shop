from dataclasses import dataclass, field
from typing import Protocol


class ProviderUnavailable(Exception):
    """Safe public boundary: no upstream response bodies or credentials."""


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


@dataclass(frozen=True)
class Plan:
    calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    enabled: bool

    def plan(self, messages: list[dict], tools: list[dict]) -> Plan: ...


class DisabledProvider:
    enabled = False

    def plan(self, messages: list[dict], tools: list[dict]) -> Plan:
        return Plan()
