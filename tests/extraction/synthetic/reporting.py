# pattern: Imperative Shell
"""Rich-formatted reporting for extraction quality results.

Provides human-readable summary output: green/yellow/red dashboard
per feature type and noise tier, regression flagging.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table


def print_summary(report_data: dict[str, Any], console: Console | None = None) -> None:
    """Print a human-readable quality summary.

    Args:
        report_data: Output of QualityReport.to_dict().
        console: Rich console to print to. Uses default if None.
    """
    con = console or Console()
    results = report_data.get("results", {})

    con.print(
        f"\n[bold]Extraction Quality Report[/bold]  "
        f"[dim]{report_data.get('timestamp', 'unknown')}  "
        f"pipeline: {report_data.get('pipeline_version', 'unknown')}[/dim]\n"
    )

    for doc_name, doc_tiers in results.items():
        table = Table(title=doc_name, show_header=True, header_style="bold")
        table.add_column("Tier", style="bold")
        table.add_column("CER", justify="right")
        table.add_column("WER", justify="right")
        table.add_column("Failures", justify="right")
        table.add_column("Detection", justify="right")

        for tier_name in ["T0_clean", "T1_ocr_needed", "T2_moderate_scan", "T3_degraded"]:
            tier_data = doc_tiers.get(tier_name, {})
            if not tier_data:
                continue

            semantic = tier_data.get("semantic", {})
            cer = semantic.get("CER", 0.0)
            wer = semantic.get("WER", 0.0)
            failures = len(tier_data.get("alignment_failures", []))
            structural = tier_data.get("structural", {})

            # Compute overall detection rate
            total_detected = sum(
                v.get("detection_rate", 0.0) * v.get("count", 0) for v in structural.values()
            )
            total_count = sum(v.get("count", 0) for v in structural.values())
            detection_rate = total_detected / total_count if total_count > 0 else 0.0

            # Color coding
            cer_str = _color_metric(cer, good=0.05, warn=0.15)
            wer_str = _color_metric(wer, good=0.10, warn=0.25)
            fail_str = f"[green]{failures}[/green]" if failures == 0 else f"[red]{failures}[/red]"
            # Color detection rate: low detection is bad (invert for threshold)
            det_str = _color_metric(1.0 - detection_rate, good=0.05, warn=0.20).replace(
                f"{1.0 - detection_rate:.4f}", f"{detection_rate:.1%}"
            )

            table.add_row(tier_name, cer_str, wer_str, fail_str, det_str)

        con.print(table)
        con.print()


def print_regressions(regressions: list[dict[str, Any]], console: Console | None = None) -> None:
    """Print regression summary.

    Args:
        regressions: List from compare_to_baseline().
        console: Rich console to print to.
    """
    con = console or Console()

    if not regressions:
        con.print("[green]No regressions detected.[/green]\n")
        return

    con.print(f"[red bold]Regressions detected: {len(regressions)}[/red bold]\n")

    table = Table(show_header=True, header_style="bold red")
    table.add_column("Document")
    table.add_column("Tier")
    table.add_column("Metric")
    table.add_column("Baseline", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Change", justify="right")

    for r in regressions:
        change = r["relative_increase"]
        table.add_row(
            r["document"],
            r["tier"],
            r["metric"],
            f"{r['baseline']:.4f}",
            f"{r['current']:.4f}",
            f"[red]+{change:.1%}[/red]",
        )

    con.print(table)
    con.print()


def _color_metric(value: float, good: float, warn: float) -> str:
    """Color a metric value: green if <= good, yellow if <= warn, red."""
    formatted = f"{value:.4f}"
    if value <= good:
        return f"[green]{formatted}[/green]"
    elif value <= warn:
        return f"[yellow]{formatted}[/yellow]"
    else:
        return f"[red]{formatted}[/red]"
