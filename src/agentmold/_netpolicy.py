"""Shared network-policy helpers for tool factories.

These helpers enforce the same SSRF and private-network guards for both
:func:`agentmold.tools.http_tools` and :func:`agentmold.mcp.mcp_tools`.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlsplit

__all__ = [
    "normalise_host",
    "normalise_allowed_hosts",
    "resolved_addresses",
    "validate_server_url",
]


def normalise_host(host: str) -> str:
    """Return a comparable lowercase hostname or IP literal."""
    value = host.strip().strip("[]").rstrip(".").lower()
    if not value:
        raise ValueError("allowed_hosts must contain non-empty hostnames")
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        try:
            return value.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"invalid host: {host!r}") from exc


def normalise_allowed_hosts(allowed_hosts: Iterable[str]) -> frozenset[str]:
    """Validate and normalise a hostname allowlist (no URLs, paths, or ports)."""
    hosts = []
    for host in allowed_hosts:
        raw = str(host).strip()
        if not raw or "://" in raw or any(char in raw for char in "/@?#"):
            raise ValueError("allowed_hosts must contain hostnames only, without URLs or paths")
        try:
            parsed = urlsplit(f"//{raw}")
            if parsed.port is not None:
                raise ValueError("allowed_hosts must not include ports")
        except ValueError as exc:
            raise ValueError(f"invalid allowed host {host!r}: {exc}") from exc
        hosts.append(normalise_host(raw))
    if not hosts:
        raise ValueError("allowed_hosts must not be empty")
    return frozenset(hosts)


def resolved_addresses(host: str, port: int) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve *host* to a set of IP addresses, rejecting DNS failures."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError(f"could not resolve host {host!r}: {exc}") from exc
        addresses = {ipaddress.ip_address(info[4][0]) for info in infos}
    else:
        addresses = {literal}
    if not addresses:
        raise ValueError(f"host {host!r} resolved to no addresses")
    return addresses


def validate_server_url(
    url: str,
    allowed_hosts: frozenset[str] | None,
    allow_private: bool,
) -> str:
    """Validate that *url* may be contacted under the network policy.

    Returns the normalised hostname.  Raises ``ValueError`` if the host is not
    allowlisted, DNS resolves to a private/non-global address, or the URL is
    malformed.
    """
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme: {parsed.scheme!r} (expected http or https)")
    host = (parsed.hostname or "").strip().strip("[]")
    if not host:
        raise ValueError(f"URL has no host: {url!r}")
    normalised = normalise_host(host)
    if allowed_hosts is not None and normalised not in allowed_hosts:
        raise ValueError(f"host {host!r} is not in the allowed_hosts allowlist")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = resolved_addresses(normalised, port)
    if not allow_private:
        for addr in addresses:
            if not addr.is_global:
                raise ValueError(
                    f"host {host!r} resolves to non-global address {addr}; "
                    "pass allow_private=True to reach local/lab servers"
                )
    return normalised
