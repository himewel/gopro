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
    start: datetime
    end: datetime

    @model_serializer
    def _serialize_captured_range(self) -> str:
        return (
            f"{self.start.isoformat()}T00:00:00.000Z,"
            f"{self.end.isoformat()}T00:00:00.000Z"
        )


class GoProMediaSearchParams(BaseModel):
    processing_states: List[str] = DEFAULT_PROCESSING_STATES
    fields: List[str] = DEFAULT_FIELDS
    type: List[str] = DEFAULT_MEDIA_TYPES
    captured_range: CapturedRange = CapturedRange(start=datetime.min, end=datetime.max)
    page: int = 1
    per_page: int = 1

    @field_serializer("processing_states", "fields", "type")
    def _serialize_csv_lists(self, value: List[str]) -> str:
        return ",".join(value)


class GoProMediaSearchItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    gopro_user_id: str
    source_gumi: str
    source_mgumi: Optional[str]


class GoProMediaSearchEmbedded(BaseModel):
    model_config = ConfigDict(extra="allow")

    media: List[GoProMediaSearchItem]
    errors: List[Any] = []


class GoProMediaSearchPages(BaseModel):
    current_page: int
    per_page: int
    total_items: int
    total_pages: int


class GoProMediaSearchResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    embedded: GoProMediaSearchEmbedded = Field(alias="_embedded")
    pages: GoProMediaSearchPages = Field(alias="_pages")


class GoProMediaDownloadFile(BaseModel):
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
    model_config = ConfigDict(extra="allow")

    url: str
    head: str
    label: str
    type: str
    fps: int
    available: bool


class GoProMediaDownloadEmbedded(BaseModel):
    model_config = ConfigDict(extra="allow")

    files: List[GoProMediaDownloadFile]
    variations: List[GoProMediaDownloadVariation]
    sprites: List[Any]
    sidecar_files: List[GoProMediaDownloadSidecarFile]


class GoProMediaDownloadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    filename: str
    embedded: GoProMediaDownloadEmbedded = Field(alias="_embedded")
