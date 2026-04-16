"""Synchronous GoPro cloud API client (``requests``)."""

import requests

from gopro_api.config import GP_ACCESS_TOKEN
from gopro_api.api.models import (
    GoProMediaDownloadResponse,
    GoProMediaSearchParams,
    GoProMediaSearchResponse,
)


class GoProAPI:
    """Synchronous client for ``https://api.gopro.com`` (Quik / cloud library).

    Use as a context manager so a ``requests.Session`` is created and closed
    around ``search`` and ``download``. Pass ``access_token`` to override
    ``gopro_api.config.GP_ACCESS_TOKEN``.
    """

    def __init__(self, access_token: str | None = None, timeout: float = 10.0) -> None:
        """Create a sync client.

        ``access_token``: cookie value; defaults to ``GP_ACCESS_TOKEN``.
        ``timeout``: per-request timeout in seconds.
        """
        self.access_token = access_token or GP_ACCESS_TOKEN
        self._timeout = timeout
        self._session: requests.Session | None = None

    @property
    def base_url(self) -> str:
        """API origin (``https://api.gopro.com``)."""
        return "https://api.gopro.com"

    def get_headers(self, accept: str) -> dict[str, str]:
        """Build ``Cookie`` and ``Accept`` headers for an API call."""
        return {
            "Cookie": "gp_access_token=" + self.access_token,
            "Accept": accept,
        }

    def __enter__(self) -> "GoProAPI":
        """Open a ``requests.Session`` for the duration of the ``with`` block."""
        self._session = requests.Session()
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the session."""
        if self._session is not None:
            self._session.close()
            self._session = None

    def _session_or_raise(self) -> requests.Session:
        """Return the active session or raise if used outside a context manager."""
        if self._session is None:
            msg = "Use GoProAPI as a context manager: with GoProAPI() as api: ..."
            raise RuntimeError(msg)
        return self._session

    def download(self, media_id: str) -> GoProMediaDownloadResponse:
        """``GET /media/{media_id}/download`` — metadata and CDN URLs for files."""
        headers = self.get_headers("application/vnd.gopro.jk.media+json; version=2.0.0")
        session = self._session_or_raise()
        response = session.get(
            f"{self.base_url}/media/{media_id}/download",
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return GoProMediaDownloadResponse.model_validate_json(response.text)

    def search(self, params: GoProMediaSearchParams) -> GoProMediaSearchResponse:
        """``GET /media/search`` using ``params.model_dump()`` as query string."""
        headers = self.get_headers(
            "application/vnd.gopro.jk.media.search+json; version=2.0.0",
        )
        session = self._session_or_raise()
        response = session.get(
            f"{self.base_url}/media/search",
            headers=headers,
            params=params.model_dump(),
            timeout=self._timeout,
        )
        response.raise_for_status()
        return GoProMediaSearchResponse.model_validate_json(response.text)
