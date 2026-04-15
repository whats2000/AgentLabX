# tests/integration/test_lan_requires_tls.py
from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.config.settings import AppSettings, BindMode, TLSConfigurationError


@pytest.mark.integration
def test_lan_without_tls_raises(tmp_workspace: Path) -> None:
    with pytest.raises(TLSConfigurationError):
        AppSettings(
            workspace=tmp_workspace,
            bind_mode=BindMode.LAN,
            bind_host="0.0.0.0",  # noqa: S104
        )


@pytest.mark.integration
def test_lan_with_tls_files_missing_raises(tmp_workspace: Path) -> None:
    with pytest.raises(TLSConfigurationError):
        AppSettings(
            workspace=tmp_workspace,
            bind_mode=BindMode.LAN,
            bind_host="0.0.0.0",  # noqa: S104
            tls_cert=tmp_workspace / "nope.pem",
            tls_key=tmp_workspace / "nope.key",
        )


@pytest.mark.integration
def test_loopback_without_tls_succeeds(tmp_workspace: Path) -> None:
    s = AppSettings(workspace=tmp_workspace)
    assert s.bind_mode is BindMode.LOOPBACK
    assert s.tls_cert is None
