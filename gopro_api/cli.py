"""Command-line interface for gopro-api."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Optional

import typer
from rich.console import Console
from rich.filesize import decimal as format_decimal_size
from rich.table import Table

from gopro_api.api.models import (
    DEFAULT_FIELDS,
    CapturedRange,
    GoProMediaDownloadFile,
    GoProMediaDownloadResponse,
    GoProMediaDownloadSidecarFile,
    GoProMediaDownloadVariation,
    GoProMediaSearchItem,
    GoProMediaSearchParams,
    GoProMediaSearchResponse,
)
from gopro_api.client import AsyncGoProClient
from gopro_api.config import GP_ACCESS_TOKEN
from gopro_api.exceptions import NoVariationsError
from gopro_api.utils import DownloadAsset, is_video_filename, pull_assets_for_response

app = typer.Typer(
    name="gopro-api",
    help="CLI for the unofficial GoPro cloud API (api.gopro.com).",
    no_args_is_help=True,
)


def _version() -> str:
    try:
        return package_version("gopro-api")
    except PackageNotFoundError:
        return "0.0.0"


def _version_callback(value: Optional[bool]) -> None:
    if value:
        typer.echo(f"gopro-api {_version()}")
        raise typer.Exit()


@app.callback()
def _main_callback(
    ctx: typer.Context,
    timeout: float = typer.Option(
        60.0,
        "--timeout",
        help="HTTP timeout in seconds (default: 60)",
    ),
    show_version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    del show_version  # handled by eager callback (--version exits before commands)
    ctx.ensure_object(dict)
    ctx.obj["timeout"] = timeout


def _parse_dt(raw: str) -> datetime:
    """Parse a CLI date or datetime string.

    Args:
        raw: ``YYYY-MM-DD`` or full ISO 8601 string (``Z`` normalized to offset).

    Returns:
        Parsed naive or aware ``datetime`` as produced by ``fromisoformat``.

    Raises:
        ValueError: If the string is not a valid ISO date/datetime.
    """
    raw = raw.strip()
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return datetime.fromisoformat(raw)
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _validate_positive_px(value: Optional[int], flag: str) -> Optional[int]:
    if value is None:
        return None
    if value <= 0:
        raise typer.BadParameter("must be a positive integer", param_hint=flag)
    return value


def _require_token() -> None:
    """Ensure ``GP_ACCESS_TOKEN`` is configured.

    Raises:
        typer.Exit: With code ``2`` if the token is missing.
    """
    if not GP_ACCESS_TOKEN:
        typer.secho(
            "error: GP_ACCESS_TOKEN is not set. "
            "Add it to your environment or a .env file.",
            fg=typer.colors.RED,
            bold=True,
            err=True,
        )
        raise typer.Exit(2)


def _search_item_cells(item: GoProMediaSearchItem) -> list[str]:
    row = item.model_dump(mode="json")
    return ["" if row.get(c) is None else str(row[c]) for c in DEFAULT_FIELDS]


def _search_item_cells_rich(item: GoProMediaSearchItem) -> list[str]:
    row = item.model_dump(mode="json")
    cells: list[str] = []
    for c in DEFAULT_FIELDS:
        val = row.get(c)
        if val is None:
            cells.append("")
        elif c == "file_size":
            cells.append(format_decimal_size(int(val)))
        else:
            cells.append(str(val))
    return cells


def _format_search_item_plain(item: GoProMediaSearchItem) -> str:
    return "\t".join(_search_item_cells(item))


def _pages_meta_line(page_result: GoProMediaSearchResponse) -> str:
    pages = page_result.pages
    return (
        f"# _pages: current_page={pages.current_page} per_page={pages.per_page} "
        f"total_items={pages.total_items} total_pages={pages.total_pages}"
    )


def _emit_search_embedded_errors(page_result: GoProMediaSearchResponse) -> None:
    if page_result.embedded.errors:
        for err in page_result.embedded.errors:
            typer.secho(
                f"# _embedded.errors: {json.dumps(err, ensure_ascii=False)}",
                fg=typer.colors.YELLOW,
                err=True,
            )


_FIELD_LABELS: dict[str, str] = {
    "type": "media",
    "file_extension": "type",
    "file_size": "size",
    "item_count": "items",
}


def _renamed_field(name: str) -> str:
    return _FIELD_LABELS.get(name, name)


def _rename_media_item_keys(item: dict) -> dict:
    return {_renamed_field(k): v for k, v in item.items()}


def _rename_search_payload(payload: dict) -> dict:
    embedded = payload.get("_embedded")
    if isinstance(embedded, dict):
        media = embedded.get("media")
        if isinstance(media, list):
            embedded["media"] = [
                _rename_media_item_keys(it) if isinstance(it, dict) else it
                for it in media
            ]
    return payload


def _make_search_table() -> Table:
    table = Table(show_header=True, header_style="bold")
    for name in DEFAULT_FIELDS:
        col_kw: dict = {}
        if name == "filename":
            col_kw["overflow"] = "ellipsis"
            col_kw["max_width"] = 40
        elif name == "captured_at":
            col_kw["overflow"] = "ellipsis"
            col_kw["max_width"] = 28
        elif name == "id":
            col_kw["overflow"] = "fold"
        elif name == "type":
            col_kw["overflow"] = "ellipsis"
            col_kw["max_width"] = 14
        table.add_column(_renamed_field(name), **col_kw)
    return table


def _print_search_plain_header() -> None:
    typer.echo("\t".join(_renamed_field(c) for c in DEFAULT_FIELDS))


def _print_search_plain_page(
    page_result: GoProMediaSearchResponse,
    *,
    print_header: bool = True,
) -> None:
    typer.echo(_pages_meta_line(page_result))
    _emit_search_embedded_errors(page_result)
    if print_header:
        _print_search_plain_header()
    for item in page_result.embedded.media:
        typer.echo(_format_search_item_plain(item))


def _print_search_rich_page(page_result: GoProMediaSearchResponse) -> None:
    _emit_search_embedded_errors(page_result)
    typer.echo(_pages_meta_line(page_result))
    table = _make_search_table()
    for item in page_result.embedded.media:
        table.add_row(*_search_item_cells_rich(item))
    Console(soft_wrap=True).print(table)


def _append_search_rich_rows(table: Table, page_result: GoProMediaSearchResponse) -> None:
    _emit_search_embedded_errors(page_result)
    for item in page_result.embedded.media:
        table.add_row(*_search_item_cells_rich(item))


async def _run_search(
    *,
    timeout: float,
    start: str,
    end: str,
    page: int,
    per_page: int,
    all_pages: bool,
    json_out: bool,
    tsv: bool,
) -> None:
    _require_token()
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)

    async with AsyncGoProClient(timeout=timeout) as client:
        if all_pages:
            all_pages_payload: list[dict] = []
            first_plain_page = True
            rich_table: Optional[Table] = None
            last_page: Optional[GoProMediaSearchResponse] = None
            async for page_result in client.iter_nonempty_search_pages(
                start_dt,
                end_dt,
                per_page=per_page,
                start_page=page,
            ):
                last_page = page_result
                if json_out:
                    all_pages_payload.append(
                        _rename_search_payload(
                            page_result.model_dump(by_alias=True, mode="json"),
                        ),
                    )
                elif tsv:
                    _print_search_plain_page(
                        page_result,
                        print_header=first_plain_page,
                    )
                    first_plain_page = False
                else:
                    if rich_table is None:
                        rich_table = _make_search_table()
                    _append_search_rich_rows(rich_table, page_result)
            if json_out:
                typer.echo(json.dumps(all_pages_payload, indent=2))
            elif not tsv and rich_table is not None and last_page is not None:
                typer.echo(_pages_meta_line(last_page))
                Console(soft_wrap=True).print(rich_table)
            return

        params = GoProMediaSearchParams(
            captured_range=CapturedRange(start=start_dt, end=end_dt),
            page=page,
            per_page=per_page,
        )
        page_result = await client.search(params)
    if json_out:
        typer.echo(
            json.dumps(
                _rename_search_payload(
                    page_result.model_dump(by_alias=True, mode="json"),
                ),
                indent=2,
            ),
        )
    elif tsv:
        _print_search_plain_page(page_result)
    else:
        _print_search_rich_page(page_result)


@app.command(
    "search",
    help=(
        "List media in a capture date range (Rich table by default; "
        "--tsv for tab-separated fields; --json for raw API payloads)"
    ),
)
def search_command(
    ctx: typer.Context,
    *,
    start: str = typer.Option(
        ...,
        "--start",
        help="Range start: YYYY-MM-DD or ISO datetime",
    ),
    end: str = typer.Option(
        ...,
        "--end",
        help=(
            "Range end: YYYY-MM-DD or ISO datetime "
            "(API treats range as in query string)"
        ),
    ),
    page: int = typer.Option(1, "--page", help="Page number (default: 1)"),
    per_page: int = typer.Option(30, "--per-page", help="Page size (default: 30)"),
    all_pages: bool = typer.Option(
        False,
        "--all-pages",
        help="Keep requesting pages until a page returns no media",
    ),
    tsv: bool = typer.Option(
        False,
        "--tsv",
        help="Print tab-separated values (header row + metadata line) for scripting",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Print full API JSON (with --all-pages: list of page payloads)",
    ),
) -> None:
    """Run search against the cloud API and print results."""
    timeout = ctx.obj["timeout"]
    asyncio.run(
        _run_search(
            timeout=timeout,
            start=start,
            end=end,
            page=page,
            per_page=per_page,
            all_pages=all_pages,
            json_out=json_out,
            tsv=tsv,
        ),
    )


_VARIATION_HEADERS = ["idx", "label", "quality", "type", "dim", "available", "url"]
_FILE_HEADERS = ["idx", "item", "camera", "dim", "available", "url"]
_SIDECAR_HEADERS = ["idx", "label", "type", "fps", "available", "url"]


def _build_basic_table(headers: list[str], *, fold_cols: tuple[str, ...] = ("url",)) -> Table:
    table = Table(show_header=True, header_style="bold")
    for h in headers:
        if h in fold_cols:
            table.add_column(h, overflow="fold")
        else:
            table.add_column(h)
    return table


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _info_variation_cells(idx: int, v: GoProMediaDownloadVariation) -> list[str]:
    return [
        str(idx),
        v.label,
        v.quality,
        v.type,
        f"{v.width}x{v.height}",
        _yes_no(v.available),
        v.url,
    ]


def _info_file_cells(idx: int, f: GoProMediaDownloadFile) -> list[str]:
    return [
        str(idx),
        str(f.item_number),
        f.camera_position,
        f"{f.width}x{f.height}",
        _yes_no(f.available),
        f.url,
    ]


def _info_sidecar_cells(idx: int, s: GoProMediaDownloadSidecarFile) -> list[str]:
    return [
        str(idx),
        s.label,
        s.type,
        str(s.fps),
        _yes_no(s.available),
        s.url,
    ]


def _print_info_rich(meta: GoProMediaDownloadResponse) -> None:
    typer.secho(meta.filename, bold=True)
    console = Console(soft_wrap=True)
    if is_video_filename(meta.filename):
        table = _build_basic_table(_VARIATION_HEADERS)
        for idx, v in enumerate(meta.embedded.variations):
            table.add_row(*_info_variation_cells(idx, v))
    else:
        table = _build_basic_table(_FILE_HEADERS)
        for idx, f in enumerate(meta.embedded.files):
            table.add_row(*_info_file_cells(idx, f))
    console.print(table)
    if meta.embedded.sidecar_files:
        typer.secho("sidecars", bold=True)
        sidecars = _build_basic_table(_SIDECAR_HEADERS)
        for idx, s in enumerate(meta.embedded.sidecar_files):
            sidecars.add_row(*_info_sidecar_cells(idx, s))
        console.print(sidecars)


def _print_info_tsv(meta: GoProMediaDownloadResponse) -> None:
    typer.echo(f"# filename: {meta.filename}")
    if is_video_filename(meta.filename):
        typer.echo("\t".join(_VARIATION_HEADERS))
        for idx, v in enumerate(meta.embedded.variations):
            typer.echo("\t".join(_info_variation_cells(idx, v)))
    else:
        typer.echo("\t".join(_FILE_HEADERS))
        for idx, f in enumerate(meta.embedded.files):
            typer.echo("\t".join(_info_file_cells(idx, f)))
    if meta.embedded.sidecar_files:
        typer.echo("# sidecars")
        typer.echo("\t".join(_SIDECAR_HEADERS))
        for idx, s in enumerate(meta.embedded.sidecar_files):
            typer.echo("\t".join(_info_sidecar_cells(idx, s)))


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
        _print_info_tsv(meta)
    else:
        _print_info_rich(meta)


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


_PULL_HEADERS = ["filename", "dim", "available", "url"]


def _pull_summary_cells(filename: str, asset: DownloadAsset) -> list[str]:
    return [
        filename,
        f"{asset.width}x{asset.height}",
        _yes_no(asset.available),
        asset.url,
    ]


def _print_pull_rich(assets: dict[str, DownloadAsset], destination: str) -> None:
    typer.secho(
        f"Pulling {len(assets)} file(s) to {destination}",
        bold=True,
    )
    table = _build_basic_table(_PULL_HEADERS)
    for filename, asset in assets.items():
        table.add_row(*_pull_summary_cells(filename, asset))
    Console(soft_wrap=True).print(table)


def _print_pull_tsv(assets: dict[str, DownloadAsset], destination: str) -> None:
    typer.echo(f"# destination: {destination}")
    typer.echo("\t".join(_PULL_HEADERS))
    for filename, asset in assets.items():
        typer.echo("\t".join(_pull_summary_cells(filename, asset)))


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
            _print_pull_tsv(assets, destination)
        else:
            _print_pull_rich(assets, destination)

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


def main(argv: Optional[list[str]] = None) -> None:
    """CLI entrypoint: parse ``argv`` and run the selected command.

    Args:
        argv: Argument list (defaults to process arguments when ``None``).
    """
    app(args=argv)


if __name__ == "__main__":
    main()
