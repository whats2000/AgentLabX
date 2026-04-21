"""Cross-cutting type aliases and primitives shared across packages.

This package is intentionally dependency-free: any module may import from it
without creating cycles. It currently exposes the JSON value type aliases used
by the event bus and the MCP host.
"""
