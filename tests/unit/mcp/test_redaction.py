"""Unit tests for the MCP redaction primitives."""

from __future__ import annotations

from agentlabx.core.json_types import JSONValue
from agentlabx.mcp.redaction import SECRET_KEYS, redact_args, redact_text

# ---------------------------------------------------------------------------
# redact_args
# ---------------------------------------------------------------------------


def test_redact_args_top_level_secret_key() -> None:
    args: dict[str, JSONValue] = {"api_key": "sk-live-abc123", "model": "gpt-4"}
    out = redact_args(args)
    assert out == {"api_key": "***", "model": "gpt-4"}


def test_redact_args_case_insensitive_keys() -> None:
    args: dict[str, JSONValue] = {
        "API_KEY": "k1",
        "Authorization": "Bearer xyz",
        "X-Api-Key": "k2",
        "Bearer": "tok",
    }
    out = redact_args(args)
    assert out == {
        "API_KEY": "***",
        "Authorization": "***",
        "X-Api-Key": "***",
        "Bearer": "***",
    }


def test_redact_args_nested_dict() -> None:
    args: dict[str, JSONValue] = {
        "config": {
            "endpoint": "https://api.example.com",
            "credentials": {"token": "t-1", "username": "alice"},
        }
    }
    out = redact_args(args)
    assert out == {
        "config": {
            "endpoint": "https://api.example.com",
            "credentials": {"token": "***", "username": "alice"},
        }
    }


def test_redact_args_list_in_dict() -> None:
    # Secret detection is by key name only — values whose dict key is in
    # SECRET_KEYS get scrubbed; sibling keys ("name", "trace") pass through.
    args: dict[str, JSONValue] = {
        "headers": [
            {"name": "auth", "authorization": "Bearer xyz"},
            {"name": "trace", "trace_id": "abc"},
        ]
    }
    out = redact_args(args)
    assert out == {
        "headers": [
            {"name": "auth", "authorization": "***"},
            {"name": "trace", "trace_id": "abc"},
        ]
    }


def test_redact_args_deeply_nested_lists_and_dicts() -> None:
    args: dict[str, JSONValue] = {
        "items": [
            [{"password": "p1"}, {"keep": "v"}],
            [{"refresh_token": "r1"}],
        ]
    }
    out = redact_args(args)
    assert out == {
        "items": [
            [{"password": "***"}, {"keep": "v"}],
            [{"refresh_token": "***"}],
        ]
    }


def test_redact_args_no_secrets_passthrough() -> None:
    args: dict[str, JSONValue] = {"a": 1, "b": [1, 2, 3], "c": {"d": True, "e": None}}
    out = redact_args(args)
    assert out == args
    # But it's a fresh dict — caller can mutate without aliasing.
    assert out is not args


def test_redact_args_idempotent() -> None:
    args: dict[str, JSONValue] = {
        "api_key": "k",
        "nested": {"token": "t", "data": [{"password": "p"}, "plain"]},
    }
    once = redact_args(args)
    twice = redact_args(once)
    assert once == twice


def test_redact_args_preserves_scalars_and_none() -> None:
    args: dict[str, JSONValue] = {"x": 0, "y": False, "z": None, "f": 1.5}
    out = redact_args(args)
    assert out == args


def test_redact_args_secret_keys_constant_lowercase() -> None:
    # Sanity: invariant the implementation depends on.
    assert all(k == k.lower() for k in SECRET_KEYS)


# ---------------------------------------------------------------------------
# redact_text
# ---------------------------------------------------------------------------


def test_redact_text_single_slot() -> None:
    out = redact_text("connecting with token=sk-abc-123 ok", ["sk-abc-123"])
    assert out == "connecting with token=*** ok"


def test_redact_text_multiple_slots() -> None:
    out = redact_text("a=A1 b=B2 c=A1", ["A1", "B2"])
    assert out == "a=*** b=*** c=***"


def test_redact_text_empty_slot_is_skipped() -> None:
    text = "hello world"
    assert redact_text(text, [""]) == text
    # Empty mixed with real slot should still scrub the real one.
    assert redact_text("hello world", ["", "world"]) == "hello ***"


def test_redact_text_descending_length_order() -> None:
    # If "AA" were processed first, "AAAA" would become "******" (two ***).
    # Processing longest-first yields a single "***".
    out = redact_text("AAAA", ["AA", "AAAA"])
    assert out == "***"


def test_redact_text_no_match_returns_original() -> None:
    assert redact_text("nothing secret here", ["zzz"]) == "nothing secret here"


def test_redact_text_empty_iterable() -> None:
    assert redact_text("hello", []) == "hello"


def test_redact_text_accepts_generator() -> None:
    def gen() -> list[str]:
        return ["secret"]

    # Single-pass iterator must be safe — implementation materialises it.
    out = redact_text("a secret value", iter(gen()))
    assert out == "a *** value"
