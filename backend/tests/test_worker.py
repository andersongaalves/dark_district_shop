import logging
import os
from pathlib import Path
import subprocess
import sys

import pytest

import worker
from services import delivery_service


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
