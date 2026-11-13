"""Reglages : l'environnement d'abord, sinon un fichier /secrets/app/<NOM>."""
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SECRETS_DIR = "/secrets/app"


class MissingSetting(RuntimeError):
    pass


def _read(name, secrets_dir):
    value = os.environ.get(name)
    if value is not None and value.strip():
        return value.strip()
    path = Path(secrets_dir) / name
    if path.is_file():
        return path.read_text().strip() or None
    return None


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    owner_telegram_id: int
    site_password_hash: str
    session_secret: str
    library_repo_url: str
    library_git_token: str
    public_base_url: str
    claude_token: str | None
    anthropic_api_key: str | None
    claude_model: str
    claude_bin: str
    library_dir: Path


def load(secrets_dir=None):
    secrets_dir = secrets_dir or os.environ.get("SECRETS_DIR", DEFAULT_SECRETS_DIR)

    def required(name):
        value = _read(name, secrets_dir)
        if value is None:
            raise MissingSetting(f"Reglage obligatoire absent : {name}")
        return value

    token = _read("CLAUDE_CODE_OAUTH_TOKEN", secrets_dir)
    api_key = _read("ANTHROPIC_API_KEY", secrets_dir)
    if not token and not api_key:
        raise MissingSetting("Reglage obligatoire absent : CLAUDE_CODE_OAUTH_TOKEN (ou ANTHROPIC_API_KEY)")

    return Settings(
        telegram_bot_token=required("TELEGRAM_BOT_TOKEN"),
        owner_telegram_id=int(required("OWNER_TELEGRAM_ID")),
        site_password_hash=required("SITE_PASSWORD_HASH"),
        session_secret=required("SESSION_SECRET"),
        library_repo_url=required("LIBRARY_REPO_URL"),
        library_git_token=required("LIBRARY_GIT_TOKEN"),
        public_base_url=required("PUBLIC_BASE_URL").rstrip("/"),
        claude_token=token,
        anthropic_api_key=api_key,
        claude_model=_read("CLAUDE_MODEL", secrets_dir) or "sonnet",
        claude_bin=_read("CLAUDE_BIN", secrets_dir) or "claude",
        library_dir=Path(_read("LIBRARY_DIR", secrets_dir) or "/data/library"),
    )
