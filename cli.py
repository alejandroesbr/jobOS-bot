"""jobOS-bot v2.0 - 4 Nuclear CLI Commands.

Clean Architecture + CQS + Multi-Worker + Obsidian Graph Database.
Only 4 commands: scan, sync, auth, export.
All other operations via MCP server.
"""

from dotenv import load_dotenv
load_dotenv()

import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from src.adapters.db.repository import ApplicationRepository
from src.adapters.obsidian.adapter import ObsidianVaultAdapter
from src.adapters.scrapers.orchestrator import (
    MultiWorkerScraperOrchestrator,
    DEFAULT_PORTAL_REGISTRY,
)
from src.application.commands import (
    ScanPortalsCommand,
    ScanPortalsResult,
    SyncVaultCommand,
    SyncVaultResult,
    SyncExternalCommand,
    SyncExternalResult,
)
from src.application.handlers import (
    ScanPortalsHandler,
    SyncVaultHandler,
    SyncExternalHandler,
)
from src.application.queries import (
    GetApplicationsQuery,
    GetApplicationsResult,
)
from src.application.handlers import GetApplicationsHandler
from src.config_loader import load_filter_config
from src.domain.models import PortalName
from src.ports.repository_port import ApplicationRepositoryPort
from src.ports.vault_port import KnowledgeVaultPort
from src.ports.scraper_port import MultiPortalScraperPort


console = Console()


def print_banner(title: str, subtitle: str = "") -> None:
    console.print(f"\n[bold cyan]═══ {title} ═══[/bold cyan]")
    if subtitle:
        console.print(f"[dim]{subtitle}[/dim]")
    console.print()


def print_error(message: str) -> None:
    console.print(f"[bold red]✗ Error:[/bold red] {message}")


def print_success(message: str) -> None:
    console.print(f"[bold green]✓ {message}[/bold green]")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]⚠ {message}[/bold yellow]")


def print_info(message: str) -> None:
    console.print(f"[cyan]ℹ {message}[/cyan]")


@click.group()
def cli() -> None:
    """jobOS-bot v2.0 — Concurrent Multi-Worker Intelligence Engine with Local Graph Database.

    4 Nuclear Commands:
      scan   - Multi-worker concurrent scan with Obsidian sync
      sync   - Obsidian vault sync (rebuild or incremental)
      auth   - Browser authentication for portals
      export - Export applications to JSON/CSV
    """
    pass


# ============================================================================
# SCAN COMMAND - Multi-worker concurrent scan with Obsidian sync
# ============================================================================

@cli.command(name="scan")
@click.option(
    "--portal",
    "portal_arg",
    default="all",
    help="Portales a escanear: linkedin, getonbrd, computrabajo, elempleo, glassdoor, indeed o all (separados por coma).",
)
@click.option(
    "--limit",
    "limit_arg",
    default=15,
    type=int,
    help="Límite máximo de ofertas a procesar por portal.",
)
@click.option(
    "--headless/--no-headless",
    default=True,
    help="Ejecutar el navegador en modo headless (invisible) o visible.",
)
@click.option(
    "--workers",
    "max_workers",
    default=4,
    type=int,
    help="Número máximo de workers concurrentes (1-6).",
)
@click.option(
    "--db-path",
    default="data/jobs.db",
    help="Ruta al archivo SQLite local.",
)
@click.option(
    "--vault-path",
    default="vault",
    help="Ruta al vault de Obsidian.",
)
@click.option(
    "--no-obsidian",
    is_flag=True,
    default=False,
    help="Desactivar sincronización con Obsidian vault.",
)
@click.option(
    "--schema-v2/--schema-v1",
    default=True,
    help="Usar schema v2.0 con índices compuestos y tablas de métricas.",
)
def scan_cmd(
    portal_arg: str,
    limit_arg: int,
    headless: bool,
    max_workers: int,
    db_path: str,
    vault_path: str,
    no_obsidian: bool,
    schema_v2: bool,
) -> None:
    """Escaneo multi-worker concurrente con aislamiento de BrowserContext y sync a Obsidian."""
    print_banner(
        "jobOS-bot v2.0 — Motor Multi-Worker Concurrente",
        f"Workers: {max_workers} | Headless: {headless} | Obsidian: {'OFF' if no_obsidian else 'ON'}"
    )

    # Parse portals
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

    # Initialize dependencies
    try:
        # Repository with schema v2.0 if requested
        repo = ApplicationRepository(db_path)
        if schema_v2:
            _initialize_schema_v2(repo)

        config = load_filter_config()

        # Multi-worker orchestrator
        orchestrator: MultiPortalScraperPort = MultiWorkerScraperOrchestrator(
            registry=DEFAULT_PORTAL_REGISTRY,
            max_workers=max_workers,
        )

        # Vault adapter (optional)
        vault: KnowledgeVaultPort | None = None
        if not no_obsidian:
            vault = ObsidianVaultAdapter(vault_path)

        # Create and execute command via handler
        command = ScanPortalsCommand(
            portals=portals,
            limit_per_portal=limit_arg,
            headless=headless,
            max_workers=max_workers,
            sync_obsidian=not no_obsidian,
            vault_path=vault_path,
            config=config,
        )

        handler = ScanPortalsHandler(
            repository=repo,
            scraper=orchestrator,
            vault=vault,
        )

        result: ScanPortalsResult = handler.handle(command)

        # Print summary
        _print_scan_summary(result)

    except Exception as ex:
        print_error(f"Error durante el escaneo: {ex}")
        sys.exit(1)
    finally:
        try:
            repo.close()
        except Exception:
            pass


def _initialize_schema_v2(repo: ApplicationRepository) -> None:
    """Initialize schema v2.0 with composite indexes and new tables."""
    schema_path = Path(__file__).parent / "src" / "adapters" / "db" / "schema_v2.sql"
    if schema_path.is_file():
        sql = schema_path.read_text(encoding="utf-8")
        repo._conn.executescript(sql)
        print_info("Schema v2.0 inicializado (índices compuestos, tablas métricas, triggers)")
    else:
        print_warning("schema_v2.sql no encontrado, usando schema v1")


def _print_scan_summary(result: ScanPortalsResult) -> None:
    """Print formatted scan summary."""
    console.print()
    console.print(f"[bold]TOTAL ESCANEADO:[/bold] {result.total_scanned} ofertas")
    console.print(f"[bold]TOTAL MATCH (≥{40}%):[/bold] {result.total_matched}")
    console.print(f"[green]Nuevas postulaciones:[/green] {result.new_applications}")
    console.print(f"[blue]Re-postulaciones:[/blue] {result.reapplications}")
    console.print(f"[yellow]Saltadas por cooldown:[/yellow] {result.skipped_cooldown}")
    console.print(f"[red]Hard rejects:[/red] {result.hard_rejected}")

    if result.offers_by_portal:
        console.print("\n[bold]Por portal:[/bold]")
        for portal, count in result.offers_by_portal.items():
            console.print(f"  {portal}: {count}")

    if result.errors_by_portal:
        console.print("\n[bold red]Errores:[/bold red]")
        for portal, error in result.errors_by_portal.items():
            console.print(f"  {portal}: {error}")

    if result.obsidian_synced:
        console.print(f"\n[bold cyan]Obsidian:[/bold cyan] {result.obsidian_created} creadas, {result.obsidian_updated} actualizadas")

    console.print(f"\n[dim]Tiempo de ejecución: {result.execution_time_ms}ms[/dim]")


# ============================================================================
# SYNC COMMAND - Obsidian vault sync (rebuild or incremental)
# ============================================================================

@cli.command(name="sync")
@click.option(
    "--db-path",
    default="data/jobs.db",
    help="Ruta al archivo SQLite local.",
)
@click.option(
    "--vault-path",
    default="vault",
    help="Ruta al vault de Obsidian.",
)
@click.option(
    "--rebuild/--incremental",
    default=False,
    help="Reconstruir vault completo (borra notas existentes) o sync incremental.",
)
def sync_cmd(db_path: str, vault_path: str, rebuild: bool) -> None:
    """Sincroniza base de datos SQLite con vault Obsidian (Graphify-compatible)."""
    action = "REBUILD completo" if rebuild else "INCREMENTAL"
    print_banner(
        f"jobOS-bot v2.0 — Sync Obsidian Vault ({action})",
        f"DB: {db_path} | Vault: {vault_path}"
    )

    try:
        repo = ApplicationRepository(db_path)
        vault = ObsidianVaultAdapter(vault_path)

        # Get all applications
        applications = repo.find_all(limit=10000)

        if rebuild:
            command = SyncVaultCommand(
                applications=applications,
                vault_path=vault_path,
                full_rebuild=True,
            )
        else:
            command = SyncVaultCommand(
                applications=applications,
                vault_path=vault_path,
                full_rebuild=False,
            )

        handler = SyncVaultHandler(vault=vault)
        result: SyncVaultResult = handler.handle(command)

        print_success(f"Vault sincronizado: {result.created} creadas, {result.updated} actualizadas, {result.hubs_updated} hubs")
        console.print(f"[dim]Tiempo: {result.execution_time_ms}ms[/dim]")

    except Exception as ex:
        print_error(f"Error sincronizando vault: {ex}")
        sys.exit(1)
    finally:
        try:
            repo.close()
        except Exception:
            pass


# ============================================================================
# AUTH COMMAND - Browser authentication for portals
# ============================================================================

PORTAL_LOGIN_URLS: dict[str, str] = {
    "linkedin": "https://www.linkedin.com/login",
    "glassdoor": "https://www.glassdoor.com/profile/login_input.htm",
    "computrabajo": "https://candidato.computrabajo.com/login",
    "elempleo": "https://www.elempleo.com/co/iniciar-sesion",
    "indeed": "https://secure.indeed.com/auth",
    "getonbrd": "https://www.getonbrd.com/login",
}


@cli.command(name="auth")
@click.argument("portal", required=False, default=None)
@click.option(
    "--output",
    "output_path",
    default=None,
    help="Ruta donde se guardará el estado de cookies y tokens de sesión.",
)
def auth_cmd(portal: Optional[str], output_path: Optional[str]) -> None:
    """Abre el navegador en modo visible para iniciar sesión manual en un portal y exportar cookies."""
    from playwright.sync_api import sync_playwright

    portal_name = (portal or "linkedin").strip().lower()
    target_url = PORTAL_LOGIN_URLS.get(portal_name, f"https://www.{portal_name}.com")

    if output_path is not None:
        out_file = Path(output_path)
    else:
        out_file = Path(f"data/sessions/{portal_name}_state.json")

    out_file.parent.mkdir(parents=True, exist_ok=True)

    print_banner(
        f"jobOS-bot v2.0 — Gestor de Autenticación [{portal_name.upper()}]",
        "Inicia sesión manualmente en el navegador y presiona ENTER en la consola cuando termines.",
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/133.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="es-419",
            extra_http_headers={"Accept-Language": "es-419,es;q=0.9,en;q=0.8"},
            timezone_id="America/Bogota",
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        console.print(f"[green]Navegador abierto en:[/green] [cyan]{target_url}[/cyan]")
        console.print("[yellow]Inicia sesión (resuelve Captcha o 2FA si aplica) y luego presiona ENTER en esta terminal...[/yellow]")
        console.print("[dim cyan]💡 Tip: Si el portal te muestra 'Couldn't sign you in' con Google, ingresa con correo y contraseña directa del portal.[/dim cyan]")

        page.goto(target_url)
        input()

        context.storage_state(path=str(out_file))

        # Sincronizar en data/storage_state.json para el motor de escaneo
        default_global_state = Path("data/storage_state.json")
        default_global_state.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(default_global_state))

        context.close()
        browser.close()

    console.print(f"[bold green]✓ Sesión exportada correctamente a:[/bold green] {out_file}")
    console.print(f"[dim]✓ Sincronizado en: {default_global_state}[/dim]")


# ============================================================================
# EXPORT COMMAND - Export applications to JSON/CSV
# ============================================================================

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
def export_cmd(export_format: str, output_arg: Optional[str], status_arg: Optional[str], db_path: str) -> None:
    """Exporta las vacantes registradas en SQLite a formato JSON o CSV."""
    print_banner(
        "jobOS-bot v2.0 — Exportación de Datos",
        f"Formato: {export_format.upper()} | Filtro: {status_arg or 'Todos'}"
    )

    db_file = Path(db_path)
    if not db_file.is_file():
        print_error(f"Base de datos no encontrada en '{db_path}'.")
        sys.exit(1)

    try:
        repo = ApplicationRepository(db_path)

        # Use query handler for consistent data access
        query = GetApplicationsQuery(
            status=status_arg,
            min_match_score=None,
            keyword=None,
            limit=10000,
            offset=0,
        )
        handler = GetApplicationsHandler(repository=repo)
        result: GetApplicationsResult = handler.handle(query)

        out_path = Path(output_arg) if output_arg else Path(f"exports/applications.{export_format.lower()}")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if export_format.lower() == "json":
            data = [
                {
                    "id": app.id,
                    "dedup_key": app.dedup_key,
                    "title": app.title,
                    "company": app.company,
                    "location": app.location,
                    "modality": app.modality,
                    "match_score": app.match_score,
                    "times_applied": app.times_applied,
                    "status": app.status,
                    "first_applied_at": app.first_applied_at,
                    "last_applied_at": app.last_applied_at,
                    "submissions": [
                        {
                            "attempt": s.attempt_number,
                            "portal": s.portal,
                            "url": s.canonical_url,
                            "applied_at": s.applied_at,
                        }
                        for s in app.submissions
                    ],
                    "keywords": [
                        {"keyword": k.keyword, "matched": k.is_matched, "weight": int(k.weight)}
                        for k in app.keywords
                    ],
                }
                for app in result.applications
            ]
            out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            import csv
            with out_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "ID", "Título", "Empresa", "Ubicación", "Modalidad",
                    "Match %", "Veces Postulado", "Estado", "Primer Intento", "Último Intento"
                ])
                for app in result.applications:
                    writer.writerow([
                        app.id, app.title, app.company, app.location, app.modality,
                        app.match_score, app.times_applied, app.status,
                        app.first_applied_at or "", app.last_applied_at or ""
                    ])

        print_success(f"Exportado {len(result.applications)} registros a {out_path}")

    except Exception as ex:
        print_error(f"Error exportando: {ex}")
        sys.exit(1)
    finally:
        try:
            repo.close()
        except Exception:
            pass


if __name__ == "__main__":
    cli()