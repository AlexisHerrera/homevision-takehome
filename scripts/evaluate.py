"""Evaluate the checkbox detector against the hand-reviewed ground truth.

A prediction matches a ground-truth box when their IoU is >= --iou (greedy, highest IoU
first). Reports detection metrics (precision / recall / F1), classification accuracy on
matched boxes, and end-to-end accuracy (box found AND label right). With --record, appends
the run to evaluations/history.jsonl so detector changes can be compared over time.

Usage:
    python scripts/evaluate.py [--labels data/labels.json] [--iou 0.5] [--errors]
    python scripts/evaluate.py --record --note "baseline"
    python scripts/evaluate.py --history
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import detect_checkboxes as detector

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = REPO_ROOT / "evaluations" / "history.jsonl"
# Detector module constants recorded with each run, so a result can be tied to its settings.
PARAM_NAMES = ["MIN_SIDE_FRAC", "MAX_SIDE_FRAC", "MIN_ASPECT", "MAX_ASPECT", "MIN_LINE_FRAC", "CHECKED_INK_RATIO"]

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels


def load_ground_truth(labels_path: Path) -> dict[Path, list[tuple[Box, str]]]:
    """Label Studio JSON export -> {image path: [(box, label), ...]} using the first annotation."""
    gt = {}
    for task in json.loads(labels_path.read_text()):
        # e.g. "/data/local-files/?d=data/sample_1.png" -> repo-relative path
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
            boxes.append(((x1, y1, x1 + v["width"] * w / 100, y1 + v["height"] * h / 100), v["rectanglelabels"][0]))
        gt[image] = boxes
    return gt


def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(preds: list[tuple[Box, str]], gts: list[tuple[Box, str]], min_iou: float) -> list[tuple[int, int, float]]:
    """Greedy one-to-one matching, highest IoU first. Returns (pred_idx, gt_idx, iou)."""
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


def evaluate_image(image: Path, gts: list[tuple[Box, str]], min_iou: float) -> dict:
    detections, _ = detector.detect(image)
    preds = [((x, y, x + w, y + h), d["label"]) for d in detections for x, y, w, h in [d["box"]]]
    matches = match(preds, gts, min_iou)
    matched_p = {i for i, _, _ in matches}
    matched_g = {j for _, j, _ in matches}

    def fmt(box: Box) -> list[int]:
        return [round(c) for c in box]

    errors = (
        [{"type": "false_positive", "bbox": fmt(preds[i][0]), "pred": preds[i][1]}
         for i in range(len(preds)) if i not in matched_p]
        + [{"type": "false_negative", "bbox": fmt(gts[j][0]), "gt": gts[j][1]}
           for j in range(len(gts)) if j not in matched_g]
        + [{"type": "misclassified", "bbox": fmt(gts[j][0]), "pred": preds[i][1], "gt": gts[j][1]}
           for i, j, _ in matches if preds[i][1] != gts[j][1]]
    )
    return {
        "image": image.relative_to(REPO_ROOT).as_posix(),
        "gt": len(gts),
        "pred": len(preds),
        "tp": len(matches),
        "correct": sum(preds[i][1] == gts[j][1] for i, j, _ in matches),
        "iou_sum": sum(s for _, _, s in matches),
        "errors": errors,
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
        # Box found with the right label, out of all ground-truth boxes.
        "e2e_accuracy": correct / gt if gt else 0.0,
        "mean_iou": iou_sum / tp if tp else 0.0,
    }


def git_info() -> dict:
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()

    return {"commit": run("rev-parse", "--short", "HEAD"), "dirty": bool(run("status", "--porcelain"))}


def print_table(rows: list[tuple[str, dict]]) -> None:
    header = f"{'image':<22}{'gt':>5}{'pred':>6}{'fp':>5}{'fn':>5}{'miscls':>8}{'prec':>8}{'recall':>8}{'f1':>8}{'cls_acc':>9}{'e2e':>8}{'iou':>7}"
    print(header)
    print("-" * len(header))
    for name, m in rows:
        print(
            f"{name:<22}{m['gt']:>5}{m['pred']:>6}{m['fp']:>5}{m['fn']:>5}{m['misclassified']:>8}"
            f"{m['precision']:>8.3f}{m['recall']:>8.3f}{m['f1']:>8.3f}{m['cls_accuracy']:>9.3f}"
            f"{m['e2e_accuracy']:>8.3f}{m['mean_iou']:>7.3f}"
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
    parser.add_argument("--record", action="store_true", help=f"Append this run to {HISTORY_PATH.relative_to(REPO_ROOT)}")
    parser.add_argument("--note", default="", help="Short description of the change being evaluated")
    parser.add_argument("--history", action="store_true", help="Print recorded runs and exit")
    args = parser.parse_args()

    if args.history:
        print_history()
        return

    results = [evaluate_image(img, boxes, args.iou) for img, boxes in load_ground_truth(args.labels).items()]
    keys = ("gt", "pred", "tp", "correct", "iou_sum")
    per_image = {r["image"]: summarize(*(r[k] for k in keys)) for r in results}
    overall = summarize(*(sum(r[k] for r in results) for k in keys))

    print(f"IoU threshold: {args.iou}\n")
    print_table([(Path(name).name, m) for name, m in per_image.items()] + [("OVERALL", overall)])

    if args.errors:
        for r in results:
            for e in r["errors"]:
                print(f"{Path(r['image']).name}: {json.dumps(e)}")

    if args.record:
        git = git_info()
        if git["dirty"]:
            print("\nWarning: working tree has uncommitted changes; the recorded commit won't reproduce this run.",
                  file=sys.stderr)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git": git,
            "model_version": detector.MODEL_VERSION,
            "note": args.note,
            "labels": args.labels.resolve().relative_to(REPO_ROOT).as_posix(),
            "iou_threshold": args.iou,
            "params": {name: getattr(detector, name) for name in PARAM_NAMES},
            "overall": overall,
            "per_image": per_image,
            "errors": {r["image"]: r["errors"] for r in results if r["errors"]},
        }
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_PATH.open("a") as f:
            f.write(json.dumps(record) + "\n")
        print(f"\nRecorded to {HISTORY_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
