"""Command-line interface for gopro-api."""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
import json
import os
import sys

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
        from importlib.metadata import version

        return version("gopro-api")
    except Exception:
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
    v = int(raw)
    if v <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return v


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
        return max(variations, key=lambda v: v.height)

    def score(v: GoProMediaDownloadVariation) -> int:
        dh = 0 if target_height is None else (v.height - target_height) ** 2
        dw = 0 if target_width is None else (v.width - target_width) ** 2
        return dh + dw

    best = min(score(v) for v in variations)
    tied = [v for v in variations if score(v) == best]
    return max(tied, key=lambda v: (v.height, v.width))


def _require_token() -> None:
    if not GP_ACCESS_TOKEN:
        sys.stderr.write(
            "error: GP_ACCESS_TOKEN is not set. Add it to your environment or a .env file.\n",
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
        """Execute after global parse; ``args`` includes parent options (e.g. ``timeout``)."""


class SearchCommand(CliSubcommand):
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
            help="Range end: YYYY-MM-DD or ISO datetime (API treats range as in query string)",
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
                    r = api.search(params)
                    if not r.embedded.media:
                        break
                    if args.json:
                        all_pages.append(r.model_dump(by_alias=True, mode="json"))
                    else:
                        for item in r.embedded.media:
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
            r = api.search(params)
            if args.json:
                print(json.dumps(r.model_dump(by_alias=True, mode="json"), indent=2))
            else:
                for item in r.embedded.media:
                    print(item.id)


class InfoCommand(CliSubcommand):
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
            r = api.download(args.media_id)
        if args.json:
            print(json.dumps(r.model_dump(by_alias=True, mode="json"), indent=2))
        else:
            print(r.filename)

            if _is_video_filename(r.filename):
                media_list = r.embedded.variations
            else:
                media_list = r.embedded.files

            for idx, f in enumerate(media_list):
                print(f"  {idx:>3}  {f.width}x{f.height}  {f.url}")


class PullCommand(CliSubcommand):
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
            help="For video: pick the variation whose height is closest to PX (default: tallest)",
        )
        parser.add_argument(
            "--width",
            type=_positive_int,
            default=None,
            metavar="PX",
            help="For video: pick the variation whose width is closest to PX (default: tallest)",
        )

    def run(self, args: argparse.Namespace) -> None:
        _require_token()
        with GoProAPI(timeout=args.timeout) as api:
            r = api.download(args.media_id)

            if _is_video_filename(r.filename):
                chosen = _select_video_variation(
                    r.embedded.variations,
                    target_height=args.height,
                    target_width=args.width,
                )
                media_list = [chosen]
            else:
                media_list = r.embedded.files

            for idx, file in enumerate(media_list):
                os.makedirs(args.destination, exist_ok=True)
                media_name = r.filename.split(".")[0]
                media_type = r.filename.split(".")[-1]
                item_number = str(idx).zfill(3)
                media_file_name = f"{media_name}{item_number}.{media_type}"
                with open(f"{args.destination}/{media_file_name}", "wb") as f:
                    response = requests.get(file.url, timeout=args.timeout)
                    response.raise_for_status()
                    f.write(response.content)


class CliBuilder:
    """Assembles the root parser and one subparser per registered command."""

    def __init__(self, commands: Sequence[CliSubcommand]) -> None:
        self._commands = list(commands)

    def build(self) -> argparse.ArgumentParser:
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
