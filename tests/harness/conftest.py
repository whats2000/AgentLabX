"""Harness suite conftest — skips every test unless a live provider is configured.

The harness tests require a real LLM provider. Skipping at collection time (not
test time) keeps `pytest` runs clean when env vars are absent.
"""
from __future__ import annotations

import os

import pytest


def _load_dotenv() -> None:
    """Load .env file from repo root into os.environ (without overriding existing vars)."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]  # tests/harness/conftest.py → AgentLabX/
    env_file = repo_root / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

# If GEMINI_API_KEY is present but AGENTLABX_LLM__DEFAULT_MODEL is not,
# set a sensible Gemini flash default for the harness.
if os.environ.get("GEMINI_API_KEY") and not os.environ.get("AGENTLABX_LLM__DEFAULT_MODEL"):
    os.environ["AGENTLABX_LLM__DEFAULT_MODEL"] = "gemini/gemini-2.5-flash"


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
