from __future__ import annotations

from pathlib import Path

from mcp_memory.shared.config import Settings, get_settings


def test_settings_default_db_path_is_not_expanded():
    """AC21: el modelo pydantic no expande "~" — la expansión es responsabilidad
    exclusiva de get_settings(), para que los tests puedan construir
    Settings(db_path=...) directo sin efectos de os.path."""
    settings = Settings()
    assert settings.db_path == "~/.agent-memory/memory.db"


def test_get_settings_expands_default_db_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DB_PATH", raising=False)

    settings = get_settings()

    assert settings.db_path == str(Path.home() / ".agent-memory" / "memory.db")


def test_get_settings_preserves_memory_sentinel(tmp_path, monkeypatch):
    """AC22: ":memory:" no se expande — pasa intacto a aiosqlite.connect."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DB_PATH", ":memory:")

    settings = get_settings()

    assert settings.db_path == ":memory:"


def test_get_settings_expands_custom_path(tmp_path, monkeypatch):
    """AC23: una ruta custom con "~" se expande a la home real del usuario."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DB_PATH", "~/custom/path.db")

    settings = get_settings()

    assert settings.db_path == str(Path.home() / "custom" / "path.db")


def test_get_settings_reads_absolute_db_path_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    absolute = str(tmp_path / "abs" / "memory.db")
    monkeypatch.setenv("DB_PATH", absolute)

    settings = get_settings()

    assert settings.db_path == absolute
