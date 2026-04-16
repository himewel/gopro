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
DEFAULT_FIELDS: List[str] = ["id", "capturedate"]
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
    """Capture window for search; serialized to the API ``captured_range`` string."""

    start: datetime
    end: datetime

    @model_serializer
    def _serialize_captured_range(self) -> str:
        """Emit the ``captured_range`` query fragment expected by the API."""
        return (
            f"{self.start.isoformat()}T00:00:00.000Z,"
            f"{self.end.isoformat()}T00:00:00.000Z"
        )


class GoProMediaSearchParams(BaseModel):
    """Query parameters for ``GET /media/search`` (lists as comma-separated values)."""

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
        """Join list fields into one comma-separated string for the query."""
        return ",".join(value)


class GoProMediaSearchItem(BaseModel):
    """Single item in ``_embedded.media`` from a media search response."""

    model_config = ConfigDict(extra="allow")

    id: str
    gopro_user_id: str
    source_gumi: str
    source_mgumi: Optional[str]


class GoProMediaSearchEmbedded(BaseModel):
    """``_embedded`` object on a media search response."""

    model_config = ConfigDict(extra="allow")

    media: List[GoProMediaSearchItem]
    errors: List[Any] = []


class GoProMediaSearchPages(BaseModel):
    """Pagination block ``_pages`` on a media search response."""

    current_page: int
    per_page: int
    total_items: int
    total_pages: int


class GoProMediaSearchResponse(BaseModel):
    """Top-level JSON body from ``GET /media/search``."""

    model_config = ConfigDict(populate_by_name=True)

    embedded: GoProMediaSearchEmbedded = Field(alias="_embedded")
    pages: GoProMediaSearchPages = Field(alias="_pages")


class GoProMediaDownloadFile(BaseModel):
    """One downloadable file under ``_embedded.files`` from download metadata."""

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
    """Rendered size / quality variant in ``_embedded.variations``."""

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
    """Sidecar asset (e.g. zip) in ``_embedded.sidecar_files``."""

    model_config = ConfigDict(extra="allow")

    url: str
    head: str
    label: str
    type: str
    fps: int
    available: bool


class GoProMediaDownloadEmbedded(BaseModel):
    """``_embedded`` on a media download metadata response."""

    model_config = ConfigDict(extra="allow")

    files: List[GoProMediaDownloadFile]
    variations: List[GoProMediaDownloadVariation]
    sprites: List[Any]
    sidecar_files: List[GoProMediaDownloadSidecarFile]


class GoProMediaDownloadResponse(BaseModel):
    """Top-level JSON body from ``GET /media/{id}/download``."""

    model_config = ConfigDict(populate_by_name=True)

    filename: str
    embedded: GoProMediaDownloadEmbedded = Field(alias="_embedded")
