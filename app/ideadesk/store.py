"""Les fiches sur disque, copiees dans un depot Git prive (seul ecrivain : l'application)."""
import logging
import os
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .fiche import Fiche, parse, render

log = logging.getLogger("ideadesk.store")


class GitError(RuntimeError):
    pass


def themes_of(fiches):
    """Themes distincts (sans doublon de casse) d'une liste de fiches deja chargee."""
    seen = {}
    for f in fiches:
        for t in f.themes:
            seen.setdefault(t.lower(), t)
    return sorted(seen.values(), key=str.lower)


class Store:
    def __init__(self, directory, repo_url, token):
        self.dir = Path(directory)
        self.repo_url = repo_url
        self.token = token
        # Le jeton passe a git par GIT_ASKPASS, jamais dans l'URL du depot.
        askpass_dir = Path(tempfile.mkdtemp(prefix="askpass-"))
        self._askpass = askpass_dir / "askpass.sh"
        self._askpass.write_text('#!/bin/sh\ncase "$1" in Username*) echo x-access-token;; *) echo "$GIT_TOKEN";; esac\n')
        self._askpass.chmod(stat.S_IRWXU)

    def _redact(self, text):
        return (text or "").replace(self.token, "***") if self.token else (text or "")

    def _git(self, *args, cwd=None):
        env = {**os.environ, "GIT_ASKPASS": str(self._askpass), "GIT_TOKEN": self.token, "GIT_TERMINAL_PROMPT": "0"}
        done = subprocess.run(["git", *args], cwd=cwd or self.dir, env=env, capture_output=True, text=True)
        if done.returncode != 0:
            raise GitError(self._redact((done.stderr or done.stdout).strip()))
        return done.stdout

    def ensure_clone(self):
        if (self.dir / ".git").exists():
            return
        self.dir.parent.mkdir(parents=True, exist_ok=True)
        self._git("clone", self.repo_url, str(self.dir), cwd=self.dir.parent)
        self._git("config", "user.name", "idea-desk")
        self._git("config", "user.email", "idea-desk@localhost")
        (self.dir / "fiches").mkdir(exist_ok=True)

    def _path(self, fiche_id):
        return self.dir / "fiches" / f"{fiche_id}.md"

    def get(self, fiche_id):
        path = self._path(fiche_id)
        return parse(path.read_text()) if path.is_file() else None

    def list(self):
        fiches = [parse(p.read_text()) for p in (self.dir / "fiches").glob("*.md")]
        return sorted(fiches, key=lambda f: f.updated, reverse=True)

    def find_by_thread(self, thread_id):
        for path in (self.dir / "fiches").glob("*.md"):
            fiche = parse(path.read_text())
            if fiche.thread_id == thread_id:
                return fiche
        return None

    def themes(self):
        return themes_of(self.list())

    def create(self, raw_idea, thread_id=None):
        fiche = Fiche.new(raw_idea, thread_id)
        self.save(fiche)
        return fiche

    def save(self, fiche):
        fiche.updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:  # shortcut: un seul ecrivain, un echec de tirage (depot vide) ne bloque pas ; a revoir avec un second ecrivain.
            self._git("pull", "--rebase", "--autostash")
        except GitError as err:
            log.debug("git pull ignore : %s", err)
        path = self._path(fiche.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(render(fiche))
        os.replace(tmp, path)
        rel = str(path.relative_to(self.dir))
        self._git("add", rel)
        self._git("commit", "-m", f"fiche: {fiche.title[:60]}", "--", rel)
        try:
            self._git("push", "origin", "HEAD")
        except GitError as err:
            log.warning("git push a echoue, retente a la prochaine ecriture : %s", err)
