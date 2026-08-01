from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import TwinConfig
from .installer import UvInstaller
from .logger import configure_logging
from .supervisor import Supervisor
from .twin_engine import DigitalTwinEngine

app = typer.Typer(help="Arctus Digital Twin Engine & Supervisor CLI")
console = Console()
state: dict = {}


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    project_root: Path = typer.Option(Path("."), "--root", "-r"),
):
    configure_logging("DEBUG" if verbose else "INFO")
    state["config"] = TwinConfig(project_root=project_root)


@app.command()
def start():
    """Start the Digital Twin Engine & Supervisor."""

    async def _run():
        await UvInstaller.ensure()
        supervisor = Supervisor(state["config"])
        await supervisor.run()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow]")


@app.command()
def status():
    """Report current twin graph status."""

    async def _get():
        await UvInstaller.ensure()
        twin = DigitalTwinEngine(state["config"])
        await twin.bootstrap()

        st = await twin.get_status()

        table = Table(title="Arctus Digital Twin Status")
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        for k, v in st.items():
            table.add_row(k, str(v))

        console.print(table)

    asyncio.run(_get())


@app.command()
def query(q: str):
    """Run a structured query against the twin."""

    async def _query():
        await UvInstaller.ensure()
        twin = DigitalTwinEngine(state["config"])
        await twin.bootstrap()

        result = await twin.query(q)
        console.print_json(data=result)

    asyncio.run(_query())


if __name__ == "__main__":
    app()
