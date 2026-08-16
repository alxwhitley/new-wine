"""SSRF-safe, bounded PDF fetching for queued source ingestion."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Callable, Optional, Tuple
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit


def _bounded_detail(detail: str) -> str:
    return " ".join(str(detail).split())[:240]


@dataclass(frozen=True)
class FetchResult:
    content: bytes
    final_url: str
    sha256: str
    byte_count: int
    filename: str


class FetchRejected(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = _bounded_detail(detail)
        super().__init__("%s: %s" % (code, self.detail))


class FetchTransient(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = _bounded_detail(detail)
        super().__init__("%s: %s" % (code, self.detail))


def resolve_public_addresses(
    hostname: str,
    port: int,
    *,
    getaddrinfo: Callable = socket.getaddrinfo,
) -> Tuple[str, ...]:
    """Resolve once and reject the hostname if any answer is not global."""
    try:
        answers = getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchTransient("dns_failure", "DNS resolution failed") from exc

    addresses = []
    seen = set()
    for answer in answers:
        try:
            address = answer[4][0]
            parsed = ipaddress.ip_address(address)
        except (IndexError, TypeError, ValueError) as exc:
            raise FetchRejected("unsafe_url", "DNS returned an invalid address") from exc
        if (
            not parsed.is_global
            or parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_reserved
            or parsed.is_unspecified
        ):
            raise FetchRejected("unsafe_url", "DNS returned a non-global address")
        normalized = str(parsed)
        if normalized not in seen:
            seen.add(normalized)
            addresses.append(normalized)

    if not addresses:
        raise FetchRejected("unsafe_url", "DNS returned no usable address")
    return tuple(addresses)


def _validate_url(url: str):
    if not isinstance(url, str) or any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in url
    ):
        raise FetchRejected("unsafe_url", "URL contains invalid characters")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise FetchRejected("unsafe_url", "URL is malformed") from exc
    if parsed.scheme not in ("http", "https"):
        raise FetchRejected("unsafe_url", "URL scheme is not allowed")
    if not parsed.hostname:
        raise FetchRejected("unsafe_url", "URL hostname is required")
    if parsed.username is not None or parsed.password is not None:
        raise FetchRejected("unsafe_url", "URL credentials are not allowed")
    if parsed.fragment:
        raise FetchRejected("unsafe_url", "URL fragments are not allowed")
    return parsed, port or (443 if parsed.scheme == "https" else 80)


def _request_target(parsed) -> str:
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    return target


def _host_header(parsed, port: int) -> str:
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = "[%s]" % hostname
    default_port = 443 if parsed.scheme == "https" else 80
    return hostname if port == default_port else "%s:%d" % (hostname, port)


def _safe_filename(path: str) -> str:
    candidate = unquote(path.rsplit("/", 1)[-1]) or "source.pdf"
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate).strip("._")
    if not candidate:
        candidate = "source.pdf"
    if not candidate.lower().endswith(".pdf"):
        candidate += ".pdf"
    return candidate[:120]


def _safe_log_url(parsed, port: int) -> str:
    return urlunsplit(
        (parsed.scheme, _host_header(parsed, port), parsed.path or "/", "", "")
    )


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(
        self,
        hostname: str,
        port: int,
        address: str,
        timeout_seconds: float,
        socket_create: Callable,
    ):
        super().__init__(hostname, port=port, timeout=timeout_seconds)
        self._pinned_address = address
        self._socket_create = socket_create

    def connect(self):
        self.sock = self._socket_create(
            (self._pinned_address, self.port), self.timeout, self.source_address
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        hostname: str,
        port: int,
        address: str,
        timeout_seconds: float,
        socket_create: Callable,
        context,
    ):
        super().__init__(
            hostname,
            port=port,
            timeout=timeout_seconds,
            context=context,
        )
        self._pinned_address = address
        self._socket_create = socket_create
        self._tls_hostname = hostname

    def connect(self):
        raw_socket = self._socket_create(
            (self._pinned_address, self.port), self.timeout, self.source_address
        )
        try:
            self.sock = self._context.wrap_socket(
                raw_socket, server_hostname=self._tls_hostname
            )
        except Exception:
            raw_socket.close()
            raise


def _open_pinned_connection(
    *,
    scheme: str,
    hostname: str,
    port: int,
    address: str,
    timeout_seconds: float,
    socket_create: Callable = socket.create_connection,
    ssl_context=None,
):
    """Open TCP to the validated address while preserving HTTP/TLS identity."""
    if scheme == "http":
        return _PinnedHTTPConnection(
            hostname, port, address, timeout_seconds, socket_create
        )
    if scheme == "https":
        context = ssl_context if ssl_context is not None else ssl.create_default_context()
        return _PinnedHTTPSConnection(
            hostname,
            port,
            address,
            timeout_seconds,
            socket_create,
            context,
        )
    raise FetchRejected("unsafe_url", "URL scheme is not allowed")


def _close_quietly(resource) -> None:
    if resource is None:
        return
    try:
        resource.close()
    except Exception:
        pass


def fetch_pdf(
    url: str,
    *,
    resolver=resolve_public_addresses,
    connection_factory=None,
    timeout_seconds: float = 30.0,
    max_bytes: int = 50 * 1024 * 1024,
    max_redirects: int = 3,
    log_hook: Optional[Callable] = None,
) -> FetchResult:
    """Fetch one PDF through a pinned public address."""
    if timeout_seconds <= 0 or max_bytes <= 0 or max_redirects < 0:
        raise ValueError("fetch limits must be positive")
    if connection_factory is None:
        connection_factory = _open_pinned_connection

    current_url = url
    seen_urls = set()
    redirects_followed = 0

    while True:
        parsed, port = _validate_url(current_url)
        normalized_url = parsed.geturl()
        if normalized_url in seen_urls:
            raise FetchRejected("unsafe_url", "redirect loop detected")
        seen_urls.add(normalized_url)
        if log_hook is not None:
            log_hook("fetch", _safe_log_url(parsed, port))

        addresses = resolver(parsed.hostname, port)
        if not addresses:
            raise FetchRejected("unsafe_url", "DNS returned no usable address")

        try:
            connection = connection_factory(
                scheme=parsed.scheme,
                hostname=parsed.hostname,
                port=port,
                address=addresses[0],
                timeout_seconds=timeout_seconds,
            )
        except (socket.timeout, TimeoutError) as exc:
            raise FetchTransient("connect_timeout", "connection timed out") from exc
        except OSError as exc:
            raise FetchTransient("connect_failure", "connection failed") from exc

        response = None
        try:
            try:
                connection.connect()
            except (socket.timeout, TimeoutError) as exc:
                raise FetchTransient(
                    "connect_timeout", "connection timed out"
                ) from exc
            except OSError as exc:
                raise FetchTransient("connect_failure", "connection failed") from exc

            try:
                connection.request(
                    "GET",
                    _request_target(parsed),
                    body=None,
                    headers={
                        "Accept": "application/pdf",
                        "Host": _host_header(parsed, port),
                    },
                )
                response = connection.getresponse()
            except (socket.timeout, TimeoutError) as exc:
                raise FetchTransient("read_timeout", "request timed out") from exc
            except (OSError, http.client.HTTPException) as exc:
                raise FetchTransient("read_failure", "request failed") from exc

            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise FetchRejected("unsafe_url", "redirect location is missing")
                if redirects_followed >= max_redirects:
                    raise FetchRejected("unsafe_url", "redirect limit exceeded")
                next_url = urljoin(current_url, location)
                next_parsed, _ = _validate_url(next_url)
                if parsed.scheme == "https" and next_parsed.scheme == "http":
                    raise FetchRejected("unsafe_url", "HTTPS downgrade is not allowed")
                current_url = next_url
                redirects_followed += 1
                continue

            if 500 <= response.status <= 599:
                raise FetchTransient("http_5xx", "source server failed")
            if response.status != 200:
                raise FetchRejected("http_status", "source server rejected the request")

            content_type = (response.getheader("Content-Type") or "").split(";", 1)[0]
            if content_type.strip().lower() != "application/pdf":
                raise FetchRejected("not_pdf", "response is not application/pdf")

            declared_length = response.getheader("Content-Length")
            if declared_length is not None:
                try:
                    declared_bytes = int(declared_length)
                except (TypeError, ValueError) as exc:
                    raise FetchRejected(
                        "invalid_response", "Content-Length is invalid"
                    ) from exc
                if declared_bytes < 0:
                    raise FetchRejected("invalid_response", "Content-Length is invalid")
                if declared_bytes > max_bytes:
                    raise FetchRejected("pdf_too_large", "PDF exceeds byte limit")

            content = bytearray()
            while True:
                try:
                    chunk = response.read(64 * 1024)
                except (socket.timeout, TimeoutError) as exc:
                    raise FetchTransient("read_timeout", "response timed out") from exc
                except (OSError, http.client.HTTPException) as exc:
                    raise FetchTransient("read_failure", "response failed") from exc
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise FetchRejected("pdf_too_large", "PDF exceeds byte limit")

            immutable_content = bytes(content)
            return FetchResult(
                content=immutable_content,
                final_url=current_url,
                sha256=hashlib.sha256(immutable_content).hexdigest(),
                byte_count=len(immutable_content),
                filename=_safe_filename(parsed.path),
            )
        finally:
            _close_quietly(response)
            _close_quietly(connection)
