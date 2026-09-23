from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHECKBOXES_", env_file=".env", extra="ignore")

    max_upload_bytes: int = 20 * 1024 * 1024
    max_pages: int = 20
    # The detector was tuned on ~300 DPI scans.
    pdf_dpi: int = 300
    # Per page; guards against decompression bombs.
    max_pixels: int = 50_000_000
    cors_origins: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
