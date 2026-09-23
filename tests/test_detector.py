import cv2
import numpy as np

from checkboxes.detector import detect

WIDTH = 2550  # a letter page at 300 DPI


def blank_page() -> np.ndarray:
    return np.full((600, WIDTH), 255, np.uint8)


def draw_box(page: np.ndarray, x: int, y: int, side: int = 40, checked: bool = False) -> None:
    cv2.rectangle(page, (x, y), (x + side, y + side), 0, 3)
    if checked:
        cv2.line(page, (x + 8, y + 8), (x + side - 8, y + side - 8), 0, 4)
        cv2.line(page, (x + side - 8, y + 8), (x + 8, y + side - 8), 0, 4)


def test_blank_page_has_no_boxes() -> None:
    assert detect(blank_page()) == []


def test_detects_and_classifies_boxes() -> None:
    page = blank_page()
    draw_box(page, 200, 200, checked=True)
    draw_box(page, 600, 200, checked=False)
    detections = detect(page)
    assert [d.is_checked for d in detections] == [True, False]
    x1, y1, x2, y2 = detections[0].bbox
    assert 200 <= x1 < x2 <= 240 and 200 <= y1 < y2 <= 240


def test_accepts_color_images() -> None:
    page = blank_page()
    draw_box(page, 200, 200, checked=True)
    assert len(detect(cv2.cvtColor(page, cv2.COLOR_GRAY2BGR))) == 1
