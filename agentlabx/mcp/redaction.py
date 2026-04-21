"""Redaction primitives for MCP host — secret-key and slot-value scrubbing.

Pure, deterministic helpers used by the host before any payload (tool-call
arguments, captured stderr/stdout) is logged, emitted as an event, or returned
to a caller. No I/O, no logging — callers are responsible for plumbing.

Two complementary scrubbers:

- :func:`redact_args` walks a tool-call argument mapping and replaces values
  whose key (case-insensitive) is in :data:`SECRET_KEYS` with the literal
  string sentinel ``"***"``. Lists, tuples, and nested dicts are walked
  recursively.
- :func:`redact_text` replaces literal occurrences of caller-supplied secret
  values (the actual decrypted strings currently in flight) inside an
  arbitrary text blob — used to scrub subprocess stderr/stdout snippets the
  host captures. Empty slots are skipped (otherwise they'd match between
  every character) and slots are processed in descending length order so a
  longer secret containing a shorter one as a substring is matched first.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from agentlabx.core.json_types import JSONValue

SECRET_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "x-api-key",
        "token",
        "access_token",
        "refresh_token",
        "password",
        "passphrase",
        "secret",
        "authorization",
        "bearer",
    }
)
"""Keys (case-insensitive) whose values are scrubbed by :func:`redact_args`."""

_REDACTED: str = "***"


def _redact_value(value: JSONValue) -> JSONValue:
    """Recursively redact a single JSON value (helper for non-secret branches)."""
    if isinstance(value, dict):
        return redact_args(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def redact_args(args: Mapping[str, JSONValue]) -> dict[str, JSONValue]:
    """Return a copy of *args* with secret-keyed values replaced by ``"***"``.

    Key matching is case-insensitive against :data:`SECRET_KEYS`. Nested
    dicts and lists are walked recursively; tuples (which JSON does not have
    natively but may appear in loosely-typed inputs) are also walked
    element-wise and emitted as lists.
    """
    out: dict[str, JSONValue] = {}
    for key, value in args.items():
        if key.lower() in SECRET_KEYS:
            out[key] = _REDACTED
            continue
        if isinstance(value, dict):
            out[key] = redact_args(value)
        elif isinstance(value, list):
            out[key] = [_redact_value(item) for item in value]
        elif isinstance(value, tuple):
            # Defensive: ``Mapping[str, JSONValue]`` does not include tuples,
            # but real-world callers sometimes pass them. Walk element-wise
            # and materialise as a list (JSON-compatible).
            out[key] = [_redact_value(item) for item in value]
        else:
            out[key] = value
    return out


def redact_text(text: str, slots: Iterable[str]) -> str:
    """Replace every literal occurrence of each slot value in *text* with ``"***"``.

    Empty slots are skipped (replacing the empty string would mangle the
    text). Slots are processed in descending length order so that a longer
    secret containing a shorter one as a substring is redacted first.
    """
    # Materialise once; ``slots`` may be a single-pass iterator.
    candidates = [s for s in slots if s]
    candidates.sort(key=len, reverse=True)
    result = text
    for slot in candidates:
        result = result.replace(slot, _REDACTED)
    return result


__all__ = ["SECRET_KEYS", "redact_args", "redact_text"]
