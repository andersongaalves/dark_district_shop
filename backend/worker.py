"""Optional maintenance CLI; WhatsApp human support runs in the Web Service."""
import argparse
import logging
import sys

from core.support_logging import configure_support_logging
from database import engine, SessionLocal

logger = logging.getLogger("worker")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Manutenção do atendimento Dark District")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--purge-expired", action="store_true", help="Remove dados fora do prazo de retenção.")
    mode.add_argument("--hybrid", action="store_true", help="Consome a fila híbrida continuamente.")
    parser.add_argument("--once", action="store_true", help="Processa no máximo um job e encerra.")
    args = parser.parse_args(argv)
    if args.purge_expired and args.once:
        parser.error("--once não pode ser usado com --purge-expired")
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    configure_support_logging()
    try:
        if args.purge_expired:
            from services.conversation_service import purge_expired
            with SessionLocal() as db:
                purge_expired(db)
            logger.info("support_retention_completed")
        elif args.hybrid:
            if args.once:
                from services.whatsapp_hybrid_service import run_once
                logger.info("hybrid_once processed=%s", run_once())
            else:
                import signal
                from threading import Event
                from services.whatsapp_consumer import consume
                stop = Event()
                signal.signal(signal.SIGTERM, lambda *_: stop.set())
                signal.signal(signal.SIGINT, lambda *_: stop.set())
                consume(stop)
        elif args.once:
            from core.config import settings
            if settings.AI_WHATSAPP_ENABLED:
                from services.whatsapp_hybrid_service import run_once
                logger.info("hybrid_once processed=%s", run_once())
            else:
                logger.info("whatsapp_worker_not_required mode=human_only processed=false")
        else:
            logger.info("whatsapp_worker_not_required mode=human_only processed=false")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
