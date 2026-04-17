from __future__ import annotations

from sqlalchemy import select

from agentlabx.db.schema import UserConfig
from agentlabx.db.session import DatabaseHandle
from agentlabx.llm.catalog import ProviderCatalog
from agentlabx.security.fernet_store import FernetStore


class NoCredentialError(Exception):
    """Raised when a user has no stored credential for the required provider."""

    def __init__(self, provider_name: str, user_id: str) -> None:
        self.provider_name = provider_name
        self.user_id = user_id
        super().__init__(
            f"no credential stored for provider '{provider_name}' (user {user_id})"
        )


class KeyResolver:
    """Resolves a per-user API key from the encrypted credential store."""

    def __init__(
        self,
        *,
        db: DatabaseHandle,
        crypto: FernetStore,
        catalog: ProviderCatalog,
    ) -> None:
        self._db = db
        self._crypto = crypto
        self._catalog = catalog

    async def resolve(self, *, user_id: str, model: str) -> str | None:
        """Return the decrypted API key for the provider owning `model`.

        Returns None if the provider requires no credential (empty credential_slot).
        Raises NoCredentialError if the provider requires a credential but the user
        has none stored.
        """
        provider = self._catalog.resolve_provider_for_model(model)
        if provider is None:
            # Unknown model — let LiteLLM try with env vars / no key
            return None

        if not provider.credential_slot:
            # Provider needs no key (e.g. local inference server)
            return None

        slot = f"user:key:{provider.credential_slot}"
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
            raise NoCredentialError(provider_name=provider.name, user_id=user_id)

        return self._crypto.decrypt(row.ciphertext).decode("utf-8")
