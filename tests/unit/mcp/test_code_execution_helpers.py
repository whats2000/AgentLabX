"""Unit tests for ``code_execution_server`` pure helpers.

The Docker subprocess + image-pull paths cannot run in this unit context
(they need a live daemon and seconds of wall-clock); this file covers the
classifier helpers + argv builder that decide *which* failure shape the
caller sees. A future SDK / docker-cli message change that breaks the
daemon-down detection would silently downgrade an infra failure to a
user-code failure, so pinning the markers here is load-bearing.
"""

from __future__ import annotations

import pytest

from agentlabx.mcp.bundles.code_execution_server import (
    PINNED_IMAGE_DIGEST,
    _docker_command,
    _looks_like_docker_daemon_down,
)


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        # Linux: dockerd socket missing.
        ("Cannot connect to the Docker daemon at unix:///var/run/docker.sock", True),
        # Windows Docker Desktop named-pipe not present (the case captured
        # live during the user's smoke).
        (
            "open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.",
            True,
        ),
        # Generic helper-level diagnostic from `docker version`.
        ("error during connect: this error may indicate that the docker daemon...", True),
        # Daemon-down hint emitted by older docker CLI versions.
        ("Is the docker daemon running?", True),
        # User-code failures must NOT match — false positives would
        # mis-classify a ``raise SystemExit(1)`` as an infra failure.
        ("Traceback (most recent call last):\n  File '<string>', line 1...", False),
        ("ZeroDivisionError: division by zero", False),
        # Empty stderr is not a daemon-down signal.
        ("", False),
        # Random unrelated stderr.
        ("warning: package 'foo' has 3 vulnerabilities", False),
    ],
)
def test_looks_like_docker_daemon_down_marker_set(stderr: str, expected: bool) -> None:
    assert _looks_like_docker_daemon_down(stderr) is expected


def test_looks_like_docker_daemon_down_is_case_insensitive() -> None:
    """Markers are matched case-insensitively to survive cli capitalisation drift."""

    assert _looks_like_docker_daemon_down("CANNOT CONNECT TO THE DOCKER DAEMON")
    assert _looks_like_docker_daemon_down("Is The Docker Daemon Running?")


def test_docker_command_pins_digest_and_hardening_flags() -> None:
    """Every ``code.exec`` shells the same hardened argv shape.

    The pinned image digest + ``--network=none`` + memory/cpu/pids caps +
    read-only fs are the contract that lets us claim "sandboxed" — a
    refactor that drops any of them is a security regression and must be
    caught here. The user's source string is the *last* argv element
    (passed via ``python -c``).
    """

    argv = _docker_command("print(7 * 6)")

    assert argv[0] == "docker"
    assert argv[1] == "run"
    assert "--rm" in argv
    assert "--network=none" in argv
    assert "--memory=512m" in argv
    assert "--cpus=1" in argv
    assert "--read-only" in argv
    assert "--pids-limit=64" in argv
    assert "--user" in argv and argv[argv.index("--user") + 1] == "1000:1000"
    assert PINNED_IMAGE_DIGEST in argv
    # Last three: python -c <code>
    assert argv[-3:] == ("python", "-c", "print(7 * 6)")
