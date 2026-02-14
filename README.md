# browserfetch

An MCP server that fetches web pages using a stealth Playwright browser and returns clean, LLM-optimized text.

Claude Code's built-in `WebFetch` tool uses a simple HTTP client that gets blocked by many websites. `browserfetch` uses a headless Chromium browser with stealth patches to bypass bot detection, handles JavaScript-rendered content, and returns clean markdown-formatted text.

## Tools

### `fetch`

Fetch a URL and return clean text optimized for LLMs.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | *required* | The URL to fetch |
| `wait` | number | `2.0` | Seconds to wait after page load for JS rendering (max 30) |
| `scroll` | boolean | `true` | Auto-scroll to trigger lazy-loaded content |
| `max_chars` | integer | `40000` | Maximum characters to return. Set to `0` for no limit |
| `readability` | boolean | `true` | Extract only the main article content. Set to `false` for homepages or index pages |

### `screenshot`

Take a screenshot of a URL and return it as a PNG image.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | *required* | The URL to screenshot |
| `full_page` | boolean | `false` | Capture the full scrollable page (capped at 16384px height) |

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
cd ~/projects/browserfetch
uv sync
uv run playwright install chromium
```

Register with Claude Code:

```bash
claude mcp add --transport stdio -s user browserfetch -- uv run --directory ~/projects/browserfetch python server.py
```

## Security

- **SSRF protection**: URLs are validated against private/reserved IP ranges before fetching. Redirect targets are also validated.
- **Scheme restriction**: Only `http` and `https` URLs are accepted.
- **Content-type pre-check**: A HEAD request detects non-HTML content (PDFs, images, etc.) before launching the browser.
- **Resource limits**: Wait time is capped at 30s, screenshots at 20MB / 16384px height, and concurrent requests are limited to 4.
- **Chromium sandbox**: The browser runs with Chromium's security sandbox enabled by default. Set `BROWSERFETCH_NO_SANDBOX=1` only if running as root in Docker.

## Dependencies

- [mcp](https://pypi.org/project/mcp/) — FastMCP server framework
- [playwright](https://playwright.dev/python/) — Browser automation
- [playwright-stealth](https://pypi.org/project/playwright-stealth/) — Anti-detection patches
- [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/) — HTML parsing
- [inscriptis](https://github.com/weblyzard/inscriptis) — Semantic HTML-to-text conversion
- [trafilatura](https://trafilatura.readthedocs.io/) — Main content extraction
- [minify-html](https://pypi.org/project/minify-html/) — HTML minification
- [aiohttp](https://docs.aiohttp.org/) — Async HTTP for HEAD pre-checks

## License

MIT
