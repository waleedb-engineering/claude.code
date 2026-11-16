"""Studio: URL-Validierung + SSRF-Schutz des sicheren Abrufs."""

from __future__ import annotations

import http.server
import socket
import threading

from studio_helpers import run_all

from clipforge.studio import safe_fetch
from clipforge.studio.errors import StudioError


def _public_resolver(host, port, type=None):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def _transport(pages: dict):
    calls = []

    def transport(scheme, host, ip, port, path, headers, timeout, max_bytes, deadline):
        calls.append({"host": host, "ip": ip, "path": path, "headers": headers})
        status, hdrs, body = pages[(host, path)]
        return status, hdrs, body
    transport.calls = calls
    return transport


def _code(fn) -> str:
    try:
        fn()
    except StudioError as exc:
        return exc.code
    return "no_error"


def test_validate_url_rejects_bad_schemes_and_hosts():
    for bad in ("", "ftp://example.com/x", "file:///etc/passwd", "javascript:alert(1)",
                "http://", "gopher://x", "http://user:pw@example.com/"):
        assert _code(lambda b=bad: safe_fetch.validate_url(b)) in ("url_invalid", "url_blocked"), bad
    for blocked in ("http://localhost/", "http://foo.localhost/", "http://printer.local/",
                    "http://svc.internal/", "http://example.com:22/", "http://example.com:6379/"):
        assert _code(lambda b=blocked: safe_fetch.validate_url(b)) == "url_blocked", blocked
    assert safe_fetch.validate_url("https://Example.com/a?b=1") == ("https", "example.com", 443, "/a?b=1")


def test_is_public_ip_blocks_private_ranges():
    for ip in ("127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254",
               "0.0.0.0", "100.64.0.1", "224.0.0.1", "::1", "fe80::1", "fc00::1",
               "::ffff:127.0.0.1", "::ffff:169.254.169.254", "nonsense"):
        assert not safe_fetch.is_public_ip(ip), ip
    for ip in ("93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"):
        assert safe_fetch.is_public_ip(ip), ip


def test_literal_private_ips_blocked_without_dns():
    for url in ("http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
                "http://[::1]/", "http://10.1.2.3/", "http://0.0.0.0/",
                "http://2130706433/", "http://0x7f.0.0.1/"):
        code = _code(lambda u=url: safe_fetch.fetch(u, resolver=lambda *a, **k: (_ for _ in ()).throw(socket.gaierror())))
        assert code in ("url_blocked", "url_unreachable"), (url, code)


def test_dns_to_private_address_blocked():
    def resolver(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", port))]
    t = _transport({})
    assert _code(lambda: safe_fetch.fetch("http://evil.example/", resolver=resolver, transport=t)) == "url_blocked"
    assert t.calls == []  # es wurde NIE verbunden


def test_dns_rebinding_mixed_answers_blocked():
    def resolver(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]
    assert _code(lambda: safe_fetch.fetch("http://rebind.example/", resolver=resolver,
                                          transport=_transport({}))) == "url_blocked"


def test_connection_is_pinned_to_validated_ip():
    t = _transport({("example.com", "/a"): (200, {"content-type": "text/html; charset=utf-8"}, b"<p>hi there</p>")})
    res = safe_fetch.fetch("http://example.com/a", resolver=_public_resolver, transport=t)
    assert res.status == 200 and res.body == b"<p>hi there</p>"
    assert t.calls[0]["ip"] == "93.184.216.34" and t.calls[0]["headers"]["Host"] == "example.com"


def test_redirect_to_private_target_blocked():
    t = _transport({("example.com", "/r"): (302, {"location": "http://169.254.169.254/latest/"}, b"")})
    assert _code(lambda: safe_fetch.fetch("http://example.com/r", resolver=_public_resolver, transport=t)) == "url_blocked"
    assert len(t.calls) == 1


def test_redirect_chain_limit_and_success():
    pages = {("example.com", "/a"): (301, {"location": "/b"}, b""),
             ("example.com", "/b"): (200, {"content-type": "text/html"}, b"<p>ok</p>")}
    res = safe_fetch.fetch("http://example.com/a", resolver=_public_resolver, transport=_transport(pages))
    assert res.final_url == "http://example.com/b" and res.redirects == 1
    loop = {("example.com", "/a"): (302, {"location": "/a"}, b"")}
    assert _code(lambda: safe_fetch.fetch("http://example.com/a", resolver=_public_resolver,
                                          transport=_transport(loop))) == "url_too_many_redirects"


def test_size_limit_content_type_and_http_errors():
    big = {("example.com", "/"): (200, {"content-type": "text/html"}, b"x" * 2048)}
    assert _code(lambda: safe_fetch.fetch("http://example.com/", resolver=_public_resolver,
                                          transport=_transport(big), max_bytes=1024)) == "url_too_large"
    binary = {("example.com", "/"): (200, {"content-type": "application/octet-stream"}, b"MZ")}
    assert _code(lambda: safe_fetch.fetch("http://example.com/", resolver=_public_resolver,
                                          transport=_transport(binary))) == "url_unsupported_type"
    missing = {("example.com", "/"): (404, {"content-type": "text/html"}, b"nope")}
    assert _code(lambda: safe_fetch.fetch("http://example.com/", resolver=_public_resolver,
                                          transport=_transport(missing))) == "url_http_error"


def test_timeout_and_network_errors_are_mapped():
    def slow(*a, **k):
        raise socket.timeout()

    def broken(*a, **k):
        raise ConnectionResetError()
    assert _code(lambda: safe_fetch.fetch("http://example.com/", resolver=_public_resolver, transport=slow)) == "url_timeout"
    assert _code(lambda: safe_fetch.fetch("http://example.com/", resolver=_public_resolver, transport=broken)) == "url_unreachable"


def test_real_local_server_is_never_reached():
    """Echter HTTP-Server auf 127.0.0.1: der Default-Transport darf ihn nicht erreichen."""
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 8080), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert _code(lambda: safe_fetch.fetch("http://127.0.0.1:8080/secret")) == "url_blocked"
        assert _code(lambda: safe_fetch.fetch("http://localhost:8080/secret")) == "url_blocked"
        assert hits == []
    finally:
        srv.shutdown()
        srv.server_close()


def test_default_transport_enforces_size_limit_on_stream():
    """Größenlimit greift auch ohne Content-Length (gestreamte Antwort)."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            try:
                for _ in range(200):
                    self.wfile.write(b"x" * 65536)
            except OSError:
                pass

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        import time
        port = srv.server_address[1]
        code = _code(lambda: safe_fetch._default_transport(
            "http", "example.com", "127.0.0.1", port, "/", {"Host": "example.com"}, 5.0,
            100_000, time.monotonic() + 5))
        assert code == "url_too_large"
    finally:
        srv.shutdown()
        srv.server_close()


if __name__ == "__main__":
    run_all(globals())
