import cv2
import numpy as np
import pytest

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


def test_ignores_label_cell_between_adjacent_boxes() -> None:
    page = blank_page()
    for y in (195, 249):
        cv2.line(page, (0, y), (WIDTH, y), 0, 3)
    draw_box(page, 200, 199, side=46)
    draw_box(page, 300, 199, side=46)
    # The cell between the boxes is closed off by the table lines.
    cv2.putText(page, "Att.", (252, 232), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 2)
    assert [d.bbox[0] for d in detect(page)] == [pytest.approx(200, abs=5), pytest.approx(300, abs=5)]


def test_stroke_crossing_the_box_is_not_a_check() -> None:
    page = blank_page()
    draw_box(page, 300, 200)
    draw_box(page, 600, 200, checked=True)
    cv2.line(page, (200, 300), (420, 180), 0, 4)
    assert [d.is_checked for d in detect(page)] == [False, True]


def test_check_mark_overshooting_the_border_is_still_a_check() -> None:
    page = blank_page()
    draw_box(page, 300, 200)
    cv2.line(page, (310, 225), (318, 250), 0, 4)
    cv2.line(page, (318, 250), (352, 190), 0, 4)
    assert [d.is_checked for d in detect(page)] == [True]


def test_recovers_box_with_broken_corner() -> None:
    page = blank_page()
    for x in (200, 400, 600, 800):
        draw_box(page, x, 200)
    cv2.rectangle(page, (796, 204), (804, 206), 255, -1)
    assert [d.bbox[0] for d in detect(page)] == [pytest.approx(x, abs=5) for x in (200, 400, 600, 800)]
