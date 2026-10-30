from collections.abc import Iterator
from contextlib import contextmanager
import json
import logging
from pathlib import Path
import random
import time
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, ViewportSize, sync_playwright

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)

DEFAULT_VIEWPORT: ViewportSize = {"width": 1280, "height": 800}


def human_delay(min_seconds: float = 2.0, max_seconds: float = 4.5) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def smooth_scroll(page: Page, steps: int = 3) -> None:
    for _ in range(steps):
        page.evaluate("window.scrollBy(0, window.innerHeight * 0.7);")
        time.sleep(random.uniform(0.4, 0.9))


@contextmanager
def create_browser_session(
    headless: bool = True,
    storage_state_path: Path | str | None = None,
    user_data_dir: Path | str | None = None,
) -> Iterator[BrowserContext]:
    state_file: str | None = None
    if storage_state_path is not None:
        p = Path(storage_state_path)
        if p.is_file():
            state_file = str(p)

    with sync_playwright() as playwright:
        if user_data_dir is not None:
            data_dir = Path(user_data_dir)
            data_dir.mkdir(parents=True, exist_ok=True)
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(data_dir),
                headless=headless,
                user_agent=DEFAULT_USER_AGENT,
                viewport=DEFAULT_VIEWPORT,
                locale="es-CO",
                timezone_id="America/Bogota",
                extra_http_headers={"Accept-Language": "es-CO,es-419;q=0.9,es;q=0.8,en;q=0.7"},
                args=["--disable-blink-features=AutomationControlled"],
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            if state_file:
                try:
                    with open(state_file, "r", encoding="utf-8") as sf:
                        cookie_data = json.load(sf)
                        cookies = cookie_data.get("cookies", [])
                        if cookies:
                            context.add_cookies(cookies)
                except Exception as ex:
                    logger.debug("No se pudieron cargar cookies de storage_state: %s", ex)
            try:
                yield context
            finally:
                context.close()
        else:
            browser: Browser = playwright.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context_kwargs: dict[str, Any] = {
                "user_agent": DEFAULT_USER_AGENT,
                "viewport": DEFAULT_VIEWPORT,
                "locale": "es-CO",
                "timezone_id": "America/Bogota",
                "extra_http_headers": {"Accept-Language": "es-CO,es-419;q=0.9,es;q=0.8,en;q=0.7"},
            }
            if state_file:
                context_kwargs["storage_state"] = state_file

            context = browser.new_context(**context_kwargs)
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            try:
                yield context
            finally:
                context.close()
                browser.close()
