import logging
import subprocess

import pytest

from ideadesk import store as store_mod
from ideadesk.fiche import Fiche
from ideadesk.store import Store

TOKEN = "SECRETTOKEN123"


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def remote_log(remote):
    out = subprocess.run(["git", "log", "--oneline"], cwd=remote, capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l]


def test_created_fiche_is_written_committed_and_pushed(store, remote):
    fiche = store.create("Mon idée", thread_id=9)
    assert store.get(fiche.id) == fiche
    assert len(remote_log(remote)) == 1


def test_save_updates_existing_fiche(store):
    fiche = store.create("a")
    fiche.status = "prete"
    store.save(fiche)
    assert store.get(fiche.id).status == "prete"


def test_failed_push_keeps_local_write_and_retries_on_next_write(store, remote, tmp_path, caplog):
    moved = tmp_path / "moved.git"
    remote.rename(moved)
    with caplog.at_level(logging.WARNING):
        first = store.create("hors ligne")
    assert store.get(first.id).raw_idea == "hors ligne"
    assert "push" in caplog.text.lower()
    moved.rename(remote)
    store.create("de retour")
    assert len(remote_log(remote)) == 2


def test_push_error_text_is_logged_without_the_token(store, monkeypatch, caplog):
    real = subprocess.run

    def fake(args, *a, **kw):
        if "push" in args:
            return subprocess.CompletedProcess(args, 1, "", f"fatal: auth failed {TOKEN}")
        return real(args, *a, **kw)

    monkeypatch.setattr(store_mod.subprocess, "run", fake)
    with caplog.at_level(logging.WARNING):
        store.create("x")
    assert "auth failed" in caplog.text
    assert TOKEN not in caplog.text


def test_themes_come_from_fiches_without_case_duplicates(store):
    a = store.create("a")
    a.themes = ["SaaS", "immobilier"]
    store.save(a)
    b = store.create("b")
    b.themes = ["saas"]
    store.save(b)
    assert sorted(t.lower() for t in store.themes()) == ["immobilier", "saas"]


def test_find_by_thread_returns_the_matching_fiche_or_none(store):
    a = store.create("a", thread_id=11)
    store.create("b", thread_id=12)
    assert store.find_by_thread(11).id == a.id
    assert store.find_by_thread(99) is None
