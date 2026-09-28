import pytest

from app.core.config import Settings, settings
from app.modules.similarity.providers import LocalEmbeddingProvider


def test_zero_external_ai_cannot_be_disabled():
    with pytest.raises(ValueError, match="must remain true"):
        Settings(ZERO_EXTERNAL_AI_API=False, _env_file=None)


@pytest.mark.parametrize(
    "name",
    [
        "OPENAI_API_KEY",
        "ANTHROPIC_BASE_URL",
        "GEMINI_API_KEY",
        "HF_INFERENCE_ENDPOINT",
        "DETECTOR_API_URL",
        "EMBEDDING_API_URL",
    ],
)
def test_legacy_external_ai_environment_rejected_without_secret_disclosure(
    monkeypatch, name
):
    secret = "sensitive-value-must-not-appear"
    monkeypatch.setenv(name, secret)
    with pytest.raises(ValueError, match="External AI configuration") as error:
        Settings(_env_file=None)
    assert secret not in str(error.value)


def test_external_ai_dotenv_is_not_silently_ignored(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_BASE_URL=https://external.invalid\n")
    with pytest.raises(ValueError, match="External AI configuration"):
        Settings(_env_file=env_file)


def test_unapproved_local_embedding_cannot_run_in_production(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    provider = LocalEmbeddingProvider("model_assets/all-MiniLM-L6-v2")
    assert not provider.available
    assert provider.state()["state"] == "UNAVAILABLE"
