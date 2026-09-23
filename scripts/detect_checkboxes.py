"""Detect checkboxes in form images and classify them as checked/unchecked.

Outputs a Label Studio tasks file with the detections as pre-annotations
(predictions), so they can be reviewed and corrected in the Label Studio UI.

Usage:
    python scripts/detect_checkboxes.py [--images data] [--out output/tasks.json] [--debug output/debug]
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}

# Checkbox side length, as a fraction of image width.
MIN_SIDE_FRAC = 0.008
MAX_SIDE_FRAC = 0.025
# Allowed width/height. Some forms (e.g. URAR 1004) use slightly wide boxes; tall
# narrow holes are usually slivers between a box and an adjacent table line.
MIN_ASPECT = 0.8
MAX_ASPECT = 1.5
# Min stroke length kept as a "line"; long enough to drop text and X marks.
MIN_LINE_FRAC = 0.007
# Fraction of dark pixels inside the box (border excluded) above which it's "checked".
CHECKED_INK_RATIO = 0.06


def binarize(gray: np.ndarray) -> np.ndarray:
    """Ink = 255, paper = 0. Adaptive so light-colored cell shading is treated as paper."""
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )


def line_mask(binary: np.ndarray, min_len: int) -> np.ndarray:
    """Keep only horizontal/vertical strokes at least `min_len` px long (drops text and X marks)."""
    h = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (min_len, 1)))
    v = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_len)))
    lines = cv2.bitwise_or(h, v)
    # Close small gaps at corners.
    return cv2.dilate(lines, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))


def find_boxes(binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    img_w = binary.shape[1]
    min_side = int(img_w * MIN_SIDE_FRAC)
    max_side = int(img_w * MAX_SIDE_FRAC)

    lines = line_mask(binary, max(int(img_w * MIN_LINE_FRAC), 5))
    # Boxes appear as enclosed holes in the line mask, whether or not they touch table grid lines.
    contours, _ = cv2.findContours(255 - lines, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if not (min_side <= w <= max_side and min_side <= h <= max_side):
            continue
        if not MIN_ASPECT <= w / h <= MAX_ASPECT:
            continue
        # The hole must be (nearly) rectangular.
        if cv2.contourArea(c) / (w * h) < 0.85:
            continue
        if not has_solid_border(lines, (x, y, w, h)):
            continue
        boxes.append((x, y, w, h))
    return dedupe(boxes)


def has_solid_border(lines: np.ndarray, box: tuple[int, int, int, int], min_coverage: float = 0.9) -> bool:
    """All four sides must be drawn lines. Rejects letter counters (e.g. "n", "m") that form holes."""
    x, y, w, h = box
    t = 4  # strip thickness just outside the hole
    H, W = lines.shape
    strips = [
        lines[max(y - t, 0) : y, x : x + w].any(axis=0),  # top
        lines[y + h : min(y + h + t, H), x : x + w].any(axis=0),  # bottom
        lines[y : y + h, max(x - t, 0) : x].any(axis=1),  # left
        lines[y : y + h, x + w : min(x + w + t, W)].any(axis=1),  # right
    ]
    return all(s.size and s.mean() >= min_coverage for s in strips)


def dedupe(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    kept: list[tuple[int, int, int, int]] = []
    for b in sorted(boxes, key=lambda b: b[2] * b[3], reverse=True):
        bx, by, bw, bh = b
        cx, cy = bx + bw / 2, by + bh / 2
        if any(kx <= cx <= kx + kw and ky <= cy <= ky + kh for kx, ky, kw, kh in kept):
            continue
        kept.append(b)
    return sorted(kept, key=lambda b: (b[1], b[0]))


def ink_ratio(binary: np.ndarray, box: tuple[int, int, int, int]) -> float:
    x, y, w, h = box
    pad_x, pad_y = max(int(w * 0.15), 2), max(int(h * 0.15), 2)
    inner = binary[y + pad_y : y + h - pad_y, x + pad_x : x + w - pad_x]
    return float(inner.mean() / 255) if inner.size else 0.0


def detect(image_path: Path) -> tuple[list[dict], np.ndarray]:
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Could not read {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = binarize(gray)

    detections = []
    for box in find_boxes(binary):
        ratio = ink_ratio(binary, box)
        detections.append({
            "box": box,
            "label": "checked" if ratio >= CHECKED_INK_RATIO else "unchecked",
            "score": ratio,
        })
    return detections, img


def to_ls_task(image_path: Path, url_prefix: str, detections: list[dict], width: int, height: int) -> dict:
    result = []
    for i, d in enumerate(detections):
        x, y, w, h = d["box"]
        result.append({
            "id": f"{image_path.stem}_{i}",
            "from_name": "label",
            "to_name": "image",
            "type": "rectanglelabels",
            "original_width": width,
            "original_height": height,
            "image_rotation": 0,
            "value": {
                "x": 100 * x / width,
                "y": 100 * y / height,
                "width": 100 * w / width,
                "height": 100 * h / height,
                "rotation": 0,
                "rectanglelabels": [d["label"]],
            },
        })
    return {
        "data": {"image": f"{url_prefix}{image_path.as_posix()}"},
        "predictions": [{"model_version": "opencv-v1", "result": result}],
    }


def draw_debug(img: np.ndarray, detections: list[dict]) -> np.ndarray:
    out = img.copy()
    for d in detections:
        x, y, w, h = d["box"]
        color = (0, 180, 0) if d["label"] == "checked" else (0, 0, 255)
        cv2.rectangle(out, (x - 2, y - 2), (x + w + 2, y + h + 2), color, 3)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--images", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("output/tasks.json"))
    parser.add_argument("--debug", type=Path, help="Write images with detections drawn to this dir")
    parser.add_argument(
        "--url-prefix",
        default="/data/local-files/?d=",
        help="Prefix for image URLs; the default works with Label Studio local file serving",
    )
    args = parser.parse_args()

    tasks = []
    for path in sorted(p for p in args.images.iterdir() if p.suffix.lower() in IMAGE_EXTS):
        detections, img = detect(path)
        h, w = img.shape[:2]
        tasks.append(to_ls_task(path, args.url_prefix, detections, w, h))
        n_checked = sum(d["label"] == "checked" for d in detections)
        print(f"{path.name}: {len(detections)} boxes ({n_checked} checked)")
        if args.debug:
            args.debug.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(args.debug / f"{path.stem}.jpg"), draw_debug(img, detections))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(tasks, indent=2))
    print(f"Wrote {len(tasks)} tasks to {args.out}")


if __name__ == "__main__":
    main()
