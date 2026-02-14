import base64
import atexit
import asyncio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image
from fetch import fetch_page, take_screenshot, shutdown
from process import html_to_text

mcp = FastMCP("webfetch")


@mcp.tool()
async def fetch(url: str, wait: float = 2.0, scroll: bool = True) -> str:
    """Fetch a URL and return clean text optimized for LLMs.

    Uses a stealth Playwright browser to bypass bot detection.
    Extracts readable text with markdown-formatted tables and links.

    Args:
        url: The URL to fetch
        wait: Seconds to wait after page load for JS rendering (default 2.0)
        scroll: Auto-scroll to trigger lazy-loaded content (default True)
    """
    html = await fetch_page(url, wait=wait, scroll=scroll)
    return html_to_text(html, base_url=url)


@mcp.tool()
async def screenshot(url: str, full_page: bool = False) -> Image:
    """Take a screenshot of a URL and return it as a PNG image.

    Uses a stealth Playwright browser to bypass bot detection.

    Args:
        url: The URL to screenshot
        full_page: Capture the full scrollable page instead of just the viewport (default False)
    """
    png_bytes = await take_screenshot(url, full_page=full_page)
    return Image(data=base64.b64encode(png_bytes).decode(), format="png")


def _cleanup():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(shutdown())
        else:
            loop.run_until_complete(shutdown())
    except Exception:
        pass


atexit.register(_cleanup)

if __name__ == "__main__":
    mcp.run(transport="stdio")
