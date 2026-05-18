from __future__ import annotations

import typer
from rich import print as rprint

from outfitmatch.config import load_config

app = typer.Typer(add_completion=False, help="OutfitMatch experiment runner")


@app.command()
def run(
    config: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate config and exit"),
) -> None:
    """Run a single experiment from a YAML config."""
    cfg = load_config(config)
    rprint(
        f"[bold green]Loaded:[/] {cfg.name} "
        f"(task={cfg.task}, model={cfg.model.checkpoint}, "
        f"rows={cfg.dataset.max_rows})"
    )
    if dry_run:
        rprint("[yellow]--dry-run: exiting before training.[/]")
        raise typer.Exit(0)

    from outfitmatch.runner import execute

    execute(cfg, group=cfg.name.split("-")[0], job_type=cfg.task)


@app.command()
def sweep(
    config_dir: str,
    out_csv: str = typer.Option(
        "docs/experiments/ablation.csv", "--out-csv", help="Output CSV path"
    ),
) -> None:
    """Run every YAML in a directory as one experiment cycle."""
    from pathlib import Path

    from outfitmatch.export import append_result_row
    from outfitmatch.runner import execute

    yamls = sorted(Path(config_dir).glob("*.yaml"))
    if not yamls:
        rprint("[red]No YAML configs found in[/] " + config_dir)
        raise typer.Exit(1)

    for yaml_path in yamls:
        cfg = load_config(yaml_path)
        rprint(f"[cyan]>>>[/] {cfg.name}")
        metrics = execute(cfg, group=Path(config_dir).name, job_type=cfg.task)
        append_result_row(
            out_csv,
            {"name": cfg.name, "model": cfg.model.checkpoint,
             "rows": cfg.dataset.max_rows, **metrics},
        )

    rprint(f"[bold green]Cycle complete.[/] Results → {out_csv}")


if __name__ == "__main__":
    app()
