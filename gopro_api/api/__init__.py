"""Low-level sync and async HTTP clients for ``https://api.gopro.com``.

Prefer ``gopro_api.client.GoProClient`` / ``AsyncGoProClient`` for pagination
and downloads unless you need direct control over requests.
"""

from .gopro import GoProAPI
from .async_gopro import AsyncGoProAPI

__all__ = ["GoProAPI", "AsyncGoProAPI"]
