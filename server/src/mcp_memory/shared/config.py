import os
import socket

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    ollama_url: str = "http://host.docker.internal:11434"
    ollama_api_key: str | None = None

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "mcp_memory"

    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765

    default_namespace: str = "default"


def _is_in_container() -> bool:
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")


def get_settings() -> Settings:
    settings = Settings()
    if not _is_in_container() and not os.environ.get("QDRANT_URL"):
        try:
            socket.gethostbyname("qdrant")
        except socket.gaierror:
            settings.qdrant_url = "http://localhost:6333"

    if not _is_in_container() and not os.environ.get("OLLAMA_URL"):
        try:
            socket.gethostbyname("host.docker.internal")
        except socket.gaierror:
            settings.ollama_url = "http://localhost:11434"

    return settings

