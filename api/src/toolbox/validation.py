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


async def validate_url(url: str) -> None:
    """Reject URLs that could cause SSRF or are obviously invalid.

    Blocks: file://, ftp://, non-HTTP schemes, loopback (127.x, ::1),
    link-local (169.254.x), unspecified (0.0.0.0), IPv4-mapped IPv6
    loopback (::ffff:127.0.0.1), and cloud metadata endpoints.
    LAN private ranges (192.168.x, 10.x) are allowed since this
    is a LAN-only service and agents may need to fetch from local hosts.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL.")

    if not parsed.scheme or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: missing scheme or host.")

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail=f"URL scheme '{parsed.scheme}' is not allowed. Use http or https.",
        )

    hostname = parsed.hostname.lower()

    if hostname in BLOCKED_HOSTS:
        raise HTTPException(status_code=400, detail="Access to this host is not allowed.")

    # Resolve hostname and check for dangerous IPs
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # It's a hostname — resolve via DNS in a thread to avoid blocking the event loop
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
        raise HTTPException(
            status_code=400,
            detail="Access to loopback/link-local addresses is not allowed.",
        )

    # IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) — check the inner IPv4
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        mapped = addr.ipv4_mapped
        if mapped.is_loopback or mapped.is_link_local or mapped.is_unspecified:
            raise HTTPException(
                status_code=400,
                detail="Access to loopback/link-local addresses is not allowed.",
            )
