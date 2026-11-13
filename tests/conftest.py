import subprocess

import pytest

from ideadesk.store import Store


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(path)], check=True, capture_output=True)
    return path


@pytest.fixture
def store(tmp_path, remote):
    s = Store(tmp_path / "library", str(remote), "SECRETTOKEN123")
    s.ensure_clone()
    return s
