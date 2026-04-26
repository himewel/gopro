"""Exceptions for gopro-api."""

from __future__ import annotations

__all__ = ["NoVariationsError"]


class NoVariationsError(Exception):
    """Raised when no video variations are available for a media item."""
