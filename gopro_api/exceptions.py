"""Exceptions for gopro-api."""

from __future__ import annotations

__all__ = ["NoVariationsError"]


class NoVariationsError(Exception):
    """Raised when video download metadata lists zero renditions.

    Typical cause: ``_embedded.variations`` is empty while the media filename
    is treated as video (for example ``.mp4``).
    """
