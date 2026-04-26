"""Environment-backed settings loaded from the environment and ``.env``."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings resolved from environment variables and ``.env``.

    Attributes:
        gp_access_token: GoPro cloud access token (env var ``GP_ACCESS_TOKEN``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    gp_access_token: str | None = None


settings = Settings()

# Backward-compatible module-level alias used throughout the package.
GP_ACCESS_TOKEN = settings.gp_access_token
