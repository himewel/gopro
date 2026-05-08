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

        Args:
            access_token: ``gp_access_token`` cookie value; defaults to
                ``gopro_api.config.GP_ACCESS_TOKEN``.
            timeout: Per-request timeout in seconds passed to ``requests``.
        """
        self.access_token = access_token or GP_ACCESS_TOKEN
        self._timeout = timeout
        self._session: requests.Session | None = None

    @property
    def base_url(self) -> str:
        """HTTPS origin for API requests.

        Returns:
            Always ``https://api.gopro.com``.
        """
        return "https://api.gopro.com"

    def get_headers(self, accept: str) -> dict[str, str]:
        """Build headers for a JSON API request.

        Args:
            accept: Full ``Accept`` header value (vendor MIME type + version).

        Returns:
            Mapping with ``Cookie`` (token) and ``Accept``.
        """
        return {
            "Cookie": "gp_access_token=" + self.access_token,
            "Accept": accept,
        }

    def __enter__(self) -> "GoProAPI":
        """Open a ``requests.Session`` for the duration of the ``with`` block.

        Returns:
            ``self`` for use inside the ``with`` body.
        """
        self._session = requests.Session()
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the session and clear internal state.

        Args:
            *exc: Exception info from the interpreter (ignored).
        """
        if self._session is not None:
            self._session.close()
            self._session = None

    def _session_or_raise(self) -> requests.Session:
        """Return the active ``requests.Session``.

        Returns:
            The session opened in ``__enter__``.

        Raises:
            RuntimeError: If called before ``__enter__`` or after ``__exit__``.
        """
        if self._session is None:
            msg = "Use GoProAPI as a context manager: with GoProAPI() as api: ..."
            raise RuntimeError(msg)
        return self._session

    def download(self, media_id: str) -> GoProMediaDownloadResponse:
        """Return download metadata and CDN URLs for one media item.

        Calls ``GET /media/{media_id}/download`` with the GoPro media JSON
        vendor MIME type.

        Args:
            media_id: Cloud library identifier for the media item.

        Returns:
            Parsed response (filenames, variations, embedded files, CDN URLs).

        Raises:
            RuntimeError: If used outside ``with GoProAPI() as api``.
            requests.HTTPError: When the response status is not successful.
            pydantic.ValidationError: If the JSON body does not match the model.
        """
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
        """Search media in the cloud library with structured query parameters.

        Calls ``GET /media/search``; ``params.model_dump()`` is sent as the query
        string after serialization.

        Args:
            params: Search filters (capture range, pagination, fields, etc.).

        Returns:
            Paginated search results and embedded media rows.

        Raises:
            RuntimeError: If used outside ``with GoProAPI() as api``.
            requests.HTTPError: When the response status is not successful.
            pydantic.ValidationError: If the JSON body does not match the model.
        """
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
