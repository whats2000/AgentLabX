from __future__ import annotations

import logging
from collections.abc import Iterable

import litellm
from litellm.exceptions import BadRequestError
from sqlalchemy import select

from agentlabx.db.schema import UserConfig
from agentlabx.db.session import DatabaseHandle
from agentlabx.security.fernet_store import FernetStore

_log = logging.getLogger(__name__)


class NoCredentialError(Exception):
    """Raised when a user has no stored credential for the required provider."""

    def __init__(self, provider_name: str, user_id: str) -> None:
        self.provider_name = provider_name
        self.user_id = user_id
        super().__init__(f"no credential stored for provider '{provider_name}' (user {user_id})")


class KeyResolver:
    """Resolves a per-user API key from the encrypted credential store.

    Uses LiteLLM's built-in model registry to determine which provider
    owns a model, then looks up the user's encrypted key for that provider.
    The set of "local" providers (no key required) is configurable via
    ``AppSettings.local_providers``.
    """

    def __init__(
        self,
        *,
        db: DatabaseHandle,
        crypto: FernetStore,
        local_providers: Iterable[str] = (),
    ) -> None:
        self._db = db
        self._crypto = crypto
        self._local_providers = frozenset(local_providers)

    async def resolve(self, *, user_id: str, model: str) -> str | None:
        """Return the decrypted API key for the provider owning ``model``.

        Returns None if the provider needs no key (local inference).
        Raises NoCredentialError if the provider requires a key but the user
        has none stored.
        """
        try:
            _model, provider, _key, _base = litellm.get_llm_provider(model)
        except BadRequestError:
            _log.debug("cannot resolve provider for model %s — falling back to env", model)
            return None

        if provider in self._local_providers:
            return None

        slot = f"user:key:{provider}"
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(UserConfig).where(
                        UserConfig.user_id == user_id,
                        UserConfig.slot == slot,
                    )
                )
            ).scalar_one_or_none()

        if row is None:
            raise NoCredentialError(provider_name=provider, user_id=user_id)

        return self._crypto.decrypt(row.ciphertext).decode("utf-8")
