"""One bounded consumer per process; PostgreSQL leases coordinate replicas."""
from contextlib import asynccontextmanager
from threading import Event, Thread
import logging
from core.config import settings

logger = logging.getLogger(__name__)


def consume(stop):
    from services.whatsapp_hybrid_service import run_once
    while not stop.is_set():
        try:
            worked = run_once()
        except Exception:
            logger.error("hybrid_consumer_iteration_failed")
            worked = False
        if not worked:
            stop.wait(settings.WORKER_POLL_SECONDS)


@asynccontextmanager
async def lifespan(app):
    stop, thread = Event(), None
    if settings.AI_WHATSAPP_ENABLED and settings.WHATSAPP_EMBEDDED_CONSUMER:
        thread = Thread(target=consume, args=(stop,), name="whatsapp-consumer", daemon=True)
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread:
            import asyncio
            await asyncio.to_thread(thread.join, settings.LLM_TIMEOUT_SECONDS + settings.WHATSAPP_HTTP_TIMEOUT_SECONDS + 10)
            logger.info("hybrid_consumer_stopped drained=%s", not thread.is_alive())
