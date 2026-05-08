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
    """Return whether the filename looks like MP4 video.

    Args:
        filename: Basename or path ending (extension is checked case-insensitively).

    Returns:
        ``True`` if the suffix is ``.mp4``.
    """
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

    Returns:
        The selected ``GoProMediaDownloadVariation``.

    Raises:
        NoVariationsError: If ``variations`` is empty.
    """
    if not variations:
        raise NoVariationsError("API returned no video variations for this media id.")
    if target_height is None and target_width is None:
        return max(variations, key=lambda variation: variation.height)

    def score(variation: GoProMediaDownloadVariation) -> int:
        height_delta_sq = (
            0 if target_height is None else (variation.height - target_height) ** 2
        )
        width_delta_sq = (
            0 if target_width is None else (variation.width - target_width) ** 2
        )
        return height_delta_sq + width_delta_sq

    best_score = min(score(variation) for variation in variations)
    tied = [variation for variation in variations if score(variation) == best_score]
    return max(tied, key=lambda variation: (variation.height, variation.width))


def get_file_name(root_name: str, item_number: int) -> str:
    """Build a part filename by inserting a zero-padded index before the extension.

    Example: ``get_file_name("GX010001.MP4", 2)`` → ``"GX010001002.MP4"``.

    Args:
        root_name: Original media filename including extension.
        item_number: Non-negative part index (three-digit zero padding).

    Returns:
        Derived filename string.
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

    Args:
        result: Parsed download-metadata response for one media id.
        target_height: Optional preferred video height for variation scoring.
        target_width: Optional preferred video width for variation scoring.

    Returns:
        Mapping of local filename to downloadable file or variation row.

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
    """Write binary data to a path (blocking I/O).

    Args:
        path: Destination file path.
        data: Raw bytes to persist.

    Raises:
        OSError: If the file cannot be opened or written.
    """
    with open(path, "wb") as out_file:
        out_file.write(data)
