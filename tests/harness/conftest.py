"""Harness suite conftest — skips every test unless a live provider is configured.

The harness tests require a real LLM provider. Skipping at collection time (not
test time) keeps `pytest` runs clean when env vars are absent.
"""
from __future__ import annotations

import os

import pytest


REQUIRED_MODEL_VAR = "AGENTLABX_LLM__DEFAULT_MODEL"

# Map provider prefix (before '/') → env var that must be set for that provider.
PROVIDER_KEY_VARS = {
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "azure": "AZURE_API_KEY",
}


def _missing_requirements() -> str | None:
    model = os.environ.get(REQUIRED_MODEL_VAR)
    if not model:
        return f"{REQUIRED_MODEL_VAR} not set"
    prefix = model.split("/", 1)[0].lower()
    key_var = PROVIDER_KEY_VARS.get(prefix)
    if key_var is None:
        return f"Unknown provider prefix '{prefix}' in {REQUIRED_MODEL_VAR}"
    if not os.environ.get(key_var):
        return f"{key_var} not set (required for provider '{prefix}')"
    return None


def pytest_collection_modifyitems(config, items):
    """Skip any test marked live_harness when provider env vars are missing."""
    reason = _missing_requirements()
    if reason is None:
        return
    skip_marker = pytest.mark.skip(reason=f"live_harness skipped: {reason}")
    for item in items:
        if "live_harness" in item.keywords:
            item.add_marker(skip_marker)
