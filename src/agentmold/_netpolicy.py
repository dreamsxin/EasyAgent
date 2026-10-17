"""Shared network-policy helpers for tool factories.

These helpers enforce the same SSRF and private-network guards for both
:func:`agentmold.tools.http_tools` and :func:`agentmold.mcp.mcp_tools`.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import SplitResult, urlsplit, urlunsplit

import idna

__all__ = [
    "normalise_host",
    "normalise_allowed_hosts",
    "resolved_addresses",
    "safe_request_url",
    "validate_server_url",
]


def normalise_host(host: str) -> str:
    """Return a comparable hostname or IP literal, encoded the way httpx sends it.

    The encoding must match the transport exactly.  ``str.encode("idna")`` is
    the stdlib IDNA2003 codec, whose nameprep mapping disagrees with the
    IDNA2008/UTS-46 encoding used by ``httpx`` (via the ``idna`` package):
    ``straße.example`` becomes ``strasse.example`` under IDNA2003 but
    ``xn--strae-oqa.example`` under UTS-46.  Validating one form while
    requesting the other would let an allowlisted name reach a different host.
    """
    value = host.strip().strip("[]").rstrip(".").lower()
    if not value:
        raise ValueError("allowed_hosts must contain non-empty hostnames")
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        pass
    if value.isascii():
        # httpx sends ASCII hosts verbatim (lowercased) without IDNA encoding,
        # so re-encoding here would reject hosts the transport accepts, such as
        # the underscores common in internal DNS names.
        return value
    try:
        return idna.encode(value, uts46=True).decode("ascii")
    except idna.IDNAError as exc:
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


def safe_request_url(parsed: SplitResult, host: str) -> str:
    """Rebuild a request URL so the transport contacts the validated *host*.

    Handing the caller's raw URL string to httpx would re-derive the host from
    the original text, which is not necessarily the host that was allowlisted
    (see :func:`normalise_host`).  Rebuilding from validated parts also drops
    userinfo and the fragment, neither of which belongs in an outbound request.
    """
    netloc = f"[{host}]" if ":" in host else host
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))


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
