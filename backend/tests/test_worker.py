import asyncio
import logging
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

import worker
from core.config import Settings, settings
from services import delivery_service, whatsapp_hybrid_service
from services import whatsapp_consumer


@pytest.mark.parametrize("arguments", [[], ["--once"]])
def test_worker_does_not_consume_old_whatsapp_jobs(monkeypatch, caplog, arguments):
    monkeypatch.setattr(delivery_service, "claim_next", lambda *_: pytest.fail("Old queue must not run"))
    disposed = []
    monkeypatch.setattr(worker.engine, "dispose", lambda: disposed.append(True))
    with caplog.at_level(logging.INFO):
        assert worker.main(arguments) == 0
    assert "whatsapp_worker_not_required" in caplog.text
    assert disposed == [True]


def test_python_module_once_from_backend_needs_no_meta_or_llm():
    env = {**os.environ, "DATABASE_URL": "sqlite://", "SECRET_KEY": "x" * 40,
           "WHATSAPP_ENABLED": "true", "WHATSAPP_ACCESS_TOKEN": "",
           "WHATSAPP_PHONE_NUMBER_ID": "", "WHATSAPP_GRAPH_VERSION": "",
           "LLM_PROVIDER": "disabled", "LLM_API_KEY": "", "META_APP_SECRET": "",
           "WHATSAPP_VERIFY_TOKEN": "", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-m", "worker", "--once"],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "processed=false" in result.stdout


def test_hybrid_once_processes_one_job_and_exits(monkeypatch, caplog):
    processed = []
    monkeypatch.setattr(whatsapp_hybrid_service, "run_once", lambda: processed.append(True) or True)
    monkeypatch.setattr(worker.engine, "dispose", lambda: None)
    with caplog.at_level(logging.INFO):
        assert worker.main(["--hybrid", "--once"]) == 0
    assert processed == [True]
    assert "hybrid_once processed=True" in caplog.text


@pytest.mark.parametrize(("whatsapp", "ai_enabled", "embedded", "starts"), [
    (True, True, True, True), (True, True, False, False),
    (True, False, True, False), (False, True, True, False),
])
def test_lifespan_starts_only_the_configured_embedded_consumer(
        monkeypatch, caplog, whatsapp, ai_enabled, embedded, starts):
    for name, value in {"WHATSAPP_ENABLED": whatsapp, "AI_WHATSAPP_ENABLED": ai_enabled,
                        "WHATSAPP_EMBEDDED_CONSUMER": embedded}.items():
        monkeypatch.setattr(settings, name, value)
    created = []

    class FakeThread:
        def __init__(self, **kwargs):
            self.started = False
            self.joined = False
            created.append(self)
        def start(self):
            self.started = True
        def join(self, _timeout):
            self.joined = True
        def is_alive(self):
            return False

    monkeypatch.setattr(whatsapp_consumer, "Thread", FakeThread)

    async def run():
        async with whatsapp_consumer.lifespan(None):
            assert sum(thread.started for thread in created) == int(starts)

    with caplog.at_level(logging.INFO):
        asyncio.run(run())
    assert ("whatsapp_ai_enabled" in caplog.text) is (whatsapp and ai_enabled)
    if starts:
        assert created[0].joined
        assert "embedded_consumer_started" in caplog.text
    elif whatsapp and ai_enabled:
        assert "external_worker_required=true" in caplog.text


def test_consumer_failure_is_isolated_and_stops_cleanly(monkeypatch, caplog):
    from threading import Event
    stop = Event()
    calls = []

    def fail_once():
        calls.append(True)
        stop.set()
        raise RuntimeError("provider secret must not be logged")

    monkeypatch.setattr(whatsapp_hybrid_service, "run_once", fail_once)
    with caplog.at_level(logging.ERROR):
        whatsapp_consumer.consume(stop)
    assert calls == [True]
    assert "hybrid_consumer_iteration_failed" in caplog.text
    assert "provider secret" not in caplog.text


@pytest.mark.parametrize("field", ["WHATSAPP_ENABLED", "AI_WHATSAPP_ENABLED", "WHATSAPP_EMBEDDED_CONSUMER"])
def test_rollout_boolean_flags_fail_fast_on_invalid_values(field):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_URL="sqlite://", SECRET_KEY="x" * 40, **{field: "sometimes"})


def test_default_mode_is_safe_and_rejects_invalid_values():
    config = Settings(_env_file=None, DATABASE_URL="sqlite://", SECRET_KEY="x" * 40)
    assert config.WHATSAPP_AI_DEFAULT_MODE == "OFF"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_URL="sqlite://", SECRET_KEY="x" * 40,
                 WHATSAPP_AI_DEFAULT_MODE="INVALID")
