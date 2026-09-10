"""Run with `python -m worker` from backend, after applying migrations."""

import argparse
import logging
from threading import Event

from core.config import settings
from services.delivery_service import run_once


def main():
    parser = argparse.ArgumentParser(description="Worker de atendimento WhatsApp da Dark District")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Processa no máximo um evento e encerra.")
    mode.add_argument("--purge-expired", action="store_true", help="Remove sessões vencidas e conversas fora do prazo de retenção.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.purge_expired:
        from database import SessionLocal
        from services.conversation_service import purge_expired
        with SessionLocal() as db:
            purge_expired(db)
        logging.info("support_retention_completed")
        return
    if not settings.WHATSAPP_ENABLED:
        parser.exit(message="WhatsApp desativado. Configure WHATSAPP_ENABLED para iniciar o worker.\n")
    if not settings.WHATSAPP_ACCESS_TOKEN.get_secret_value() or not settings.WHATSAPP_GRAPH_VERSION:
        parser.exit(status=1, message="Configure o token de acesso e a versão da Graph API antes de iniciar o worker.\n")
    if args.once:
        run_once()
        return
    stop = Event()
    try:
        while not stop.is_set():
            if not run_once():
                stop.wait(settings.WORKER_POLL_SECONDS)
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
