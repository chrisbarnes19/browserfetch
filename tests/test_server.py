"""Tests for server.py — cache logic, truncation, and error handling."""
import time
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from fetch import FetchResult, FetchError

# Import the module-level functions and constants directly
import server
from server import _get_cached, _set_cached, _cache, _CACHE_TTL, MAX_CHARS_LIMIT


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the cache before each test."""
    _cache.clear()
    yield
    _cache.clear()


class TestCache:
    def test_set_and_get(self):
        result = FetchResult(html="<p>hi</p>", url="https://example.com", status=200, title="Hi")
        _set_cached("https://example.com", result)
        cached = _get_cached("https://example.com")
        assert cached is result

    def test_get_missing_returns_none(self):
        assert _get_cached("https://notcached.com") is None

    def test_expired_entry_returns_none(self):
        result = FetchResult(html="<p>old</p>", url="https://example.com", status=200, title="Old")
        _set_cached("https://example.com", result)
        # Manually expire the entry
        ts, r = _cache["https://example.com"]
        _cache["https://example.com"] = (ts - _CACHE_TTL - 1, r)
        assert _get_cached("https://example.com") is None
        assert "https://example.com" not in _cache

    def test_evicts_oldest_when_max_entries_exceeded(self):
        for i in range(25):
            r = FetchResult(html=f"<p>{i}</p>", url=f"https://example.com/{i}", status=200, title=str(i))
            _set_cached(f"https://example.com/{i}", r)
        assert len(_cache) <= 20

    def test_evicts_when_cache_bytes_exceeded(self):
        # Create a result with ~10MB of HTML
        big_html = "x" * (10 * 1024 * 1024)
        for i in range(7):
            r = FetchResult(html=big_html, url=f"https://example.com/{i}", status=200, title=str(i))
            _set_cached(f"https://example.com/{i}", r)
        total_bytes = server._cache_size_bytes()
        assert total_bytes <= server._CACHE_MAX_BYTES

    def test_eviction_uses_fifo_order(self):
        for i in range(22):
            r = FetchResult(html=f"<p>{i}</p>", url=f"https://example.com/{i}", status=200, title=str(i))
            _set_cached(f"https://example.com/{i}", r)
        # First entries should have been evicted
        assert _get_cached("https://example.com/0") is None
        assert _get_cached("https://example.com/1") is None
        # Later entries should still exist
        assert _get_cached("https://example.com/21") is not None


class TestMaxChars:
    @pytest.mark.asyncio
    async def test_max_chars_caps_at_limit(self):
        long_text = "A" * 600_000
        result = FetchResult(html=f"<p>{long_text}</p>", url="https://example.com", status=200, title="Big")

        with patch("server.head_check", new_callable=AsyncMock), \
             patch("server.fetch_page", new_callable=AsyncMock, return_value=result), \
             patch("server.extract_main_content", return_value=long_text):
            text = await server.fetch("https://example.com", max_chars=0)
            # max_chars=0 should be capped to MAX_CHARS_LIMIT
            assert len(text) <= MAX_CHARS_LIMIT + 200  # +200 for truncation message and header

    @pytest.mark.asyncio
    async def test_max_chars_over_limit_is_capped(self):
        long_text = "B" * 600_000
        result = FetchResult(html=f"<p>{long_text}</p>", url="https://example.com", status=200, title="Big")

        with patch("server.head_check", new_callable=AsyncMock), \
             patch("server.fetch_page", new_callable=AsyncMock, return_value=result), \
             patch("server.extract_main_content", return_value=long_text):
            text = await server.fetch("https://example.com", max_chars=999_999)
            assert len(text) <= MAX_CHARS_LIMIT + 200

    @pytest.mark.asyncio
    async def test_truncation_message_included(self):
        text_100 = "C" * 100
        result = FetchResult(html="<p>x</p>", url="https://example.com", status=200, title="")

        with patch("server.head_check", new_callable=AsyncMock), \
             patch("server.fetch_page", new_callable=AsyncMock, return_value=result), \
             patch("server.extract_main_content", return_value=text_100):
            text = await server.fetch("https://example.com", max_chars=50)
            assert "[Truncated" in text
            assert "100 total characters" in text


class TestFetchTool:
    @pytest.mark.asyncio
    async def test_returns_error_on_fetch_error(self):
        with patch("server.head_check", new_callable=AsyncMock, side_effect=FetchError("blocked")):
            text = await server.fetch("https://example.com")
            assert text == "Error: blocked"

    @pytest.mark.asyncio
    async def test_returns_error_on_unexpected_exception(self):
        with patch("server.head_check", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            text = await server.fetch("https://example.com")
            assert "unexpected failure" in text
            assert "boom" in text

    @pytest.mark.asyncio
    async def test_metadata_header_with_redirect(self):
        result = FetchResult(html="<p>hi</p>", url="https://other.com", status=200, title="Other")

        with patch("server.head_check", new_callable=AsyncMock), \
             patch("server.fetch_page", new_callable=AsyncMock, return_value=result), \
             patch("server.extract_main_content", return_value="content"):
            text = await server.fetch("https://example.com")
            assert "Redirected to: https://other.com" in text
            assert "Title: Other" in text

    @pytest.mark.asyncio
    async def test_metadata_header_with_error_status(self):
        result = FetchResult(html="<p>not found</p>", url="https://example.com", status=404, title="Not Found")

        with patch("server.head_check", new_callable=AsyncMock), \
             patch("server.fetch_page", new_callable=AsyncMock, return_value=result), \
             patch("server.extract_main_content", return_value="not found"):
            text = await server.fetch("https://example.com")
            assert "HTTP 404" in text

    @pytest.mark.asyncio
    async def test_readability_false_uses_html_to_text(self):
        result = FetchResult(html="<p>hello</p>", url="https://example.com", status=200, title="")

        with patch("server.head_check", new_callable=AsyncMock), \
             patch("server.fetch_page", new_callable=AsyncMock, return_value=result), \
             patch("server.html_to_text", return_value="hello from html_to_text") as mock_h2t, \
             patch("server.extract_main_content") as mock_emc:
            text = await server.fetch("https://example.com", readability=False)
            mock_h2t.assert_called_once()
            mock_emc.assert_not_called()
            assert "hello from html_to_text" in text

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self):
        result = FetchResult(html="<p>hi</p>", url="https://example.com", status=200, title="Hi")

        with patch("server.head_check", new_callable=AsyncMock), \
             patch("server.fetch_page", new_callable=AsyncMock, return_value=result) as mock_fp, \
             patch("server.extract_main_content", return_value="hi"):
            await server.fetch("https://example.com")
            await server.fetch("https://example.com")
            # fetch_page should only be called once; second call uses cache
            assert mock_fp.call_count == 1


class TestScreenshotTool:
    @pytest.mark.asyncio
    async def test_returns_image_on_success(self):
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with patch("server.head_check", new_callable=AsyncMock), \
             patch("server.take_screenshot", new_callable=AsyncMock, return_value=fake_png):
            img = await server.screenshot("https://example.com")
            assert img.data == fake_png

    @pytest.mark.asyncio
    async def test_raises_on_fetch_error(self):
        with patch("server.head_check", new_callable=AsyncMock, side_effect=FetchError("blocked")):
            with pytest.raises(ValueError, match="blocked"):
                await server.screenshot("https://example.com")

    @pytest.mark.asyncio
    async def test_raises_on_unexpected_error(self):
        with patch("server.head_check", new_callable=AsyncMock), \
             patch("server.take_screenshot", new_callable=AsyncMock, side_effect=RuntimeError("crash")):
            with pytest.raises(ValueError, match="Unexpected failure"):
                await server.screenshot("https://example.com")
