"""Tests for HTML processing."""
from process import html_to_text, extract_main_content


class TestHtmlToText:
    def test_strips_scripts(self):
        html = "<p>Hello</p><script>alert(1)</script>"
        assert "alert" not in html_to_text(html)
        assert "Hello" in html_to_text(html)

    def test_strips_styles(self):
        html = "<p>Hello</p><style>body{color:red}</style>"
        assert "color" not in html_to_text(html)

    def test_strips_nav_footer_header(self):
        html = "<nav>Menu</nav><main><p>Content</p></main><footer>Footer</footer>"
        text = html_to_text(html)
        assert "Menu" not in text
        assert "Footer" not in text
        assert "Content" in text

    def test_converts_links_to_markdown(self):
        html = '<a href="/page">Click here</a>'
        text = html_to_text(html, base_url="https://example.com")
        assert "[Click here](https://example.com/page)" in text

    def test_converts_images_to_markdown(self):
        html = '<img src="/img.png" alt="Photo">'
        text = html_to_text(html, base_url="https://example.com")
        assert "![Photo](https://example.com/img.png)" in text

    def test_converts_tables_to_markdown(self):
        html = "<table><tr><th>Name</th><th>Age</th></tr><tr><td>Alice</td><td>30</td></tr></table>"
        text = html_to_text(html)
        assert "| Name | Age |" in text
        assert "| Alice | 30 |" in text

    def test_collapses_blank_lines(self):
        html = "<p>A</p>" + "<br>" * 10 + "<p>B</p>"
        text = html_to_text(html)
        # Should not have more than 2 consecutive blank lines
        assert "\n\n\n\n" not in text

    def test_empty_html(self):
        assert html_to_text("") == ""

    def test_plain_text_passthrough(self):
        text = html_to_text("Just plain text")
        assert "Just plain text" in text


class TestExtractMainContent:
    def test_fallback_to_html_to_text(self):
        html = "<p>Simple paragraph</p>"
        result = extract_main_content(html)
        assert "Simple paragraph" in result

    def test_extracts_article(self):
        html = """
        <html><body>
        <nav>Navigation links</nav>
        <article><p>This is the main article content that should be extracted.</p></article>
        <aside>Sidebar ads</aside>
        <footer>Copyright 2024</footer>
        </body></html>
        """
        result = extract_main_content(html)
        assert "main article content" in result
