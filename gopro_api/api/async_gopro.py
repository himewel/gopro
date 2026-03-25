import aiohttp

from gopro_api.config import GP_ACCESS_TOKEN
from gopro_api.api.models import GoProMediaSearchParams, GoProMediaDownloadResponse, GoProMediaSearchResponse


class AsyncGoProAPI:
    def __init__(self, access_token: str | None = None, timeout: float = 10.0) -> None:
        self.access_token = access_token or GP_ACCESS_TOKEN
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    @property
    def base_url(self) -> str:
        return "https://api.gopro.com"

    def get_headers(self, accept: str) -> dict[str, str]:
        return {
            "Cookie": "gp_access_token=" + self.access_token,
            "Accept": accept,
        }

    async def __aenter__(self) -> "AsyncGoProAPI":
        self._session = aiohttp.ClientSession(
            base_url=self.base_url,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _session_or_raise(self) -> aiohttp.ClientSession:
        if self._session is None:
            msg = (
                "Use AsyncGoProAPI as an async context manager: "
                "async with AsyncGoProAPI() as api: ..."
            )
            raise RuntimeError(msg)
        return self._session

    async def download(self, media_id: str) -> GoProMediaDownloadResponse:
        headers = self.get_headers("application/vnd.gopro.jk.media+json; version=2.0.0")
        session = self._session_or_raise()
        async with session.get(f"/media/{media_id}/download", headers=headers) as response:
            response.raise_for_status()
            body = await response.text()
        return GoProMediaDownloadResponse.model_validate_json(body)

    async def search(self, params: GoProMediaSearchParams) -> GoProMediaSearchResponse:
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
