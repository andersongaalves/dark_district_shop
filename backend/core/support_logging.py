"""Access logs must not retain the verification secret carried in Meta's GET URL."""
import logging


class WebhookAccessFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args = list(record.args)
            path = args[2]
            if isinstance(path, str) and "/webhooks/whatsapp" in path:
                args[2] = path.partition("?")[0]
                record.args = tuple(args)
        return True


class MapsRequestFilter(logging.Filter):
    def filter(self, record):
        # Geocoding URLs carry an address and an API key; never retain them.
        return not any(host in record.getMessage() for host in ("maps.googleapis.com", "routes.googleapis.com"))


def configure_support_logging():
    # httpcore debug records can include request headers on child loggers, whose
    # records do not pass through parent logger filters.
    for name in ("httpcore", "httpcore.http11", "httpcore.http2", "httpcore.connection", "httpcore.proxy"):
        logging.getLogger(name).setLevel(logging.WARNING)
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, WebhookAccessFilter) for item in access.filters):
        access.addFilter(WebhookAccessFilter())
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, MapsRequestFilter) for item in logger.filters):
            logger.addFilter(MapsRequestFilter())
