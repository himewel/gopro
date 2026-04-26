"""Unofficial Python client for the GoPro cloud API (api.gopro.com)."""

from gopro_api.api.async_gopro import AsyncGoProAPI
from gopro_api.api.gopro import GoProAPI
from gopro_api.api.models import (
    CapturedRange,
    GoProMediaDownloadResponse,
    GoProMediaDownloadVariation,
    GoProMediaSearchParams,
    GoProMediaSearchResponse,
)
from gopro_api.client import AsyncGoProClient, GoProClient
from gopro_api.exceptions import NoVariationsError

__all__ = [
    "GoProAPI",
    "AsyncGoProAPI",
    "GoProClient",
    "AsyncGoProClient",
    "NoVariationsError",
    "GoProMediaSearchParams",
    "GoProMediaDownloadResponse",
    "GoProMediaSearchResponse",
    "GoProMediaDownloadVariation",
    "CapturedRange",
]
