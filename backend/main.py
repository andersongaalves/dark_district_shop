from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from core.config import settings
from core.request_security import LoginRateLimiter, RequestSecurityMiddleware

from routers.auth import router as auth_router
from routers.produtos import router as produtos_router
from routers.catalog import categories_router, collections_router
from services.catalog import CatalogError
from services.customer_service import SupportError
from routers.webchat import router as webchat_router
from routers.whatsapp import router as whatsapp_router
from routers.atendimento_admin import router as atendimento_router
from core.support_logging import configure_support_logging


app = FastAPI(
    title="Dark District API",
    version="1.0.0"
)
app.state.login_limiter = LoginRateLimiter(
    attempts=settings.LOGIN_ATTEMPTS,
    window_seconds=settings.LOGIN_WINDOW_SECONDS,
)
app.state.chat_ip_limiter = LoginRateLimiter(attempts=60, window_seconds=60)
app.state.chat_creation_limiter = LoginRateLimiter(attempts=settings.CHAT_SESSIONS_PER_HOUR, window_seconds=3600)
app.state.chat_session_limiter = LoginRateLimiter(attempts=settings.CHAT_REQUESTS_PER_MINUTE, window_seconds=60)
app.state.chat_global_limiter = LoginRateLimiter(attempts=settings.CHAT_GLOBAL_REQUESTS_PER_MINUTE, window_seconds=60)
configure_support_logging()


app.add_middleware(
    RequestSecurityMiddleware,
    max_body_bytes=settings.MAX_REQUEST_BODY_BYTES,
    max_login_body_bytes=settings.MAX_LOGIN_BODY_BYTES,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(produtos_router)
app.include_router(categories_router)
app.include_router(collections_router)
app.include_router(webchat_router)
app.include_router(whatsapp_router)
app.include_router(atendimento_router)


@app.exception_handler(CatalogError)
async def catalog_error_handler(_request, error: CatalogError):
    return JSONResponse(status_code=error.status_code, content={"detail": str(error)})


@app.exception_handler(SupportError)
async def support_error_handler(_request, error: SupportError):
    headers = {"Retry-After": "60"} if error.status_code == 429 else None
    return JSONResponse(status_code=error.status_code, content={"detail": str(error)}, headers=headers)


@app.get("/")
def root():
    return {
        "message": "Dark District API online"
    }
