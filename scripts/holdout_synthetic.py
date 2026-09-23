"""Generate synthetic filled forms with exact ground truth for the held-out set.

Templates are the blank-form pages (sources b*) of data/holdout/real_reviewed.json at 300 DPI, so run
`holdout_real.py fetch render` first. Each image gets one degradation profile (its directory) and each
box a mark (sets the label) plus maybe a box condition; both are stored as region meta tags
("mark:<name>", "cond:<name>") so evaluate.py --breakdown can score them separately.

Deterministic for a given --seed and pypdfium2/OpenCV version; images are not committed.

Usage:
    uv run scripts/holdout_synthetic.py [--seed 0] [--per-profile 20]
"""

import argparse
import itertools
import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
HOLDOUT = REPO_ROOT / "data" / "holdout"
TEMPLATES = HOLDOUT / "real_reviewed.json"
OUT_DIR = HOLDOUT / "synthetic"
LABELS = HOLDOUT / "synthetic.json"
URL_PREFIX = "/data/local-files/?d="

PROFILES = ("clean", "jpeg", "lowres", "blur", "noise", "rotate", "lighting", "scan")
CHECKED_MARKS = {"x": 14, "check": 12, "filled": 5, "small": 6, "offcenter": 5, "overshoot": 6, "typed_x": 5}
UNCHECKED_MARKS = {"empty": 33, "crossing_stroke": 7, "erased_x": 7}
CONDITIONS = {"faint": 0.06, "broken_corner": 0.05, "table_line": 0.05}
ADJACENT_PER_IMAGE = 2

Rect = tuple[int, int, int, int]  # x1, y1, x2, y2


@dataclass
class Box:
    rect: Rect
    mark: str = "empty"
    conds: list[str] = field(default_factory=list)
    path: np.ndarray | None = None

    @property
    def label(self) -> str:
        return "checked" if self.mark in CHECKED_MARKS else "unchecked"


def load_templates(path: Path) -> list[tuple[Path, list[Rect]]]:
    templates = []
    for task in json.loads(path.read_text()):
        rel = Path(unquote(task["data"]["image"].split("?d=")[-1]))
        if not rel.name.startswith("b"):
            continue
        rects = []
        for r in task["annotations"][0]["result"]:
            if r.get("type") != "rectanglelabels":
                continue
            v, w, h = r["value"], r["original_width"], r["original_height"]
            x1, y1 = v["x"] * w / 100, v["y"] * h / 100
            rects.append((round(x1), round(y1), round(x1 + v["width"] * w / 100), round(y1 + v["height"] * h / 100)))
        if rects:
            templates.append((rel, rects))
    return templates


def ink_color(rng: np.random.Generator) -> tuple[int, int, int]:
    """BGR: black, blue ballpoint or pencil gray."""
    kind = rng.choice(3, p=[0.45, 0.35, 0.2])
    if kind == 0:
        return (int(rng.integers(0, 40)),) * 3
    if kind == 1:
        return int(rng.integers(90, 150)), int(rng.integers(20, 60)), int(rng.integers(0, 30))
    return (int(rng.integers(70, 110)),) * 3


def stroke(img: np.ndarray, pts: np.ndarray, color, thickness: int, rng: np.random.Generator, wobble: float) -> None:
    """Hand-drawn line through pts: resampled with a little jitter."""
    dense = []
    for a, b in itertools.pairwise(pts):
        n = max(int(np.linalg.norm(b - a) / 6), 2)
        for t in np.linspace(0, 1, n, endpoint=False):
            dense.append(a + (b - a) * t)
    dense.append(pts[-1])
    dense = np.array(dense) + rng.normal(0, wobble, (len(dense), 2))
    cv2.polylines(img, [np.round(dense).astype(np.int32)], False, color, thickness, cv2.LINE_AA)


def draw_x(img, x1, y1, x2, y2, color, t, rng):
    s = (x2 - x1) * 0.08
    stroke(img, np.array([[x1, y1], [x2, y2]], float) + rng.normal(0, s, (2, 2)), color, t, rng, 0.6)
    stroke(img, np.array([[x2, y1], [x1, y2]], float) + rng.normal(0, s, (2, 2)), color, t, rng, 0.6)


def draw_mark(img: np.ndarray, box: Box, rng: np.random.Generator) -> None:
    x1, y1, x2, y2 = box.rect
    side = min(x2 - x1, y2 - y1)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    color = ink_color(rng)
    t = int(rng.integers(2, 5))
    m = box.mark
    if m in ("x", "small", "offcenter", "overshoot", "erased_x"):
        half = {"x": 0.4, "small": 0.2, "offcenter": 0.3, "overshoot": 0.75, "erased_x": 0.47}[m] * side
        if m == "small":
            half *= rng.uniform(0.8, 1.2)
        dx, dy = (rng.uniform(-0.25, 0.25, 2) * side) if m in ("offcenter", "small") else (0.0, 0.0)
        draw_x(img, cx + dx - half, cy + dy - half, cx + dx + half, cy + dy + half, color, t, rng)
        if m == "erased_x":
            inset = int(side * rng.uniform(0.15, 0.25))
            cv2.rectangle(img, (x1 + inset, y1 + inset), (x2 - inset, y2 - inset), (250, 250, 250), -1)
    elif m == "check":
        s = side * rng.uniform(0.8, 1.2)
        pts = np.array([[-0.35, 0.0], [-0.1, 0.3], [0.45, -0.5]]) * s + [cx, cy]
        stroke(img, pts, color, t, rng, 0.7)
    elif m == "filled":
        inset = int(side * rng.uniform(0.1, 0.2))
        cv2.rectangle(img, (x1 + inset, y1 + inset), (x2 - inset, y2 - inset), color, -1)
    elif m == "typed_x":
        font = int(rng.choice([cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX, cv2.FONT_HERSHEY_PLAIN]))
        target = side * rng.uniform(0.55, 0.8)
        (tw, th), _ = cv2.getTextSize("X", font, 1.0, 1)
        scale = target / th
        (tw, th), _ = cv2.getTextSize("X", font, scale, 2)
        org = (int(cx - tw / 2), int(cy + th / 2))
        cv2.putText(img, "X", org, font, scale, (20, 20, 20), 2, cv2.LINE_AA)
    elif m == "crossing_stroke":
        stroke(img, box.path, color, t, rng, 1.0)


def crossing_path(box: Box, others: list[Box], rng: np.random.Generator) -> np.ndarray | None:
    """A long stroke through the box that doesn't touch any other box, or None."""
    x1, y1, x2, y2 = box.rect
    side = x2 - x1
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    for _ in range(20):
        length = side * rng.uniform(4, 9)
        angle = rng.uniform(-0.6, 0.6) + (math.pi / 2 if rng.random() < 0.3 else 0)
        d = np.array([math.cos(angle), math.sin(angle)])
        ts = np.linspace(-length / 2, length / 2, 7) + rng.uniform(-0.3, 0.3) * length
        ts[np.argmin(np.abs(ts))] = 0  # pass through the box center
        normal = np.array([-d[1], d[0]])
        pts = np.array([[cx, cy] + d * t + normal * rng.normal(0, side * 0.25) for t in ts])
        dense = np.concatenate([np.linspace(a, b, 20) for a, b in itertools.pairwise(pts)])
        if not any(
            o is not box
            and np.any(
                (dense[:, 0] > o.rect[0] - 8)
                & (dense[:, 0] < o.rect[2] + 8)
                & (dense[:, 1] > o.rect[1] - 8)
                & (dense[:, 1] < o.rect[3] + 8)
            )
            for o in others
        ):
            return pts
    return None


def apply_condition(img: np.ndarray, box: Box, cond: str, rng: np.random.Generator) -> None:
    x1, y1, x2, y2 = box.rect
    side = x2 - x1
    if cond == "faint":
        pad = 5
        region = img[y1 - pad : y2 + pad, x1 - pad : x2 + pad]
        level = rng.uniform(0.25, 0.45)  # remaining ink darkness
        region[:] = (255 - (255 - region.astype(np.float32)) * level).astype(np.uint8)
        # Dark content right next to it.
        gap = int(rng.integers(3, 8))
        if rng.random() < 0.5:
            cv2.rectangle(img, (x2 + pad + gap, y1 - 2), (x2 + pad + gap + side * 3, y2 + 2), (15, 15, 15), -1)
        else:
            cv2.putText(img, "WWW", (x2 + pad + gap, y2), cv2.FONT_HERSHEY_DUPLEX, side / 22, (0, 0, 0), 4, cv2.LINE_AA)
    elif cond == "broken_corner":
        n = int(side * rng.uniform(0.3, 0.5))
        corner = rng.integers(4)
        vertical = rng.random() < 0.5
        cx = x1 - 5 if corner in (0, 2) else x2 - 3
        cy = y1 - 5 if corner in (0, 1) else y2 - 3
        if vertical:
            y0 = y1 - 5 if corner in (0, 1) else y2 + 5 - n
            cv2.rectangle(img, (cx, y0), (cx + 8, y0 + n), (255, 255, 255), -1)
        else:
            x0 = x1 - 5 if corner in (0, 2) else x2 + 5 - n
            cv2.rectangle(img, (x0, cy), (x0 + n, cy + 8), (255, 255, 255), -1)
    elif cond == "table_line":
        t = int(rng.integers(2, 4))
        span = int(side * rng.uniform(4, 12))
        if rng.random() < 0.6:
            y = y1 - 2 if rng.random() < 0.5 else y2 + 1
            x0 = x1 - int(rng.uniform(0, 1) * span)
            cv2.line(img, (x0, y), (x0 + span, y), (0, 0, 0), t)
        else:
            x = x1 - 2 if rng.random() < 0.5 else x2 + 1
            y0 = y1 - int(rng.uniform(0, 1) * span)
            cv2.line(img, (x, y0), (x, y0 + span), (0, 0, 0), t)


def add_adjacent(img: np.ndarray, boxes: list[Box], rng: np.random.Generator) -> None:
    """Draw a new box to the right of an existing one, with a ruled label cell between them."""
    w_img = img.shape[1]
    for i in rng.permutation(len(boxes)):
        b = boxes[i]
        x1, y1, x2, y2 = b.rect
        side = x2 - x1
        cell = int(side * rng.uniform(1.8, 3.0))
        nx1 = x2 + cell
        nx2 = nx1 + side
        if nx2 + side >= w_img:
            continue
        area = img[y1 - 6 : y2 + 6, x2 + 8 : nx2 + side // 2, 0]
        if area.size == 0 or area.min() < 200:
            continue
        t = 3
        cv2.rectangle(img, (nx1 - t, y1 - t), (nx2 + t - 1, y2 + t - 1), (0, 0, 0), t)
        lx1, lx2 = x2 + (cell // 6), nx1 - (cell // 6)
        for x in (lx1, lx2):
            cv2.line(img, (x, y1 - side // 2), (x, y2 + side // 2), (0, 0, 0), 2)
        cv2.putText(img, "N/A", (lx1 + 4, y2 - 3), cv2.FONT_HERSHEY_SIMPLEX, side / 45, (0, 0, 0), 2, cv2.LINE_AA)
        b.conds.append("adjacent")
        boxes.append(Box((nx1, y1, nx2, y2), conds=["adjacent"]))
        return


def degrade(img: np.ndarray, rects: list[Rect], profile: str, rng: np.random.Generator):
    """Returns (image, rects, file extension)."""
    steps = {
        "clean": [],
        "jpeg": ["jpeg"],
        "lowres": ["lowres"],
        "blur": ["blur"],
        "noise": ["noise"],
        "rotate": ["rotate"],
        "lighting": ["lighting"],
        "scan": ["rotate", "lighting", "lowres", "blur", "noise", "jpeg"],
    }[profile]
    boxes = np.array(rects, float)
    quality = None
    for step in steps:
        if step == "rotate":
            h, w = img.shape[:2]
            angle = rng.uniform(0.5, 2.0) * rng.choice([-1, 1])
            m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            img = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
            corners = np.stack(
                [boxes[:, [0, 1]], boxes[:, [2, 1]], boxes[:, [0, 3]], boxes[:, [2, 3]]], axis=1
            )  # n x 4 x 2
            moved = corners @ m[:, :2].T + m[:, 2]
            boxes = np.concatenate([moved.min(axis=1), moved.max(axis=1)], axis=1)
        elif step == "lowres":
            f = rng.uniform(1400, 1700) / img.shape[1]
            img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
            boxes *= f
        elif step == "blur":
            sigma = rng.uniform(0.6, 1.0) if profile == "scan" else rng.uniform(1.0, 2.0)
            img = cv2.GaussianBlur(img, (0, 0), sigma)
        elif step == "noise":
            sigma = rng.uniform(6, 14)
            noisy = img.astype(np.float32) + rng.normal(0, sigma, img.shape[:2])[..., None]
            speck = rng.random(img.shape[:2]) < 0.0015
            noisy[speck] = rng.uniform(0, 120)
            img = np.clip(noisy, 0, 255).astype(np.uint8)
        elif step == "lighting":
            h, w = img.shape[:2]
            gx, gy = np.meshgrid(np.linspace(-1, 1, w, dtype=np.float32), np.linspace(-1, 1, h, dtype=np.float32))
            a, b = rng.uniform(-1, 1, 2)
            gain = 1 - rng.uniform(0.15, 0.35) * (0.5 + 0.5 * (a * gx + b * gy) / math.hypot(a, b))
            paper = rng.uniform(0.82, 0.95)
            tint = np.array([rng.uniform(0.95, 1.0), rng.uniform(0.97, 1.0), 1.0], np.float32)
            img = np.clip(img.astype(np.float32) * (gain * paper)[..., None] * tint, 0, 255).astype(np.uint8)
        elif step == "jpeg":
            quality = int(rng.integers(40, 70) if profile == "scan" else rng.integers(20, 55))
    return img, [tuple(float(v) for v in b) for b in boxes], quality


def to_task(rel: Path, w: int, h: int, boxes: list[Box], rects: list[Rect]) -> dict:
    result = []
    for i, (b, (x1, y1, x2, y2)) in enumerate(zip(boxes, rects, strict=True)):
        result.append(
            {
                "id": f"{rel.stem}_{i}",
                "from_name": "label",
                "to_name": "image",
                "type": "rectanglelabels",
                "original_width": w,
                "original_height": h,
                "image_rotation": 0,
                "value": {
                    "x": 100 * x1 / w,
                    "y": 100 * y1 / h,
                    "width": 100 * (x2 - x1) / w,
                    "height": 100 * (y2 - y1) / h,
                    "rotation": 0,
                    "rectanglelabels": [b.label],
                },
                "meta": {"text": [f"mark:{b.mark}", *(f"cond:{c}" for c in b.conds)]},
            }
        )
    return {"data": {"image": URL_PREFIX + rel.as_posix()}, "annotations": [{"result": result}]}


def generate(template: Path, rects: list[Rect], profile: str, rng: np.random.Generator):
    img = cv2.imread(str(REPO_ROOT / template))
    boxes = [Box(r) for r in rects]
    for _ in range(ADJACENT_PER_IMAGE):
        add_adjacent(img, boxes, rng)
    marks = {**CHECKED_MARKS, **UNCHECKED_MARKS}
    names, weights = list(marks), np.array(list(marks.values()), float)
    for b in boxes:
        b.mark = str(rng.choice(names, p=weights / weights.sum()))
        if b.mark == "crossing_stroke":
            b.path = crossing_path(b, boxes, rng)
            if b.path is None:
                b.mark = "empty"
        for cond, p in CONDITIONS.items():
            if rng.random() < p:
                b.conds.append(cond)
    # Conditions first so marks drawn on top aren't lightened or cut.
    for b in boxes:
        for c in b.conds:
            if c != "adjacent":
                apply_condition(img, b, c, rng)
    for b in boxes:
        draw_mark(img, b, rng)
    img, out_rects, quality = degrade(img, [b.rect for b in boxes], profile, rng)
    return img, boxes, out_rects, quality


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--per-profile", type=int, default=20, help="Images per degradation profile")
    parser.add_argument("--templates", type=Path, default=TEMPLATES)
    args = parser.parse_args()

    templates = load_templates(args.templates)
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    tasks = []
    for p_idx, profile in enumerate(PROFILES):
        (OUT_DIR / profile).mkdir(parents=True)
        for i in range(args.per_profile):
            rng = np.random.default_rng([args.seed, p_idx, i])
            template, rects = templates[int(rng.integers(len(templates)))]
            img, boxes, out_rects, quality = generate(template, rects, profile, rng)
            ext = ".jpg" if quality else ".png"
            rel = OUT_DIR.relative_to(REPO_ROOT) / profile / f"{profile}_{i:03d}_{template.stem}{ext}"
            params = [cv2.IMWRITE_JPEG_QUALITY, quality] if quality else []
            cv2.imwrite(str(REPO_ROOT / rel), img, params)
            h, w = img.shape[:2]
            tasks.append(to_task(rel, w, h, boxes, out_rects))
        print(f"{profile}: {args.per_profile} images")
    LABELS.write_text(json.dumps(tasks, indent=1))
    print(f"Wrote {len(tasks)} tasks to {LABELS.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
