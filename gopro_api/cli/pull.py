"""Pull command: PullPrinter class, async runner, and Typer callback."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import typer
from rich.console import Console

from gopro_api.client import AsyncGoProClient
from gopro_api.exceptions import NoVariationsError
from gopro_api.utils import DownloadAsset, pull_assets_for_response

from .app import app
from ._common import _build_basic_table, _require_token, _validate_positive_px, _yes_no


class PullPrinter:
    """Handles Rich table and TSV rendering for the pull command."""

    HEADERS = ["filename", "dim", "available", "url"]

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console(soft_wrap=True)

    def summary_cells(self, filename: str, asset: DownloadAsset) -> list[str]:
        return [
            filename,
            f"{asset.width}x{asset.height}",
            _yes_no(asset.available),
            asset.url,
        ]

    def print_rich(self, assets: dict[str, DownloadAsset], destination: str) -> None:
        typer.secho(
            f"Pulling {len(assets)} file(s) to {destination}",
            bold=True,
        )
        table = _build_basic_table(self.HEADERS)
        for filename, asset in assets.items():
            table.add_row(*self.summary_cells(filename, asset))
        self._console.print(table)

    def print_tsv(self, assets: dict[str, DownloadAsset], destination: str) -> None:
        typer.echo(f"# destination: {destination}")
        typer.echo("\t".join(self.HEADERS))
        for filename, asset in assets.items():
            typer.echo("\t".join(self.summary_cells(filename, asset)))


async def _run_pull(
    *,
    timeout: float,
    media_id: str,
    destination: str,
    height: Optional[int],
    width: Optional[int],
    tsv: bool,
) -> None:
    _require_token()
    printer = PullPrinter()
    async with AsyncGoProClient(timeout=timeout) as client:
        meta = await client.download(media_id)
        try:
            assets = pull_assets_for_response(
                meta,
                target_height=height,
                target_width=width,
            )
        except NoVariationsError as exc:
            typer.secho(f"error: {exc}", fg=typer.colors.RED, bold=True, err=True)
            raise typer.Exit(2) from exc

        if tsv:
            printer.print_tsv(assets, destination)
        else:
            printer.print_rich(assets, destination)

        os.makedirs(destination, exist_ok=True)
        await asyncio.gather(
            *(
                client.download_url_to_path(
                    asset.url,
                    os.path.join(destination, filename),
                )
                for filename, asset in assets.items()
            )
        )

    typer.secho(f"Done. ({len(assets)} file(s))", fg=typer.colors.GREEN)


@app.command(
    "pull",
    help=(
        "Download files from a media id (prints a Rich summary by default; "
        "--tsv for tab-separated)"
    ),
)
def pull_command(
    ctx: typer.Context,
    media_id: str = typer.Argument(..., help="Media id from search"),
    destination: str = typer.Argument(..., help="Path to save the file"),
    height: Optional[int] = typer.Option(
        None,
        "--height",
        metavar="PX",
        help=(
            "For video: pick the variation whose height is closest to PX "
            "(default: tallest)"
        ),
    ),
    width: Optional[int] = typer.Option(
        None,
        "--width",
        metavar="PX",
        help=(
            "For video: pick the variation whose width is closest to PX "
            "(default: tallest)"
        ),
    ),
    tsv: bool = typer.Option(
        False,
        "--tsv",
        help="Print tab-separated summary instead of the Rich table",
    ),
) -> None:
    """Download all resolved files for ``media_id`` into ``destination``."""
    height = _validate_positive_px(height, "--height")
    width = _validate_positive_px(width, "--width")
    asyncio.run(
        _run_pull(
            timeout=ctx.obj["timeout"],
            media_id=media_id,
            destination=destination,
            height=height,
            width=width,
            tsv=tsv,
        ),
    )
