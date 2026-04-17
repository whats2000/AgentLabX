from __future__ import annotations

from pathlib import Path

from agentlabx.llm.catalog import ModelEntry, ProviderCatalog, ProviderEntry


def test_load_from_yaml_string() -> None:
    yaml_content = """\
providers:
  - name: provider-a
    display_name: Provider A
    env_var: PROVIDER_A_KEY
    credential_slot: provider-a
    models:
      - id: provider-a/model-1
        display_name: Model 1
      - id: provider-a/model-2
        display_name: Model 2
  - name: provider-b
    display_name: Provider B
    env_var: PROVIDER_B_KEY
    credential_slot: provider-b
    models:
      - id: provider-b/model-1
        display_name: Model 1
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    assert len(catalog.providers) == 2
    assert catalog.providers[0].name == "provider-a"
    assert len(catalog.providers[0].models) == 2
    assert catalog.providers[1].name == "provider-b"


def test_list_all_models() -> None:
    yaml_content = """\
providers:
  - name: provider-a
    display_name: Provider A
    env_var: PROVIDER_A_KEY
    credential_slot: provider-a
    models:
      - id: provider-a/model-1
        display_name: Model 1
  - name: provider-b
    display_name: Provider B
    env_var: PROVIDER_B_KEY
    credential_slot: provider-b
    models:
      - id: provider-b/model-1
        display_name: Model 1
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    models = catalog.list_models()
    assert len(models) == 2
    ids = [m.id for m in models]
    assert "provider-a/model-1" in ids
    assert "provider-b/model-1" in ids


def test_get_provider_by_name() -> None:
    yaml_content = """\
providers:
  - name: provider-a
    display_name: Provider A
    env_var: PROVIDER_A_KEY
    credential_slot: provider-a
    models:
      - id: provider-a/model-1
        display_name: Model 1
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    provider = catalog.get_provider("provider-a")
    assert provider is not None
    assert provider.display_name == "Provider A"


def test_get_provider_missing_returns_none() -> None:
    yaml_content = """\
providers: []
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    assert catalog.get_provider("nonexistent") is None


def test_resolve_provider_for_model() -> None:
    yaml_content = """\
providers:
  - name: provider-a
    display_name: Provider A
    env_var: PROVIDER_A_KEY
    credential_slot: provider-a
    models:
      - id: provider-a/model-1
        display_name: Model 1
  - name: provider-b
    display_name: Provider B
    env_var: PROVIDER_B_KEY
    credential_slot: provider-b
    models:
      - id: provider-b/model-1
        display_name: Model 1
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    provider = catalog.resolve_provider_for_model("provider-a/model-1")
    assert provider is not None
    assert provider.name == "provider-a"
    provider2 = catalog.resolve_provider_for_model("provider-b/model-1")
    assert provider2 is not None
    assert provider2.name == "provider-b"


def test_resolve_provider_for_unknown_model_returns_none() -> None:
    yaml_content = """\
providers:
  - name: provider-a
    display_name: Provider A
    env_var: PROVIDER_A_KEY
    credential_slot: provider-a
    models:
      - id: provider-a/model-1
        display_name: Model 1
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    assert catalog.resolve_provider_for_model("nonexistent-model") is None


def test_load_from_file(tmp_path: Path) -> None:
    yaml_file = tmp_path / "providers.yaml"
    yaml_file.write_text("""\
providers:
  - name: local-provider
    display_name: Local Provider
    env_var: ""
    credential_slot: ""
    models:
      - id: local-provider/model-1
        display_name: Local Model 1
""")
    catalog = ProviderCatalog.from_file(yaml_file)
    assert len(catalog.providers) == 1
    assert catalog.providers[0].name == "local-provider"


def test_provider_entry_fields() -> None:
    entry = ProviderEntry(
        name="test",
        display_name="Test Provider",
        env_var="TEST_API_KEY",
        credential_slot="test",
        models=[ModelEntry(id="test/model-1", display_name="Test Model")],
    )
    assert entry.name == "test"
    assert entry.env_var == "TEST_API_KEY"
    assert entry.credential_slot == "test"


def test_malformed_yaml_missing_providers_key() -> None:
    """YAML with no 'providers' key yields an empty catalog."""
    catalog = ProviderCatalog.from_yaml("something_else: true\n")
    assert len(catalog.providers) == 0


def test_malformed_yaml_missing_model_fields() -> None:
    """Provider entry with missing model fields is skipped gracefully."""
    yaml_content = """\
providers:
  - name: broken
    display_name: Broken Provider
    env_var: X
    credential_slot: x
    models:
      - not_a_valid_model: true
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    assert len(catalog.providers) == 1
    # The malformed model entry should be skipped (no 'id' key)
    assert len(catalog.providers[0].models) == 0
