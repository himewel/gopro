"""Command-line interface for gopro-api."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Optional

import typer

from gopro_api.api.models import (
    DEFAULT_FIELDS,
    CapturedRange,
    GoProMediaSearchItem,
    GoProMediaSearchParams,
    GoProMediaSearchResponse,
)
from gopro_api.client import AsyncGoProClient
from gopro_api.config import GP_ACCESS_TOKEN
from gopro_api.exceptions import NoVariationsError
from gopro_api.utils import is_video_filename, pull_assets_for_response

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
        typer.echo(
            "error: GP_ACCESS_TOKEN is not set. "
            "Add it to your environment or a .env file.",
            err=True,
        )
        raise typer.Exit(2)


def _print_search_plain_header() -> None:
    cols = list(DEFAULT_FIELDS)
    print("\t".join(cols))


def _format_search_item_plain(item: GoProMediaSearchItem) -> str:
    row = item.model_dump(mode="json")
    cells = ["" if row.get(c) is None else str(row[c]) for c in DEFAULT_FIELDS]
    return "\t".join(cells)


def _print_search_plain_page(
    page_result: GoProMediaSearchResponse,
    *,
    print_header: bool = True,
) -> None:
    pages = page_result.pages
    print(
        f"# _pages: current_page={pages.current_page} per_page={pages.per_page} "
        f"total_items={pages.total_items} total_pages={pages.total_pages}",
    )
    if page_result.embedded.errors:
        for err in page_result.embedded.errors:
            print(
                f"# _embedded.errors: {json.dumps(err, ensure_ascii=False)}",
                file=sys.stderr,
            )
    if print_header:
        _print_search_plain_header()
    for item in page_result.embedded.media:
        print(_format_search_item_plain(item))


async def _run_search(
    *,
    timeout: float,
    start: str,
    end: str,
    page: int,
    per_page: int,
    all_pages: bool,
    json_out: bool,
) -> None:
    _require_token()
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)

    async with AsyncGoProClient(timeout=timeout) as client:
        if all_pages:
            all_pages_payload: list[dict] = []
            first_plain_page = True
            async for page_result in client.iter_nonempty_search_pages(
                start_dt,
                end_dt,
                per_page=per_page,
                start_page=page,
            ):
                if json_out:
                    all_pages_payload.append(
                        page_result.model_dump(by_alias=True, mode="json"),
                    )
                else:
                    _print_search_plain_page(
                        page_result,
                        print_header=first_plain_page,
                    )
                    first_plain_page = False
            if json_out:
                print(json.dumps(all_pages_payload, indent=2))
            return

        params = GoProMediaSearchParams(
            captured_range=CapturedRange(start=start_dt, end=end_dt),
            page=page,
            per_page=per_page,
        )
        page_result = await client.search(params)
    if json_out:
        print(
            json.dumps(
                page_result.model_dump(by_alias=True, mode="json"),
                indent=2,
            ),
        )
    else:
        _print_search_plain_page(page_result)


@app.command(
    "search",
    help=(
        "List media in a capture date range (tab-separated fields; "
        "use --json for raw API payloads)"
    ),
)
def search_command(
    ctx: typer.Context,
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
        ),
    )


async def _run_info(
    *,
    timeout: float,
    media_id: str,
    json_out: bool,
) -> None:
    _require_token()
    async with AsyncGoProClient(timeout=timeout) as client:
        meta = await client.download(media_id)
    if json_out:
        print(
            json.dumps(
                meta.model_dump(by_alias=True, mode="json"),
                indent=2,
            ),
        )
    else:
        print(meta.filename)
        media_list = (
            meta.embedded.variations
            if is_video_filename(meta.filename)
            else meta.embedded.files
        )
        for idx, media_item in enumerate(media_list):
            print(
                f"  {idx:>3}  {media_item.width}x{media_item.height}  "
                f"{media_item.url}",
            )


@app.command("info", help="Show download metadata (URLs, sizes) for one media id")
def info_command(
    ctx: typer.Context,
    media_id: str = typer.Argument(..., help="Media id from search"),
    json_out: bool = typer.Option(False, "--json", help="Print full API JSON"),
) -> None:
    """Fetch and display download metadata for ``media_id``."""
    asyncio.run(
        _run_info(timeout=ctx.obj["timeout"], media_id=media_id, json_out=json_out),
    )


async def _run_pull(
    *,
    timeout: float,
    media_id: str,
    destination: str,
    height: Optional[int],
    width: Optional[int],
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
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(2) from exc

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


@app.command("pull", help="Download files from a media id")
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
        ),
    )


def main(argv: Optional[list[str]] = None) -> None:
    """CLI entrypoint: parse ``argv`` and run the selected command.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).
    """
    app(args=argv)


if __name__ == "__main__":
    main()
