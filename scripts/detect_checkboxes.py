"""Detect checkboxes in form images and classify them as checked/unchecked.

Outputs a Label Studio tasks file with the detections as pre-annotations
(predictions), so they can be reviewed and corrected in the Label Studio UI.

Usage:
    uv run scripts/detect_checkboxes.py [--images data] [--out output/tasks.json] [--debug output/debug]

Labeling aid for layouts the default parameters miss: each --params runs one extra detector pass with those
overrides and the detections are merged, e.g.
    uv run scripts/detect_checkboxes.py --images data/holdout/real/300 --pattern 'f[23]_*' \
        --params min_side_frac=0.003,min_line_frac=0.006,min_border_coverage=0.75,min_fill=0.75 \
        --params min_side_frac=0.003,min_line_frac=0.003,min_border_coverage=0.75,min_fill=0.75
"""

import argparse
import json
from dataclasses import fields, replace
from pathlib import Path

import cv2
import numpy as np

from checkboxes.detector import MODEL_VERSION, Detection, DetectorParams, detect

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def parse_params(spec: str) -> DetectorParams:
    types = {f.name: f.type for f in fields(DetectorParams)}
    overrides = {}
    for item in spec.split(","):
        key, value = item.split("=")
        overrides[key] = (int if types[key] in (int, "int") else float)(value)
    return replace(DetectorParams(), **overrides)


def overlaps(a: Detection, b: Detection) -> bool:
    ax1, ay1, ax2, ay2 = a.bbox
    bx1, by1, bx2, by2 = b.bbox
    inter = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(0, min(ay2, by2) - max(ay1, by1))
    return inter > 0.3 * min(a.box[2] * a.box[3], b.box[2] * b.box[3])


def detect_passes(img: np.ndarray, passes: list[DetectorParams]) -> list[Detection]:
    """Union of the passes; earlier passes win on overlap."""
    merged: list[Detection] = []
    for params in passes:
        merged += [d for d in detect(img, params) if not any(overlaps(d, m) for m in merged)]
    return sorted(merged, key=lambda d: (d.box[1], d.box[0]))


def to_ls_task(
    image_path: Path, url_prefix: str, detections: list[Detection], width: int, height: int, model_version: str
) -> dict:
    result = []
    for i, d in enumerate(detections):
        x, y, w, h = d.box
        result.append(
            {
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
                    "rectanglelabels": [d.label],
                },
            }
        )
    return {
        "data": {"image": f"{url_prefix}{image_path.as_posix()}"},
        "predictions": [{"model_version": model_version, "result": result}],
    }


def draw_debug(img: np.ndarray, detections: list[Detection]) -> np.ndarray:
    out = img.copy()
    for d in detections:
        x, y, w, h = d.box
        color = (0, 180, 0) if d.is_checked else (0, 0, 255)
        cv2.rectangle(out, (x - 2, y - 2), (x + w + 2, y + h + 2), color, 3)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--images", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("output/tasks.json"))
    parser.add_argument("--debug", type=Path, help="Write images with detections drawn to this dir")
    parser.add_argument("--pattern", default="*", help="Glob for image names within --images")
    parser.add_argument(
        "--params",
        action="append",
        type=parse_params,
        help="KEY=VALUE[,...] DetectorParams overrides for one pass; repeat for more passes",
    )
    parser.add_argument(
        "--url-prefix",
        default="/data/local-files/?d=",
        help="Prefix for image URLs; the default works with Label Studio local file serving",
    )
    args = parser.parse_args()
    passes = args.params or [DetectorParams()]
    model_version = MODEL_VERSION if not args.params else f"{MODEL_VERSION}+{len(passes)}-pass-override"

    tasks = []
    for path in sorted(p for p in args.images.glob(args.pattern) if p.suffix.lower() in IMAGE_EXTS):
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"Could not read {path}")
        detections = detect_passes(img, passes)
        h, w = img.shape[:2]
        tasks.append(to_ls_task(path, args.url_prefix, detections, w, h, model_version))
        n_checked = sum(d.is_checked for d in detections)
        print(f"{path.name}: {len(detections)} boxes ({n_checked} checked)")
        if args.debug:
            args.debug.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(args.debug / f"{path.stem}.jpg"), draw_debug(img, detections))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(tasks, indent=2))
    print(f"Wrote {len(tasks)} tasks to {args.out}")


if __name__ == "__main__":
    main()
