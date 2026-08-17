"""Application configuration via pydantic-settings (12-factor: everything from env)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Security — REQUIRED in real deployments, dev defaults provided.
    SECRET_KEY: str = "dev-secret-key-change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24h

    # Ollama
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4"

    # Storage
    DATA_DIR: Path = BASE_DIR / "data"
    MAX_UPLOAD_MB: int = 50

    # CORS — local dev tool; override in production.
    CORS_ORIGINS: list[str] = ["*"]

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.DATA_DIR / 'rag.db'}"

    @property
    def pdf_dir(self) -> Path:
        return self.DATA_DIR / "pdfs"

    @property
    def chroma_dir(self) -> Path:
        return self.DATA_DIR / "chroma"


settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.pdf_dir.mkdir(parents=True, exist_ok=True)
settings.chroma_dir.mkdir(parents=True, exist_ok=True)
