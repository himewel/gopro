import requests

from gopro_api.config import GP_ACCESS_TOKEN
from gopro_api.api.models import (
    GoProMediaDownloadResponse,
    GoProMediaSearchParams,
    GoProMediaSearchResponse,
)


class GoProAPI:
    """Synchronous GoPro cloud API client (``requests``)."""

    def __init__(self, access_token: str | None = None, timeout: float = 10.0) -> None:
        self.access_token = access_token or GP_ACCESS_TOKEN
        self._timeout = timeout
        self._session: requests.Session | None = None

    @property
    def base_url(self) -> str:
        return "https://api.gopro.com"

    def get_headers(self, accept: str) -> dict[str, str]:
        return {
            "Cookie": "gp_access_token=" + self.access_token,
            "Accept": accept,
        }

    def __enter__(self) -> "GoProAPI":
        self._session = requests.Session()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def _session_or_raise(self) -> requests.Session:
        if self._session is None:
            msg = "Use GoProAPI as a context manager: with GoProAPI() as api: ..."
            raise RuntimeError(msg)
        return self._session

    def download(self, media_id: str) -> GoProMediaDownloadResponse:
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
