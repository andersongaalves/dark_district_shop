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


def configure_support_logging():
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, WebhookAccessFilter) for item in access.filters):
        access.addFilter(WebhookAccessFilter())
