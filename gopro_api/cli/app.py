"""Typer application instance, root callback, and CLI entrypoint."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Optional

import typer

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


def main(argv: Optional[list[str]] = None) -> None:
    """CLI entrypoint: parse ``argv`` and run the selected command.

    Args:
        argv: Argument list (defaults to process arguments when ``None``).
    """
    app(args=argv)
