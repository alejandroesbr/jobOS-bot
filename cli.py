import csv
import json
from pathlib import Path
import sys
from typing import Any

import click
from dotenv import load_dotenv

load_dotenv()
from rich.markdown import Markdown

from src.adapters.db.repository import ApplicationRepository
from src.config_loader import load_filter_config
from src.domain.models import ApplicationStatus, PortalName
from src.services.assist_service import AssistService
from src.services.career_service import CareerService
from src.services.cv_service import CvService
from src.services.scan_service import ScanService
from src.ui.console import (
    console,
    print_application_stats,
    print_banner,
    print_error,
    print_export_success,
    print_pending_applications_table,
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
    default=False,
    help="Ejecutar el navegador de forma invisible (headless) o visible. Con HEADLESS=true en el entorno siempre es invisible.",
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


@cli.command(name="cv")
@click.argument("targets", nargs=-1, required=False)
@click.option("--all", "-a", "all_pending", is_flag=True, default=False, help="Generar CV para todas las vacantes pendientes.")
@click.option("--min-score", default=None, type=int, help="Con --all, solo vacantes con afinidad mínima (ej. 60).")
@click.option("--force", is_flag=True, default=False, help="Regenerar el PDF aunque ya exista.")
@click.option("--db-path", default="data/jobs.db", help="Ruta al archivo SQLite local.")
def cv_cmd(targets: tuple[str, ...], all_pending: bool, min_score: int | None, force: bool, db_path: str) -> None:
    """Genera un PDF de tu CV adaptado a cada vacante (ej. 'cv 4 7' o 'cv --all --min-score 60'). No postula."""
    from src.adapters.pdf.cv_renderer import PlaywrightPdfRenderer

    if not Path(db_path).is_file():
        print_error(f"Base de datos no encontrada en '{db_path}'. Ejecuta un escaneo primero con 'scan'.")
        sys.exit(1)

    repo = ApplicationRepository(db_path)
    try:
        ids: list[int] = []
        for t in targets:
            for token in t.replace(",", " ").split():
                if token.isdigit():
                    ids.append(int(token))
                else:
                    print_warning(f"'{token}' no es un ID numérico. Omitiendo.")

        if all_pending:
            pending = repo.find_all(status=ApplicationStatus.PENDING, limit=500)
            ids += [r.id for r in pending if min_score is None or r.match_score >= min_score]

        ids = list(dict.fromkeys(ids))
        if not ids:
            print_warning("No hay vacantes para procesar. Indica IDs (ej. 'cv 4 7') o usa '--all'.")
            return

        service = CvService(repository=repo)
        print_banner("jobOS-bot — CV Personalizado por Vacante", f"{len(ids)} vacante(s) — salida en '{service.output_dir}/'")
        generated = 0
        with PlaywrightPdfRenderer() as renderer:
            for app_id in ids:
                try:
                    result = service.generate(app_id, renderer, force=force)
                except FileNotFoundError as ex:
                    print_error(str(ex))
                    sys.exit(1)
                except Exception as ex:
                    print_error(f"Vacante #{app_id}: {ex}")
                    continue
                if result.reused_existing:
                    console.print(f"[dim]#{app_id} ya tenía CV:[/dim] [cyan]{result.pdf_path}[/cyan] [dim](usa --force para regenerar)[/dim]")
                else:
                    generated += 1
                    console.print(f"[green]✓ #{app_id}[/green] [cyan]{result.pdf_path}[/cyan] [dim](resumen: {result.summary_source})[/dim]")

        console.print(f"\n[bold green]CV generados: {generated}/{len(ids)}[/bold green]")
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
@click.argument("targets", nargs=-1, required=False)
@click.option("--all", "-a", "all_pending", is_flag=True, default=False, help="Procesar todas las vacantes pendientes en cola automáticamente sin preguntar.")
@click.option("--min-score", default=None, type=int, help="Filtrar vacantes con puntaje mínimo de afinidad (ej. 70).")
@click.option("--top", default=None, type=int, help="Procesar las mejores N vacantes pendientes en cola.")
@click.option("--headless", is_flag=True, default=False, help="Ejecutar el navegador en segundo plano sin interfaz gráfica.")
@click.option("--db-path", default="data/jobs.db", help="Ruta al archivo SQLite local.")
def assist_cmd(
    targets: tuple[str, ...],
    all_pending: bool,
    min_score: int | None,
    top: int | None,
    headless: bool,
    db_path: str,
) -> None:
    """Abre el navegador en modo copiloto y autocompleta el formulario de postulación.

    Permite enviar múltiples IDs en una sola línea (ej. 'python cli.py assist 1 3 5' o '1,3,5')
    o URLs directas. Sin argumentos, muestra la lista de vacantes prioritarias pendientes.
    """
    db_file = Path(db_path)
    if not db_file.is_file():
        print_error(f"Base de datos no encontrada en '{db_path}'. Ejecuta un escaneo primero con 'scan'.")
        sys.exit(1)

    repo = ApplicationRepository(db_path)
    try:
        # 1. Parse tokens from arguments
        tokens: list[str] = []
        for t in targets:
            for sub in t.replace(",", " ").split():
                if sub.strip():
                    tokens.append(sub.strip())

        # 2. If no tokens provided, check options or show interactive table
        if not tokens:
            pending_records = repo.find_all(status=ApplicationStatus.PENDING, limit=100)
            if not pending_records:
                print_warning("No hay vacantes en estado 'Pendiente' en la base de datos.")
                return

            if min_score is not None:
                pending_records = [r for r in pending_records if r.match_score >= min_score]

            if top is not None:
                pending_records = pending_records[:top]

            if all_pending or top is not None or (min_score is not None and not targets):
                tokens = [str(r.id) for r in pending_records]
                if not tokens:
                    msg = f" con Match >= {min_score}%" if min_score is not None else ""
                    print_warning(f"No se encontraron vacantes pendientes{msg}.")
                    return
            else:
                print_pending_applications_table(pending_records[:15])
                console.print("\n[bold cyan]Selecciona las vacantes que deseas postular:[/bold cyan]")
                prompt_input = click.prompt(
                    "Ingresa uno o varios IDs (ej. '1 3 5' o '1,3,5') o 'q' para salir",
                    default="q",
                )
                if prompt_input.strip().lower() in {"q", "quit", "exit"}:
                    return
                for sub in prompt_input.replace(",", " ").split():
                    if sub.strip():
                        tokens.append(sub.strip())

        # 3. Resolve items to process
        items_to_process: list[tuple[int | None, str, str, str, int | None]] = []
        for token in tokens:
            if token.isdigit():
                app_id = int(token)
                record = repo.find_by_id(app_id)
                if not record:
                    print_warning(f"Vacante con ID #{app_id} no existe en SQLite. Omitiendo.")
                    continue
                url = record.submissions[-1].canonical_url if record.submissions else None
                if not url:
                    print_warning(f"La vacante #{app_id} ({record.company} - {record.title}) no tiene URL registrada.")
                    continue
                items_to_process.append((app_id, url, record.title, record.company, record.match_score))
            elif token.startswith("http://") or token.startswith("https://"):
                items_to_process.append((None, token, "Postulación Directa", "Web", None))
            else:
                print_warning(f"Valor '{token}' no es un ID numérico ni una URL válida. Omitiendo.")

        if not items_to_process:
            print_warning("No hay vacantes válidas para procesar.")
            return

        # 4. Process each item sequentially in the queue
        service = AssistService(repository=repo)
        total_items = len(items_to_process)
        completed_count = 0

        for idx, (target_id, target_url, target_title, target_company, target_score) in enumerate(items_to_process, 1):
            score_text = f" | Afinidad: [bold green]{target_score}%[/bold green]" if target_score is not None else ""
            id_text = f"Vacante #{target_id}" if target_id else "Postulación Directa"
            print_banner(
                f"jobOS-bot — Cola de Postulación ({idx}/{total_items})",
                f"{id_text}: {target_company} — {target_title}{score_text}",
            )
            console.print(f"[dim]URL: {target_url}[/dim]\n")

            try:
                service.run_assist(
                    target_url,
                    application_id=target_id,
                    headless=headless,
                )
                completed_count += 1
            except KeyboardInterrupt:
                console.print("\n[yellow]Cola de postulación pausada por el usuario (Ctrl+C).[/yellow]")
                break
            except Exception as ex:
                print_error(f"Fallo asistiendo vacante {id_text}: {ex}")

            if idx < total_items:
                console.print(f"\n[bold cyan]✓ Completada {idx}/{total_items}. Pasando a la siguiente vacante en cola...[/bold cyan]\n")

        console.print(
            f"\n[bold green]Sesión de asistencia finalizada:[/bold green] {completed_count}/{total_items} vacante(s) procesadas con éxito.\n"
        )
    finally:
        repo.close()


@cli.command(name="autopilot")
@click.option(
    "--portal",
    "portal_arg",
    default="all",
    help="Portal a escanear: linkedin, getonbrd, computrabajo o all (separados por coma).",
)
@click.option(
    "--limit",
    "limit_arg",
    default=15,
    type=int,
    help="Límite máximo de ofertas a inspeccionar por portal. Por defecto 15.",
)
@click.option(
    "--headless",
    is_flag=True,
    default=False,
    help="Ejecutar navegadores en segundo plano sin interfaz gráfica.",
)
@click.option(
    "--db-path",
    default="data/jobs.db",
    help="Ruta al archivo SQLite local.",
)
def autopilot_cmd(
    portal_arg: str,
    limit_arg: int,
    headless: bool,
    db_path: str,
) -> None:
    """Ejecuta el ciclo desatendido: Escaneo -> Sync Notion. Nunca postula; usa 'assist' para eso."""
    print_banner(
        "jobOS-bot — Piloto Automático",
        "Pipeline desatendido: 1. Escaneo Multi-Portal -> 2. Sync Notion (sin postular)",
    )

    portals: list[PortalName] = []
    if portal_arg.lower().strip() == "all":
        portals = list(PortalName)
    else:
        for p in portal_arg.split(","):
            cleaned = p.strip().lower()
            try:
                portals.append(PortalName(cleaned))
            except ValueError:
                print_warning(f"Portal '{cleaned}' ignorado. Válidos: {[e.value for e in PortalName]}")

    if not portals:
        print_error("No se especificaron portales válidos.")
        sys.exit(1)

    repo = ApplicationRepository(db_path)
    config = load_filter_config()
    scan_service = ScanService(repository=repo, config=config)

    try:
        # FASE 1: Escaneo y clasificación
        console.print("\n[bold cyan]━━━ FASE 1: Escaneo y descubrimiento de vacantes ━━━[/bold cyan]\n")
        scan_summary = scan_service.run_scan_pipeline(
            portals=portals,
            limit_per_portal=limit_arg,
            headless=headless,
        )
        print_scan_summary(scan_summary)

        # FASE 2: Sincronización y CRM
        console.print("\n[bold cyan]━━━ FASE 2: Sincronización con Notion CRM y Seguimiento ━━━[/bold cyan]\n")
        try:
            career_service = CareerService(repository=repo)
            report = career_service.sync_with_notion()
            console.print(f"[green]• Vacantes nuevas enviadas a Notion (Push):[/green] {report.pushed_new}")
            console.print(f"[blue]• Re-postulaciones actualizadas en Notion:[/blue] {report.updated_existing}")
            console.print(f"[yellow]• Postulaciones marcadas para seguimiento (+7 días):[/yellow] {report.stalled_followups}")
        except Exception as ex:
            console.print(f"[yellow]Sincronización omitida o no configurada: {ex}[/yellow]")

        console.print("\n[bold green]══════════════════════════════════════════════════════════[/bold green]")
        console.print("[bold green]✓ Ciclo de Piloto Automático completado con éxito.[/bold green]")
        console.print("[bold green]══════════════════════════════════════════════════════════[/bold green]\n")
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

    print_banner(
        "jobOS-bot — Gestor de Autenticación de Portales",
        "Inicia sesión en tus portales preferidos y presiona ENTER en la terminal para guardar cookies.",
    )
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    user_dir = Path("data/browser_profile")
    user_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_dir),
            headless=False,
            locale="es-CO",
            timezone_id="America/Bogota",
            extra_http_headers={"Accept-Language": "es-CO,es-419;q=0.9,es;q=0.8,en;q=0.7"},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        console.print("[green]✓ Navegador abierto con perfil persistente en 'data/browser_profile'.[/green]")
        console.print("[dim]Accede a LinkedIn, GetOnBrd, Computrabajo, etc. e inicia sesión con tus cuentas.[/dim]")
        console.print("[bold yellow]IMPORTANTE: No cierres la ventana del navegador todavía.[/bold yellow]")
        console.print("[bold yellow]Una vez hayas iniciado sesión en tus portales, presiona ENTER aquí en la terminal...[/bold yellow]\n")

        try:
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass

        try:
            input()
        except EOFError:
            pass

        try:
            context.storage_state(path=str(out_file))
            console.print(f"[bold green]✓ Sesión y cookies exportadas correctamente a:[/bold green] [cyan]{out_file}[/cyan]")
        except Exception as ex:
            console.print(f"[bold yellow]AVISO:[/bold yellow] La ventana del navegador se cerró antes de exportar '{out_file}'.")
            console.print("[dim]Tus cookies ya quedaron guardadas automáticamente en disco en 'data/browser_profile'.[/dim]")
            console.print("[dim]Si necesitas generar el archivo JSON para Docker o GitHub Actions, mantén la ventana abierta hasta presionar ENTER.[/dim]")
        finally:
            try:
                context.close()
            except Exception:
                pass


if __name__ == "__main__":
    cli()
