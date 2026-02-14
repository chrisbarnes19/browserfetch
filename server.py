import asyncio
import sys
import time
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image
from fetch import fetch_page, take_screenshot, head_check, shutdown, FetchError, FetchResult
from process import html_to_text, extract_main_content

mcp = FastMCP("browserfetch")

# Simple TTL cache: {url: (timestamp, FetchResult)}
_cache: dict[str, tuple[float, FetchResult]] = {}
_CACHE_TTL = 300  # 5 minutes
_CACHE_MAX_ENTRIES = 20
_CACHE_MAX_BYTES = 50 * 1024 * 1024  # 50 MB total HTML in cache

MAX_CHARS_LIMIT = 500_000


def _cache_size_bytes() -> int:
    return sum(len(r.html.encode("utf-8", errors="replace")) for _, r in _cache.values())


def _get_cached(url: str) -> FetchResult | None:
    if url in _cache:
        ts, result = _cache[url]
        if time.time() - ts < _CACHE_TTL:
            return result
        del _cache[url]
    return None


def _set_cached(url: str, result: FetchResult) -> None:
    _cache[url] = (time.time(), result)
    # Evict oldest entries if over limits (dict maintains insertion order)
    while len(_cache) > _CACHE_MAX_ENTRIES or _cache_size_bytes() > _CACHE_MAX_BYTES:
        if not _cache:
            break
        oldest_key = next(iter(_cache))
        del _cache[oldest_key]


@mcp.tool()
async def fetch(url: str, wait: float = 2.0, scroll: bool = True,
                max_chars: int = 40000, readability: bool = True) -> str:
    """Fetch a URL and return clean text optimized for LLMs.

    Uses a stealth Playwright browser to bypass bot detection.
    Extracts readable text with markdown-formatted tables and links.

    Args:
        url: The URL to fetch
        wait: Seconds to wait after page load for JS rendering (default 2.0, max 30.0)
        scroll: Auto-scroll to trigger lazy-loaded content (default True)
        max_chars: Maximum characters to return (default 40000, max 500000). Set to 0 for max.
        readability: Extract only the main article content, removing boilerplate (default True). Set to False for homepages or index pages where you want everything.
    """
    # Cap max_chars to prevent memory exhaustion
    if max_chars <= 0 or max_chars > MAX_CHARS_LIMIT:
        max_chars = MAX_CHARS_LIMIT

    try:
        await head_check(url)
        cached = _get_cached(url)
        if cached:
            result = cached
        else:
            result = await fetch_page(url, wait=wait, scroll=scroll)
            _set_cached(url, result)
    except FetchError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: unexpected failure fetching {url}: {e}"

    if readability:
        text = extract_main_content(result.html, base_url=result.url)
    else:
        text = html_to_text(result.html, base_url=result.url)

    # Build header with metadata
    header_parts = [f"Title: {result.title}"] if result.title else []
    if result.url != url:
        header_parts.append(f"Redirected to: {result.url}")
    if result.status and result.status >= 400:
        header_parts.append(f"HTTP {result.status}")
    header = "\n".join(header_parts)
    if header:
        text = header + "\n\n" + text

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[Truncated — {len(text)} total characters, showing first {max_chars}]"
    return text


@mcp.tool()
async def screenshot(url: str, full_page: bool = False) -> Image:
    """Take a screenshot of a URL and return it as a PNG image.

    Uses a stealth Playwright browser to bypass bot detection.

    Args:
        url: The URL to screenshot
        full_page: Capture the full scrollable page instead of just the viewport (default False)
    """
    try:
        await head_check(url)
        png_bytes = await take_screenshot(url, full_page=full_page)
    except FetchError as e:
        raise ValueError(str(e))
    except Exception as e:
        raise ValueError(f"Unexpected failure screenshotting {url}: {e}")
    return Image(data=png_bytes, format="png")


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    finally:
        asyncio.run(shutdown())
