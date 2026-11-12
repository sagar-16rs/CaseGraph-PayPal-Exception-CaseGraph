"""Environment loading behaves the way the setup instructions promise.

Regression: `.env` was never read. A developer could copy `.env.example`, fill it in
correctly, start the app and get a process with no PayPal credentials — with no
indication that the file had been ignored.
"""

from __future__ import annotations

import os

from backend import config


def test_dotenv_values_reach_the_process_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("CASEGRAPH_DOTENV_MARKER", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("CASEGRAPH_DOTENV_MARKER=from_file\n", encoding="utf-8")

    config.load_environment(env_file)

    assert os.environ.get("CASEGRAPH_DOTENV_MARKER") == "from_file"


def test_real_environment_wins_over_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CASEGRAPH_DOTENV_MARKER", "from_shell")
    env_file = tmp_path / ".env"
    env_file.write_text("CASEGRAPH_DOTENV_MARKER=from_file\n", encoding="utf-8")

    config.load_environment(env_file)

    assert os.environ["CASEGRAPH_DOTENV_MARKER"] == "from_shell"


def test_missing_env_file_is_not_an_error(tmp_path):
    # Running without a .env (CI, containers, production) must stay supported.
    config.load_environment(tmp_path / "does-not-exist.env")


def test_repository_env_file_is_the_default_target():
    assert config._ENV_FILE.name == ".env"
    assert config._ENV_FILE.parent.name == "casegraph"
