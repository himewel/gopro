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
    """Return the installed package version string.

    Returns:
        Version string from package metadata, or ``"0.0.0"`` when not installed.
    """
    try:
        return package_version("gopro-api")
    except PackageNotFoundError:
        return "0.0.0"


def _version_callback(value: Optional[bool]) -> None:
    """Print the package version and exit when ``--version`` is passed.

    Args:
        value: ``True`` when the ``--version`` flag is present; ``None`` otherwise.

    Raises:
        typer.Exit: Immediately after printing the version string.
    """
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
    """Store shared CLI options in the Typer context for all subcommands.

    Args:
        ctx: Typer context used to pass ``timeout`` to subcommands.
        timeout: HTTP timeout in seconds forwarded to ``AsyncGoProClient``.
        show_version: Consumed by the eager ``--version`` callback before this runs.
    """
    del show_version  # handled by eager callback (--version exits before commands)
    ctx.ensure_object(dict)
    ctx.obj["timeout"] = timeout


def main(argv: Optional[list[str]] = None) -> None:
    """CLI entrypoint: parse ``argv`` and run the selected command.

    Args:
        argv: Argument list (defaults to process arguments when ``None``).
    """
    app(args=argv)
