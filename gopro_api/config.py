"""Environment-backed settings loaded from the environment and ``.env``."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from the process environment and optional ``.env`` file.

    Values are read at instantiation; use ``gopro_api.config.settings`` or the
    ``GP_ACCESS_TOKEN`` alias for the token used by API clients and the CLI.

    Attributes:
        gp_access_token: GoPro cloud cookie value. Environment variable:
            ``GP_ACCESS_TOKEN``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    gp_access_token: str | None = None


settings = Settings()

# Backward-compatible module-level alias used throughout the package.
GP_ACCESS_TOKEN = settings.gp_access_token
