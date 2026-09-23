import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from checkboxes.api.config import get_settings
from checkboxes.api.routes import detect, health


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Checkbox Detection API",
        description="Detect checkboxes in appraisal forms and classify them as checked / unchecked.",
        version="0.1.0",
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["*"]
        )
    app.include_router(health.router)
    app.include_router(detect.router)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
