"""SSRF-sicherer HTTP(S)-Abruf für vom Nutzer angegebene URLs.

Schutzmaßnahmen:
  - nur http/https, keine Zugangsdaten in der URL, nur Standard-Web-Ports
  - DNS wird EINMAL aufgelöst, JEDE Adresse muss öffentlich sein, und die
    Verbindung geht an genau diese geprüfte IP (kein DNS-Rebinding)
  - localhost, private Netze, Link-Local (inkl. Cloud-Metadaten
    169.254.169.254), CGNAT, Multicast, reservierte Bereiche → blockiert
  - Redirects werden manuell verfolgt und jedes Ziel erneut geprüft
  - hartes Größenlimit, Gesamt-Zeitlimit, Content-Type-Allowlist
Externe Inhalte gelten als nicht vertrauenswürdig (nur Text-Extraktion).
"""

from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from .errors import StudioError

ALLOWED_PORTS = {80, 443, 8080, 8443}
HTML_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
USER_AGENT = "ClipForgeStudio/1.0 (+local-first; user-initiated fetch)"


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def max_fetch_bytes() -> int:
    return _env_int("CLIPFORGE_STUDIO_MAX_FETCH_MB", 5) * 1024 * 1024


def fetch_timeout() -> float:
    return float(_env_int("CLIPFORGE_STUDIO_FETCH_TIMEOUT", 15))


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    redirects: int


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(ip.is_global) and not ip.is_multicast


def validate_url(url: str) -> tuple[str, str, int, str]:
    """Prüft die URL syntaktisch. Liefert (scheme, host, port, path+query)."""
    if not isinstance(url, str) or not url.strip() or len(url) > 2048:
        raise StudioError("url_invalid", "Bitte eine gültige http(s)-URL angeben.")
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise StudioError("url_invalid", "Nur http- und https-URLs sind erlaubt.")
    if parts.username or parts.password:
        raise StudioError("url_blocked", "URLs mit Zugangsdaten sind nicht erlaubt.")
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise StudioError("url_invalid", "Die URL enthält keinen Hostnamen.")
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise StudioError("url_invalid", "Ungültiger Port in der URL.") from exc
    if port not in ALLOWED_PORTS:
        raise StudioError("url_blocked", f"Port {port} ist nicht erlaubt.")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise StudioError("url_blocked", "Lokale/interne Adressen sind nicht erlaubt.")
    try:  # IP-Literal direkt prüfen (frühe, klare Absage schon beim Anlegen)
        ipaddress.ip_address(host)
        if not is_public_ip(host):
            raise StudioError("url_blocked", "Lokale/private Adressen sind nicht erlaubt.")
    except ValueError:
        pass
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return scheme, host, port, path


def resolve_public(host: str, port: int, resolver=None) -> list[str]:
    """Löst den Host auf; ALLE Adressen müssen öffentlich sein."""
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        resolver = resolver or socket.getaddrinfo
        try:
            infos = resolver(host, port, type=socket.SOCK_STREAM)
        except (socket.gaierror, OSError) as exc:
            raise StudioError(
                "url_unreachable", "Der Hostname konnte nicht aufgelöst werden.", 502
            ) from exc
        addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses:
        raise StudioError("url_unreachable", "Der Hostname hat keine Adresse.", 502)
    for addr in addresses:
        if not is_public_ip(addr):
            raise StudioError(
                "url_blocked",
                "Diese Adresse zeigt auf ein lokales oder privates Netz und wird "
                "aus Sicherheitsgründen nicht abgerufen.",
            )
    return addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TLS zur geprüften IP, Zertifikat/SNI gegen den echten Hostnamen."""

    def __init__(self, host: str, ip: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout,
                         context=ssl.create_default_context())
        self._pinned_ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, ip: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


def _default_transport(scheme, host, ip, port, path, headers, timeout, max_bytes, deadline):
    """Echter Abruf an die geprüfte IP. Liefert (status, headers-dict, body)."""
    cls = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    conn = cls(host, ip, port, timeout)
    try:
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        if resp.status in (301, 302, 303, 307, 308):
            return resp.status, hdrs, b""
        declared = hdrs.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise StudioError("url_too_large", "Die Seite ist zu groß.", 413)
        chunks, total = [], 0
        while True:
            if time.monotonic() > deadline:
                raise StudioError("url_timeout", "Zeitlimit beim Abruf überschritten.", 504)
            chunk = resp.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise StudioError("url_too_large", "Die Seite ist zu groß.", 413)
            chunks.append(chunk)
        return resp.status, hdrs, b"".join(chunks)
    finally:
        conn.close()


def fetch(url: str, *, allowed_types: tuple[str, ...] = HTML_TYPES,
          max_bytes: int | None = None, timeout: float | None = None,
          max_redirects: int = 3, resolver=None, transport=None) -> FetchResult:
    """Ruft eine öffentliche URL sicher ab (siehe Modul-Doku)."""
    max_bytes = max_bytes or max_fetch_bytes()
    timeout = timeout or fetch_timeout()
    transport = transport or _default_transport
    deadline = time.monotonic() + timeout
    current = url
    for hop in range(max_redirects + 1):
        scheme, host, port, path = validate_url(current)
        ip = resolve_public(host, port, resolver)[0]
        headers = {
            "Host": host if port in (80, 443) else f"{host}:{port}",
            "User-Agent": USER_AGENT,
            "Accept": ", ".join(allowed_types),
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        try:
            status, hdrs, body = transport(
                scheme, host, ip, port, path, headers, timeout, max_bytes, deadline)
        except StudioError:
            raise
        except (socket.timeout, TimeoutError) as exc:
            raise StudioError("url_timeout", "Zeitlimit beim Abruf überschritten.", 504) from exc
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            raise StudioError(
                "url_unreachable", "Die Seite konnte nicht abgerufen werden.", 502
            ) from exc
        if status in (301, 302, 303, 307, 308):
            location = hdrs.get("location")
            if not location:
                raise StudioError("url_unreachable", "Weiterleitung ohne Ziel.", 502)
            current = urljoin(current, location)
            continue
        if status >= 400:
            raise StudioError(
                "url_http_error", f"Die Seite antwortete mit HTTP {status}.", 502,
                {"http_status": status})
        if len(body) > max_bytes:
            raise StudioError("url_too_large", "Die Seite ist zu groß.", 413)
        ctype = (hdrs.get("content-type") or "").split(";")[0].strip().lower()
        if ctype not in allowed_types:
            raise StudioError(
                "url_unsupported_type",
                f"Inhaltstyp '{ctype or 'unbekannt'}' wird nicht unterstützt.", 415)
        return FetchResult(url=url, final_url=current, status=status,
                           content_type=hdrs.get("content-type") or ctype,
                           body=body, redirects=hop)
    raise StudioError("url_too_many_redirects", "Zu viele Weiterleitungen.", 502)
