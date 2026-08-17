#!/usr/bin/env python3
"""Deterministic security and behavior checks for queued PDF fetching."""

import socket
import ssl
import unittest

from source_ingest_queue.fetcher import (
    FetchRejected,
    FetchResult,
    FetchTransient,
    _open_pinned_connection,
    fetch_html,
    fetch_pdf,
    resolve_public_addresses,
)


def address_info(*addresses):
    rows = []
    for address in addresses:
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        rows.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443)))
    return rows


class FakeResponse:
    def __init__(self, *, status=200, headers=None, chunks=(), read_error=None):
        self.status = status
        self._headers = {key.lower(): value for key, value in (headers or {}).items()}
        self._chunks = list(chunks)
        self._read_error = read_error
        self.closed = False

    def getheader(self, name, default=None):
        return self._headers.get(name.lower(), default)

    def read(self, size):
        if self._read_error is not None:
            raise self._read_error
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, response, *, connect_error=None):
        self.response = response
        self.connect_error = connect_error
        self.requests = []
        self.closed = False

    def connect(self):
        if self.connect_error is not None:
            raise self.connect_error

    def request(self, method, target, body=None, headers=None):
        self.requests.append((method, target, body, headers or {}))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class ResolvePublicAddressesTests(unittest.TestCase):
    def test_accepts_and_deduplicates_global_addresses(self):
        result = resolve_public_addresses(
            "example.com",
            443,
            getaddrinfo=lambda *args, **kwargs: address_info(
                "93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946", "93.184.216.34"
            ),
        )

        self.assertEqual(
            result,
            ("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"),
        )

    def test_rejects_every_non_global_address_class(self):
        unsafe_addresses = (
            "127.0.0.1",
            "10.0.0.1",
            "169.254.1.1",
            "224.0.0.1",
            "192.0.2.1",
            "0.0.0.0",
            "::1",
            "fc00::1",
            "fe80::1",
            "ff00::1",
            "2001:db8::1",
            "::",
        )

        for address in unsafe_addresses:
            with self.subTest(address=address):
                with self.assertRaises(FetchRejected) as raised:
                    resolve_public_addresses(
                        "blocked.test",
                        443,
                        getaddrinfo=lambda *args, _address=address, **kwargs: (
                            address_info(_address)
                        ),
                    )
                self.assertEqual(raised.exception.code, "unsafe_url")

    def test_rejects_entire_mixed_public_private_answer(self):
        with self.assertRaises(FetchRejected) as raised:
            resolve_public_addresses(
                "rebind.test",
                443,
                getaddrinfo=lambda *args, **kwargs: address_info(
                    "93.184.216.34", "127.0.0.1"
                ),
            )

        self.assertEqual(raised.exception.code, "unsafe_url")

    def test_rejects_malformed_and_empty_dns_answers(self):
        with self.assertRaises(FetchRejected) as malformed:
            resolve_public_addresses(
                "malformed.test",
                443,
                getaddrinfo=lambda *args, **kwargs: address_info("not-an-ip"),
            )
        self.assertEqual(malformed.exception.code, "unsafe_url")

        with self.assertRaises(FetchRejected) as empty:
            resolve_public_addresses(
                "empty.test", 443, getaddrinfo=lambda *args, **kwargs: []
            )
        self.assertEqual(empty.exception.code, "unsafe_url")


class FetchPdfValidationTests(unittest.TestCase):
    def test_rejects_malformed_or_unsafe_url_before_resolution(self):
        unsafe_urls = (
            "ftp://example.com/doc.pdf",
            "https:///doc.pdf",
            "https://user:password@example.com/doc.pdf",
            "https://example.com/doc.pdf#private-fragment",
            "https://example.com/doc.pdf\r\nX-Test: injected",
        )

        for url in unsafe_urls:
            with self.subTest(url=url):
                resolver_called = []
                with self.assertRaises(FetchRejected) as raised:
                    fetch_pdf(
                        url,
                        resolver=lambda *args: resolver_called.append(args),
                        connection_factory=lambda **kwargs: None,
                    )
                self.assertEqual(raised.exception.code, "unsafe_url")
                self.assertEqual(resolver_called, [])

    def test_fetches_pdf_using_hostname_and_pinned_address(self):
        content = b"%PDF-1.4\npdf-body"
        response = FakeResponse(
            headers={
                "Content-Type": "application/pdf; charset=binary",
                "Content-Length": str(len(content)),
            },
            chunks=(content,),
        )
        connection = FakeConnection(response)
        resolved = []
        opened = []

        def resolver(hostname, port):
            resolved.append((hostname, port))
            return ("93.184.216.34",)

        def connection_factory(**kwargs):
            opened.append(kwargs)
            return connection

        result = fetch_pdf(
            "https://example.com/library/Book%20Name.pdf?download=1",
            resolver=resolver,
            connection_factory=connection_factory,
        )

        self.assertIsInstance(result, FetchResult)
        self.assertEqual(result.content, content)
        self.assertEqual(
            result.sha256,
            "0c7447ec58c65a44dd7b0f4e5f4e5297ca7a1162f0dfdb0fdc53eaa94377dab0",
        )
        self.assertEqual(result.byte_count, 17)
        self.assertEqual(result.final_url, "https://example.com/library/Book%20Name.pdf?download=1")
        self.assertEqual(result.filename, "Book_Name.pdf")
        self.assertEqual(resolved, [("example.com", 443)])
        self.assertEqual(
            opened,
            [
                {
                    "scheme": "https",
                    "hostname": "example.com",
                    "port": 443,
                    "address": "93.184.216.34",
                    "timeout_seconds": 30.0,
                }
            ],
        )
        self.assertEqual(
            connection.requests,
            [
                (
                    "GET",
                    "/library/Book%20Name.pdf?download=1",
                    None,
                    {"Accept": "application/pdf", "Host": "example.com"},
                )
            ],
        )
        self.assertTrue(response.closed)
        self.assertTrue(connection.closed)

    def test_https_connects_to_pinned_ip_with_hostname_sni(self):
        raw_socket = object()
        wrapped_socket = object()
        socket_calls = []
        sni_calls = []

        def socket_create(address, timeout, source_address=None):
            socket_calls.append((address, timeout, source_address))
            return raw_socket

        class FakeContext:
            verify_mode = ssl.CERT_REQUIRED
            check_hostname = True

            def wrap_socket(self, sock, *, server_hostname):
                sni_calls.append((sock, server_hostname))
                return wrapped_socket

        connection = _open_pinned_connection(
            scheme="https",
            hostname="example.com",
            port=443,
            address="93.184.216.34",
            timeout_seconds=30.0,
            socket_create=socket_create,
            ssl_context=FakeContext(),
        )
        connection.connect()

        self.assertEqual(
            socket_calls, [(('93.184.216.34', 443), 30.0, None)]
        )
        self.assertEqual(sni_calls, [(raw_socket, "example.com")])
        self.assertIs(connection.sock, wrapped_socket)

    def test_https_closes_raw_socket_when_tls_wrap_fails(self):
        class RawSocket:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        raw_socket = RawSocket()

        class RejectingContext:
            verify_mode = ssl.CERT_REQUIRED
            check_hostname = True

            def wrap_socket(self, sock, *, server_hostname):
                raise ssl.SSLError("certificate rejected")

        connection = _open_pinned_connection(
            scheme="https",
            hostname="example.com",
            port=443,
            address="93.184.216.34",
            timeout_seconds=30.0,
            socket_create=lambda *args: raw_socket,
            ssl_context=RejectingContext(),
        )

        with self.assertRaises(ssl.SSLError):
            connection.connect()
        self.assertTrue(raw_socket.closed)

    def test_redirect_revalidates_dns_and_redacts_queries_from_logs(self):
        first = FakeResponse(
            status=302,
            headers={"Location": "https://cdn.example.org/doc.pdf?token=two"},
        )
        second = FakeResponse(
            headers={"Content-Type": "application/pdf"},
            chunks=(b"pdf",),
        )
        responses = [first, second]
        resolver_calls = []
        opened = []
        logged = []

        def resolver(hostname, port):
            resolver_calls.append((hostname, port))
            return {
                "example.com": ("93.184.216.34",),
                "cdn.example.org": ("93.184.216.35",),
            }[hostname]

        def connection_factory(**kwargs):
            opened.append(kwargs)
            return FakeConnection(responses.pop(0))

        result = fetch_pdf(
            "https://example.com/start?secret=one",
            resolver=resolver,
            connection_factory=connection_factory,
            log_hook=lambda event, safe_url: logged.append((event, safe_url)),
        )

        self.assertEqual(
            resolver_calls,
            [("example.com", 443), ("cdn.example.org", 443)],
        )
        self.assertEqual(
            [item["address"] for item in opened],
            ["93.184.216.34", "93.184.216.35"],
        )
        self.assertEqual(
            result.final_url, "https://cdn.example.org/doc.pdf?token=two"
        )
        self.assertEqual(
            logged,
            [
                ("fetch", "https://example.com/start"),
                ("fetch", "https://cdn.example.org/doc.pdf"),
            ],
        )
        self.assertNotIn("secret", repr(logged))
        self.assertNotIn("token", repr(logged))

    def test_rejects_redirect_downgrade_loop_and_fourth_redirect(self):
        cases = (
            (
                "downgrade",
                "https://example.com/start",
                [FakeResponse(status=302, headers={"Location": "http://example.com/doc.pdf"})],
            ),
            (
                "loop",
                "https://example.com/start",
                [FakeResponse(status=302, headers={"Location": "/start"})],
            ),
            (
                "fourth",
                "https://example.com/0",
                [
                    FakeResponse(status=302, headers={"Location": "/1"}),
                    FakeResponse(status=302, headers={"Location": "/2"}),
                    FakeResponse(status=302, headers={"Location": "/3"}),
                    FakeResponse(status=302, headers={"Location": "/4"}),
                ],
            ),
        )

        for name, url, responses in cases:
            with self.subTest(name=name):
                remaining = list(responses)
                with self.assertRaises(FetchRejected) as raised:
                    fetch_pdf(
                        url,
                        resolver=lambda *args: ("93.184.216.34",),
                        connection_factory=lambda **kwargs: FakeConnection(
                            remaining.pop(0)
                        ),
                    )
                self.assertEqual(raised.exception.code, "unsafe_url")

    def test_rejects_non_pdf_and_declared_or_streamed_oversize_body(self):
        cases = (
            (
                "not_pdf",
                100,
                FakeResponse(headers={"Content-Type": "text/html"}),
            ),
            (
                "pdf_too_large",
                5,
                FakeResponse(
                    headers={"Content-Type": "application/pdf", "Content-Length": "6"}
                ),
            ),
            (
                "pdf_too_large",
                5,
                FakeResponse(
                    headers={"Content-Type": "application/pdf"},
                    chunks=(b"123", b"456"),
                ),
            ),
        )

        for code, max_bytes, response in cases:
            with self.subTest(code=code, declared=response.getheader("Content-Length")):
                with self.assertRaises(FetchRejected) as raised:
                    fetch_pdf(
                        "https://example.com/doc.pdf",
                        resolver=lambda *args: ("93.184.216.34",),
                        connection_factory=lambda **kwargs: FakeConnection(response),
                        max_bytes=max_bytes,
                    )
                self.assertEqual(raised.exception.code, code)

    def test_classifies_connect_read_and_server_failures_as_transient(self):
        def timed_out_factory(**kwargs):
            return FakeConnection(
                FakeResponse(),
                connect_error=socket.timeout("connect detail must stay private"),
            )

        cases = (
            (
                "connect_timeout",
                timed_out_factory,
            ),
            (
                "read_timeout",
                lambda **kwargs: FakeConnection(
                    FakeResponse(
                        headers={"Content-Type": "application/pdf"},
                        read_error=socket.timeout("read detail must stay private"),
                    )
                ),
            ),
            (
                "http_5xx",
                lambda **kwargs: FakeConnection(FakeResponse(status=503)),
            ),
        )

        for code, factory in cases:
            with self.subTest(code=code):
                with self.assertRaises(FetchTransient) as raised:
                    fetch_pdf(
                        "https://example.com/doc.pdf",
                        resolver=lambda *args: ("93.184.216.34",),
                        connection_factory=factory,
                    )
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("detail must stay private", raised.exception.detail)


class FetchHtmlValidationTests(unittest.TestCase):
    """fetch_html() reuses fetch_pdf()'s SSRF/redirect/timeout protections
    (same _validate_url, resolve_public_addresses, _open_pinned_connection
    core) but accepts text/html content and returns the raw article HTML
    for a downstream extractor to isolate the article body from."""

    def test_rejects_malformed_or_unsafe_url_before_resolution(self):
        unsafe_urls = (
            "ftp://example.com/post",
            "https:///post",
            "https://user:password@example.com/post",
            "https://example.com/post#private-fragment",
            "https://example.com/post\r\nX-Test: injected",
        )

        for url in unsafe_urls:
            with self.subTest(url=url):
                resolver_called = []
                with self.assertRaises(FetchRejected) as raised:
                    fetch_html(
                        url,
                        resolver=lambda *args: resolver_called.append(args),
                        connection_factory=lambda **kwargs: None,
                    )
                self.assertEqual(raised.exception.code, "unsafe_url")
                self.assertEqual(resolver_called, [])

    def test_fetches_html_using_hostname_and_pinned_address(self):
        content = "<html><body><article>Hello world</article></body></html>".encode()
        response = FakeResponse(
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Content-Length": str(len(content)),
            },
            chunks=(content,),
        )
        connection = FakeConnection(response)
        resolved = []
        opened = []

        def resolver(hostname, port):
            resolved.append((hostname, port))
            return ("93.184.216.34",)

        def connection_factory(**kwargs):
            opened.append(kwargs)
            return connection

        result = fetch_html(
            "https://example.com/blog/my-post?utm_source=x",
            resolver=resolver,
            connection_factory=connection_factory,
        )

        self.assertIsInstance(result, FetchResult)
        self.assertEqual(result.content, content)
        self.assertEqual(result.byte_count, len(content))
        self.assertEqual(
            result.final_url, "https://example.com/blog/my-post?utm_source=x"
        )
        self.assertEqual(resolved, [("example.com", 443)])
        self.assertEqual(
            connection.requests,
            [
                (
                    "GET",
                    "/blog/my-post?utm_source=x",
                    None,
                    {
                        "Accept": "text/html,application/xhtml+xml",
                        "Host": "example.com",
                    },
                )
            ],
        )
        self.assertTrue(response.closed)
        self.assertTrue(connection.closed)

    def test_accepts_xhtml_content_type(self):
        content = b"<html><body><article>Hi</article></body></html>"
        response = FakeResponse(headers={"Content-Type": "application/xhtml+xml"}, chunks=(content,))

        result = fetch_html(
            "https://example.com/post",
            resolver=lambda *args: ("93.184.216.34",),
            connection_factory=lambda **kwargs: FakeConnection(response),
        )
        self.assertEqual(result.content, content)

    def test_rejects_non_html_content_type(self):
        response = FakeResponse(headers={"Content-Type": "application/pdf"})

        with self.assertRaises(FetchRejected) as raised:
            fetch_html(
                "https://example.com/post",
                resolver=lambda *args: ("93.184.216.34",),
                connection_factory=lambda **kwargs: FakeConnection(response),
            )
        self.assertEqual(raised.exception.code, "not_html")

    def test_rejects_declared_or_streamed_oversize_body(self):
        cases = (
            (
                "declared",
                FakeResponse(
                    headers={"Content-Type": "text/html", "Content-Length": "999999"}
                ),
            ),
            (
                "streamed",
                FakeResponse(
                    headers={"Content-Type": "text/html"},
                    chunks=(b"a" * 5, b"b" * 5),
                ),
            ),
        )
        for name, response in cases:
            with self.subTest(name=name):
                with self.assertRaises(FetchRejected) as raised:
                    fetch_html(
                        "https://example.com/post",
                        resolver=lambda *args: ("93.184.216.34",),
                        connection_factory=lambda **kwargs: FakeConnection(response),
                        max_bytes=8,
                    )
                self.assertEqual(raised.exception.code, "html_too_large")

    def test_redirect_and_downgrade_protection_match_fetch_pdf(self):
        first = FakeResponse(
            status=302, headers={"Location": "https://cdn.example.org/post?token=two"}
        )
        second = FakeResponse(
            headers={"Content-Type": "text/html"}, chunks=(b"<html>ok</html>",)
        )
        responses = [first, second]

        result = fetch_html(
            "https://example.com/start?secret=one",
            resolver=lambda hostname, port: {
                "example.com": ("93.184.216.34",),
                "cdn.example.org": ("93.184.216.35",),
            }[hostname],
            connection_factory=lambda **kwargs: FakeConnection(responses.pop(0)),
        )
        self.assertEqual(result.final_url, "https://cdn.example.org/post?token=two")

        with self.assertRaises(FetchRejected) as raised:
            fetch_html(
                "https://example.com/start",
                resolver=lambda *args: ("93.184.216.34",),
                connection_factory=lambda **kwargs: FakeConnection(
                    FakeResponse(
                        status=302,
                        headers={"Location": "http://example.com/downgraded"},
                    )
                ),
            )
        self.assertEqual(raised.exception.code, "unsafe_url")

    def test_classifies_connect_and_read_failures_as_transient(self):
        with self.assertRaises(FetchTransient) as raised:
            fetch_html(
                "https://example.com/post",
                resolver=lambda *args: ("93.184.216.34",),
                connection_factory=lambda **kwargs: FakeConnection(
                    FakeResponse(),
                    connect_error=socket.timeout("connect detail must stay private"),
                ),
            )
        self.assertEqual(raised.exception.code, "connect_timeout")
        self.assertNotIn("detail must stay private", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
