from __future__ import annotations

import pytest
from pydantic import SecretStr

from app import search_client


def test_search_configuration_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_client.settings, "azure_search_endpoint", None)
    monkeypatch.setattr(search_client.settings, "azure_search_query_key", None)
    assert search_client.search_is_configured() is False

    monkeypatch.setattr(search_client.settings, "azure_search_endpoint", "https://search.example")
    monkeypatch.setattr(search_client.settings, "azure_search_query_key", SecretStr("test-key"))
    assert search_client.search_is_configured() is True


def test_get_search_client_rejects_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    search_client.get_search_client.cache_clear()
    monkeypatch.setattr(search_client.settings, "azure_search_endpoint", None)
    monkeypatch.setattr(search_client.settings, "azure_search_query_key", None)

    with pytest.raises(RuntimeError, match="not configured"):
        search_client.get_search_client()

    search_client.get_search_client.cache_clear()


def test_legacy_admin_key_does_not_configure_runtime(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("AZURE_SEARCH_QUERY_KEY", raising=False)
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "legacy-admin")
    assert Settings().azure_search_query_key is None
