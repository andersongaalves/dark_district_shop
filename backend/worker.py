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
    mode.add_argument("--once", action="store_true", help="Compatibilidade: não processa a fila antiga do WhatsApp.")
    mode.add_argument("--purge-expired", action="store_true", help="Remove dados fora do prazo de retenção.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    configure_support_logging()
    try:
        if args.purge_expired:
            from services.conversation_service import purge_expired
            with SessionLocal() as db:
                purge_expired(db)
            logger.info("support_retention_completed")
        else:
            logger.info("whatsapp_worker_not_required mode=human_only processed=false")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
