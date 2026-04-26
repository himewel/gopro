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
    selection, and file download helpers.  Use as a context manager; the
    underlying HTTP session is opened and closed for you.

    Args:
        access_token: Cookie value; defaults to ``GP_ACCESS_TOKEN``.
        timeout: Per-request HTTP timeout in seconds.
        page_size: Items per search page for ``iter_nonempty_search_pages``.
        max_items: Upper bound on items returned from ``list_media_items``.
        prefer_height: Target height in pixels for variation scoring.
        prefer_width: Target width in pixels for variation scoring.
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
        self._api = GoProAPI(access_token=access_token, timeout=timeout)
        self._timeout = timeout
        self.page_size = page_size
        self.max_items = max_items
        self.prefer_height = prefer_height
        self.prefer_width = prefer_width

    def __enter__(self) -> "GoProClient":
        self._api.__enter__()
        return self

    def __exit__(self, *exc: object) -> None:
        self._api.__exit__(*exc)

    # ------------------------------------------------------------------
    # Low-level proxies (keeps cli.py and other callers unchanged)
    # ------------------------------------------------------------------

    def search(self, params: GoProMediaSearchParams) -> GoProMediaSearchResponse:
        """Proxy to ``GoProAPI.search``."""
        return self._api.search(params)

    def download(self, media_id: str) -> GoProMediaDownloadResponse:
        """Proxy to ``GoProAPI.download``."""
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
            start_date: Capture range start.
            end_date: Capture range end.
            per_page: Items per page; defaults to ``self.page_size``.
            start_page: First page number to request (1-indexed).
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
        """Return up to ``max_items`` media items in the capture window."""
        all_media: list[GoProMediaSearchItem] = []
        for page_result in self.iter_nonempty_search_pages(start_date, end_date):
            all_media.extend(page_result.embedded.media)
            if len(all_media) >= self.max_items:
                break
        return all_media[: self.max_items]

    def get_download_url(
        self, media_items: list[GoProMediaSearchItem]
    ) -> dict[str, DownloadAsset]:
        """Resolve download assets for each item in ``media_items``.

        Returns a merged ``filename → asset`` mapping for all items.
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
        """Fetch ``url`` and write bytes to ``dest_path``.

        CDN URLs are on a different host from ``api.gopro.com`` so a dedicated
        one-shot ``requests.get`` is used rather than the API session.
        """
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        dest_dir = os.path.dirname(dest_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        with open(dest_path, "wb") as fh:
            fh.write(response.content)


class AsyncGoProClient:
    """High-level async client for GoPro cloud media.

    Wraps ``AsyncGoProAPI`` via composition and mirrors ``GoProClient`` using
    ``async/await`` and ``aiohttp`` for all I/O.  Use as an async context
    manager; the underlying ``aiohttp.ClientSession`` is opened and closed
    for you.

    Args:
        access_token: Cookie value; defaults to ``GP_ACCESS_TOKEN``.
        timeout: Total ``aiohttp`` client timeout in seconds.
        page_size: Items per search page.
        max_items: Upper bound on items returned from ``list_media_items``.
        prefer_height: Target height in pixels for variation scoring.
        prefer_width: Target width in pixels for variation scoring.
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
        self._api = AsyncGoProAPI(access_token=access_token, timeout=timeout)
        self.page_size = page_size
        self.max_items = max_items
        self.prefer_height = prefer_height
        self.prefer_width = prefer_width

    async def __aenter__(self) -> "AsyncGoProClient":
        await self._api.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._api.__aexit__(*exc)

    # ------------------------------------------------------------------
    # Low-level proxies
    # ------------------------------------------------------------------

    async def search(self, params: GoProMediaSearchParams) -> GoProMediaSearchResponse:
        """Proxy to ``AsyncGoProAPI.search``."""
        return await self._api.search(params)

    async def download(self, media_id: str) -> GoProMediaDownloadResponse:
        """Proxy to ``AsyncGoProAPI.download``."""
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
            start_date: Capture range start.
            end_date: Capture range end.
            per_page: Items per page; defaults to ``self.page_size``.
            start_page: First page number to request (1-indexed).
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
        """Return up to ``max_items`` media items in the capture window."""
        all_media: list[GoProMediaSearchItem] = []
        async for page_result in self.iter_nonempty_search_pages(start_date, end_date):
            all_media.extend(page_result.embedded.media)
            if len(all_media) >= self.max_items:
                break
        return all_media[: self.max_items]

    async def get_download_url(
        self, media_items: list[GoProMediaSearchItem]
    ) -> dict[str, DownloadAsset]:
        """Resolve download assets for all items in parallel via ``asyncio.gather``.

        Returns a merged ``filename → asset`` mapping for all items.
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
        """Fetch ``url`` and write bytes to ``dest_path``.

        Always opens a fresh ``aiohttp.ClientSession`` (without a base URL) so
        that CDN URLs on domains other than ``api.gopro.com`` are handled
        correctly.  The full response body is buffered in memory before the
        file write is offloaded to a thread via ``asyncio.to_thread``, which is
        acceptable for typical GoPro file sizes.
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                data = await resp.read()

        dest_dir = os.path.dirname(dest_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        await asyncio.to_thread(write_bytes, dest_path, data)
