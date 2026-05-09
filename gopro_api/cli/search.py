"""Search command: SearchPrinter class, async runner, and Typer callback."""

from __future__ import annotations

import asyncio
import json
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


class SearchPrinter:
    """Handles all search output formatting: Rich table, TSV, and JSON key renaming."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console(soft_wrap=True)

    def page_meta_line(self, page: GoProMediaSearchResponse) -> str:
        pages = page.pages
        return (
            f"# _pages: current_page={pages.current_page} per_page={pages.per_page} "
            f"total_items={pages.total_items} total_pages={pages.total_pages}"
        )

    def emit_embedded_errors(self, page: GoProMediaSearchResponse) -> None:
        if page.embedded.errors:
            for err in page.embedded.errors:
                typer.secho(
                    f"# _embedded.errors: {json.dumps(err, ensure_ascii=False)}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )

    def cells_plain(self, item: GoProMediaSearchItem) -> list[str]:
        row = item.model_dump(mode="json")
        return ["" if row.get(c) is None else str(row[c]) for c in DEFAULT_FIELDS]

    def cells_rich(self, item: GoProMediaSearchItem) -> list[str]:
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
        self._console.print(table)

    def print_tsv_page(
        self, page: GoProMediaSearchResponse, *, header: bool = True
    ) -> None:
        typer.echo(self.page_meta_line(page))
        self.emit_embedded_errors(page)
        if header:
            typer.echo("\t".join(_renamed_field(c) for c in DEFAULT_FIELDS))
        for item in page.embedded.media:
            typer.echo("\t".join(self.cells_plain(item)))

    def print_rich_page(self, page: GoProMediaSearchResponse) -> None:
        self.emit_embedded_errors(page)
        typer.echo(self.page_meta_line(page))
        table = self.make_table()
        for item in page.embedded.media:
            table.add_row(*self.cells_rich(item))
        self._console.print(table)

    def append_rich_rows(self, table: Table, page: GoProMediaSearchResponse) -> None:
        self.emit_embedded_errors(page)
        for item in page.embedded.media:
            table.add_row(*self.cells_rich(item))

    def rename_payload(self, payload: dict) -> dict:
        embedded = payload.get("_embedded")
        if isinstance(embedded, dict):
            media = embedded.get("media")
            if isinstance(media, list):
                embedded["media"] = [
                    {_renamed_field(k): v for k, v in it.items()}
                    if isinstance(it, dict)
                    else it
                    for it in media
                ]
        return payload


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
    printer = SearchPrinter()
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
                        printer.rename_payload(
                            page_result.model_dump(by_alias=True, mode="json"),
                        ),
                    )
                elif tsv:
                    printer.print_tsv_page(page_result, header=first_plain_page)
                    first_plain_page = False
                else:
                    if rich_table is None:
                        rich_table = printer.make_table()
                    printer.append_rich_rows(rich_table, page_result)
            if json_out:
                typer.echo(json.dumps(all_pages_payload, indent=2))
            elif not tsv and rich_table is not None and last_page is not None:
                typer.echo(printer.page_meta_line(last_page))
                printer.print_table(rich_table)
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
                printer.rename_payload(
                    page_result.model_dump(by_alias=True, mode="json"),
                ),
                indent=2,
            ),
        )
    elif tsv:
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
