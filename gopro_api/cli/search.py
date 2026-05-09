"""Search command: SearchPrinter class, async runner, and Typer callback."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.filesize import decimal as format_decimal_size
from rich.table import Table

from gopro_api.api.models import (
    DEFAULT_FIELDS,
    CapturedRange,
    GoProMediaSearchItem,
    GoProMediaSearchParams,
    GoProMediaSearchResponse,
)
from gopro_api.client import AsyncGoProClient

from .app import app
from ._common import _parse_dt, _renamed_field, _require_token


@dataclass(frozen=True, slots=True)
class _SearchParams:
    """Bundled search parameters passed from the Typer callback to the async runner."""

    start: str
    end: str
    page: int
    per_page: int
    all_pages: bool
    json_out: bool
    tsv: bool


class SearchPrinter:
    """Handles all search output formatting: Rich table, TSV, and JSON key renaming."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize with an optional Rich console.

        Args:
            console: Console used for Rich output; a default soft-wrap console is
                created when ``None``.
        """
        self._console = console or Console(soft_wrap=True)

    def page_meta_line(self, page: GoProMediaSearchResponse) -> str:
        """Format the pagination metadata comment line for a search page.

        Args:
            page: Search response containing pagination details.

        Returns:
            A ``# _pages:`` comment string with current page, per-page, total items,
            and total pages.
        """
        pages = page.pages
        return (
            f"# _pages: current_page={pages.current_page} per_page={pages.per_page} "
            f"total_items={pages.total_items} total_pages={pages.total_pages}"
        )

    def emit_embedded_errors(self, page: GoProMediaSearchResponse) -> None:
        """Print any embedded API errors to stderr as yellow comment lines.

        Args:
            page: Search response whose ``_embedded.errors`` list is checked.
        """
        if page.embedded.errors:
            for err in page.embedded.errors:
                typer.secho(
                    f"# _embedded.errors: {json.dumps(err, ensure_ascii=False)}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )

    def cells_plain(self, item: GoProMediaSearchItem) -> list[str]:
        """Build raw string cells for TSV output.

        Args:
            item: A single media item from the search response.

        Returns:
            Ordered list of strings for each field in ``DEFAULT_FIELDS``;
            missing values are represented as empty strings.
        """
        row = item.model_dump(mode="json")
        return ["" if row.get(c) is None else str(row[c]) for c in DEFAULT_FIELDS]

    def cells_rich(self, item: GoProMediaSearchItem) -> list[str]:
        """Build human-formatted cells for Rich table output.

        File sizes are formatted with decimal SI units; all other values are
        stringified as-is.

        Args:
            item: A single media item from the search response.

        Returns:
            Ordered list of display strings for each field in ``DEFAULT_FIELDS``.
        """
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

    def make_table(self) -> Table:
        """Build an empty Rich Table with the default search columns.

        Returns:
            A ``rich.table.Table`` configured with per-column overflow settings,
            ready to receive rows via ``add_row``.
        """
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

    def print_table(self, table: Table) -> None:
        """Print a Rich table to the console.

        Args:
            table: Fully populated Rich table to render.
        """
        self._console.print(table)

    def print_tsv_page(
        self, page: GoProMediaSearchResponse, *, header: bool = True
    ) -> None:
        """Print a TSV-formatted search page to stdout.

        Args:
            page: Search response page to render.
            header: When ``True`` (default), emit the column-name header row first;
                set to ``False`` for subsequent pages in ``--all-pages`` mode.
        """
        typer.echo(self.page_meta_line(page))
        self.emit_embedded_errors(page)
        if header:
            typer.echo("\t".join(_renamed_field(c) for c in DEFAULT_FIELDS))
        for item in page.embedded.media:
            typer.echo("\t".join(self.cells_plain(item)))

    def print_rich_page(self, page: GoProMediaSearchResponse) -> None:
        """Print a single Rich-formatted search page with metadata and a table.

        Args:
            page: Search response page to render.
        """
        self.emit_embedded_errors(page)
        typer.echo(self.page_meta_line(page))
        table = self.make_table()
        for item in page.embedded.media:
            table.add_row(*self.cells_rich(item))
        self._console.print(table)

    def append_rich_rows(self, table: Table, page: GoProMediaSearchResponse) -> None:
        """Append a page's media rows to an existing Rich table.

        Used in ``--all-pages`` mode to accumulate rows across pages before a
        single final render.

        Args:
            table: Rich table to append rows to.
            page: Search response page whose media items are appended.
        """
        self.emit_embedded_errors(page)
        for item in page.embedded.media:
            table.add_row(*self.cells_rich(item))

    def rename_payload(self, payload: dict) -> dict:
        """Apply display-name aliases to a raw API JSON payload.

        Renames keys inside ``_embedded.media`` items according to
        ``_FIELD_LABELS`` so that JSON output uses the same names as the table
        headers.

        Args:
            payload: Raw API payload dict (typically from ``model_dump``).

        Returns:
            The same ``payload`` dict with ``_embedded.media`` keys renamed in-place.
        """
        embedded = payload.get("_embedded")
        if isinstance(embedded, dict):
            media = embedded.get("media")
            if isinstance(media, list):
                embedded["media"] = [
                    (
                        {_renamed_field(k): v for k, v in it.items()}
                        if isinstance(it, dict)
                        else it
                    )
                    for it in media
                ]
        return payload


async def _collect_all_pages(
    *,
    client: AsyncGoProClient,
    printer: SearchPrinter,
    params: _SearchParams,
    start_dt: datetime,
    end_dt: datetime,
) -> None:
    """Stream all non-empty search pages and render them incrementally.

    Args:
        client: Open ``AsyncGoProClient`` to use for API calls.
        printer: ``SearchPrinter`` instance used for rendering.
        params: Bundled search options controlling output format and pagination.
        start_dt: Parsed capture-range start datetime.
        end_dt: Parsed capture-range end datetime.
    """
    all_pages_payload: list[dict] = []
    first_plain_page = True
    rich_table: Optional[Table] = None
    last_page: Optional[GoProMediaSearchResponse] = None
    async for page_result in client.iter_nonempty_search_pages(
        start_dt,
        end_dt,
        per_page=params.per_page,
        start_page=params.page,
    ):
        last_page = page_result
        if params.json_out:
            all_pages_payload.append(
                printer.rename_payload(
                    page_result.model_dump(by_alias=True, mode="json"),
                ),
            )
        elif params.tsv:
            printer.print_tsv_page(page_result, header=first_plain_page)
            first_plain_page = False
        else:
            if rich_table is None:
                rich_table = printer.make_table()
            printer.append_rich_rows(rich_table, page_result)
    if params.json_out:
        typer.echo(json.dumps(all_pages_payload, indent=2))
    elif not params.tsv and rich_table is not None and last_page is not None:
        typer.echo(printer.page_meta_line(last_page))
        printer.print_table(rich_table)


async def _run_search(*, timeout: float, params: _SearchParams) -> None:
    """Execute a media search against the GoPro cloud API and print results.

    Args:
        timeout: HTTP timeout in seconds passed to ``AsyncGoProClient``.
        params: Bundled search options (date range, pagination, output format).
    """
    _require_token()
    printer = SearchPrinter()
    start_dt = _parse_dt(params.start)
    end_dt = _parse_dt(params.end)

    async with AsyncGoProClient(timeout=timeout) as client:
        if params.all_pages:
            await _collect_all_pages(
                client=client,
                printer=printer,
                params=params,
                start_dt=start_dt,
                end_dt=end_dt,
            )
            return

        search_params = GoProMediaSearchParams(
            captured_range=CapturedRange(start=start_dt, end=end_dt),
            page=params.page,
            per_page=params.per_page,
        )
        page_result = await client.search(search_params)
    if params.json_out:
        typer.echo(
            json.dumps(
                printer.rename_payload(
                    page_result.model_dump(by_alias=True, mode="json"),
                ),
                indent=2,
            ),
        )
    elif params.tsv:
        printer.print_tsv_page(page_result)
    else:
        printer.print_rich_page(page_result)


@app.command(
    "search",
    help=(
        "List media in a capture date range (Rich table by default; "
        "--tsv for tab-separated fields; --json for raw API payloads)"
    ),
)
def search_command(  # pylint: disable=too-many-arguments
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
    asyncio.run(
        _run_search(
            timeout=ctx.obj["timeout"],
            params=_SearchParams(
                start=start,
                end=end,
                page=page,
                per_page=per_page,
                all_pages=all_pages,
                json_out=json_out,
                tsv=tsv,
            ),
        ),
    )
