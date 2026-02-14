"""Tests for URL validation (SSRF protection)."""
import pytest
from fetch import validate_url, FetchError


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
