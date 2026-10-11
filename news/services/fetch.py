from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from django.conf import settings


class FeedFetchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FeedResponse:
    body: bytes
    etag: str | None
    last_modified: str | None
    not_modified: bool = False
    final_url: str = ""


AddressResolver = Callable[[str], Iterable[str]]


def _resolve_addresses(hostname: str) -> tuple[str, ...]:
    try:
        results = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise FeedFetchError("The feed host could not be resolved") from error
    return tuple({result[4][0] for result in results})


def _validate_url(url: str, allowed_hosts: frozenset[str], resolver: AddressResolver, *, allow_public_redirects=False) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise FeedFetchError("The feed URL or redirected address is invalid") from error
    hostname = parsed.hostname.lower() if parsed.hostname else None
    if (
        parsed.scheme != "https"
        or not hostname
        or (not allow_public_redirects and hostname not in allowed_hosts)
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        raise FeedFetchError("The feed URL is not an allowed HTTPS source")
    addresses = tuple(resolver(hostname))
    if not addresses:
        raise FeedFetchError("The feed host did not resolve to an address")
    try:
        if any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise FeedFetchError("The feed host resolved to a non-public address")
    except ValueError as error:
        raise FeedFetchError("The feed host resolved to an invalid address") from error


def fetch_feed(
    url: str,
    *,
    allowed_hosts: set[str] | frozenset[str],
    etag: str | None = None,
    last_modified: str | None = None,
    client: httpx.Client | None = None,
    resolver: AddressResolver = _resolve_addresses,
    allow_public_redirects: bool = False,
) -> FeedResponse:
    normalized_hosts = frozenset(host.lower() for host in allowed_hosts)
    headers = {
        "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml;q=0.9",
        # These integrations request English feeds. Some publishers reject an
        # otherwise valid feed request when its language preference is absent.
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": settings.NEWS_USER_AGENT,
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    timeout = httpx.Timeout(
        connect=settings.NEWS_HTTP_CONNECT_TIMEOUT_SECONDS,
        read=settings.NEWS_HTTP_READ_TIMEOUT_SECONDS,
        write=settings.NEWS_HTTP_CONNECT_TIMEOUT_SECONDS,
        pool=settings.NEWS_HTTP_CONNECT_TIMEOUT_SECONDS,
    )
    owns_client = client is None
    request_client = client or httpx.Client(
        follow_redirects=False,
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
        timeout=timeout,
    )
    started_at = time.monotonic()
    current_url = url
    try:
        for redirect_count in range(settings.NEWS_HTTP_MAX_REDIRECTS + 1):
            _validate_url(current_url, normalized_hosts, resolver, allow_public_redirects=allow_public_redirects)
            try:
                with request_client.stream("GET", current_url, headers=headers, timeout=timeout) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location or redirect_count >= settings.NEWS_HTTP_MAX_REDIRECTS:
                            raise FeedFetchError("The feed exceeded the redirect limit")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status_code == 304:
                        return FeedResponse(
                            body=b"",
                            etag=response.headers.get("ETag") or etag,
                            last_modified=response.headers.get("Last-Modified") or last_modified,
                            not_modified=True,
                            final_url=current_url,
                        )
                    response.raise_for_status()
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > settings.NEWS_HTTP_MAX_BYTES:
                        raise FeedFetchError("The feed response exceeded the size limit")
                    chunks = []
                    byte_count = 0
                    for chunk in response.iter_bytes():
                        byte_count += len(chunk)
                        if byte_count > settings.NEWS_HTTP_MAX_BYTES:
                            raise FeedFetchError("The feed response exceeded the size limit")
                        if time.monotonic() - started_at > settings.NEWS_HTTP_TOTAL_TIMEOUT_SECONDS:
                            raise FeedFetchError("The feed request exceeded the total time limit")
                        chunks.append(chunk)
                    return FeedResponse(
                        body=b"".join(chunks),
                        etag=response.headers.get("ETag"),
                        last_modified=response.headers.get("Last-Modified"),
                        final_url=current_url,
                    )
            except httpx.HTTPStatusError as error:
                status = error.response.status_code
                if status == 403:
                    detail = "The publisher refused the feed request (HTTP 403)"
                elif status == 404:
                    detail = "The feed address or channel ID was not found (HTTP 404)"
                elif status == 429:
                    detail = "The publisher is rate-limiting feed requests (HTTP 429)"
                else:
                    detail = f"The publisher returned HTTP {status}"
                raise FeedFetchError(detail) from error
            except httpx.TimeoutException as error:
                raise FeedFetchError("The publisher did not respond within the time limit") from error
            except httpx.HTTPError as error:
                raise FeedFetchError("Could not connect to the publisher or read its response") from error
            except ValueError as error:
                raise FeedFetchError("The publisher returned an invalid response") from error
        raise FeedFetchError("The feed exceeded the redirect limit")
    finally:
        if owns_client:
            request_client.close()
