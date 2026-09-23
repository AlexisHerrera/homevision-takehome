from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHECKBOXES_", env_file=".env", extra="ignore")

    max_upload_bytes: int = 20 * 1024 * 1024
    max_pixels: int = 50_000_000
    cors_origins: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
