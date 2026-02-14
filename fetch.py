import asyncio
import random
from dataclasses import dataclass
from playwright.async_api import (
    async_playwright, Browser, BrowserContext, Page, Response,
    Error as PlaywrightError,
)
from playwright_stealth import Stealth


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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

_stealth = Stealth()
_playwright = None
_browser: Browser | None = None
_semaphore = asyncio.Semaphore(4)


async def get_browser() -> Browser:
    global _playwright, _browser
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
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


async def _navigate(page: Page, url: str) -> Response:
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


async def fetch_page(url: str, wait: float = 2.0, scroll: bool = True) -> FetchResult:
    async with _semaphore:
        page = await new_page()
        try:
            response = await _navigate(page, url)
            status = response.status if response else 0
            final_url = page.url
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
    async with _semaphore:
        page = await new_page()
        try:
            await _navigate(page, url)
            await page.wait_for_timeout(1000)
            return await page.screenshot(full_page=full_page, type="png")
        finally:
            await page.context.close()


async def _auto_scroll(page: Page, max_scrolls: int = 10):
    prev_height = 0
    for _ in range(max_scrolls):
        height = await page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            break
        prev_height = height
        await page.keyboard.press("PageDown")
        await page.wait_for_timeout(500)
    # scroll back to top
    await page.evaluate("window.scrollTo(0, 0)")


async def head_check(url: str) -> None:
    """Quick HEAD request to detect non-HTML content before launching full browser."""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=5),
                                     allow_redirects=True) as resp:
                ct = resp.headers.get("Content-Type", "")
                if ct and not any(t in ct for t in ["text/html", "text/plain", "application/xhtml"]):
                    raise FetchError(
                        f"URL content type is '{ct}', not a web page: {url}"
                    )
    except aiohttp.ClientError:
        pass  # let Playwright handle it
    except asyncio.TimeoutError:
        pass  # let Playwright handle it


async def shutdown():
    global _playwright, _browser
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
