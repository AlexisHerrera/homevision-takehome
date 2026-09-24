"""Score the detector against the hand-reviewed labels (a match is IoU >= --iou).

Usage:
    uv run scripts/evaluate.py [--labels data/labels.json] [--iou 0.5] [--errors]
    uv run scripts/evaluate.py --record --note "baseline"
    uv run scripts/evaluate.py --history
    uv run scripts/evaluate.py --labels data/holdout/synthetic.json --group-by '/([^/]+)/[^/]+$' --breakdown

Try a parameter change without editing the detector (not recordable), optionally on a subset of images:
    uv run scripts/evaluate.py --labels data/holdout/synthetic.json --images '/(lowres|scan)/' \
        --params min_size_ratio=0.75 --breakdown
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import cv2

from checkboxes import detector

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = REPO_ROOT / "evaluations" / "history.jsonl"

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels


def load_ground_truth(labels_path: Path) -> dict[Path, list[tuple[Box, str, list[str]]]]:
    """Label Studio export -> {image: [(box, label, tags), ...]}, first annotation per task.

    Tags come from the region's meta text (set by the synthetic generator)."""
    gt = {}
    for task in json.loads(labels_path.read_text()):
        image = REPO_ROOT / unquote(task["data"]["image"].split("?d=")[-1])
        annotations = [a for a in task["annotations"] if not a.get("was_cancelled")]
        if not annotations:
            continue
        boxes = []
        for r in annotations[0]["result"]:
            if r.get("type") != "rectanglelabels":
                continue
            v, w, h = r["value"], r["original_width"], r["original_height"]
            x1, y1 = v["x"] * w / 100, v["y"] * h / 100
            box = (x1, y1, x1 + v["width"] * w / 100, y1 + v["height"] * h / 100)
            boxes.append((box, v["rectanglelabels"][0], r.get("meta", {}).get("text", [])))
        gt[image] = boxes
    return gt


def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(preds: list[tuple[Box, str]], gts: list[tuple[Box, str]], min_iou: float) -> list[tuple[int, int, float]]:
    """Greedy, highest IoU first. Returns (pred_idx, gt_idx, iou)."""
    pairs = sorted(
        ((iou(p[0], g[0]), i, j) for i, p in enumerate(preds) for j, g in enumerate(gts)),
        reverse=True,
    )
    used_p, used_g, matches = set(), set(), []
    for score, i, j in pairs:
        if score < min_iou:
            break
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        matches.append((i, j, score))
    return matches


def evaluate_image(
    image: Path,
    gts: list[tuple[Box, str, list[str]]],
    min_iou: float,
    params: detector.DetectorParams = detector.DetectorParams(),
) -> dict:
    img = cv2.imread(str(image))
    if img is None:
        raise ValueError(f"Could not read {image}")
    preds = [(d.bbox, d.label) for d in detector.detect(img, params)]
    matches = match(preds, gts, min_iou)
    matched_p = {i for i, _, _ in matches}
    matched_g = {j for _, j, _ in matches}
    pred_of = {j: i for i, j, _ in matches}

    def fmt(box: Box) -> list[int]:
        return [round(c) for c in box]

    errors = (
        [
            {"type": "false_positive", "bbox": fmt(preds[i][0]), "pred": preds[i][1]}
            for i in range(len(preds))
            if i not in matched_p
        ]
        + [
            {"type": "false_negative", "bbox": fmt(gts[j][0]), "gt": gts[j][1]}
            for j in range(len(gts))
            if j not in matched_g
        ]
        + [
            {"type": "misclassified", "bbox": fmt(gts[j][0]), "pred": preds[i][1], "gt": gts[j][1]}
            for i, j, _ in matches
            if preds[i][1] != gts[j][1]
        ]
    )
    return {
        "image": image.relative_to(REPO_ROOT).as_posix(),
        "gt": len(gts),
        "pred": len(preds),
        "tp": len(matches),
        "correct": sum(preds[i][1] == gts[j][1] for i, j, _ in matches),
        "iou_sum": sum(s for _, _, s in matches),
        "errors": errors,
        # Per GT box: (tags, found, found with the right label).
        "gt_outcomes": [(g[2], j in pred_of, j in pred_of and preds[pred_of[j]][1] == g[1]) for j, g in enumerate(gts)],
    }


def summarize(gt: int, pred: int, tp: int, correct: int, iou_sum: float) -> dict:
    precision = tp / pred if pred else 0.0
    recall = tp / gt if gt else 0.0
    return {
        "gt": gt,
        "pred": pred,
        "tp": tp,
        "fp": pred - tp,
        "fn": gt - tp,
        "misclassified": tp - correct,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "cls_accuracy": correct / tp if tp else 0.0,
        # Found with the right label, out of all GT boxes.
        "e2e_accuracy": correct / gt if gt else 0.0,
        "mean_iou": iou_sum / tp if tp else 0.0,
    }


def git_info() -> dict:
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()

    return {"commit": run("rev-parse", "--short", "HEAD"), "dirty": bool(run("status", "--porcelain"))}


def print_table(rows: list[tuple[str, dict]], title: str = "image") -> None:
    header = (
        f"{title:<22}{'gt':>5}{'pred':>6}{'fp':>5}{'fn':>5}{'miscls':>8}"
        f"{'prec':>8}{'recall':>8}{'f1':>8}{'cls_acc':>9}{'e2e':>8}{'iou':>7}"
    )
    print(header)
    print("-" * len(header))
    for name, m in rows:
        print(
            f"{name:<22}{m['gt']:>5}{m['pred']:>6}{m['fp']:>5}{m['fn']:>5}{m['misclassified']:>8}"
            f"{m['precision']:>8.3f}{m['recall']:>8.3f}{m['f1']:>8.3f}{m['cls_accuracy']:>9.3f}"
            f"{m['e2e_accuracy']:>8.3f}{m['mean_iou']:>7.3f}"
        )


def group_metrics(results: list[dict], pattern: str) -> dict[str, dict]:
    """Aggregate per-image counts by the first capture group of `pattern` in the image path."""
    keys = ("gt", "pred", "tp", "correct", "iou_sum")
    groups = defaultdict(list)
    for r in results:
        m = re.search(pattern, r["image"])
        groups[m.group(1) if m else "(no match)"].append(r)
    return {g: summarize(*(sum(r[k] for r in rs) for k in keys)) for g, rs in sorted(groups.items())}


def tag_metrics(results: list[dict]) -> dict[str, dict]:
    """Recall and end-to-end accuracy per GT tag (FPs have no tag)."""
    counts = defaultdict(lambda: {"gt": 0, "found": 0, "correct": 0})
    for r in results:
        for tags, found, correct in r["gt_outcomes"]:
            for t in tags:
                c = counts[t]
                c["gt"] += 1
                c["found"] += found
                c["correct"] += correct
    return {
        t: {**c, "recall": c["found"] / c["gt"], "e2e_accuracy": c["correct"] / c["gt"]}
        for t, c in sorted(counts.items())
    }


def print_tags(tags: dict[str, dict]) -> None:
    print(f"{'tag':<24}{'gt':>6}{'missed':>8}{'miscls':>8}{'recall':>8}{'e2e':>8}")
    for t, c in tags.items():
        print(
            f"{t:<24}{c['gt']:>6}{c['gt'] - c['found']:>8}{c['found'] - c['correct']:>8}"
            f"{c['recall']:>8.3f}{c['e2e_accuracy']:>8.3f}"
        )


def print_history() -> None:
    if not HISTORY_PATH.exists():
        print(f"No history yet ({HISTORY_PATH.relative_to(REPO_ROOT)})")
        return
    print(f"{'timestamp':<21}{'commit':<10}{'version':<12}{'fp':>4}{'fn':>4}{'miscls':>7}{'f1':>7}{'e2e':>7}  note")
    for line in HISTORY_PATH.read_text().splitlines():
        r = json.loads(line)
        m = r["overall"]
        commit = r["git"]["commit"] + ("*" if r["git"]["dirty"] else "")
        print(
            f"{r['timestamp'][:19]:<21}{commit:<10}{r['model_version']:<12}{m['fp']:>4}{m['fn']:>4}"
            f"{m['misclassified']:>7}{m['f1']:>7.3f}{m['e2e_accuracy']:>7.3f}  {r.get('note', '')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels", type=Path, default=REPO_ROOT / "data" / "labels.json")
    parser.add_argument("--iou", type=float, default=0.5, help="Min IoU for a prediction to match a GT box")
    parser.add_argument("--errors", action="store_true", help="List every FP / FN / misclassified box")
    parser.add_argument(
        "--record", action="store_true", help=f"Append this run to {HISTORY_PATH.relative_to(REPO_ROOT)}"
    )
    parser.add_argument("--note", default="", help="Short description of the change being evaluated")
    parser.add_argument("--history", action="store_true", help="Print recorded runs and exit")
    parser.add_argument(
        "--group-by", metavar="REGEX", help="Print totals grouped by the first capture group in the image path"
    )
    parser.add_argument("--breakdown", action="store_true", help="Print recall per GT region tag")
    parser.add_argument("--images", metavar="REGEX", help="Only evaluate images whose path matches")
    parser.add_argument("--params", metavar="KEY=VALUE[,...]", help="DetectorParams overrides (experiments only)")
    args = parser.parse_args()

    if args.history:
        print_history()
        return
    if args.record and (args.params or args.images):
        parser.error("--record scores the committed detector on the whole label set; drop --params / --images")

    params = detector.parse_params(args.params) if args.params else detector.DetectorParams()
    results = [
        evaluate_image(img, boxes, args.iou, params)
        for img, boxes in load_ground_truth(args.labels).items()
        if not args.images or re.search(args.images, img.as_posix())
    ]
    keys = ("gt", "pred", "tp", "correct", "iou_sum")
    per_image = {r["image"]: summarize(*(r[k] for k in keys)) for r in results}
    overall = summarize(*(sum(r[k] for r in results) for k in keys))

    groups = group_metrics(results, args.group_by) if args.group_by else None
    tags = tag_metrics(results) if args.breakdown else None

    print(f"IoU threshold: {args.iou}\n")
    if groups:
        print_table([*groups.items(), ("OVERALL", overall)], title="group")
    else:
        print_table([(Path(name).name, m) for name, m in per_image.items()] + [("OVERALL", overall)])
    if tags:
        print()
        print_tags(tags)

    if args.errors:
        for r in results:
            for e in r["errors"]:
                print(f"{Path(r['image']).name}: {json.dumps(e)}")

    if args.record:
        git = git_info()
        if git["dirty"]:
            print(
                "\nWarning: working tree has uncommitted changes; the recorded commit won't reproduce this run.",
                file=sys.stderr,
            )
        record = {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "git": git,
            "model_version": detector.MODEL_VERSION,
            "note": args.note,
            "labels": args.labels.resolve().relative_to(REPO_ROOT).as_posix(),
            "iou_threshold": args.iou,
            "params": asdict(detector.DetectorParams()),
            "overall": overall,
            "per_image": per_image,
            "errors": {r["image"]: r["errors"] for r in results if r["errors"]},
        }
        if groups:
            record["group_by"] = args.group_by
            record["groups"] = groups
        if tags:
            record["tags"] = tags
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_PATH.open("a") as f:
            f.write(json.dumps(record) + "\n")
        print(f"\nRecorded to {HISTORY_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
