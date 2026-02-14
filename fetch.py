import random
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth

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
    )
    await _stealth.apply_stealth_async(context)
    page = await context.new_page()
    return page


async def fetch_page(url: str, wait: float = 2.0, scroll: bool = True) -> str:
    page = await new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        if wait > 0:
            await page.wait_for_timeout(wait * 1000)
        if scroll:
            await _auto_scroll(page)
        return await page.content()
    finally:
        await page.context.close()


async def take_screenshot(url: str, full_page: bool = False) -> bytes:
    page = await new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
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


async def shutdown():
    global _playwright, _browser
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
