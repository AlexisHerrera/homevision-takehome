import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from checkboxes.api.config import Settings, get_settings
from checkboxes.api.schemas import Box, DetectResponse
from checkboxes.detector import detect
from checkboxes.documents import DocumentTooLargeError, UnsupportedDocumentError, load_pages

logger = logging.getLogger(__name__)

router = APIRouter(tags=["detection"])


def run_detection(data: bytes, settings: Settings) -> DetectResponse:
    pages = load_pages(data, pdf_dpi=settings.pdf_dpi, max_pages=settings.max_pages, max_pixels=settings.max_pixels)
    boxes = [
        Box(bbox=d.bbox, is_checked=d.is_checked, page=number)
        for number, image in enumerate(pages, start=1)
        for d in detect(image)
    ]
    return DetectResponse(boxes=boxes)


@router.post(
    "/detect",
    responses={
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "File, page count or page size over the limit"},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": "Not a PDF or a supported image"},
    },
)
async def detect_checkboxes(file: UploadFile, settings: Annotated[Settings, Depends(get_settings)]) -> DetectResponse:
    """Detect checkboxes in a PDF or image and classify each as checked / unchecked."""
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {settings.max_upload_bytes:,} bytes")

    start = time.perf_counter()
    try:
        # CPU-bound
        result = await run_in_threadpool(run_detection, data, settings)
    except UnsupportedDocumentError as e:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(e)) from e
    except DocumentTooLargeError as e:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(e)) from e

    logger.info(
        "detect file=%r boxes=%d ms=%.0f",
        file.filename,
        len(result.boxes),
        (time.perf_counter() - start) * 1000,
    )
    return result
