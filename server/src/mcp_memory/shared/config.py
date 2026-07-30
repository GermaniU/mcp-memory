import os
import socket

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    @field_validator("embedding_dim")
    @classmethod
    def _validate_embedding_dim(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"EMBEDDING_DIM debe ser un entero positivo, recibido: {v}")
        return v

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
    # Only fall back to localhost when the value is still the Docker-only default —
    # os.environ misses values set via .env (pydantic-settings reads .env directly
    # into the model without touching the process environment), which silently
    # clobbered user-configured remote QDRANT_URL/OLLAMA_URL.
    qdrant_default = Settings.model_fields["qdrant_url"].default
    if not _is_in_container() and settings.qdrant_url == qdrant_default:
        try:
            socket.gethostbyname("qdrant")
        except socket.gaierror:
            settings.qdrant_url = "http://localhost:6333"

    ollama_default = Settings.model_fields["ollama_url"].default
    if not _is_in_container() and settings.ollama_url == ollama_default:
        try:
            socket.gethostbyname("host.docker.internal")
        except socket.gaierror:
            settings.ollama_url = "http://localhost:11434"

    return settings

