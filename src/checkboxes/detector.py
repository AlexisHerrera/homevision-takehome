"""Find checkboxes (solid-line squares) and classify them by the ink inside."""

from dataclasses import dataclass, replace

import cv2
import numpy as np

# Bump on any change to the logic or parameters.
MODEL_VERSION = "opencv-v5"

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
    # Recovery passes: max size difference from the page's median box.
    recover_size_tolerance: float = 0.15
    # Recovery passes: darkness below the local paper level that counts as faint ink.
    faint_ink_contrast: int = 30
    # Recovery passes: longest line break to bridge, as a fraction of image width.
    recover_gap_frac: float = 0.003
    recover_min_fill: float = 0.7
    # Narrower images are upscaled to this width first; the pixel constants assume ~25+ px boxes.
    min_width: int = 2550
    max_upscaled_pixels: int = 12_000_000
    # Boxes smaller than this fraction of the page's median box are dropped (glyph holes).
    min_size_ratio: float = 0.8


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
    gray, scale = upscale(gray, params)
    binary = binarize(gray)
    boxes = find_boxes(binary, params)
    boxes = sorted(boxes + recover_boxes(gray, binary, boxes, params), key=lambda b: (b[1], b[0]))
    boxes = drop_small(boxes, params.min_size_ratio)
    h_lines, v_lines, _ = line_masks(binary, min_line_len(binary, params))
    lines = cv2.bitwise_or(h_lines, v_lines)
    detections = []
    for box in boxes:
        ratio = ink_ratio(binary, lines, box)
        detections.append(Detection(box=unscale(box, scale), is_checked=ratio >= params.checked_ink_ratio, score=ratio))
    return detections


def upscale(gray: np.ndarray, params: DetectorParams) -> tuple[np.ndarray, float]:
    h, w = gray.shape
    scale = min(params.min_width / w, (params.max_upscaled_pixels / (w * h)) ** 0.5)
    if scale <= 1:
        return gray, 1.0
    return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC), scale


def unscale(box: Rect, scale: float) -> Rect:
    x, y, w, h = box
    x1, y1 = round(x / scale), round(y / scale)
    return x1, y1, round((x + w) / scale) - x1, round((y + h) / scale) - y1


def binarize(gray: np.ndarray) -> np.ndarray:
    """Ink = 255. Adaptive, so shaded cells count as paper."""
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)


def faint_ink(gray: np.ndarray, contrast: int) -> np.ndarray:
    """Ink = 255 where darker than the nearby paper; unlike `binarize`, dark neighbors don't hide faint lines."""
    k = max(int(gray.shape[1] * 0.004) | 1, 3)
    paper = cv2.dilate(gray, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    return np.where(paper.astype(np.int16) - gray > contrast, 255, 0).astype(np.uint8)


def min_line_len(binary: np.ndarray, params: DetectorParams) -> int:
    return max(int(binary.shape[1] * params.min_line_frac), 5)


def line_masks(binary: np.ndarray, min_len: int, close_gap: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Horizontal lines, vertical lines, and both merged and dilated to close small gaps."""
    h = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (min_len, 1)))
    v = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_len)))
    lines = cv2.bitwise_or(h, v)
    if close_gap:
        lines = cv2.bitwise_or(
            cv2.morphologyEx(lines, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (close_gap, 1))),
            cv2.morphologyEx(lines, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, close_gap))),
        )
    lines = cv2.dilate(lines, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    return h, v, lines


def find_boxes(binary: np.ndarray, params: DetectorParams, close_gap: int = 0) -> list[Rect]:
    img_w = binary.shape[1]
    min_side = int(img_w * params.min_side_frac)
    max_side = int(img_w * params.max_side_frac)

    h_lines, v_lines, lines = line_masks(binary, min_line_len(binary, params), close_gap)
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
    boxes = dedupe(boxes)
    return [b for b in boxes if not is_slot(b, boxes, lines, h_lines, v_lines)]


def recover_boxes(gray: np.ndarray, binary: np.ndarray, found: list[Rect], params: DetectorParams) -> list[Rect]:
    """Looser passes for damaged boxes (faint, broken corner, crossed by a stroke).

    Each pass relaxes one step. A result is kept only if it is new and the size of the boxes already found,
    since a form's checkboxes share one size; the strict results are never changed.
    """
    if len(found) < 3:
        return []
    med_w, med_h = np.median([b[2] for b in found]), np.median([b[3] for b in found])
    tol = params.recover_size_tolerance
    passes = [
        find_boxes(cv2.bitwise_or(binary, faint_ink(gray, params.faint_ink_contrast)), params),
        find_boxes(binary, params, close_gap=max(int(gray.shape[1] * params.recover_gap_frac), 5)),
        find_boxes(binary, replace(params, min_fill=params.recover_min_fill)),
    ]
    added: list[Rect] = []
    for box in (b for boxes in passes for b in boxes):
        _, _, w, h = box
        if abs(w - med_w) > tol * med_w or abs(h - med_h) > tol * med_h:
            continue
        if overlaps(box, found + added):
            continue
        added.append(box)
    return added


def drop_small(boxes: list[Rect], min_ratio: float) -> list[Rect]:
    """A form's checkboxes share one size; much smaller holes are letters, e.g. white-on-black sidebar text."""
    if len(boxes) < 3:
        return boxes
    med = np.median([max(b[2], b[3]) for b in boxes])
    return [b for b in boxes if max(b[2], b[3]) >= min_ratio * med]


def overlaps(box: Rect, boxes: list[Rect]) -> bool:
    x, y, w, h = box
    return any(x < bx + bw and bx < x + w and y < by + bh and by < y + h for bx, by, bw, bh in boxes)


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


def is_slot(box: Rect, boxes: list[Rect], lines: np.ndarray, h_lines: np.ndarray, v_lines: np.ndarray) -> bool:
    """A gap between two adjacent boxes, closed off by lines running past it (e.g. a label cell)."""
    others = [b for b in boxes if b != box]
    if (
        any(shares_edge(lines, b, box) for b in others)
        and any(shares_edge(lines, box, b) for b in others)
        and runs_past(h_lines, box, -1)
        and runs_past(h_lines, box, 1)
    ):
        return True
    t_box, t_others = transpose(box), [transpose(b) for b in others]
    return (
        any(shares_edge(lines.T, b, t_box) for b in t_others)
        and any(shares_edge(lines.T, t_box, b) for b in t_others)
        and runs_past(v_lines.T, t_box, -1)
        and runs_past(v_lines.T, t_box, 1)
    )


def transpose(box: Rect) -> Rect:
    x, y, w, h = box
    return y, x, h, w


def shares_edge(lines: np.ndarray, left: Rect, right: Rect) -> bool:
    """`right` sits just right of `left`, with only a line between them."""
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    if not 0 <= rx - (lx + lw) <= min(lw, rw) // 4:
        return False
    y0, y1 = max(ly, ry), min(ly + lh, ry + rh)
    if y1 - y0 < min(lh, rh) / 2:
        return False
    return bool(lines[y0:y1, lx + lw : rx].all())


def runs_past(h_lines: np.ndarray, box: Rect, step: int) -> bool:
    """The edge above (step=-1) or below (+1) the box is a line continuing past both corners."""
    x, y, w, h = box
    H, W = h_lines.shape
    margin = max(w // 3, 3)
    if x - margin < 0 or x + w + margin > W:
        return False

    def is_edge(r: int) -> bool:
        return 0 <= r < H and h_lines[r, x : x + w].mean() > 127

    r = y - 1 if step < 0 else y + h
    # The dilated mask puts the hole within 2 px of the edge.
    for _ in range(3):
        if is_edge(r):
            break
        r += step
    while is_edge(r):
        if h_lines[r, x - margin : x + w + margin].all():
            return True
        r += step
    return False


def dedupe(boxes: list[Rect]) -> list[Rect]:
    kept: list[Rect] = []
    for b in sorted(boxes, key=lambda b: b[2] * b[3], reverse=True):
        bx, by, bw, bh = b
        cx, cy = bx + bw / 2, by + bh / 2
        if any(kx <= cx <= kx + kw and ky <= cy <= ky + kh for kx, ky, kw, kh in kept):
            continue
        kept.append(b)
    return sorted(kept, key=lambda b: (b[1], b[0]))


def ink_ratio(binary: np.ndarray, lines: np.ndarray, box: Rect) -> float:
    """Ink fraction inside the box, ignoring strokes that run a box size or more outside it (e.g. a cross-out)."""
    x, y, w, h = box
    H, W = binary.shape
    m = max(w, h)
    x0, y0, x1, y1 = max(x - m, 0), max(y - m, 0), min(x + w + m, W), min(y + h + m, H)
    ink = binary[y0:y1, x0:x1] > 0
    on_line = lines[y0:y1, x0:x1] > 0
    strokes = ink & ~on_line
    # Rejoin strokes cut where they crossed a line, bridging only through line pixels.
    k = max(m // 4, 3)
    grown = cv2.dilate(strokes.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))) > 0
    joined = (strokes | (grown & on_line)).astype(np.uint8)
    _, labels, stats, _ = cv2.connectedComponentsWithStats(joined)
    left, top, cw, ch = (stats[:, i] for i in range(4))
    reaches_edge = (left == 0) | (top == 0) | (left + cw == x1 - x0) | (top + ch == y1 - y0)
    reaches_edge[0] = False
    ink &= ~(strokes & reaches_edge[labels])

    pad_x, pad_y = max(int(w * 0.15), 2), max(int(h * 0.15), 2)
    bx, by = x - x0, y - y0
    inner = ink[by + pad_y : by + h - pad_y, bx + pad_x : bx + w - pad_x]
    return float(inner.mean()) if inner.size else 0.0
