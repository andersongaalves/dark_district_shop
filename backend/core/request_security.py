from collections import OrderedDict
from math import ceil
from threading import Lock
from time import monotonic

from starlette.responses import JSONResponse


class LoginRateLimiter:
    """Bounded, process-local limits by client address; no credentials are stored."""

    def __init__(self, attempts=10, window_seconds=60, max_clients=10_000, clock=monotonic):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self.clock = clock
        self._windows = OrderedDict()
        self._lock = Lock()

    def retry_after(self, client: str) -> int | None:
        with self._lock:
            now = self.clock()
            while self._windows:
                started, _ = next(iter(self._windows.values()))
                if now - started < self.window_seconds:
                    break
                self._windows.popitem(last=False)

            current = self._windows.get(client)
            if current is None:
                if len(self._windows) >= self.max_clients:
                    # Do not evict active limits when a caller sends new addresses.
                    oldest, _ = next(iter(self._windows.values()))
                    return max(1, ceil(oldest + self.window_seconds - now))
                self._windows[client] = (now, 1)
                return None

            started, count = current
            if count >= self.attempts:
                return max(1, ceil(started + self.window_seconds - now))
            self._windows[client] = (started, count + 1)
            return None


class RequestSecurityMiddleware:
    """Limit bodies before parsing and protect the login endpoint before hashing."""

    def __init__(self, app, max_body_bytes, max_login_body_bytes):
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.max_login_body_bytes = min(max_body_bytes, max_login_body_bytes)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_path = scope["path"]
        root_path = scope.get("root_path", "").rstrip("/")
        if root_path and request_path.startswith(root_path + "/"):
            request_path = request_path[len(root_path):]
        is_login = request_path.rstrip("/") == "/auth/login"
        is_chat = request_path.startswith("/api/chat/")
        is_shipping = request_path.startswith("/shipping/")
        private_response = is_login or is_chat or is_shipping or request_path.startswith("/admin/conversations") or request_path.startswith("/webhooks/whatsapp")

        async def secure_send(message):
            if private_response and message["type"] == "http.response.start":
                message = {**message, "headers": [
                    (key, value) for key, value in message.get("headers", [])
                    if key.lower() not in {b"cache-control", b"pragma"}
                ] + [(b"cache-control", b"no-store"), (b"pragma", b"no-cache")]}
            await send(message)

        async def reject(status, detail, headers=None):
            response = JSONResponse({"detail": detail}, status_code=status, headers=headers)
            await response(scope, receive, secure_send)

        if is_shipping and scope["method"] != "OPTIONS" and request_path.rstrip("/") != "/shipping/policy":
            client = scope.get("client")
            address = client[0] if client else "unknown"
            retry = scope["app"].state.shipping_ip_limiter.retry_after(address)
            if retry is None:
                retry = scope["app"].state.shipping_global_limiter.retry_after("all")
            if retry is not None:
                await reject(429, "Muitas consultas de frete. Aguarde um pouco.", {"Retry-After": str(retry)})
                return

        if is_chat and scope["method"] != "OPTIONS":
            client = scope.get("client")
            address = client[0] if client else "unknown"
            limiter = scope["app"].state.chat_ip_limiter
            retry = limiter.retry_after(address)
            if retry is None and scope["method"] == "POST":
                retry = scope["app"].state.chat_global_limiter.retry_after("all")
            if retry is None and request_path.rstrip("/") == "/api/chat/sessions" and scope["method"] == "POST":
                retry = scope["app"].state.chat_creation_limiter.retry_after(address)
            if retry is not None:
                await reject(429, "Muitas solicitações de atendimento. Aguarde antes de tentar novamente.", {"Retry-After": str(retry)})
                return

        # A trailing-slash request redirects to the canonical route: count it once.
        if request_path == "/auth/login" and scope["method"] == "POST":
            # Trust only the ASGI client address, never raw forwarding headers.
            client = scope.get("client")
            retry = scope["app"].state.login_limiter.retry_after(client[0] if client else "unknown")
            if retry is not None:
                await reject(429, "Muitas tentativas de login. Tente novamente mais tarde.",
                             {"Retry-After": str(retry)})
                return

        if scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, secure_send)
            return

        limit = self.max_login_body_bytes if is_login else self.max_body_bytes
        if is_chat:
            limit = min(limit, 16384)
        if is_shipping:
            limit = min(limit, 32768)
        lengths = [value for key, value in scope["headers"] if key.lower() == b"content-length"]
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 20:
                await reject(400, "Tamanho de requisição inválido.")
                return
            if int(lengths[0]) > limit:
                await reject(413, "Corpo da requisição excede o limite permitido.")
                return

        body = bytearray()
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await reject(413, "Corpo da requisição excede o limite permitido.")
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        body = bytes(body)
        sent = False

        async def replay_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, secure_send)
