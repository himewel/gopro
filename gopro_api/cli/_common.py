"""Shared helpers: token gating, date parsing, pixel validation, Rich table builder."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import typer
from rich.table import Table

from gopro_api.config import GP_ACCESS_TOKEN

_FIELD_LABELS: dict[str, str] = {
    "type": "media",
    "file_extension": "type",
    "file_size": "size",
    "item_count": "items",
}


def _renamed_field(name: str) -> str:
    return _FIELD_LABELS.get(name, name)


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


def _build_basic_table(
    headers: list[str], *, fold_cols: tuple[str, ...] = ("url",)
) -> Table:
    table = Table(show_header=True, header_style="bold")
    for h in headers:
        if h in fold_cols:
            table.add_column(h, overflow="fold")
        else:
            table.add_column(h)
    return table


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
