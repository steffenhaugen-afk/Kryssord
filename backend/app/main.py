from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import api_router
from .config import settings

app = FastAPI(
    title="Kryssord Norge API",
    version="0.1.0",
    description="API for norske kryssord — ordbank, synonymer og kryssordgenerator.",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["meta"])
def health_check():
    return {"status": "ok", "version": app.version}
