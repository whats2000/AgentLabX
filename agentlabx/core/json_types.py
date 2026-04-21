"""Recursive JSON value type aliases used wherever payloads cross module boundaries.

Both ``agentlabx.events`` and ``agentlabx.mcp`` need a precise type for arbitrary
JSON-serialisable structures. Defining them in this neutral package avoids any
``events -> mcp`` reverse import.
"""

JSONScalar = str | int | float | bool | None
"""Any JSON primitive (no containers)."""

# PEP 695 named type alias — recursive aliases must be declared with `type` so
# pydantic (and other introspectors) can resolve the self-reference without
# blowing the recursion limit. We deliberately omit `from __future__ import
# annotations` here: PEP 695 `type` statements need to be evaluated at runtime.
type JSONValue = JSONScalar | dict[str, "JSONValue"] | list["JSONValue"]
"""A JSON-serialisable value: scalar, JSON object, or JSON array (recursive)."""

__all__ = ["JSONScalar", "JSONValue"]
