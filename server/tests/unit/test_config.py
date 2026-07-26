from __future__ import annotations

import socket

from mcp_memory.shared.config import Settings, get_settings


def test_get_settings_preserves_dotenv_qdrant_url(tmp_path, monkeypatch):
    """A QDRANT_URL set only via .env (not exported to the process env) must survive
    the local auto-fallback — regression test for the silent-clobber bug where
    get_settings() checked os.environ instead of the resolved Settings value."""
    (tmp_path / ".env").write_text("QDRANT_URL=http://my-remote-qdrant:6333\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.setattr("mcp_memory.shared.config._is_in_container", lambda: False)

    settings = get_settings()

    assert settings.qdrant_url == "http://my-remote-qdrant:6333"


def test_get_settings_preserves_dotenv_ollama_url(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OLLAMA_URL=https://ollama.example.com\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.setattr("mcp_memory.shared.config._is_in_container", lambda: False)

    settings = get_settings()

    assert settings.ollama_url == "https://ollama.example.com"


def test_get_settings_falls_back_when_unset(tmp_path, monkeypatch):
    """With no .env and no env vars, the Docker-only default hostname is unresolvable
    on a native host, so get_settings() should still fall back to localhost."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.setattr("mcp_memory.shared.config._is_in_container", lambda: False)

    def _unresolvable(_host: str) -> str:
        raise socket.gaierror("mock: name not resolvable")

    monkeypatch.setattr("socket.gethostbyname", _unresolvable)

    settings = get_settings()

    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.ollama_url == "http://localhost:11434"


def test_get_settings_leaves_defaults_inside_container(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.setattr("mcp_memory.shared.config._is_in_container", lambda: True)

    settings = get_settings()

    assert settings.qdrant_url == Settings.model_fields["qdrant_url"].default
    assert settings.ollama_url == Settings.model_fields["ollama_url"].default
