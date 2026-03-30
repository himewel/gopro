"""Command-line interface for gopro-api."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from gopro_api.api import GoProAPI
from gopro_api.api.models import CapturedRange, GoProMediaSearchParams
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


def _require_token() -> None:
    if not GP_ACCESS_TOKEN:
        sys.stderr.write(
            "error: GP_ACCESS_TOKEN is not set. Add it to your environment or a .env file.\n",
        )
        raise SystemExit(2)


def _cmd_search(args: argparse.Namespace) -> None:
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


def _cmd_download_info(args: argparse.Namespace) -> None:
    _require_token()
    with GoProAPI(timeout=args.timeout) as api:
        r = api.download(args.media_id)
    if args.json:
        print(json.dumps(r.model_dump(by_alias=True, mode="json"), indent=2))
    else:
        print(r.filename)
        for f in r.embedded.files:
            print(f"  {f.item_number:>3}  {f.width}x{f.height}  {f.url}")


def main(argv: list[str] | None = None) -> None:
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

    p_search = sub.add_parser("search", help="List media ids in a capture date range")
    p_search.add_argument(
        "--start",
        required=True,
        help="Range start: YYYY-MM-DD or ISO datetime",
    )
    p_search.add_argument(
        "--end",
        required=True,
        help="Range end: YYYY-MM-DD or ISO datetime (API treats range as in query string)",
    )
    p_search.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    p_search.add_argument(
        "--per-page",
        type=int,
        default=30,
        metavar="N",
        help="Page size (default: 30)",
    )
    p_search.add_argument(
        "--all-pages",
        action="store_true",
        help="Keep requesting pages until a page returns no media",
    )
    p_search.add_argument(
        "--json",
        action="store_true",
        help="Print full API JSON (with --all-pages: list of page payloads)",
    )
    p_search.set_defaults(func=_cmd_search)

    p_info = sub.add_parser(
        "download-info",
        help="Show download metadata (URLs, sizes) for one media id",
    )
    p_info.add_argument("media_id", help="Media id from search")
    p_info.add_argument(
        "--json",
        action="store_true",
        help="Print full API JSON",
    )
    p_info.set_defaults(func=_cmd_download_info)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
