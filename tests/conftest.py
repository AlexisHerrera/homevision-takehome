from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from checkboxes.api.app import create_app
from checkboxes.api.config import Settings, get_settings

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)
