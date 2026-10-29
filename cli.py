import csv
import json
from pathlib import Path
import sys
from typing import Any

import click
from rich.markdown import Markdown

from src.adapters.db.repository import ApplicationRepository
from src.config_loader import load_filter_config
from src.domain.models import ApplicationStatus, PortalName
from src.services.assist_service import AssistService
from src.services.career_service import CareerService
from src.services.scan_service import ScanService
from src.ui.console import (
    console,
    print_application_stats,
    print_banner,
    print_error,
    print_export_success,
    print_scan_summary,
    print_warning,
)


@click.group()
def cli() -> None:
    """jobOS-bot — Asistente de Búsqueda Laboral y Automatización Hexagonal."""
    pass


@cli.command(name="scan")
@click.option(
    "--portal",
    "portal_arg",
    default="all",
    help="Portal a escanear: linkedin, getonbrd, computrabajo, elempleo, glassdoor, indeed o all (separados por coma).",
)
@click.option(
    "--limit",
    "limit_arg",
    default=10,
    type=int,
    help="Límite máximo de ofertas a procesar por portal.",
)
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Ejecutar el navegador de forma invisible (headless) o visible.",
)
@click.option(
    "--db-path",
    default="data/jobs.db",
    help="Ruta al archivo SQLite local.",
)
def scan_cmd(portal_arg: str, limit_arg: int, headless: bool, db_path: str) -> None:
    """Escanea portales de empleo de forma secuencial single-thread y registra postulaciones."""
    print_banner("jobOS-bot — Motor de Escaneo Multi-Portal", "Ejecución secuencial single-thread con graceful degradation")

    portals: list[PortalName] = []
    if portal_arg.lower().strip() == "all":
        portals = list(PortalName)
    else:
        for p in portal_arg.split(","):
            cleaned = p.strip().lower()
            try:
                portals.append(PortalName(cleaned))
            except ValueError:
                print_warning(f"Portal desconocido '{cleaned}' ignorado. Válidos: {[e.value for e in PortalName]}")

    if not portals:
        print_error("No se especificaron portales válidos para el escaneo.")
        sys.exit(1)

    repo = ApplicationRepository(db_path)
    config = load_filter_config()
    service = ScanService(repository=repo, config=config)

    try:
        summary = service.run_scan_pipeline(
            portals=portals,
            limit_per_portal=limit_arg,
            headless=headless,
        )
        print_scan_summary(summary)
    finally:
        repo.close()


@cli.command(name="stats")
@click.option(
    "--db-path",
    default="data/jobs.db",
    help="Ruta al archivo SQLite local.",
)
def stats_cmd(db_path: str) -> None:
    """Muestra estadísticas actuales del pipeline y radar de tecnologías más demandadas."""
    print_banner("jobOS-bot — Estadísticas y Radar de Mercado", "Resumen de aplicaciones SQLite 3NF")
    db_file = Path(db_path)
    if not db_file.is_file():
        print_warning(f"No existe la base de datos en '{db_path}'. Ejecuta un escaneo primero con 'scan'.")
        return

    repo = ApplicationRepository(db_path)
    try:
        records = repo.find_all(limit=500)
        kw_stats = repo.get_keyword_stats()
        print_application_stats(records, kw_stats)
    finally:
        repo.close()


@cli.command(name="export")
@click.option(
    "--format",
    "export_format",
    type=click.Choice(["json", "csv"], case_sensitive=False),
    default="json",
    help="Formato de exportación (json o csv).",
)
@click.option(
    "--output",
    "output_arg",
    default=None,
    help="Ruta del archivo de salida. Por defecto 'exports/applications.<formato>'.",
)
@click.option(
    "--status",
    "status_arg",
    default=None,
    help="Filtrar por estado específico (ej. 'Enviado', 'Entrevista Programada').",
)
@click.option(
    "--db-path",
    default="data/jobs.db",
    help="Ruta al archivo SQLite local.",
)
def export_cmd(export_format: str, output_arg: str | None, status_arg: str | None, db_path: str) -> None:
    """Exporta las vacantes registradas en SQLite a formato JSON o CSV."""
    db_file = Path(db_path)
    if not db_file.is_file():
        print_error(f"Base de datos no encontrada en '{db_path}'.")
        sys.exit(1)

    repo = ApplicationRepository(db_path)
    try:
        app_status = ApplicationStatus(status_arg) if status_arg else None
        records = repo.find_all(status=app_status, limit=1000)

        out_path = Path(output_arg) if output_arg else Path(f"exports/applications.{export_format.lower()}")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if export_format.lower() == "json":
            data = [
                {
                    "id": r.id,
                    "dedup_key": r.dedup_key,
                    "title": r.title,
                    "company": r.company,
                    "location": r.location,
                    "modality": r.modality.value,
                    "match_score": r.match_score,
                    "times_applied": r.times_applied,
                    "status": r.status.value,
                    "first_applied_at": r.first_applied_at,
                    "last_applied_at": r.last_applied_at,
                    "submissions": [
                        {
                            "attempt": s.attempt_number,
                            "portal": s.portal.value,
                            "url": s.canonical_url,
                            "applied_at": s.applied_at,
                        }
                        for s in r.submissions
                    ],
                    "keywords": [
                        {"keyword": k.keyword, "matched": k.is_matched, "weight": int(k.weight)}
                        for k in r.keywords
                    ],
                }
                for r in records
            ]
            out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            with out_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "ID", "Título", "Empresa", "Ubicación", "Modalidad",
                    "Match %", "Veces Postulado", "Estado", "Primer Intento", "Último Intento"
                ])
                for r in records:
                    writer.writerow([
                        r.id, r.title, r.company, r.location, r.modality.value,
                        r.match_score, r.times_applied, r.status.value,
                        r.first_applied_at or "", r.last_applied_at or ""
                    ])

        print_export_success(export_format, str(out_path), len(records))
    finally:
        repo.close()


@cli.command(name="tailor")
@click.argument("job_id", type=int)
@click.option("--db-path", default="data/jobs.db", help="Ruta al archivo SQLite local.")
def tailor_cmd(job_id: int, db_path: str) -> None:
    """Optimiza tu CV para una vacante específica detectando la brecha de keywords ATS."""
    repo = ApplicationRepository(db_path)
    try:
        service = CareerService(repository=repo)
        analysis = service.tailor_cv(job_id)
        print_banner(f"jobOS-bot — Adaptación Quirúrgica de CV (Vacante #{job_id})")
        console.print(Markdown(analysis))
    except Exception as ex:
        print_error(str(ex))
        sys.exit(1)
    finally:
        repo.close()


@cli.command(name="prep")
@click.argument("job_id", type=int)
@click.option("--db-path", default="data/jobs.db", help="Ruta al archivo SQLite local.")
def prep_cmd(job_id: int, db_path: str) -> None:
    """Genera una guía técnica completa de entrevista (preguntas, live coding y preguntas para el entrevistador)."""
    repo = ApplicationRepository(db_path)
    try:
        service = CareerService(repository=repo)
        out_path = service.prepare_interview(job_id)
        print_banner(f"jobOS-bot — Preparador de Entrevista Técnica (Vacante #{job_id})")
        console.print(f"[bold green]Guía técnica generada con éxito en:[/bold green] [cyan]{out_path}[/cyan]")
    except Exception as ex:
        print_error(str(ex))
        sys.exit(1)
    finally:
        repo.close()


@cli.command(name="sync")
@click.option("--db-path", default="data/jobs.db", help="Ruta al archivo SQLite local.")
def sync_cmd(db_path: str) -> None:
    """Sincroniza la base de datos local con Notion y detecta follow-ups estancados."""
    print_banner("jobOS-bot — Sincronizador con Notion y Detección de Follow-ups")
    repo = ApplicationRepository(db_path)
    try:
        service = CareerService(repository=repo)
        report = service.sync_with_notion()
        console.print(f"[green]• Vacantes nuevas enviadas a Notion (Push):[/green] {report.pushed_new}")
        console.print(f"[blue]• Re-postulaciones actualizadas en Notion:[/blue] {report.updated_existing}")
        console.print(f"[cyan]• Cambios de estado leídos desde Notion (Pull):[/cyan] {report.pulled_statuses}")
        console.print(f"[magenta]• Guías técnicas generadas automáticamente:[/magenta] {report.interview_preps_triggered}")
        console.print(f"[yellow]• Postulaciones marcadas para seguimiento (+7 días):[/yellow] {report.stalled_followups}")
        if report.bootstrapped_from_notion > 0:
            console.print(f"[bold green]• Vacantes restauradas desde Notion (Bootstrap Multi-PC):[/bold green] {report.bootstrapped_from_notion}")
    except Exception as ex:
        print_error(str(ex))
        sys.exit(1)
    finally:
        repo.close()


@cli.command(name="assist")
@click.argument("url")
@click.option("--db-path", default="data/jobs.db", help="Ruta al archivo SQLite local.")
def assist_cmd(url: str, db_path: str) -> None:
    """Abre el navegador en modo copiloto y autocompleta el formulario de postulación."""
    repo = ApplicationRepository(db_path)
    try:
        service = AssistService(repository=repo)
        service.run_assist(url)
    except Exception as ex:
        print_error(str(ex))
        sys.exit(1)
    finally:
        repo.close()


@cli.command(name="auth")
@click.option(
    "--output",
    "output_path",
    default="data/storage_state.json",
    help="Ruta donde se guardará el estado de cookies y tokens de sesión.",
)
def auth_cmd(output_path: str) -> None:
    """Abre el navegador en modo visible para iniciar sesión manual y exportar storage_state.json."""
    from playwright.sync_api import sync_playwright

    print_banner("jobOS-bot — Gestor de Autenticación de Portales", "Inicia sesión en tus portales preferidos y cierra el navegador cuando termines.")
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        console.print("[green]Navegador abierto. Accede a LinkedIn, GetOnBrd, Computrabajo, etc. e inicia sesión.[/green]")
        console.print("[yellow]Presiona ENTER en esta terminal una vez hayas iniciado sesión para guardar tus cookies...[/yellow]")

        page.goto("https://www.linkedin.com/login")
        input()

        context.storage_state(path=str(out_file))
        context.close()
        browser.close()

    console.print(f"[bold green]Sesión exportada correctamente a:[/bold green] {out_file}")


if __name__ == "__main__":
    cli()
