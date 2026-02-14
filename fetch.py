import asyncio
import ipaddress
import os
import random
import socket
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

import aiohttp
from playwright.async_api import (
    async_playwright, Browser, BrowserContext, Page, Response,
    Error as PlaywrightError,
)
from playwright_stealth import Stealth

MAX_WAIT = 30.0
MAX_SCREENSHOT_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_SCREENSHOT_HEIGHT = 16384


class FetchError(Exception):
    """Raised when a page cannot be fetched."""
    pass


@dataclass
class FetchResult:
    """Result of fetching a page."""
    html: str
    url: str  # final URL after redirects
    status: int
    title: str


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
]

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_stealth = Stealth()
_playwright = None
_browser: Browser | None = None
_browser_lock: asyncio.Lock | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_lock() -> asyncio.Lock:
    global _browser_lock
    if _browser_lock is None:
        _browser_lock = asyncio.Lock()
    return _browser_lock


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(4)
    return _semaphore


# ---------------------------------------------------------------------------
# URL validation (SSRF protection)
# ---------------------------------------------------------------------------

def validate_url(url: str) -> None:
    """Reject URLs targeting internal networks or non-HTTP schemes."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise FetchError(f"Only http and https URLs are supported, got: {parsed.scheme!r}")
    if not parsed.hostname:
        raise FetchError(f"Invalid URL (no hostname): {url}")
    _check_hostname(parsed.hostname)


def _check_hostname(hostname: str) -> None:
    """Resolve hostname and verify it doesn't point to a private/reserved IP."""
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise FetchError(f"Could not resolve hostname: {hostname}")
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        # Handle IPv6-mapped IPv4 addresses (e.g. ::ffff:127.0.0.1)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        for network in PRIVATE_NETWORKS:
            if addr in network:
                raise FetchError(f"Access to private/internal addresses is blocked: {hostname} resolves to {addr}")


# ---------------------------------------------------------------------------
# Browser management
# ---------------------------------------------------------------------------

def _ensure_chromium_installed() -> None:
    """Install Chromium via Playwright if not already present."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True, timeout=300,
            )
    except (FileNotFoundError, subprocess.SubprocessError):
        # --dry-run not supported in older playwright versions; try launching directly
        pass


async def get_browser() -> Browser:
    global _playwright, _browser
    async with _get_lock():
        if _browser is None:
            _ensure_chromium_installed()
            _playwright = await async_playwright().start()
            args = ["--disable-blink-features=AutomationControlled"]
            if os.environ.get("BROWSERFETCH_NO_SANDBOX") == "1":
                args.append("--no-sandbox")
            _browser = await _playwright.chromium.launch(headless=True, args=args)
    return _browser


async def new_page() -> Page:
    browser = await get_browser()
    context: BrowserContext = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1280, "height": 720},
        locale="en-US",
        accept_downloads=False,
    )
    await _stealth.apply_stealth_async(context)
    page = await context.new_page()
    return page


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

async def _navigate(page: Page, url: str) -> Response | None:
    """Navigate to a URL, trying networkidle first then falling back to domcontentloaded."""
    response = None
    try:
        try:
            response = await page.goto(url, wait_until="networkidle", timeout=15000)
        except PlaywrightError as e:
            if _is_fatal_nav_error(e):
                raise
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except PlaywrightError as e:
        msg = str(e)
        if "ERR_NAME_NOT_RESOLVED" in msg:
            raise FetchError(f"Could not resolve domain for URL: {url}")
        if "ERR_CONNECTION_REFUSED" in msg:
            raise FetchError(f"Connection refused for URL: {url}")
        if "ERR_EMPTY_RESPONSE" in msg:
            raise FetchError(f"Server returned an empty response for URL: {url}")
        if "Download is starting" in msg:
            raise FetchError(f"URL points to a downloadable file, not a web page: {url}")
        if "Timeout" in msg:
            raise FetchError(f"Page load timed out for URL: {url}")
        raise FetchError(f"Failed to load URL: {url} ({msg})")
    return response


def _is_fatal_nav_error(e: PlaywrightError) -> bool:
    """Check if a navigation error is fatal and shouldn't be retried."""
    msg = str(e)
    fatal = ["ERR_NAME_NOT_RESOLVED", "ERR_CONNECTION_REFUSED", "ERR_EMPTY_RESPONSE",
             "Download is starting"]
    return any(f in msg for f in fatal)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_page(url: str, wait: float = 2.0, scroll: bool = True) -> FetchResult:
    validate_url(url)
    wait = max(0.0, min(wait, MAX_WAIT))
    async with _get_semaphore():
        page = await new_page()
        try:
            response = await _navigate(page, url)
            status = response.status if response else 0
            final_url = page.url
            # Re-validate after redirects to prevent SSRF via redirect chain
            if final_url != url:
                validate_url(final_url)
            await _dismiss_cookie_banner(page)
            if wait > 0:
                await page.wait_for_timeout(wait * 1000)
            if scroll:
                await _auto_scroll(page)
            html = await page.content()
            title = await page.title()
            return FetchResult(html=html, url=final_url, status=status, title=title)
        finally:
            await page.context.close()


async def take_screenshot(url: str, full_page: bool = False) -> bytes:
    validate_url(url)
    async with _get_semaphore():
        page = await new_page()
        try:
            await _navigate(page, url)
            # Re-validate after redirects to prevent SSRF via redirect chain
            final_url = page.url
            if final_url != url:
                validate_url(final_url)
            await _dismiss_cookie_banner(page)
            await page.wait_for_timeout(1000)
            if full_page:
                height = await page.evaluate("document.body.scrollHeight")
                if height > MAX_SCREENSHOT_HEIGHT:
                    await page.set_viewport_size({"width": 1280, "height": MAX_SCREENSHOT_HEIGHT})
                    full_page = False
            png = await page.screenshot(full_page=full_page, type="png")
            if len(png) > MAX_SCREENSHOT_BYTES:
                raise FetchError(f"Screenshot too large ({len(png) // 1024 // 1024}MB, limit is {MAX_SCREENSHOT_BYTES // 1024 // 1024}MB)")
            return png
        finally:
            await page.context.close()


async def head_check(url: str) -> None:
    """Quick HEAD request to detect non-HTML content before launching browser."""
    validate_url(url)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=5),
                                    allow_redirects=True) as resp:
                # Re-validate the final URL after redirects
                final_url = str(resp.url)
                if final_url != url:
                    validate_url(final_url)
                ct = resp.headers.get("Content-Type", "")
                if ct and not any(t in ct for t in ["text/html", "text/plain", "application/xhtml"]):
                    raise FetchError(
                        f"URL content type is '{ct}', not a web page: {url}"
                    )
    except (aiohttp.ClientError, asyncio.TimeoutError):
        pass  # let Playwright handle network errors


COOKIE_ACCEPT_SELECTORS = [
    # Common "Accept All" / "Accept" buttons by text
    "button:has-text('Accept All')",
    "button:has-text('Accept all')",
    "button:has-text('Accept Cookies')",
    "button:has-text('Accept cookies')",
    "button:has-text('Allow All')",
    "button:has-text('Allow all')",
    "button:has-text('I Agree')",
    "button:has-text('I agree')",
    "button:has-text('Got it')",
    "button:has-text('OK')",
    # Common by ID / class / aria-label
    "[id*='cookie'] button:has-text('Accept')",
    "[class*='cookie'] button:has-text('Accept')",
    "[id*='consent'] button:has-text('Accept')",
    "[class*='consent'] button:has-text('Accept')",
    "[aria-label*='cookie' i] button",
    "[aria-label*='Accept' i][role='button']",
    # OneTrust (very common enterprise cookie manager)
    "#onetrust-accept-btn-handler",
    # Cookiebot
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    # Quantcast / other common frameworks
    ".qc-cmp2-summary-buttons button[mode='primary']",
    "[data-testid='cookie-policy-dialog-accept-button']",
]


async def _dismiss_cookie_banner(page: Page) -> None:
    """Try to click a cookie consent 'Accept' button and remove banner from DOM."""
    clicked = False
    for selector in COOKIE_ACCEPT_SELECTORS:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=200):
                await btn.click(timeout=1000)
                await page.wait_for_timeout(500)
                clicked = True
                break
        except PlaywrightError:
            continue

    if clicked:
        # Remove common cookie banner containers from the DOM so they don't
        # pollute content extraction (banners often stay hidden in the DOM).
        await page.evaluate("""() => {
            const selectors = [
                '#onetrust-banner-sdk', '#onetrust-consent-sdk',
                '#CybotCookiebotDialog', '#cookiebanner',
                '.qc-cmp2-container',
                '[class*="cookie-banner"]', '[class*="cookie-consent"]',
                '[class*="cookieBanner"]', '[class*="cookieConsent"]',
                '[id*="cookie-banner"]', '[id*="cookie-consent"]',
                '[id*="cookieBanner"]', '[id*="cookieConsent"]',
                '[aria-label*="cookie" i]',
            ];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(el => el.remove());
            }
        }""")


async def _auto_scroll(page: Page, max_scrolls: int = 10):
    prev_height = 0
    for _ in range(max_scrolls):
        height = await page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            break
        prev_height = height
        await page.keyboard.press("PageDown")
        await page.wait_for_timeout(500)
    await page.evaluate("window.scrollTo(0, 0)")


async def shutdown():
    global _playwright, _browser
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
