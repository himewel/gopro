"""Info command: InfoPrinter class, async runner, and Typer callback."""

from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console

from gopro_api.api.models import (
    GoProMediaDownloadFile,
    GoProMediaDownloadResponse,
    GoProMediaDownloadSidecarFile,
    GoProMediaDownloadVariation,
)
from gopro_api.client import AsyncGoProClient
from gopro_api.utils import is_video_filename

from .app import app
from ._common import _build_basic_table, _require_token, _yes_no


class InfoPrinter:
    """Handles Rich table and TSV rendering for the info command."""

    VARIATION_HEADERS = ["idx", "label", "quality", "type", "dim", "available", "url"]
    FILE_HEADERS = ["idx", "item", "camera", "dim", "available", "url"]
    SIDECAR_HEADERS = ["idx", "label", "type", "fps", "available", "url"]

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console(soft_wrap=True)

    def variation_cells(self, idx: int, v: GoProMediaDownloadVariation) -> list[str]:
        return [
            str(idx),
            v.label,
            v.quality,
            v.type,
            f"{v.width}x{v.height}",
            _yes_no(v.available),
            v.url,
        ]

    def file_cells(self, idx: int, f: GoProMediaDownloadFile) -> list[str]:
        return [
            str(idx),
            str(f.item_number),
            f.camera_position,
            f"{f.width}x{f.height}",
            _yes_no(f.available),
            f.url,
        ]

    def sidecar_cells(self, idx: int, s: GoProMediaDownloadSidecarFile) -> list[str]:
        return [
            str(idx),
            s.label,
            s.type,
            str(s.fps),
            _yes_no(s.available),
            s.url,
        ]

    def print_rich(self, meta: GoProMediaDownloadResponse) -> None:
        typer.secho(meta.filename, bold=True)
        if is_video_filename(meta.filename):
            table = _build_basic_table(self.VARIATION_HEADERS)
            for idx, v in enumerate(meta.embedded.variations):
                table.add_row(*self.variation_cells(idx, v))
        else:
            table = _build_basic_table(self.FILE_HEADERS)
            for idx, f in enumerate(meta.embedded.files):
                table.add_row(*self.file_cells(idx, f))
        self._console.print(table)
        if meta.embedded.sidecar_files:
            typer.secho("sidecars", bold=True)
            sidecars = _build_basic_table(self.SIDECAR_HEADERS)
            for idx, s in enumerate(meta.embedded.sidecar_files):
                sidecars.add_row(*self.sidecar_cells(idx, s))
            self._console.print(sidecars)

    def print_tsv(self, meta: GoProMediaDownloadResponse) -> None:
        typer.echo(f"# filename: {meta.filename}")
        if is_video_filename(meta.filename):
            typer.echo("\t".join(self.VARIATION_HEADERS))
            for idx, v in enumerate(meta.embedded.variations):
                typer.echo("\t".join(self.variation_cells(idx, v)))
        else:
            typer.echo("\t".join(self.FILE_HEADERS))
            for idx, f in enumerate(meta.embedded.files):
                typer.echo("\t".join(self.file_cells(idx, f)))
        if meta.embedded.sidecar_files:
            typer.echo("# sidecars")
            typer.echo("\t".join(self.SIDECAR_HEADERS))
            for idx, s in enumerate(meta.embedded.sidecar_files):
                typer.echo("\t".join(self.sidecar_cells(idx, s)))


async def _run_info(
    *,
    timeout: float,
    media_id: str,
    json_out: bool,
    tsv: bool,
) -> None:
    _require_token()
    async with AsyncGoProClient(timeout=timeout) as client:
        meta = await client.download(media_id)
    if json_out:
        typer.echo(
            json.dumps(
                meta.model_dump(by_alias=True, mode="json"),
                indent=2,
            ),
        )
    elif tsv:
        InfoPrinter().print_tsv(meta)
    else:
        InfoPrinter().print_rich(meta)


@app.command(
    "info",
    help=(
        "Show download metadata for one media id "
        "(Rich table by default; --tsv for tab-separated; --json for raw API)"
    ),
)
def info_command(
    ctx: typer.Context,
    media_id: str = typer.Argument(..., help="Media id from search"),
    tsv: bool = typer.Option(
        False,
        "--tsv",
        help="Print tab-separated values for scripting",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print full API JSON"),
) -> None:
    """Fetch and display download metadata for ``media_id``."""
    asyncio.run(
        _run_info(
            timeout=ctx.obj["timeout"],
            media_id=media_id,
            json_out=json_out,
            tsv=tsv,
        ),
    )
