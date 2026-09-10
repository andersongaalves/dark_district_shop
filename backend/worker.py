"""Run with `python -m worker` from backend, after applying migrations."""

import argparse
import logging
from threading import Event

from core.config import settings
from services.delivery_service import run_once


def main():
    parser = argparse.ArgumentParser(description="Worker de atendimento WhatsApp da Dark District")
    parser.add_argument("--once", action="store_true", help="Processa no máximo um evento e encerra.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not settings.WHATSAPP_ENABLED:
        parser.exit(message="WhatsApp desativado. Configure WHATSAPP_ENABLED para iniciar o worker.\n")
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
