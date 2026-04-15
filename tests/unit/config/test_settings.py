from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.config.settings import AppSettings, BindMode, TLSConfigurationError


def test_defaults_are_loopback_and_no_tls(tmp_workspace: Path) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    assert settings.bind_mode is BindMode.LOOPBACK
    assert settings.bind_host == "127.0.0.1"
    assert settings.tls_cert is None
    assert settings.tls_key is None
    assert settings.db_path == tmp_workspace / "agentlabx.db"


def test_lan_bind_without_tls_raises(tmp_workspace: Path) -> None:
    with pytest.raises(TLSConfigurationError):
        AppSettings(workspace=tmp_workspace, bind_mode=BindMode.LAN)


def test_lan_bind_with_tls_succeeds(tmp_workspace: Path) -> None:
    cert = tmp_workspace / "cert.pem"
    key = tmp_workspace / "key.pem"
    cert.write_text("fake")
    key.write_text("fake")
    settings = AppSettings(
        workspace=tmp_workspace,
        bind_mode=BindMode.LAN,
        bind_host="0.0.0.0",  # noqa: S104 — LAN bind is explicit here
        tls_cert=cert,
        tls_key=key,
    )
    assert settings.bind_host == "0.0.0.0"  # noqa: S104


def test_lan_bind_with_missing_cert_file_raises(tmp_workspace: Path) -> None:
    with pytest.raises(TLSConfigurationError):
        AppSettings(
            workspace=tmp_workspace,
            bind_mode=BindMode.LAN,
            tls_cert=tmp_workspace / "nonexistent.pem",
            tls_key=tmp_workspace / "nonexistent.key",
        )
