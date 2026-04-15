from __future__ import annotations

from agentlabx.auth.protocol import Auther, Identity


def test_identity_is_frozen_and_equal_by_value() -> None:
    a = Identity(
        id="u1",
        auther_name="default",
        display_name="Alice",
        email="alice@example.com",
        capabilities=frozenset({"admin"}),
    )
    b = Identity(
        id="u1",
        auther_name="default",
        display_name="Alice",
        email="alice@example.com",
        capabilities=frozenset({"admin"}),
    )
    assert a == b


def test_auther_protocol_can_be_satisfied_by_plain_class() -> None:
    class FakeAuther:
        name = "fake"

        def authenticate(self, credentials: dict[str, str]) -> Identity:
            return Identity(
                id="u1",
                auther_name="fake",
                display_name="F",
                email="fake@example.com",
                capabilities=frozenset(),
            )

    a: Auther = FakeAuther()  # static-type assertion + runtime check via isinstance
    assert isinstance(a, Auther)
