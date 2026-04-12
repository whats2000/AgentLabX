"""Tests for the agentlabx CLI."""

from __future__ import annotations

import os
from unittest.mock import patch

from click.testing import CliRunner

from agentlabx.cli.main import _build_app_with_config, cli


class TestCliBasics:
    def test_version_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help_shows_commands(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "serve" in result.output

    def test_serve_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output
        assert "--mock-llm" in result.output
        assert "--reload" in result.output


class TestServeCommand:
    def test_serve_invokes_uvicorn_with_factory(self, tmp_path):
        """serve() passes the factory string to uvicorn.run."""
        os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
        os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
        try:
            runner = CliRunner()
            with patch("agentlabx.cli.main.uvicorn.run") as mock_run:
                result = runner.invoke(cli, ["serve", "--port", "9999", "--mock-llm"])
            assert result.exit_code == 0
            mock_run.assert_called_once()
            kwargs = mock_run.call_args.kwargs
            assert kwargs["port"] == 9999
            assert kwargs["host"] == "0.0.0.0"
            assert kwargs["factory"] is True
            # First positional arg is the factory import path
            args = mock_run.call_args.args
            assert args[0] == "agentlabx.cli.main:_build_app_with_config"
        finally:
            os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
            os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)

    def test_serve_sets_mock_llm_global(self, tmp_path):
        """After invoking serve --mock-llm, the module flag is set."""
        import agentlabx.cli.main as cli_main

        os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
        os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
        try:
            # Reset flag to known state
            cli_main._USE_MOCK_LLM = False
            runner = CliRunner()
            with patch("agentlabx.cli.main.uvicorn.run"):
                runner.invoke(cli, ["serve", "--mock-llm"])
            assert cli_main._USE_MOCK_LLM is True
        finally:
            os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
            os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


class TestFactory:
    def test_build_app_returns_fastapi(self, tmp_path):
        """The factory function builds a valid FastAPI app."""
        from fastapi import FastAPI

        os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
        os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
        try:
            app = _build_app_with_config()
            assert isinstance(app, FastAPI)
            assert app.title == "AgentLabX"
        finally:
            os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
            os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)
