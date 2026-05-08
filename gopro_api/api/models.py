"""Pydantic models for GoPro cloud media search and download JSON."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_serializer


DEFAULT_PROCESSING_STATES: List[str] = [
    "rendering",
    "pretranscoding",
    "transcoding",
    "stabilizing",
    "ready",
    "failure",
]
DEFAULT_FIELDS: List[str] = [
    "id",
    "type",
    "filename",
    "file_extension",
    "captured_at",
    "file_size",
    "item_count",
    "width",
    "height",
]
DEFAULT_MEDIA_TYPES: List[str] = [
    "Burst",
    "BurstVideo",
    "Continuous",
    "LoopedVideo",
    "Photo",
    "TimeLapse",
    "TimeLapseVideo",
    "Video",
    "MultiClipEdit",
    "Edit",
]


class CapturedRange(BaseModel):
    """Inclusive capture date window used in search queries.

    Serialized to a single ``captured_range`` query string with fixed
    ``T00:00:00.000Z`` suffixes, as required by the cloud API.

    Attributes:
        start: Range start (date portion used in the wire format).
        end: Range end (date portion used in the wire format).
    """

    start: datetime
    end: datetime

    @model_serializer
    def _serialize_captured_range(self) -> str:
        """Serialize this range for the ``captured_range`` query parameter.

        Returns:
            Comma-separated ISO date pair with ``Z`` UTC suffixes.
        """
        return (
            f"{self.start.isoformat()}T00:00:00.000Z,"
            f"{self.end.isoformat()}T00:00:00.000Z"
        )


class GoProMediaSearchParams(BaseModel):
    """Query body for ``GET /media/search``.

    List fields are serialized to comma-separated strings in the query string.
    Defaults match typical Quik / cloud library expectations.

    Attributes:
        processing_states: Allowed processing states filter.
        fields: Columns to request for each media row.
        type: Media type filter.
        captured_range: Capture time window.
        page: 1-based page index.
        per_page: Page size.
    """

    processing_states: List[str] = DEFAULT_PROCESSING_STATES
    fields: List[str] = DEFAULT_FIELDS
    type: List[str] = DEFAULT_MEDIA_TYPES
    captured_range: CapturedRange = CapturedRange(
        start=datetime.min,
        end=datetime.max,
    )
    page: int = 1
    per_page: int = 1

    @field_serializer("processing_states", "fields", "type")
    def _serialize_csv_lists(self, value: List[str]) -> str:
        """Join list fields into one comma-separated string for the query.

        Args:
            value: String sequence to join.

        Returns:
            Single CSV fragment suitable for the query string.
        """
        return ",".join(value)


class GoProMediaSearchItem(BaseModel):
    """One media row from ``GET /media/search``.

    Unknown JSON keys are retained via ``extra="allow"`` for forward compatibility.

    Attributes:
        id: Cloud media identifier (used with ``download``).
        type: Media kind (video, photo, burst, etc.).
        captured_at: Capture timestamp when provided.
        filename: Primary filename when provided.
        file_extension: Extension without dot when provided.
        file_size: Size in bytes when provided.
        item_count: Parts in a burst/set when provided.
        width: Pixel width when provided.
        height: Pixel height when provided.
        gopro_user_id: Owning user id from the API.
        source_gumi: Source identifier from the API.
        source_mgumi: Optional secondary source id.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    type: Optional[str] = None
    captured_at: Optional[datetime] = None
    filename: Optional[str] = None
    file_extension: Optional[str] = None
    file_size: Optional[int] = None
    item_count: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    gopro_user_id: str
    source_gumi: str
    source_mgumi: Optional[str]


class GoProMediaSearchEmbedded(BaseModel):
    """``_embedded`` block for a search response (``_embedded`` in JSON).

    Attributes:
        media: Result rows for the current page.
        errors: Non-fatal API warnings or error objects.
    """

    model_config = ConfigDict(extra="allow")

    media: List[GoProMediaSearchItem]
    errors: List[Any] = []


class GoProMediaSearchPages(BaseModel):
    """Pagination metadata (``_pages`` in JSON).

    Attributes:
        current_page: Active 1-based page.
        per_page: Requested page size.
        total_items: Total rows matching the query.
        total_pages: Total pages available.
    """

    current_page: int
    per_page: int
    total_items: int
    total_pages: int


class GoProMediaSearchResponse(BaseModel):
    """Top-level JSON body from ``GET /media/search``.

    Attributes:
        embedded: Media rows and errors (alias ``_embedded``).
        pages: Pagination (alias ``_pages``).
    """

    model_config = ConfigDict(populate_by_name=True)

    embedded: GoProMediaSearchEmbedded = Field(alias="_embedded")
    pages: GoProMediaSearchPages = Field(alias="_pages")


class GoProMediaDownloadFile(BaseModel):
    """Non-video or burst member file with a CDN URL.

    Attributes:
        url: HTTPS URL for this part.
        head: API-specific head token.
        camera_position: Camera slot label from the API.
        item_number: Part index within the set.
        width: Pixel width.
        height: Pixel height.
        orientation: EXIF-style orientation integer.
        available: Whether the asset is listed as fetchable.
    """

    model_config = ConfigDict(extra="allow")

    url: str
    head: str
    camera_position: str
    item_number: int
    width: int
    height: int
    orientation: int
    available: bool


class GoProMediaDownloadVariation(BaseModel):
    """Video rendition (resolution / quality) with a CDN URL.

    Attributes:
        url: HTTPS URL for this rendition.
        head: API-specific head token.
        width: Pixel width.
        height: Pixel height.
        label: Human-readable label from the API.
        type: Rendition type string from the API.
        quality: Quality bucket from the API.
        available: Whether the rendition is listed as fetchable.
    """

    model_config = ConfigDict(extra="allow")

    url: str
    head: str
    width: int
    height: int
    label: str
    type: str
    quality: str
    available: bool


class GoProMediaDownloadSidecarFile(BaseModel):
    """Auxiliary asset such as a ZIP sidecar.

    Attributes:
        url: HTTPS URL when available.
        head: API-specific head token.
        label: Display label.
        type: Asset type string from the API.
        fps: Frames per second when applicable.
        available: Whether the asset is listed as fetchable.
    """

    model_config = ConfigDict(extra="allow")

    url: str
    head: str
    label: str
    type: str
    fps: int
    available: bool


class GoProMediaDownloadEmbedded(BaseModel):
    """Payload nested under ``_embedded`` for download metadata.

    Attributes:
        files: Non-video / multi-part files.
        variations: Video renditions.
        sprites: Sprite sheet metadata (structure varies).
        sidecar_files: Additional downloadable bundles.
    """

    model_config = ConfigDict(extra="allow")

    files: List[GoProMediaDownloadFile]
    variations: List[GoProMediaDownloadVariation]
    sprites: List[Any]
    sidecar_files: List[GoProMediaDownloadSidecarFile]


class GoProMediaDownloadResponse(BaseModel):
    """Top-level JSON body from ``GET /media/{id}/download``.

    Attributes:
        filename: Primary media filename from the API.
        embedded: Nested files, variations, and sidecars (alias ``_embedded``).
    """

    model_config = ConfigDict(populate_by_name=True)

    filename: str
    embedded: GoProMediaDownloadEmbedded = Field(alias="_embedded")
