"""Detect checkboxes in form images and classify them as checked/unchecked.

Outputs a Label Studio tasks file with the detections as pre-annotations
(predictions), so they can be reviewed and corrected in the Label Studio UI.

Usage:
    uv run scripts/detect_checkboxes.py [--images data] [--out output/tasks.json] [--debug output/debug]
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from checkboxes.detector import MODEL_VERSION, Detection, detect

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def to_ls_task(image_path: Path, url_prefix: str, detections: list[Detection], width: int, height: int) -> dict:
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
        "predictions": [{"model_version": MODEL_VERSION, "result": result}],
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
    parser.add_argument(
        "--url-prefix",
        default="/data/local-files/?d=",
        help="Prefix for image URLs; the default works with Label Studio local file serving",
    )
    args = parser.parse_args()

    tasks = []
    for path in sorted(p for p in args.images.iterdir() if p.suffix.lower() in IMAGE_EXTS):
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"Could not read {path}")
        detections = detect(img)
        h, w = img.shape[:2]
        tasks.append(to_ls_task(path, args.url_prefix, detections, w, h))
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
