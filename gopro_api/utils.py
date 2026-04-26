"""Pure helper functions for GoPro media selection, naming, and I/O."""

from __future__ import annotations

from gopro_api.api.models import (
    GoProMediaDownloadFile,
    GoProMediaDownloadResponse,
    GoProMediaDownloadVariation,
)
from gopro_api.exceptions import NoVariationsError

DownloadAsset = GoProMediaDownloadFile | GoProMediaDownloadVariation

__all__ = [
    "DownloadAsset",
    "is_video_filename",
    "select_video_variation",
    "get_file_name",
    "pull_assets_for_response",
    "write_bytes",
]


def is_video_filename(filename: str) -> bool:
    """Return True if ``filename`` has a ``.mp4`` extension (case-insensitive)."""
    parts = filename.rsplit(".", 1)
    return len(parts) == 2 and parts[1].lower() == "mp4"


def select_video_variation(
    variations: list[GoProMediaDownloadVariation],
    *,
    target_height: int | None = None,
    target_width: int | None = None,
) -> GoProMediaDownloadVariation:
    """Pick the best variation from ``variations``.

    When neither target is set, returns the variation with the greatest height.
    Otherwise scores each candidate by the sum of squared deltas for the requested
    dimensions; ties break toward the larger ``(height, width)``.

    Args:
        variations: Candidate renditions from the API download metadata.
        target_height: Desired height in pixels, or ``None``.
        target_width: Desired width in pixels, or ``None``.

    Raises:
        NoVariationsError: If ``variations`` is empty.
    """
    if not variations:
        raise NoVariationsError("API returned no video variations for this media id.")
    if target_height is None and target_width is None:
        return max(variations, key=lambda v: v.height)

    def score(v: GoProMediaDownloadVariation) -> int:
        dh = 0 if target_height is None else (v.height - target_height) ** 2
        dw = 0 if target_width is None else (v.width - target_width) ** 2
        return dh + dw

    best_score = min(score(v) for v in variations)
    tied = [v for v in variations if score(v) == best_score]
    return max(tied, key=lambda v: (v.height, v.width))


def get_file_name(root_name: str, item_number: int) -> str:
    """Build a part filename by inserting a zero-padded index before the extension.

    Example: ``get_file_name("GX010001.MP4", 2)`` → ``"GX010001002.MP4"``.
    """
    media_name, _, file_format = root_name.rpartition(".")
    return f"{media_name}{str(item_number).zfill(3)}.{file_format}"


def pull_assets_for_response(
    result: GoProMediaDownloadResponse,
    *,
    target_height: int | None = None,
    target_width: int | None = None,
) -> dict[str, DownloadAsset]:
    """Map output filenames to assets to download for ``result``.

    Video (``.mp4``): picks one variation via ``select_video_variation``.
    Non-video: returns every file in ``_embedded.files`` in enumeration order
    (no ``available`` filtering, preserving CLI behaviour for burst sets).

    Raises:
        NoVariationsError: For video media when no variations are present.
    """
    name = result.filename
    if is_video_filename(name):
        chosen = select_video_variation(
            result.embedded.variations,
            target_height=target_height,
            target_width=target_width,
        )
        return {get_file_name(name, 0): chosen}

    return {get_file_name(name, idx): f for idx, f in enumerate(result.embedded.files)}


def write_bytes(path: str, data: bytes) -> None:
    """Write ``data`` to ``path`` (helper for ``asyncio.to_thread``)."""
    with open(path, "wb") as fh:
        fh.write(data)
