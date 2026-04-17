from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

import yaml


@dataclass(frozen=True)
class ModelEntry:
    """A single model available from a provider."""

    id: str
    display_name: str


@dataclass(frozen=True)
class ProviderEntry:
    """A provider with its models and credential mapping."""

    name: str
    display_name: str
    env_var: str
    credential_slot: str
    models: list[ModelEntry] = field(default_factory=list)


class ProviderCatalog:
    """Loads providers.yaml and provides model/provider lookups."""

    def __init__(self, providers: list[ProviderEntry]) -> None:
        self._providers = providers
        self._model_to_provider: dict[str, ProviderEntry] = {}
        for p in providers:
            for m in p.models:
                self._model_to_provider[m.id] = p

    @property
    def providers(self) -> list[ProviderEntry]:
        return list(self._providers)

    @classmethod
    def from_yaml(cls, content: str) -> Self:
        data: dict[str, list[dict[str, str | list[dict[str, str]]]]] = yaml.safe_load(
            content
        )
        providers: list[ProviderEntry] = []
        if not isinstance(data, dict):
            return cls(providers)
        for p in data.get("providers", []):
            if not isinstance(p, dict):
                continue
            models_raw = p.get("models", [])
            models: list[ModelEntry] = []
            if isinstance(models_raw, list):
                for m in models_raw:
                    if isinstance(m, dict) and "id" in m and "display_name" in m:
                        models.append(
                            ModelEntry(
                                id=str(m["id"]),
                                display_name=str(m["display_name"]),
                            )
                        )
            providers.append(
                ProviderEntry(
                    name=str(p["name"]),
                    display_name=str(p["display_name"]),
                    env_var=str(p.get("env_var", "")),
                    credential_slot=str(p.get("credential_slot", "")),
                    models=models,
                )
            )
        return cls(providers)

    @classmethod
    def from_file(cls, path: Path) -> Self:
        return cls.from_yaml(path.read_text(encoding="utf-8"))

    def list_models(self) -> list[ModelEntry]:
        """Return all models across all providers."""
        result: list[ModelEntry] = []
        for p in self._providers:
            result.extend(p.models)
        return result

    def get_provider(self, name: str) -> ProviderEntry | None:
        """Look up a provider by name."""
        for p in self._providers:
            if p.name == name:
                return p
        return None

    def resolve_provider_for_model(self, model_id: str) -> ProviderEntry | None:
        """Return the provider that owns this model, or None."""
        return self._model_to_provider.get(model_id)
