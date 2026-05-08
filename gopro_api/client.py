"""GoPro cloud listing and download-URL resolution (Quik / api.gopro.com)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from datetime import datetime

import aiohttp
import requests

from gopro_api.api.async_gopro import AsyncGoProAPI
from gopro_api.api.gopro import GoProAPI
from gopro_api.api.models import (
    CapturedRange,
    GoProMediaDownloadResponse,
    GoProMediaSearchItem,
    GoProMediaSearchParams,
    GoProMediaSearchResponse,
)
from gopro_api.exceptions import NoVariationsError
from gopro_api.utils import DownloadAsset, pull_assets_for_response, write_bytes

__all__ = [
    "DownloadAsset",
    "GoProClient",
    "AsyncGoProClient",
    "NoVariationsError",
]


class GoProClient:
    """High-level sync client for GoPro cloud media.

    Wraps ``GoProAPI`` via composition and adds search pagination, asset
    selection, and file download helpers. Use as a context manager; the
    underlying HTTP session is opened and closed for you.
    """

    def __init__(
        self,
        access_token: str | None = None,
        timeout: float = 10.0,
        *,
        page_size: int = 1000,
        max_items: int = 1,
        prefer_height: int | None = None,
        prefer_width: int | None = None,
    ) -> None:
        """Create a sync high-level client.

        Args:
            access_token: ``gp_access_token`` cookie value; defaults to
                ``gopro_api.config.GP_ACCESS_TOKEN``.
            timeout: Per-request HTTP timeout in seconds (API and CDN fetches).
            page_size: Default page size for ``iter_nonempty_search_pages``.
            max_items: Maximum rows returned by ``list_media_items``.
            prefer_height: Preferred video height in pixels for ``get_download_url``.
            prefer_width: Preferred video width in pixels for ``get_download_url``.
        """
        self._api = GoProAPI(access_token=access_token, timeout=timeout)
        self._timeout = timeout
        self.page_size = page_size
        self.max_items = max_items
        self.prefer_height = prefer_height
        self.prefer_width = prefer_width

    def __enter__(self) -> "GoProClient":
        """Enter the underlying ``GoProAPI`` context.

        Returns:
            ``self``.
        """
        self._api.__enter__()
        return self

    def __exit__(self, *exc: object) -> None:
        """Exit the underlying ``GoProAPI`` context."""
        self._api.__exit__(*exc)

    # ------------------------------------------------------------------
    # Low-level proxies (keeps cli.py and other callers unchanged)
    # ------------------------------------------------------------------

    def search(self, params: GoProMediaSearchParams) -> GoProMediaSearchResponse:
        """Run a single media search request.

        Args:
            params: Query parameters for ``GET /media/search``.

        Returns:
            Parsed search response.

        Raises:
            RuntimeError: If used outside ``with GoProClient()``.
            requests.HTTPError: When the HTTP status is not successful.
            pydantic.ValidationError: If the JSON body does not match the model.
        """
        return self._api.search(params)

    def download(self, media_id: str) -> GoProMediaDownloadResponse:
        """Fetch download metadata for one media id.

        Args:
            media_id: Cloud library identifier.

        Returns:
            Parsed download metadata response.

        Raises:
            RuntimeError: If used outside ``with GoProClient()``.
            requests.HTTPError: When the HTTP status is not successful.
            pydantic.ValidationError: If the JSON body does not match the model.
        """
        return self._api.download(media_id)

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    def iter_nonempty_search_pages(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        per_page: int | None = None,
        start_page: int = 1,
    ) -> Iterator[GoProMediaSearchResponse]:
        """Yield search result pages until one returns an empty ``_embedded.media``.

        Args:
            start_date: Capture range start (inclusive semantics per API).
            end_date: Capture range end.
            per_page: Items per page; defaults to ``self.page_size``.
            start_page: First page number to request (1-indexed).

        Yields:
            Each non-empty ``GoProMediaSearchResponse`` page.
        """
        page = start_page
        size = per_page if per_page is not None else self.page_size
        while True:
            params = GoProMediaSearchParams(
                captured_range=CapturedRange(start=start_date, end=end_date),
                page=page,
                per_page=size,
            )
            result = self._api.search(params)
            if not result.embedded.media:
                return
            yield result
            page += 1

    def list_media_items(
        self, start_date: datetime, end_date: datetime
    ) -> list[GoProMediaSearchItem]:
        """Collect media rows across pages up to ``max_items``.

        Args:
            start_date: Capture range start.
            end_date: Capture range end.

        Returns:
            Up to ``self.max_items`` ``GoProMediaSearchItem`` instances.

        Raises:
            RuntimeError: If used outside ``with GoProClient()`` on any underlying
                ``search`` call.
            requests.HTTPError: When any underlying ``search`` HTTP status is not
                successful.
            pydantic.ValidationError: If any underlying ``search`` JSON body does not
                match the model.
        """
        all_media: list[GoProMediaSearchItem] = []
        for page_result in self.iter_nonempty_search_pages(start_date, end_date):
            all_media.extend(page_result.embedded.media)
            if len(all_media) >= self.max_items:
                break
        return all_media[: self.max_items]

    def get_download_url(
        self, media_items: list[GoProMediaSearchItem]
    ) -> dict[str, DownloadAsset]:
        """Resolve download assets for each search row.

        Args:
            media_items: One or more media rows (typically from search).

        Returns:
            Merged mapping of output filename to file or variation metadata.

        Raises:
            NoVariationsError: For video items with no variations.
            RuntimeError: If used outside ``with GoProClient()`` on any underlying
                ``download`` call.
            requests.HTTPError: When any underlying ``download`` HTTP status is not
                successful.
            pydantic.ValidationError: If any underlying ``download`` JSON body does not
                match the model.
        """
        assets: dict[str, DownloadAsset] = {}
        for item in media_items:
            result = self._api.download(item.id)
            assets.update(
                pull_assets_for_response(
                    result,
                    target_height=self.prefer_height,
                    target_width=self.prefer_width,
                )
            )
        return assets

    def download_url_to_path(self, url: str, dest_path: str) -> None:
        """Download a CDN URL to a local path.

        Uses a one-shot ``requests.get`` because CDN hosts differ from
        ``api.gopro.com``.

        Args:
            url: Fully qualified HTTPS URL from download metadata.
            dest_path: Filesystem path for the response body.

        Raises:
            requests.HTTPError: When the HTTP status is not successful.
            OSError: If the destination cannot be written.
        """
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        dest_dir = os.path.dirname(dest_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        with open(dest_path, "wb") as out_file:
            out_file.write(response.content)


class AsyncGoProClient:
    """High-level async client for GoPro cloud media.

    Wraps ``AsyncGoProAPI`` via composition and mirrors ``GoProClient`` using
    ``async/await`` and ``aiohttp``. Use as an async context manager; the
    underlying ``aiohttp.ClientSession`` is opened and closed for you.
    """

    def __init__(
        self,
        access_token: str | None = None,
        timeout: float = 10.0,
        *,
        page_size: int = 1000,
        max_items: int = 1,
        prefer_height: int | None = None,
        prefer_width: int | None = None,
    ) -> None:
        """Create an async high-level client.

        Args:
            access_token: ``gp_access_token`` cookie value; defaults to
                ``gopro_api.config.GP_ACCESS_TOKEN``.
            timeout: Total ``aiohttp`` client timeout in seconds.
            page_size: Default page size for ``iter_nonempty_search_pages``.
            max_items: Maximum rows returned by ``list_media_items``.
            prefer_height: Preferred video height in pixels for ``get_download_url``.
            prefer_width: Preferred video width in pixels for ``get_download_url``.
        """
        self._api = AsyncGoProAPI(access_token=access_token, timeout=timeout)
        self.page_size = page_size
        self.max_items = max_items
        self.prefer_height = prefer_height
        self.prefer_width = prefer_width

    async def __aenter__(self) -> "AsyncGoProClient":
        """Enter the underlying ``AsyncGoProAPI`` context.

        Returns:
            ``self``.
        """
        await self._api.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Exit the underlying ``AsyncGoProAPI`` context."""
        await self._api.__aexit__(*exc)

    # ------------------------------------------------------------------
    # Low-level proxies
    # ------------------------------------------------------------------

    async def search(self, params: GoProMediaSearchParams) -> GoProMediaSearchResponse:
        """Run a single media search request.

        Args:
            params: Query parameters for ``GET /media/search``.

        Returns:
            Parsed search response.

        Raises:
            RuntimeError: If used outside ``async with AsyncGoProClient()``.
            aiohttp.ClientResponseError: When ``raise_for_status`` fails.
            pydantic.ValidationError: If the JSON body does not match the model.
        """
        return await self._api.search(params)

    async def download(self, media_id: str) -> GoProMediaDownloadResponse:
        """Fetch download metadata for one media id.

        Args:
            media_id: Cloud library identifier.

        Returns:
            Parsed download metadata response.

        Raises:
            RuntimeError: If used outside ``async with AsyncGoProClient()``.
            aiohttp.ClientResponseError: When ``raise_for_status`` fails.
            pydantic.ValidationError: If the JSON body does not match the model.
        """
        return await self._api.download(media_id)

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    async def iter_nonempty_search_pages(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        per_page: int | None = None,
        start_page: int = 1,
    ) -> AsyncIterator[GoProMediaSearchResponse]:
        """Yield search pages until one returns an empty ``_embedded.media``.

        Args:
            start_date: Capture range start (inclusive semantics per API).
            end_date: Capture range end.
            per_page: Items per page; defaults to ``self.page_size``.
            start_page: First page number to request (1-indexed).

        Yields:
            Each non-empty ``GoProMediaSearchResponse`` page.
        """
        page = start_page
        size = per_page if per_page is not None else self.page_size
        while True:
            params = GoProMediaSearchParams(
                captured_range=CapturedRange(start=start_date, end=end_date),
                page=page,
                per_page=size,
            )
            result = await self._api.search(params)
            if not result.embedded.media:
                return
            yield result
            page += 1

    async def list_media_items(
        self, start_date: datetime, end_date: datetime
    ) -> list[GoProMediaSearchItem]:
        """Collect media rows across pages up to ``max_items``.

        Args:
            start_date: Capture range start.
            end_date: Capture range end.

        Returns:
            Up to ``self.max_items`` ``GoProMediaSearchItem`` instances.

        Raises:
            RuntimeError: If used outside ``async with AsyncGoProClient()`` on any
                underlying ``search`` call.
            aiohttp.ClientResponseError: When any underlying ``search`` raises for
                status.
            pydantic.ValidationError: If any underlying ``search`` JSON body does not
                match the model.
        """
        all_media: list[GoProMediaSearchItem] = []
        async for page_result in self.iter_nonempty_search_pages(start_date, end_date):
            all_media.extend(page_result.embedded.media)
            if len(all_media) >= self.max_items:
                break
        return all_media[: self.max_items]

    async def get_download_url(
        self, media_items: list[GoProMediaSearchItem]
    ) -> dict[str, DownloadAsset]:
        """Resolve download assets for each search row in parallel.

        Args:
            media_items: One or more media rows (typically from search).

        Returns:
            Merged mapping of output filename to file or variation metadata.

        Raises:
            NoVariationsError: For video items with no variations.
            RuntimeError: If used outside ``async with AsyncGoProClient()`` on any
                underlying ``download`` call.
            aiohttp.ClientResponseError: When any underlying ``download`` raises for
                status.
            pydantic.ValidationError: If any underlying ``download`` JSON body does not
                match the model.
        """
        results: list[GoProMediaDownloadResponse] = await asyncio.gather(
            *(self._api.download(item.id) for item in media_items)
        )
        assets: dict[str, DownloadAsset] = {}
        for result in results:
            assets.update(
                pull_assets_for_response(
                    result,
                    target_height=self.prefer_height,
                    target_width=self.prefer_width,
                )
            )
        return assets

    async def download_url_to_path(self, url: str, dest_path: str) -> None:
        """Download a CDN URL to a local path.

        Opens a dedicated ``aiohttp.ClientSession`` without ``base_url`` so CDN
        hosts work. The body is read fully into memory, then written via
        ``asyncio.to_thread``.

        Args:
            url: Fully qualified HTTPS URL from download metadata.
            dest_path: Filesystem path for the response body.

        Raises:
            aiohttp.ClientResponseError: When ``raise_for_status`` fails.
            OSError: If the destination cannot be written.
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                data = await resp.read()

        dest_dir = os.path.dirname(dest_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        await asyncio.to_thread(write_bytes, dest_path, data)
