import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "~/.agent-memory/memory.db"

    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765

    default_namespace: str = "default"


def get_settings() -> Settings:
    settings = Settings()
    if settings.db_path != ":memory:":
        settings.db_path = os.path.expanduser(settings.db_path)
    return settings
