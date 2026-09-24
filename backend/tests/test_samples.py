"""Accuracy on the provided samples (data/labels.json): detector changes must not regress it."""

import importlib.util
from pathlib import Path

import pytest

from tests.conftest import DATA_DIR

_spec = importlib.util.spec_from_file_location("evaluate", Path(__file__).parent.parent / "scripts" / "evaluate.py")
evaluate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate)

GROUND_TRUTH = evaluate.load_ground_truth(DATA_DIR / "labels.json")
KNOWN_MISCLASSIFIED: dict[str, int] = {}


@pytest.mark.parametrize("image", sorted(GROUND_TRUTH), ids=lambda p: p.name)
def test_sample_accuracy(image: Path) -> None:
    result = evaluate.evaluate_image(image, GROUND_TRUTH[image], min_iou=0.5)
    assert result["tp"] == result["gt"] == result["pred"], result["errors"]
    assert result["tp"] - result["correct"] <= KNOWN_MISCLASSIFIED.get(image.name, 0), result["errors"]
