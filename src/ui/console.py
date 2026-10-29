from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.domain.models import ApplicationRecord, ApplicationStatus
from src.services.scan_service import ScanSummary

console = Console()


def print_banner(title: str, subtitle: str = "") -> None:
    text = Text()
    text.append(f" {title} \n", style="bold cyan")
    if subtitle:
        text.append(f"{subtitle}\n", style="dim white")
    console.print(Panel(text, border_style="cyan", expand=False))


def print_scan_summary(summary: ScanSummary) -> None:
    # 1. Summary Metrics Panel
    metrics_text = Text()
    metrics_text.append(f"• Total Vacantes Escaneadas: {summary.total_scanned}\n", style="bold white")
    metrics_text.append(f"• Vacantes con Match (>= 40%): {summary.total_matched}\n", style="bold green")
    metrics_text.append(f"• Nuevas Postulaciones Registradas: {summary.new_applications}\n", style="bold green")
    metrics_text.append(f"• Re-postulaciones (times_applied + 1): {summary.reapplications}\n", style="bold blue")
    metrics_text.append(f"• Omitidas por Cooldown Activo: {summary.skipped_cooldown}\n", style="yellow")
    metrics_text.append(f"• Descartadas por Hard Reject: {summary.hard_rejected}\n", style="red")

    if summary.offers_by_portal:
        metrics_text.append("\nPor Portal:\n", style="bold underline white")
        for portal, count in summary.offers_by_portal.items():
            metrics_text.append(f"  - {portal}: {count} ofertas\n", style="dim white")

    console.print(Panel(metrics_text, title="Resumen del Escaneo", border_style="green", expand=False))

    # 2. Detailed Table of Processed Items
    if summary.processed_items:
        table = Table(title="Detalle de Vacantes Evaluadas", border_style="dim", header_style="bold cyan")
        table.add_column("Portal", style="dim")
        table.add_column("Título", style="white")
        table.add_column("Empresa", style="bold")
        table.add_column("Match %", justify="center")
        table.add_column("Acción", justify="center")
        table.add_column("Veces", justify="center")

        for item in summary.processed_items:
            score_style = "bold green" if item.evaluation.match_score >= 70 else "yellow" if item.evaluation.match_score >= 40 else "red"
            action_text = "NUEVA" if item.is_new else "RE-POSTULADO" if item.is_reapplication else "COOLDOWN" if item.evaluation.should_apply else "RECHAZADO"
            action_style = "green" if item.is_new else "blue" if item.is_reapplication else "dim yellow" if item.evaluation.should_apply else "dim red"
            times_str = str(item.record.times_applied) if item.record else "-"

            table.add_row(
                item.offer.portal.value,
                item.offer.title[:40],
                item.offer.company[:25],
                f"[{score_style}]{item.evaluation.match_score}%[/{score_style}]",
                f"[{action_style}]{action_text}[/{action_style}]",
                times_str,
            )

        console.print(table)

    # 3. Errors Warning if any
    if summary.errors_by_portal:
        err_text = Text()
        for portal, err in summary.errors_by_portal.items():
            err_text.append(f"[{portal}]: {err}\n", style="bold yellow")
        console.print(Panel(err_text, title="Avisos en Portales (Graceful Degradation)", border_style="yellow", expand=False))


def print_application_stats(
    records: list[ApplicationRecord],
    keyword_stats: list[tuple[str, int, int]],
) -> None:
    # 1. Pipeline Overview Table
    status_counts: dict[ApplicationStatus, int] = {st: 0 for st in ApplicationStatus}
    total_reapplications = 0

    for r in records:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
        if r.times_applied > 1:
            total_reapplications += (r.times_applied - 1)

    pipe_table = Table(title="Pipeline de Postulaciones (SQLite 3NF)", border_style="dim", header_style="bold magenta")
    pipe_table.add_column("Estado de Postulación", style="white")
    pipe_table.add_column("Total Vacantes", justify="center", style="bold")

    for status, count in status_counts.items():
        if count > 0:
            pipe_table.add_row(status.value, str(count))

    console.print(pipe_table)
    console.print(f"[dim]Total registros maestros: {len(records)} | Re-postulaciones históricas: {total_reapplications}[/dim]\n")

    # 2. Market Tech Radar
    if keyword_stats:
        radar_table = Table(title="Radar de Tecnologías del Mercado (Keyword Stats)", border_style="dim", header_style="bold green")
        radar_table.add_column("Tecnología", style="white")
        radar_table.add_column("Demanda (Vacantes)", justify="center", style="bold")
        radar_table.add_column("Cumplidas en tu Perfil", justify="center", style="cyan")
        radar_table.add_column("Cobertura", justify="center")

        for kw, total, matched in keyword_stats[:15]:
            coverage_pct = int((matched / total) * 100) if total > 0 else 0
            cov_style = "bold green" if coverage_pct >= 80 else "yellow" if coverage_pct >= 50 else "red"
            radar_table.add_row(
                kw,
                str(total),
                str(matched),
                f"[{cov_style}]{coverage_pct}%[/{cov_style}]",
            )

        console.print(radar_table)


def print_export_success(format_type: str, file_path: str, count: int) -> None:
    msg = f"Se exportaron exitosamente [bold green]{count}[/bold green] registros en formato [bold]{format_type.upper()}[/bold] a:\n[cyan]{file_path}[/cyan]"
    console.print(Panel(msg, title="Exportación Completa", border_style="green", expand=False))


def print_error(message: str) -> None:
    console.print(f"[bold red]ERROR:[/bold red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]AVISO:[/bold yellow] {message}")
