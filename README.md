# webfetch

A Playwright-based MCP server for Claude Code that fetches web pages using a stealth browser and returns clean, LLM-optimized text.

Claude Code's built-in `WebFetch` tool uses Axios with a default User-Agent, which gets blocked by many websites. `webfetch` uses a headless Chromium browser with stealth patches to bypass bot detection, handles JavaScript-rendered content, and returns clean markdown-formatted text.

## Tools

### `fetch`

Fetch a URL and return clean text optimized for LLMs.

- **url** (required) — The URL to fetch
- **wait** (optional, default `2.0`) — Seconds to wait after page load for JS rendering
- **scroll** (optional, default `true`) — Auto-scroll to trigger lazy-loaded content

The fetch pipeline strips scripts, styles, nav/footer/header elements, converts tables to markdown pipe tables, converts links and images to markdown syntax, and extracts clean text via inscriptis.

### `screenshot`

Take a screenshot of a URL and return it as a PNG image.

- **url** (required) — The URL to screenshot
- **full_page** (optional, default `false`) — Capture the full scrollable page instead of just the viewport

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13+.

```bash
cd ~/projects/webfetch
uv sync
uv run playwright install chromium
```

Register with Claude Code:

```bash
claude mcp add --transport stdio webfetch -- uv run --directory ~/projects/webfetch python server.py
```

## Dependencies

- [mcp](https://pypi.org/project/mcp/) — FastMCP server framework
- [playwright](https://playwright.dev/python/) — Browser automation
- [playwright-stealth](https://pypi.org/project/playwright-stealth/) — Anti-detection patches
- [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/) — HTML parsing
- [inscriptis](https://github.com/weblyzard/inscriptis) — Semantic HTML-to-text conversion
- [minify-html](https://pypi.org/project/minify-html/) — HTML minification
