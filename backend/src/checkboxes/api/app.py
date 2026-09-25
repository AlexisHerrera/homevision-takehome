import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from checkboxes.api.config import get_settings
from checkboxes.api.routes import detect, health


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Checkbox Detection API",
        description="Detect checkboxes in appraisal forms and classify them as checked / unchecked.",
        version="0.1.0",
        root_path=settings.root_path,
    )

    @app.middleware("http")
    async def reject_large_requests(request: Request, call_next):
        content_length = int(request.headers.get("content-length", 0))
        if content_length > settings.max_upload_bytes:
            return JSONResponse(
                {"detail": f"Request exceeds {settings.max_upload_bytes:,} bytes"},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
        return await call_next(request)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["*"]
        )

    app.include_router(health.router)
    app.include_router(detect.router)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
