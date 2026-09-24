from fastapi import APIRouter

from checkboxes.api.schemas import HealthResponse
from checkboxes.detector import MODEL_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok", model_version=MODEL_VERSION)
