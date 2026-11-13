import pytest

from ideadesk import config

REQUIRED = {
    "TELEGRAM_BOT_TOKEN": "tok",
    "OWNER_TELEGRAM_ID": "42",
    "SITE_PASSWORD_HASH": "hash",
    "SESSION_SECRET": "sess",
    "LIBRARY_REPO_URL": "https://example.invalid/x.git",
    "LIBRARY_GIT_TOKEN": "gt",
    "PUBLIC_BASE_URL": "https://ideas.example/",
    "CLAUDE_CODE_OAUTH_TOKEN": "cc",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in list(REQUIRED) + ["ANTHROPIC_API_KEY", "CLAUDE_MODEL"]:
        monkeypatch.delenv(name, raising=False)


def set_env(monkeypatch, skip=()):
    for k, v in REQUIRED.items():
        if k not in skip:
            monkeypatch.setenv(k, v)


def test_env_wins_over_secret_file(monkeypatch, tmp_path):
    set_env(monkeypatch)
    (tmp_path / "TELEGRAM_BOT_TOKEN").write_text("from-file")
    assert config.load(secrets_dir=tmp_path).telegram_bot_token == "tok"


def test_reads_setting_only_present_in_secret_file_and_strips(monkeypatch, tmp_path):
    set_env(monkeypatch, skip=("TELEGRAM_BOT_TOKEN",))
    (tmp_path / "TELEGRAM_BOT_TOKEN").write_text("from-file\n")
    assert config.load(secrets_dir=tmp_path).telegram_bot_token == "from-file"


def test_missing_required_names_it_and_leaks_no_value(monkeypatch, tmp_path):
    set_env(monkeypatch, skip=("SESSION_SECRET",))
    with pytest.raises(config.MissingSetting) as err:
        config.load(secrets_dir=tmp_path)
    message = str(err.value)
    assert "SESSION_SECRET" in message
    assert all(v not in message for k, v in REQUIRED.items() if k != "SESSION_SECRET")


def test_needs_a_claude_credential(monkeypatch, tmp_path):
    set_env(monkeypatch, skip=("CLAUDE_CODE_OAUTH_TOKEN",))
    with pytest.raises(config.MissingSetting) as err:
        config.load(secrets_dir=tmp_path)
    assert "CLAUDE_CODE_OAUTH_TOKEN" in str(err.value)
