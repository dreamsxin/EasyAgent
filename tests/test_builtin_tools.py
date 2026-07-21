"""Tests for the built-in tool library."""

from __future__ import annotations

import pytest

from agentmold.tools import (
    BUILTIN_TOOLS,
    calculate,
    http_get,
    list_directory,
    read_file,
    write_file,
)

# ---------------------------------------------------------------------------
# read_file / write_file / list_directory
# ---------------------------------------------------------------------------


def test_read_file_returns_content(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hello world", encoding="utf-8")
    result = read_file.call({"file_path": str(f)})
    assert result == "hello world"


def test_read_file_truncates_long_content(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("x" * 500, encoding="utf-8")
    result = read_file.call({"file_path": str(f), "max_chars": 10})
    assert result.startswith("xxxxxxxxxx")
    assert "truncated" in result


def test_read_file_missing_file(tmp_path):
    result = read_file.call({"file_path": str(tmp_path / "nope.txt")})
    assert "not found" in result.lower()


def test_write_file_creates_file(tmp_path):
    target = tmp_path / "sub" / "out.txt"
    result = write_file.call({"file_path": str(target), "content": "data"})
    assert target.read_text(encoding="utf-8") == "data"
    assert "Wrote 4 characters" in result


def test_list_directory(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    result = list_directory.call({"dir_path": str(tmp_path)})
    assert "[file] a.txt" in result
    assert "[dir] sub" in result


def test_list_directory_empty(tmp_path):
    result = list_directory.call({"dir_path": str(tmp_path)})
    assert "empty" in result.lower()


def test_list_directory_missing(tmp_path):
    result = list_directory.call({"dir_path": str(tmp_path / "nope")})
    assert "not found" in result.lower()


# ---------------------------------------------------------------------------
# calculate
# ---------------------------------------------------------------------------


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


def test_calculate_rejects_variables():
    result = calculate.call({"expression": "x + 1"})
    assert "Error" in result


def test_calculate_rejects_function_calls():
    result = calculate.call({"expression": "__import__('os')"})
    assert "Error" in result


def test_calculate_rejects_syntax_error():
    result = calculate.call({"expression": "2 + "})
    assert "Error" in result


# ---------------------------------------------------------------------------
# http_get
# ---------------------------------------------------------------------------


def test_http_get_rejects_non_http_url():
    result = http_get.call({"url": "ftp://example.com"})
    assert "Error" in result


def test_http_get_handles_invalid_host():
    # A non-routable host fails fast — no network dependency in practice.
    result = http_get.call(
        {"url": "http://agentmold-nonexistent-host-12345.invalid/x", "timeout": 3}
    )
    assert "Error" in result


# ---------------------------------------------------------------------------
# BUILTIN_TOOLS aggregate
# ---------------------------------------------------------------------------


def test_builtin_tools_list_is_complete():
    names = {t.name for t in BUILTIN_TOOLS}
    assert names == {"read_file", "write_file", "list_directory", "http_get", "calculate"}


def test_builtin_tools_have_schemas():
    for t in BUILTIN_TOOLS:
        schema = t.to_dict()
        assert schema["name"]
        assert schema["description"]
        assert "properties" in schema["parameters"]
