from pydantic import BaseModel, Field


class Box(BaseModel):
    bbox: tuple[int, int, int, int] = Field(description="[x1, y1, x2, y2] in pixels")
    is_checked: bool


class DetectResponse(BaseModel):
    boxes: list[Box]


class HealthResponse(BaseModel):
    status: str
    model_version: str
