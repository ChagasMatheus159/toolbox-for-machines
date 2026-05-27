"""Input validation utilities for toolbox endpoints."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException

ALLOWED_SCHEMES = {"http", "https"}

BLOCKED_HOSTS = {
    "metadata.google.internal",
}


class URLValidationError(Exception):
    """Raised when a URL fails validation."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def _check_url(url: str) -> str:
    """Parse and validate URL structure. Returns hostname on success."""
    try:
        parsed = urlparse(url)
    except Exception:
        raise URLValidationError("Invalid URL.")

    if not parsed.scheme or not parsed.hostname:
        raise URLValidationError("Invalid URL: missing scheme or host.")

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise URLValidationError(f"URL scheme '{parsed.scheme}' is not allowed. Use http or https.")

    hostname = parsed.hostname.lower()

    if hostname in BLOCKED_HOSTS:
        raise URLValidationError("Access to this host is not allowed.")

    return hostname


async def _check_ip(hostname: str) -> None:
    """Resolve hostname and reject dangerous IPs."""
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        loop = asyncio.get_event_loop()
        try:
            resolved = await loop.run_in_executor(
                None, socket.getaddrinfo, hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
            )
            if resolved:
                addr = ipaddress.ip_address(resolved[0][4][0])
            else:
                return
        except socket.gaierror:
            return

    if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
        raise URLValidationError("Access to loopback/link-local addresses is not allowed.")

    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        mapped = addr.ipv4_mapped
        if mapped.is_loopback or mapped.is_link_local or mapped.is_unspecified:
            raise URLValidationError("Access to loopback/link-local addresses is not allowed.")


async def validate_url_raw(url: str) -> None:
    """Validate a URL, raising URLValidationError on failure.

    Use this from non-HTTP contexts (MCP handlers).
    """
    hostname = _check_url(url)
    await _check_ip(hostname)


async def validate_url(url: str) -> None:
    """Validate a URL, raising HTTPException on failure.

    Use this from FastAPI REST handlers.
    """
    try:
        await validate_url_raw(url)
    except URLValidationError as e:
        raise HTTPException(status_code=400, detail=e.detail)
