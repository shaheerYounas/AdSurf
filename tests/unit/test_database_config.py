import pytest

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import assert_database_configured_for_environment
from apps.api.app.core.errors import ApiError


def test_missing_database_url_allowed_in_local(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert_database_configured_for_environment()

    get_settings.cache_clear()


def test_missing_database_url_fails_outside_local_and_test(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ApiError) as exc_info:
        assert_database_configured_for_environment()

    assert exc_info.value.code == "DATABASE_NOT_CONFIGURED"

    get_settings.cache_clear()
