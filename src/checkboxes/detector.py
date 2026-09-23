"""Find checkboxes (solid-line squares) and classify them by the ink inside."""

from dataclasses import dataclass

import cv2
import numpy as np

# Bump on any change to the logic or parameters.
MODEL_VERSION = "opencv-v1"

Rect = tuple[int, int, int, int]  # x, y, w, h


@dataclass(frozen=True)
class DetectorParams:
    # Box side, as a fraction of image width.
    min_side_frac: float = 0.008
    max_side_frac: float = 0.025
    # Width / height; URAR 1004 boxes are slightly wide.
    min_aspect: float = 0.8
    max_aspect: float = 1.5
    # Min line length; drops text and X marks.
    min_line_frac: float = 0.007
    # Hole area / bounding-rect area.
    min_fill: float = 0.85
    # Fraction of each side that must be drawn.
    min_border_coverage: float = 0.9
    # Ink fraction inside the box above which it's checked.
    checked_ink_ratio: float = 0.06


@dataclass(frozen=True)
class Detection:
    box: Rect
    is_checked: bool
    score: float

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """(x1, y1, x2, y2)"""
        x, y, w, h = self.box
        return x, y, x + w, y + h

    @property
    def label(self) -> str:
        return "checked" if self.is_checked else "unchecked"


def detect(image: np.ndarray, params: DetectorParams = DetectorParams()) -> list[Detection]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    binary = binarize(gray)
    detections = []
    for box in find_boxes(binary, params):
        ratio = ink_ratio(binary, box)
        detections.append(Detection(box=box, is_checked=ratio >= params.checked_ink_ratio, score=ratio))
    return detections


def binarize(gray: np.ndarray) -> np.ndarray:
    """Ink = 255. Adaptive, so shaded cells count as paper."""
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)


def line_mask(binary: np.ndarray, min_len: int) -> np.ndarray:
    h = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (min_len, 1)))
    v = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_len)))
    lines = cv2.bitwise_or(h, v)
    return cv2.dilate(lines, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))


def find_boxes(binary: np.ndarray, params: DetectorParams) -> list[Rect]:
    img_w = binary.shape[1]
    min_side = int(img_w * params.min_side_frac)
    max_side = int(img_w * params.max_side_frac)

    lines = line_mask(binary, max(int(img_w * params.min_line_frac), 5))
    # Boxes are enclosed holes in the line mask.
    contours, _ = cv2.findContours(255 - lines, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if not (min_side <= w <= max_side and min_side <= h <= max_side):
            continue
        if not params.min_aspect <= w / h <= params.max_aspect:
            continue
        if cv2.contourArea(c) / (w * h) < params.min_fill:
            continue
        if not has_solid_border(lines, (x, y, w, h), params.min_border_coverage):
            continue
        boxes.append((x, y, w, h))
    return dedupe(boxes)


def has_solid_border(lines: np.ndarray, box: Rect, min_coverage: float) -> bool:
    """Rejects holes without four drawn sides, e.g. inside letters like "n"."""
    x, y, w, h = box
    t = 4
    H, W = lines.shape
    strips = [
        lines[max(y - t, 0) : y, x : x + w].any(axis=0),
        lines[y + h : min(y + h + t, H), x : x + w].any(axis=0),
        lines[y : y + h, max(x - t, 0) : x].any(axis=1),
        lines[y : y + h, x + w : min(x + w + t, W)].any(axis=1),
    ]
    return all(s.size and s.mean() >= min_coverage for s in strips)


def dedupe(boxes: list[Rect]) -> list[Rect]:
    kept: list[Rect] = []
    for b in sorted(boxes, key=lambda b: b[2] * b[3], reverse=True):
        bx, by, bw, bh = b
        cx, cy = bx + bw / 2, by + bh / 2
        if any(kx <= cx <= kx + kw and ky <= cy <= ky + kh for kx, ky, kw, kh in kept):
            continue
        kept.append(b)
    return sorted(kept, key=lambda b: (b[1], b[0]))


def ink_ratio(binary: np.ndarray, box: Rect) -> float:
    x, y, w, h = box
    pad_x, pad_y = max(int(w * 0.15), 2), max(int(h * 0.15), 2)
    inner = binary[y + pad_y : y + h - pad_y, x + pad_x : x + w - pad_x]
    return float(inner.mean() / 255) if inner.size else 0.0
