"""Command-line interface for gopro-api."""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
import json
import os
import sys
from importlib.metadata import PackageNotFoundError, version

import requests

from gopro_api.api import GoProAPI
from gopro_api.api.models import (
    CapturedRange,
    GoProMediaDownloadVariation,
    GoProMediaSearchParams,
)
from gopro_api.config import GP_ACCESS_TOKEN


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


def _is_video_filename(filename: str) -> bool:
    base = filename.rsplit(".", 1)
    return len(base) == 2 and base[1].lower() == "mp4"


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _select_video_variation(
    variations: list[GoProMediaDownloadVariation],
    *,
    target_height: int | None,
    target_width: int | None,
) -> GoProMediaDownloadVariation:
    """Pick one variation: closest to target size, or tallest when no target."""
    if not variations:
        sys.stderr.write("error: API returned no video variations for this media id.\n")
        raise SystemExit(2)
    if target_height is None and target_width is None:
        return max(variations, key=lambda var: var.height)

    def score(variation: GoProMediaDownloadVariation) -> int:
        delta_h = (
            0 if target_height is None else (variation.height - target_height) ** 2
        )
        delta_w = 0 if target_width is None else (variation.width - target_width) ** 2
        return delta_h + delta_w

    best = min(score(variation) for variation in variations)
    tied = [variation for variation in variations if score(variation) == best]
    return max(tied, key=lambda var: (var.height, var.width))


def _require_token() -> None:
    if not GP_ACCESS_TOKEN:
        sys.stderr.write(
            "error: GP_ACCESS_TOKEN is not set. "
            "Add it to your environment or a .env file.\n",
        )
        raise SystemExit(2)


class CliSubcommand(ABC):
    """One subcommand: its parser arguments and execution."""

    name: str
    help: str

    @abstractmethod
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Configure the subparser for this command."""

    @abstractmethod
    def run(self, args: argparse.Namespace) -> None:
        """Execute after global parse.

        ``args`` includes parent options (for example ``timeout``).
        """


class SearchCommand(CliSubcommand):
    """``search`` — list media ids in a capture date range."""

    name = "search"
    help = "List media ids in a capture date range"

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

    def run(self, args: argparse.Namespace) -> None:
        _require_token()
        start = _parse_dt(args.start)
        end = _parse_dt(args.end)
        per_page = args.per_page
        page = args.page

        with GoProAPI(timeout=args.timeout) as api:
            if args.all_pages:
                all_pages: list[dict] = []
                while True:
                    params = GoProMediaSearchParams(
                        captured_range=CapturedRange(start=start, end=end),
                        page=page,
                        per_page=per_page,
                    )
                    page_result = api.search(params)
                    if not page_result.embedded.media:
                        break
                    if args.json:
                        all_pages.append(
                            page_result.model_dump(by_alias=True, mode="json"),
                        )
                    else:
                        for item in page_result.embedded.media:
                            print(item.id)
                    page += 1
                if args.json:
                    print(json.dumps(all_pages, indent=2))
                return

            params = GoProMediaSearchParams(
                captured_range=CapturedRange(start=start, end=end),
                page=page,
                per_page=per_page,
            )
            page_result = api.search(params)
            if args.json:
                print(
                    json.dumps(
                        page_result.model_dump(by_alias=True, mode="json"),
                        indent=2,
                    ),
                )
            else:
                for item in page_result.embedded.media:
                    print(item.id)


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

    def run(self, args: argparse.Namespace) -> None:
        _require_token()
        with GoProAPI(timeout=args.timeout) as api:
            meta = api.download(args.media_id)
        if args.json:
            print(
                json.dumps(
                    meta.model_dump(by_alias=True, mode="json"),
                    indent=2,
                ),
            )
        else:
            print(meta.filename)

            if _is_video_filename(meta.filename):
                media_list = meta.embedded.variations
            else:
                media_list = meta.embedded.files

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

    def run(self, args: argparse.Namespace) -> None:
        _require_token()
        with GoProAPI(timeout=args.timeout) as api:
            meta = api.download(args.media_id)

            if _is_video_filename(meta.filename):
                chosen = _select_video_variation(
                    meta.embedded.variations,
                    target_height=args.height,
                    target_width=args.width,
                )
                media_list = [chosen]
            else:
                media_list = meta.embedded.files

            for idx, file_entry in enumerate(media_list):
                os.makedirs(args.destination, exist_ok=True)
                media_name = meta.filename.split(".")[0]
                media_type = meta.filename.split(".")[-1]
                item_number = str(idx).zfill(3)
                media_file_name = f"{media_name}{item_number}.{media_type}"
                dest_path = f"{args.destination}/{media_file_name}"
                with open(dest_path, "wb") as outfile:
                    response = requests.get(file_entry.url, timeout=args.timeout)
                    response.raise_for_status()
                    outfile.write(response.content)


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
    args.func(args)


if __name__ == "__main__":
    main()
