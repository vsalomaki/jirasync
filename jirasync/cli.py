"""Command line entry point.

Phase 2 adds `doctor` and the commands behind it. The callback below is what
keeps typer from collapsing a single-command app into a bare command, so the
subcommand names stay stable as more are added.
"""

from __future__ import annotations

import typer

from . import __version__

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="One-way Jira to Jira issue synchronisation.",
)


@app.callback()
def main() -> None:
    """One-way Jira to Jira issue synchronisation."""


@app.command()
def version() -> None:
    """Print the version and exit."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
