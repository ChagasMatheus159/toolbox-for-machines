"""Toolbox configuration from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration via environment variables."""

    # API
    toolbox_port: int = 9600

    # Backend URLs
    searxng_url: str = "http://searxng:8080"
    camoufox_url: str = "http://camoufox:8790"
    whisper_url: str = "http://whisper:8200"

    # LLM
    llm_url: str = "http://192.168.3.118:8080/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen3-vl-8b"
    llm_max_concurrent: int = 1
    llm_timeout_seconds: int = 60
    llm_max_tokens: int = 512

    # Fetch
    fetch_timeout_seconds: int = 30

    # Cache
    cache_enabled: bool = True
    cache_db_path: str = "/data/cache.db"

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
