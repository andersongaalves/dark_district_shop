import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine

from core.config import settings
from database import Base
import worker


@pytest.fixture
def configured(monkeypatch):
    for name, value in {"WHATSAPP_ENABLED": True, "WHATSAPP_ACCESS_TOKEN": SecretStr("fake-token"),
                        "WHATSAPP_PHONE_NUMBER_ID": "1234567", "WHATSAPP_GRAPH_VERSION": "v23.0",
                        "LLM_PROVIDER": "disabled"}.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.delenv("RENDER", raising=False)


@pytest.mark.parametrize("name,value", [
    ("WHATSAPP_ENABLED", False), ("WHATSAPP_ACCESS_TOKEN", SecretStr("")),
    ("WHATSAPP_PHONE_NUMBER_ID", ""), ("WHATSAPP_PHONE_NUMBER_ID", "+55wrong"),
    ("WHATSAPP_GRAPH_VERSION", ""), ("WHATSAPP_GRAPH_VERSION", "invalid"),
])
def test_invalid_configuration_fails_before_claim(configured, monkeypatch, name, value):
    monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(worker, "run_once", lambda: pytest.fail("Must not claim a job"))
    with pytest.raises(SystemExit) as result:
        worker.main(["--once"])
    assert result.value.code == 1


def test_worker_does_not_require_webhook_only_secrets(configured, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", SecretStr(""))
    monkeypatch.setattr(settings, "META_APP_SECRET", SecretStr(""))
    monkeypatch.setattr(settings, "WHATSAPP_WABA_ID", "")
    assert worker.configuration_error() is None
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "LLM_API_KEY", SecretStr(""))
    assert "LLM_API_KEY" in worker.configuration_error()


def test_render_rejects_local_sqlite_queue(configured, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    assert "mesmo PostgreSQL" in worker.configuration_error()


@pytest.mark.parametrize("processed", [True, False])
def test_once_calls_one_cycle_and_reports_result(monkeypatch, caplog, processed):
    calls = []
    monkeypatch.setattr(worker, "run_once", lambda: calls.append(True) or processed)
    with caplog.at_level(logging.INFO):
        assert worker.serve(Event(), once=True) == 0
    assert len(calls) == 1
    assert f"processed={str(processed).lower()}" in caplog.text


def test_once_returns_nonzero_on_cycle_failure_without_leaking_exception(monkeypatch, caplog):
    def failing():
        raise RuntimeError("postgresql://secret:password@database customer text")
    monkeypatch.setattr(worker, "run_once", failing)
    assert worker.serve(Event(), once=True) == 1
    assert "error_type=RuntimeError" in caplog.text
    assert "password" not in caplog.text and "customer text" not in caplog.text


def test_loop_survives_database_outage_backs_off_then_recovers(monkeypatch, caplog):
    class Stop:
        stopped = False
        waits = []
        def is_set(self): return self.stopped
        def wait(self, delay): self.waits.append(delay)
    stop = Stop()
    attempts = []
    def cycle():
        attempts.append(1)
        if len(attempts) < 4: raise RuntimeError("private DB failure")
        stop.stopped = True
        return True
    monkeypatch.setattr(worker, "run_once", cycle)
    with caplog.at_level(logging.INFO):
        assert worker.serve(stop) == 0
    assert stop.waits == [2, 4, 8]
    assert "whatsapp_worker_recovered" in caplog.text
    assert "private DB failure" not in caplog.text


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_signal_finishes_current_job_stops_claiming_and_disposes(configured, monkeypatch, caplog, signum):
    calls = []
    original = signal.getsignal(signum)
    def cycle():
        calls.append("started")
        signal.getsignal(signum)(signum, None)
        calls.append("finished")
        return True
    monkeypatch.setattr(worker, "run_once", cycle)
    monkeypatch.setattr(worker.engine, "dispose", lambda: calls.append("disposed"))
    with caplog.at_level(logging.INFO):
        assert worker.main([]) == 0
    assert calls == ["started", "finished", "disposed"]
    assert signal.getsignal(signum) == original
    assert "whatsapp_worker_shutdown_requested" in caplog.text
    assert "whatsapp_worker_stopped" in caplog.text


def test_stopped_worker_does_not_claim(monkeypatch):
    stop = Event()
    stop.set()
    monkeypatch.setattr(worker, "run_once", lambda: pytest.fail("Shutdown must prevent a new claim"))
    assert worker.serve(stop) == 0


def test_python_module_once_from_backend_with_isolated_database(tmp_path):
    url = "sqlite:///" + (tmp_path / "worker.db").as_posix()
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    # Never inherit local .env credentials or a production database for this subprocess.
    env = {**os.environ, "DATABASE_URL": url, "SECRET_KEY": "x" * 40, "RENDER": "false",
           "WHATSAPP_ENABLED": "true", "WHATSAPP_ACCESS_TOKEN": "fake-token",
           "WHATSAPP_PHONE_NUMBER_ID": "1234567", "WHATSAPP_GRAPH_VERSION": "v23.0",
           "LLM_PROVIDER": "disabled", "LLM_API_KEY": "", "META_APP_SECRET": "",
           "WHATSAPP_VERIFY_TOKEN": "", "SHIPPING_GOOGLE_API_KEY": "", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-m", "worker", "--once"],
                            cwd=Path(__file__).resolve().parents[1], env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "whatsapp_worker_started" in result.stdout
    assert "processed=false" in result.stdout
    assert "whatsapp_worker_stopped" in result.stdout
