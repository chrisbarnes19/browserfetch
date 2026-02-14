# browserfetch

An MCP server that fetches web pages using a stealth Playwright browser and returns clean, LLM-optimized text.

Claude Code's built-in `WebFetch` tool uses a simple HTTP client that gets blocked by many websites. `browserfetch` uses a headless Chromium browser with stealth patches to bypass bot detection, handles JavaScript-rendered content, and returns clean markdown-formatted text.

## Install as Claude Code Plugin

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+. Chromium is installed automatically on first use.

```bash
# Add the marketplace and install the plugin
/plugin marketplace add chrisbarnes19/browserfetch
/plugin install browserfetch@chrisbarnes19-browserfetch
```

## Manual Setup

If you prefer to clone and register manually:

```bash
git clone https://github.com/chrisbarnes19/browserfetch.git ~/projects/browserfetch
cd ~/projects/browserfetch
uv sync
claude mcp add --transport stdio -s user browserfetch -- uv run --directory ~/projects/browserfetch python server.py
```

Chromium will be installed automatically the first time the server starts.

## Tools

### `fetch`

Fetch a URL and return clean text optimized for LLMs.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | *required* | The URL to fetch |
| `wait` | number | `2.0` | Seconds to wait after page load for JS rendering (max 30) |
| `scroll` | boolean | `true` | Auto-scroll to trigger lazy-loaded content |
| `max_chars` | integer | `40000` | Maximum characters to return (max 500000). Set to `0` for max |
| `readability` | boolean | `true` | Extract only the main article content. Set to `false` for homepages or index pages |

### `screenshot`

Take a screenshot of a URL and return it as a PNG image.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | *required* | The URL to screenshot |
| `full_page` | boolean | `false` | Capture the full scrollable page (capped at 16384px height) |

## Security

- **SSRF protection**: URLs are validated against private/reserved IP ranges before fetching. Redirect targets are re-validated after both the HEAD pre-check and the browser navigation to prevent redirect-based SSRF. IPv6-mapped IPv4 addresses are handled.
- **Scheme restriction**: Only `http` and `https` URLs are accepted.
- **Content-type pre-check**: A HEAD request detects non-HTML content (PDFs, images, etc.) before launching the browser.
- **Resource limits**: Wait time is capped at 30s, output at 500K characters, screenshots at 20MB / 16384px height, cache at 50MB, and concurrent requests are limited to 4.
- **Chromium sandbox**: The browser runs with Chromium's security sandbox enabled by default. Set `BROWSERFETCH_NO_SANDBOX=1` only if running as root in Docker (must be exactly `1`, not any truthy value).
- **Known limitation**: DNS rebinding attacks present a theoretical TOCTOU gap between URL validation and the actual browser connection. This is a known limitation common to SSRF defenses that use pre-flight DNS checks.

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
