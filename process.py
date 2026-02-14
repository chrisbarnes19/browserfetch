from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag
import minify_html
import inscriptis
import trafilatura


def html_to_text(html: str, base_url: str = "") -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Remove unwanted tags
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()

    # Process tables -> markdown
    for table in soup.find_all("table"):
        md = _table_to_markdown(table)
        table.replace_with(soup.new_string(md))

    # Process links -> markdown
    for a in soup.find_all("a"):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if href and text:
            abs_url = urljoin(base_url, href) if base_url else href
            a.replace_with(soup.new_string(f"[{text}]({abs_url})"))
        elif text:
            a.replace_with(soup.new_string(text))

    # Process images -> markdown
    for img in soup.find_all("img"):
        alt = img.get("alt", "")
        src = img.get("src") or img.get("data-src") or _srcset_first(img.get("srcset", ""))
        if src:
            abs_src = urljoin(base_url, src) if base_url else src
            img.replace_with(soup.new_string(f"![{alt}]({abs_src})"))
        else:
            img.decompose()

    # Minify remaining HTML, then extract text
    remaining = str(soup)
    try:
        remaining = minify_html.minify(remaining, minify_css=True, minify_js=True)
    except Exception:
        pass

    text = inscriptis.get_text(remaining)

    # Clean up excessive blank lines
    lines = text.splitlines()
    cleaned = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")
        else:
            blank_count = 0
            cleaned.append(line)

    return "\n".join(cleaned).strip()


def _table_to_markdown(table: Tag) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = []
        for td in tr.find_all(["td", "th"]):
            cells.append(td.get_text(strip=True).replace("|", "\\|"))
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    # Normalize column count
    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append("")

    lines = []
    # First row as header
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n" + "\n".join(lines) + "\n"


def extract_main_content(html: str, base_url: str = "") -> str:
    """Extract just the main article/content using trafilatura."""
    result = trafilatura.extract(
        html,
        include_links=True,
        include_tables=True,
        include_images=True,
        output_format="txt",
        url=base_url or None,
    )
    if result:
        return result
    # Fallback to full extraction if trafilatura finds nothing
    return html_to_text(html, base_url=base_url)


def _srcset_first(srcset: str) -> str:
    if not srcset:
        return ""
    first = srcset.split(",")[0].strip()
    return first.split()[0] if first else ""
