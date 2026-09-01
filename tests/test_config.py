import pytest

from trace_agent.config import Settings


def test_model_must_be_explicitly_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    with pytest.raises(ValueError, match="OPENAI_MODEL is not set"):
        Settings.from_env(tmp_path)


def test_api_runtime_settings_are_loaded(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_TIMEOUT", "45")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "1")

    settings = Settings.from_env(tmp_path)

    assert settings.model == "test-model"
    assert settings.api_timeout == 45
    assert settings.api_max_retries == 1
