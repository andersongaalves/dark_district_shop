"""Run with `python -m worker` from backend, after applying migrations."""

import argparse
import logging
import os
import re
import signal
import sys
from threading import Event

from core.config import settings
from core.support_logging import configure_support_logging
from database import engine
from services.delivery_service import run_once

logger = logging.getLogger("worker")


def configuration_error():
    if not settings.WHATSAPP_ENABLED:
        return "WhatsApp desativado. Configure WHATSAPP_ENABLED=true."
    if not settings.WHATSAPP_ACCESS_TOKEN.get_secret_value().strip():
        return "Configure WHATSAPP_ACCESS_TOKEN."
    if not re.fullmatch(r"[0-9]+", settings.WHATSAPP_PHONE_NUMBER_ID):
        return "Configure WHATSAPP_PHONE_NUMBER_ID com o ID numérico da Cloud API."
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", settings.WHATSAPP_GRAPH_VERSION):
        return "Configure WHATSAPP_GRAPH_VERSION no formato vNN.0."
    if settings.LLM_PROVIDER != "disabled" and (
        not settings.LLM_API_KEY.get_secret_value().strip() or not settings.LLM_MODEL.strip()
    ):
        return "Configure LLM_API_KEY e LLM_MODEL para o provider habilitado."
    if os.environ.get("RENDER", "").lower() == "true" and engine.dialect.name != "postgresql":
        return "No Render, configure DATABASE_URL com o mesmo PostgreSQL da API."
    return None


def serve(stop, *, once=False):
    """Finish the active job on shutdown; never take another after SIGTERM.

    Failures before claiming or while committing a result must not kill the
    polling loop. Persisted leases recover these cases without resending an
    outbound request whose acceptance is unknown.
    """
    failures = 0
    while not stop.is_set():
        try:
            processed = run_once()
        except Exception as error:
            failures += 1
            delay = min(30, settings.WORKER_POLL_SECONDS * 2 ** min(failures - 1, 5))
            # Driver/provider exceptions can contain credentials or customer data.
            logger.error("whatsapp_worker_cycle_failed error_type=%s retry_seconds=%s",
                         type(error).__name__, delay)
            if once:
                return 1
            stop.wait(delay)
            continue
        if failures:
            logger.info("whatsapp_worker_recovered")
        failures = 0
        if once:
            logger.info("whatsapp_worker_once processed=%s", str(processed).lower())
            return 0
        if not processed:
            stop.wait(settings.WORKER_POLL_SECONDS)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Worker de atendimento WhatsApp da Dark District")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Processa no máximo um evento e encerra.")
    mode.add_argument("--purge-expired", action="store_true", help="Remove sessões vencidas e conversas fora do prazo de retenção.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    configure_support_logging()
    if args.purge_expired:
        from database import SessionLocal
        from services.conversation_service import purge_expired
        with SessionLocal() as db:
            purge_expired(db)
        engine.dispose()
        logger.info("support_retention_completed")
        return 0
    error = configuration_error()
    if error:
        parser.exit(status=1, message=error + "\n")
    stop = Event()
    def shutdown(signum, _frame):
        stop.set()
        logger.info("whatsapp_worker_shutdown_requested signal=%s", signal.Signals(signum).name)
    previous = {number: signal.signal(number, shutdown) for number in (signal.SIGTERM, signal.SIGINT)}
    logger.info("whatsapp_worker_started mode=%s database=%s poll_seconds=%s lease_seconds=%s",
                "once" if args.once else "continuous", engine.dialect.name,
                settings.WORKER_POLL_SECONDS, settings.DELIVERY_LEASE_SECONDS)
    try:
        return serve(stop, once=args.once)
    except KeyboardInterrupt:
        stop.set()
        return 0
    finally:
        engine.dispose()
        for number, handler in previous.items():
            signal.signal(number, handler)
        logger.info("whatsapp_worker_stopped")


if __name__ == "__main__":
    raise SystemExit(main())
