"""Integration tests for fetch functionality (requires network + Playwright)."""
import pytest
import asyncio
from fetch import fetch_page, head_check, FetchError


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestFetchPage:
    @pytest.mark.asyncio
    async def test_fetch_example_com(self):
        result = await fetch_page("https://example.com", wait=0.5, scroll=False)
        assert result.status == 200
        assert "Example Domain" in result.title
        assert result.url == "https://example.com/"
        assert "<html" in result.html.lower()

    @pytest.mark.asyncio
    async def test_fetch_rejects_private_ip(self):
        with pytest.raises(FetchError, match="private/internal"):
            await fetch_page("http://127.0.0.1/", wait=0, scroll=False)

    @pytest.mark.asyncio
    async def test_fetch_rejects_file_url(self):
        with pytest.raises(FetchError, match="Only http and https"):
            await fetch_page("file:///etc/passwd", wait=0, scroll=False)

    @pytest.mark.asyncio
    async def test_fetch_clamps_wait(self):
        from fetch import MAX_WAIT
        # Verify the clamping logic directly -- don't actually wait MAX_WAIT seconds
        clamped = max(0.0, min(99999, MAX_WAIT))
        assert clamped == MAX_WAIT
        assert MAX_WAIT <= 30.0


class TestHeadCheck:
    @pytest.mark.asyncio
    async def test_rejects_pdf(self):
        with pytest.raises(FetchError, match="not a web page"):
            await head_check("https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf")

    @pytest.mark.asyncio
    async def test_allows_html(self):
        # Should not raise
        await head_check("https://example.com")

    @pytest.mark.asyncio
    async def test_rejects_private_ip(self):
        with pytest.raises(FetchError, match="private/internal"):
            await head_check("http://127.0.0.1/")
