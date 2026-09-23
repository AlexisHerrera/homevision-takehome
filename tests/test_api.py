import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from checkboxes.api.config import Settings
from checkboxes.detector import MODEL_VERSION

from .conftest import DATA_DIR


def post_file(client: TestClient, content: bytes, filename: str = "doc"):
    return client.post("/detect", files={"file": (filename, content, "application/octet-stream")})


def image_to_pdf(*paths, dpi: int = 300) -> bytes:
    images = [Image.open(p).convert("RGB") for p in paths]
    buf = io.BytesIO()
    images[0].save(buf, format="PDF", resolution=dpi, save_all=True, append_images=images[1:])
    return buf.getvalue()


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_version": MODEL_VERSION}


@pytest.mark.parametrize(("name", "expected"), [("sample_1.png", 119), ("sample_2.jpg", 40)])
def test_detect_image(client: TestClient, name: str, expected: int) -> None:
    response = post_file(client, (DATA_DIR / name).read_bytes(), name)
    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"boxes"}
    assert len(body["boxes"]) == expected
    for box in body["boxes"]:
        x1, y1, x2, y2 = box["bbox"]
        assert 0 <= x1 < x2 and 0 <= y1 < y2
        assert isinstance(box["is_checked"], bool)
        assert box["page"] == 1
    assert any(b["is_checked"] for b in body["boxes"]) and not all(b["is_checked"] for b in body["boxes"])


def test_detect_multipage_pdf(client: TestClient) -> None:
    pdf = image_to_pdf(DATA_DIR / "sample_3.png", DATA_DIR / "sample_4.png")
    response = post_file(client, pdf, "form.pdf")
    assert response.status_code == 200
    body = response.json()
    by_page = [sum(b["page"] == n for b in body["boxes"]) for n in (1, 2)]
    # The source images have 48 and 79; allow for PDF compression.
    assert abs(by_page[0] - 48) <= 2 and abs(by_page[1] - 79) <= 2


def test_rejects_unsupported_file(client: TestClient) -> None:
    response = post_file(client, b"just some text", "notes.txt")
    assert response.status_code == 415


def test_rejects_corrupt_pdf(client: TestClient) -> None:
    response = post_file(client, b"%PDF-1.7 truncated", "broken.pdf")
    assert response.status_code == 415


def test_requires_file(client: TestClient) -> None:
    assert client.post("/detect").status_code == 422


@pytest.mark.parametrize("settings", [Settings(max_upload_bytes=1000)])
def test_rejects_large_upload(client: TestClient) -> None:
    response = post_file(client, (DATA_DIR / "sample_1.png").read_bytes())
    assert response.status_code == 413


@pytest.mark.parametrize("settings", [Settings(max_pages=1)])
def test_rejects_too_many_pages(client: TestClient) -> None:
    pdf = image_to_pdf(DATA_DIR / "sample_3.png", DATA_DIR / "sample_4.png")
    assert post_file(client, pdf).status_code == 413


@pytest.mark.parametrize("settings", [Settings(max_pixels=1_000_000)])
def test_rejects_too_many_pixels(client: TestClient) -> None:
    assert post_file(client, (DATA_DIR / "sample_1.png").read_bytes()).status_code == 413
