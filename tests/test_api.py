import pytest
from fastapi.testclient import TestClient

from checkboxes.api.config import Settings
from checkboxes.detector import MODEL_VERSION

from .conftest import DATA_DIR


def post_file(client: TestClient, content: bytes, filename: str = "doc"):
    return client.post("/detect", files={"file": (filename, content, "application/octet-stream")})


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
        assert box.keys() == {"bbox", "is_checked"}
    assert any(b["is_checked"] for b in body["boxes"]) and not all(b["is_checked"] for b in body["boxes"])


def test_rejects_unsupported_file(client: TestClient) -> None:
    response = post_file(client, b"just some text", "notes.txt")
    assert response.status_code == 415


def test_rejects_pdf(client: TestClient) -> None:
    response = post_file(client, b"%PDF-1.7 ...", "form.pdf")
    assert response.status_code == 415


def test_rejects_corrupt_image(client: TestClient) -> None:
    response = post_file(client, b"\x89PNG\r\n\x1a\n truncated", "broken.png")
    assert response.status_code == 415


def test_requires_file(client: TestClient) -> None:
    assert client.post("/detect").status_code == 422


@pytest.mark.parametrize("settings", [Settings(max_upload_bytes=1000)])
def test_rejects_large_upload(client: TestClient) -> None:
    response = post_file(client, (DATA_DIR / "sample_1.png").read_bytes())
    assert response.status_code == 413


@pytest.mark.parametrize("settings", [Settings(max_pixels=1_000_000)])
def test_rejects_too_many_pixels(client: TestClient) -> None:
    assert post_file(client, (DATA_DIR / "sample_1.png").read_bytes()).status_code == 413
