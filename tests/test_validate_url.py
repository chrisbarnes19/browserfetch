"""Tests for URL validation (SSRF protection)."""
import ipaddress
from unittest.mock import patch
import pytest
from fetch import validate_url, _check_hostname, FetchError


class TestValidateUrl:
    def test_allows_http(self):
        validate_url("http://example.com")

    def test_allows_https(self):
        validate_url("https://example.com")

    def test_rejects_file_scheme(self):
        with pytest.raises(FetchError, match="Only http and https"):
            validate_url("file:///etc/passwd")

    def test_rejects_ftp_scheme(self):
        with pytest.raises(FetchError, match="Only http and https"):
            validate_url("ftp://example.com/file.txt")

    def test_rejects_javascript_scheme(self):
        with pytest.raises(FetchError, match="Only http and https"):
            validate_url("javascript:alert(1)")

    def test_rejects_data_scheme(self):
        with pytest.raises(FetchError, match="Only http and https"):
            validate_url("data:text/html,<h1>hi</h1>")

    def test_rejects_no_hostname(self):
        with pytest.raises(FetchError, match="no hostname"):
            validate_url("http://")

    def test_rejects_localhost(self):
        with pytest.raises(FetchError, match="private/internal"):
            validate_url("http://localhost/")

    def test_rejects_127_0_0_1(self):
        with pytest.raises(FetchError, match="private/internal"):
            validate_url("http://127.0.0.1/")

    def test_rejects_10_x(self):
        with pytest.raises(FetchError, match="private/internal"):
            validate_url("http://10.0.0.1/")

    def test_rejects_172_16_x(self):
        with pytest.raises(FetchError, match="private/internal"):
            validate_url("http://172.16.0.1/")

    def test_rejects_192_168_x(self):
        with pytest.raises(FetchError, match="private/internal"):
            validate_url("http://192.168.1.1/")

    def test_rejects_169_254_x(self):
        with pytest.raises(FetchError, match="private/internal"):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_unresolvable_domain(self):
        with pytest.raises(FetchError, match="Could not resolve"):
            validate_url("http://thisdomaindoesnotexist12345abc.invalid/")

    def test_allows_public_domain(self):
        validate_url("https://example.com")

    def test_allows_public_domain_with_path(self):
        validate_url("https://en.wikipedia.org/wiki/Main_Page")


class TestIPv6Mapped:
    """Test that IPv6-mapped IPv4 addresses are properly blocked."""

    def test_rejects_ipv6_mapped_loopback(self):
        # Mock getaddrinfo to return an IPv6-mapped IPv4 loopback
        fake_info = [(10, 1, 6, '', ('::ffff:127.0.0.1', 80, 0, 0))]
        with patch("fetch.socket.getaddrinfo", return_value=fake_info):
            with pytest.raises(FetchError, match="private/internal"):
                _check_hostname("evil.example.com")

    def test_rejects_ipv6_mapped_metadata(self):
        # Mock getaddrinfo to return IPv6-mapped AWS metadata endpoint
        fake_info = [(10, 1, 6, '', ('::ffff:169.254.169.254', 80, 0, 0))]
        with patch("fetch.socket.getaddrinfo", return_value=fake_info):
            with pytest.raises(FetchError, match="private/internal"):
                _check_hostname("evil.example.com")

    def test_rejects_ipv6_mapped_10_x(self):
        fake_info = [(10, 1, 6, '', ('::ffff:10.0.0.1', 80, 0, 0))]
        with patch("fetch.socket.getaddrinfo", return_value=fake_info):
            with pytest.raises(FetchError, match="private/internal"):
                _check_hostname("evil.example.com")

    def test_allows_ipv6_mapped_public(self):
        # IPv6-mapped public IP should be allowed
        fake_info = [(10, 1, 6, '', ('::ffff:93.184.216.34', 80, 0, 0))]
        with patch("fetch.socket.getaddrinfo", return_value=fake_info):
            _check_hostname("example.com")  # Should not raise


class TestRedirectValidation:
    """Test that post-redirect URL validation works."""

    @pytest.mark.asyncio
    async def test_fetch_page_validates_redirect_target(self):
        """Ensure fetch_page calls validate_url on the final URL after redirects."""
        import asyncio
        from unittest.mock import AsyncMock
        import fetch

        mock_page = AsyncMock()
        mock_page.url = "http://127.0.0.1/secret"
        mock_page.context = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200

        real_semaphore = asyncio.Semaphore(4)

        with patch.object(fetch, "validate_url", wraps=fetch.validate_url) as mock_validate, \
             patch.object(fetch, "new_page", new_callable=AsyncMock, return_value=mock_page), \
             patch.object(fetch, "_navigate", new_callable=AsyncMock, return_value=mock_response), \
             patch.object(fetch, "_get_semaphore", return_value=real_semaphore):
            with pytest.raises(FetchError, match="private/internal"):
                await fetch.fetch_page("https://example.com")
            # Should have been called at least twice: once for original URL, once for redirect
            assert mock_validate.call_count >= 2
