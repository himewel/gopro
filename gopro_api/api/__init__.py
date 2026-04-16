"""Sync and async HTTP clients for api.gopro.com."""

from .gopro import GoProAPI
from .async_gopro import AsyncGoProAPI


__all__ = ["GoProAPI", "AsyncGoProAPI"]
