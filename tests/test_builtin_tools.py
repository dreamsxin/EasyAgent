"""Tests for explicitly scoped built-in tools."""

from __future__ import annotations

import socket

import pytest

from agentmold.tools import calculate, http_tools, workspace_tools


def test_workspace_tools_are_confined_to_root(tmp_path):
    (tmp_path / "hello.txt").write_text("hello world", encoding="utf-8")
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    tools = {item.name: item for item in workspace_tools(tmp_path)}

    assert tools["read_file"].call({"file_path": "hello.txt"}) == "hello world"
    assert "outside" in tools["read_file"].call({"file_path": "../outside.txt"})
    assert "outside" in tools["read_file"].call({"file_path": str(outside)})
    assert "write_file" not in tools


def test_workspace_tools_support_read_listing_and_explicit_write(tmp_path):
    (tmp_path / "big.txt").write_text("x" * 500, encoding="utf-8")
    tools = {item.name: item for item in workspace_tools(tmp_path, allow_write=True)}

    assert tools["read_file"].call({"file_path": "big.txt"}).startswith("x" * 500)
    listing = tools["list_directory"].call({})
    assert "[file] big.txt" in listing

    result = tools["write_file"].call({"file_path": "sub/out.txt", "content": "data"})
    assert result == "Wrote 4 characters to sub/out.txt"
    assert (tmp_path / "sub" / "out.txt").read_text(encoding="utf-8") == "data"


def test_workspace_tools_reject_symlink_escape(tmp_path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")

    read_file = {item.name: item for item in workspace_tools(tmp_path)}["read_file"]
    assert "outside" in read_file.call({"file_path": "link.txt"})


def test_workspace_tools_validate_limits(tmp_path):
    with pytest.raises(ValueError, match="existing directory"):
        workspace_tools(tmp_path / "missing")
    with pytest.raises(ValueError, match="max_read_chars"):
        workspace_tools(tmp_path, max_read_chars=0)
    with pytest.raises(ValueError, match="max_write_chars"):
        workspace_tools(tmp_path, max_write_chars=0)


class _FakeResponse:
    def __init__(self, body: str = "ok", status_code: int = 200):
        self.text = body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


def _public_dns(*args, **kwargs):  # noqa: ARG001
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]


def test_http_tools_require_allowlisted_host(monkeypatch):
    http_get = http_tools({"example.com"})[0]
    monkeypatch.setattr(
        "agentmold.tools.httpx.get",
        lambda *args, **kwargs: pytest.fail("request should not be made"),
    )
    result = http_get.call({"url": "https://other.example.com/data"})
    assert "allowlisted" in result


def test_http_tools_block_private_destinations(monkeypatch):
    http_get = http_tools({"127.0.0.1"})[0]
    monkeypatch.setattr(
        "agentmold.tools.httpx.get",
        lambda *args, **kwargs: pytest.fail("request should not be made"),
    )
    result = http_get.call({"url": "http://127.0.0.1:8000/"})
    assert "non-global" in result


def test_http_tools_validate_dns_before_request(monkeypatch):
    http_get = http_tools({"internal.example"})[0]
    monkeypatch.setattr(
        "agentmold.tools.socket.getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.20", 80))],
    )
    monkeypatch.setattr(
        "agentmold.tools.httpx.get",
        lambda *args, **kwargs: pytest.fail("request should not be made"),
    )
    result = http_get.call({"url": "http://internal.example/data"})
    assert "non-global" in result


def test_http_tools_request_public_host_without_redirects(monkeypatch):
    http_get = http_tools({"example.com"}, max_chars=4)[0]
    monkeypatch.setattr("agentmold.tools.socket.getaddrinfo", _public_dns)
    calls = {}

    def fake_get(url, **kwargs):
        calls.update(url=url, **kwargs)
        return _FakeResponse("abcdef")

    monkeypatch.setattr("agentmold.tools.httpx.get", fake_get)
    assert http_get.call({"url": "https://example.com/data"}) == (
        "abcd\n... (truncated, 2 more chars)"
    )
    assert calls["follow_redirects"] is False


def test_http_tools_reject_redirects(monkeypatch):
    http_get = http_tools({"example.com"})[0]
    monkeypatch.setattr("agentmold.tools.socket.getaddrinfo", _public_dns)
    monkeypatch.setattr(
        "agentmold.tools.httpx.get",
        lambda *args, **kwargs: _FakeResponse(status_code=302),
    )
    result = http_get.call({"url": "https://example.com/redirect"})
    assert "redirects are disabled" in result


def test_http_tools_can_explicitly_allow_private_destinations(monkeypatch):
    http_get = http_tools({"127.0.0.1"}, allow_private=True)[0]
    monkeypatch.setattr("agentmold.tools.httpx.get", lambda *args, **kwargs: _FakeResponse("local"))
    assert http_get.call({"url": "http://127.0.0.1:8000/"}) == "local"


def test_http_tools_validate_policy_arguments():
    with pytest.raises(ValueError, match="must not be empty"):
        http_tools([])
    with pytest.raises(ValueError, match="must not include ports"):
        http_tools(["example.com:443"])
    with pytest.raises(ValueError, match="max_chars"):
        http_tools(["example.com"], max_chars=0)
    with pytest.raises(ValueError, match="timeout"):
        http_tools(["example.com"], timeout=0)


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("2 + 3", "5"),
        ("2 + 3 * 4", "14"),
        ("(2 + 3) * 4", "20"),
        ("100 / 4", "25"),
        ("7 // 2", "3"),
        ("10 % 3", "1"),
        ("2 ** 10", "1024"),
        ("-5 + 3", "-2"),
        ("3.5 + 1.5", "5"),
    ],
)
def test_calculate_valid_expressions(expr, expected):
    assert calculate.call({"expression": expr}) == expected


def test_calculate_rejects_unsafe_or_unbounded_inputs():
    assert "Error" in calculate.call({"expression": "x + 1"})
    assert "Error" in calculate.call({"expression": "__import__('os')"})
    assert "Error" in calculate.call({"expression": "2 + "})
    assert "Error" in calculate.call({"expression": "2 ** 101"})
    assert "Error" in calculate.call({"expression": "9" * 201})


def test_scoped_tools_have_openai_schemas(tmp_path):
    tools = [calculate, *workspace_tools(tmp_path), *http_tools({"example.com"})]
    for item in tools:
        schema = item.to_dict()
        assert schema["name"]
        assert schema["description"]
        assert "properties" in schema["parameters"]
