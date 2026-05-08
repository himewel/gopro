"""Asynchronous GoPro cloud API client (``aiohttp``)."""

import aiohttp

from gopro_api.config import GP_ACCESS_TOKEN
from gopro_api.api.models import (
    GoProMediaSearchParams,
    GoProMediaDownloadResponse,
    GoProMediaSearchResponse,
)


class AsyncGoProAPI:
    """Async client for ``https://api.gopro.com`` (Quik / cloud library).

    Use as an async context manager so an ``aiohttp.ClientSession`` is opened
    and closed around ``search`` and ``download``. Pass ``access_token`` to
    override ``gopro_api.config.GP_ACCESS_TOKEN``.
    """

    def __init__(self, access_token: str | None = None, timeout: float = 10.0) -> None:
        """Create an async client.

        Args:
            access_token: ``gp_access_token`` cookie value; defaults to
                ``gopro_api.config.GP_ACCESS_TOKEN``.
            timeout: Total client timeout in seconds for ``aiohttp``.
        """
        self.access_token = access_token or GP_ACCESS_TOKEN
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

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

    async def __aenter__(self) -> "AsyncGoProAPI":
        """Open an ``aiohttp.ClientSession`` for the ``async with`` body.

        Returns:
            ``self`` for use inside the ``async with`` body.
        """
        self._session = aiohttp.ClientSession(
            base_url=self.base_url,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Close the session and clear internal state.

        Args:
            *exc: Exception info from the interpreter (ignored).
        """
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _session_or_raise(self) -> aiohttp.ClientSession:
        """Return the active ``aiohttp.ClientSession``.

        Returns:
            The session opened in ``__aenter__``.

        Raises:
            RuntimeError: If called before ``__aenter__`` or after ``__aexit__``.
        """
        session = self._session
        if session is None:
            msg = (
                "Use AsyncGoProAPI as an async context manager: "
                "async with AsyncGoProAPI() as api: ..."
            )
            raise RuntimeError(msg)
        return session

    async def download(self, media_id: str) -> GoProMediaDownloadResponse:
        """Return download metadata and CDN URLs for one media item.

        Calls ``GET /media/{media_id}/download`` with the GoPro media JSON
        vendor MIME type.

        Args:
            media_id: Cloud library identifier for the media item.

        Returns:
            Parsed response (filenames, variations, embedded files, CDN URLs).

        Raises:
            RuntimeError: If used outside ``async with AsyncGoProAPI() as api``.
            aiohttp.ClientResponseError: When ``raise_for_status`` fails.
            pydantic.ValidationError: If the JSON body does not match the model.
        """
        headers = self.get_headers("application/vnd.gopro.jk.media+json; version=2.0.0")
        session = self._session_or_raise()
        async with session.get(
            f"/media/{media_id}/download",
            headers=headers,
        ) as response:
            response.raise_for_status()
            body = await response.text()
        return GoProMediaDownloadResponse.model_validate_json(body)

    async def search(self, params: GoProMediaSearchParams) -> GoProMediaSearchResponse:
        """Search media in the cloud library with structured query parameters.

        Calls ``GET /media/search``; ``params.model_dump()`` is sent as the query
        string after serialization.

        Args:
            params: Search filters (capture range, pagination, fields, etc.).

        Returns:
            Paginated search results and embedded media rows.

        Raises:
            RuntimeError: If used outside ``async with AsyncGoProAPI() as api``.
            aiohttp.ClientResponseError: When ``raise_for_status`` fails.
            pydantic.ValidationError: If the JSON body does not match the model.
        """
        headers = self.get_headers(
            "application/vnd.gopro.jk.media.search+json; version=2.0.0",
        )
        session = self._session_or_raise()
        async with session.get(
            "/media/search",
            headers=headers,
            params=params.model_dump(),
        ) as response:
            response.raise_for_status()
            body = await response.text()
        return GoProMediaSearchResponse.model_validate_json(body)
