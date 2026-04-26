"""Command-line interface for gopro-api."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version

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


def _version() -> str:
    try:
        return version("gopro-api")
    except PackageNotFoundError:
        return "0.0.0"


def _parse_dt(raw: str) -> datetime:
    """Accept YYYY-MM-DD or ISO datetime."""
    raw = raw.strip()
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return datetime.fromisoformat(raw)
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _require_token() -> None:
    if not GP_ACCESS_TOKEN:
        sys.stderr.write(
            "error: GP_ACCESS_TOKEN is not set. "
            "Add it to your environment or a .env file.\n",
        )
        raise SystemExit(2)


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
    p = page_result.pages
    print(
        f"# _pages: current_page={p.current_page} per_page={p.per_page} "
        f"total_items={p.total_items} total_pages={p.total_pages}",
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


class CliSubcommand(ABC):
    """One subcommand: its parser arguments and async execution."""

    name: str
    help: str

    @abstractmethod
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Configure the subparser for this command."""

    @abstractmethod
    async def run(self, args: argparse.Namespace) -> None:
        """Execute the command.

        ``args`` includes parent options (for example ``timeout``).
        """


class SearchCommand(CliSubcommand):
    """``search`` — list media rows in a capture date range."""

    name = "search"
    help = (
        "List media in a capture date range (tab-separated fields; "
        "use --json for raw API payloads)"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--start",
            required=True,
            help="Range start: YYYY-MM-DD or ISO datetime",
        )
        parser.add_argument(
            "--end",
            required=True,
            help=(
                "Range end: YYYY-MM-DD or ISO datetime "
                "(API treats range as in query string)"
            ),
        )
        parser.add_argument(
            "--page", type=int, default=1, help="Page number (default: 1)"
        )
        parser.add_argument(
            "--per-page",
            type=int,
            default=30,
            metavar="N",
            help="Page size (default: 30)",
        )
        parser.add_argument(
            "--all-pages",
            action="store_true",
            help="Keep requesting pages until a page returns no media",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print full API JSON (with --all-pages: list of page payloads)",
        )

    async def run(self, args: argparse.Namespace) -> None:
        _require_token()
        start = _parse_dt(args.start)
        end = _parse_dt(args.end)

        async with AsyncGoProClient(timeout=args.timeout) as client:
            if args.all_pages:
                all_pages: list[dict] = []
                first_plain_page = True
                async for page_result in client.iter_nonempty_search_pages(
                    start, end, per_page=args.per_page, start_page=args.page
                ):
                    if args.json:
                        all_pages.append(
                            page_result.model_dump(by_alias=True, mode="json"),
                        )
                    else:
                        _print_search_plain_page(
                            page_result,
                            print_header=first_plain_page,
                        )
                        first_plain_page = False
                if args.json:
                    print(json.dumps(all_pages, indent=2))
                return

            params = GoProMediaSearchParams(
                captured_range=CapturedRange(start=start, end=end),
                page=args.page,
                per_page=args.per_page,
            )
            page_result = await client.search(params)
        if args.json:
            print(
                json.dumps(
                    page_result.model_dump(by_alias=True, mode="json"),
                    indent=2,
                ),
            )
        else:
            _print_search_plain_page(page_result)


class InfoCommand(CliSubcommand):
    """``info`` — show download metadata for one media id."""

    name = "info"
    help = "Show download metadata (URLs, sizes) for one media id"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("media_id", help="Media id from search")
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print full API JSON",
        )

    async def run(self, args: argparse.Namespace) -> None:
        _require_token()
        async with AsyncGoProClient(timeout=args.timeout) as client:
            meta = await client.download(args.media_id)
        if args.json:
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


class PullCommand(CliSubcommand):
    """``pull`` — download files for one media id."""

    name = "pull"
    help = "Download files from a media id"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("media_id", help="Media id from search")
        parser.add_argument("destination", help="Path to save the file")
        parser.add_argument(
            "--height",
            type=_positive_int,
            default=None,
            metavar="PX",
            help=(
                "For video: pick the variation whose height is closest to PX "
                "(default: tallest)"
            ),
        )
        parser.add_argument(
            "--width",
            type=_positive_int,
            default=None,
            metavar="PX",
            help=(
                "For video: pick the variation whose width is closest to PX "
                "(default: tallest)"
            ),
        )

    async def run(self, args: argparse.Namespace) -> None:
        _require_token()
        async with AsyncGoProClient(timeout=args.timeout) as client:
            meta = await client.download(args.media_id)
            try:
                assets = pull_assets_for_response(
                    meta,
                    target_height=args.height,
                    target_width=args.width,
                )
            except NoVariationsError as exc:
                sys.stderr.write(f"error: {exc}\n")
                raise SystemExit(2) from exc

            os.makedirs(args.destination, exist_ok=True)
            await asyncio.gather(
                *(
                    client.download_url_to_path(
                        asset.url,
                        os.path.join(args.destination, filename),
                    )
                    for filename, asset in assets.items()
                )
            )


class CliBuilder:  # pylint: disable=too-few-public-methods
    """Assembles the root parser and one subparser per registered command."""

    def __init__(self, commands: Sequence[CliSubcommand]) -> None:
        self._commands = list(commands)

    def build(self) -> argparse.ArgumentParser:
        """Return the root parser with global options and subcommands."""
        parser = argparse.ArgumentParser(
            prog="gopro-api",
            description="CLI for the unofficial GoPro cloud API (api.gopro.com).",
        )
        parser.add_argument(
            "--version",
            action="version",
            version=f"%(prog)s {_version()}",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=60.0,
            help="HTTP timeout in seconds (default: 60)",
        )

        sub = parser.add_subparsers(dest="command", required=True)
        for cmd in self._commands:
            subparser = sub.add_parser(cmd.name, help=cmd.help)
            cmd.add_arguments(subparser)
            subparser.set_defaults(func=cmd.run)

        return parser


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and dispatch to the selected subcommand handler."""
    builder = CliBuilder(
        [
            SearchCommand(),
            InfoCommand(),
            PullCommand(),
        ],
    )
    args = builder.build().parse_args(argv)
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
