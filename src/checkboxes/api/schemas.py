from pydantic import BaseModel, Field


class Box(BaseModel):
    bbox: tuple[int, int, int, int] = Field(description="[x1, y1, x2, y2] in pixels of the page image")
    is_checked: bool
    page: int = Field(description="1-based page number")


class DetectResponse(BaseModel):
    boxes: list[Box]


class HealthResponse(BaseModel):
    status: str
    model_version: str
