from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from core.config import settings
from core.request_security import LoginRateLimiter, RequestSecurityMiddleware

from routers.auth import router as auth_router
from routers.produtos import router as produtos_router
from routers.catalog import categories_router, collections_router
from services.catalog import CatalogError


app = FastAPI(
    title="Dark District API",
    version="1.0.0"
)
app.state.login_limiter = LoginRateLimiter(
    attempts=settings.LOGIN_ATTEMPTS,
    window_seconds=settings.LOGIN_WINDOW_SECONDS,
)


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


@app.exception_handler(CatalogError)
async def catalog_error_handler(_request, error: CatalogError):
    return JSONResponse(status_code=error.status_code, content={"detail": str(error)})


@app.get("/")
def root():
    return {
        "message": "Dark District API online"
    }
