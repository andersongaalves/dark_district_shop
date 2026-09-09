from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings

from routers.auth import router as auth_router
from routers.produtos import router as produtos_router


app = FastAPI(
    title="Dark District API",
    version="1.0.0"
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


@app.get("/")
def root():
    return {
        "message": "Dark District API online"
    }
