"""Application configuration via pydantic-settings (12-factor: everything from env)."""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/

LLMProvider = Literal["gemini", "claude", "ollama"]

DEV_SECRET_KEY = "dev-secret-key-change-me-in-production"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    # Always read backend/.env, whatever folder uvicorn is started from.
    # Real environment variables override values in the file.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # "production" turns on the safety checks below (e.g. a real SECRET_KEY).
    ENVIRONMENT: Literal["development", "production"] = "development"

    # Security — REQUIRED in real deployments, dev defaults provided.
    SECRET_KEY: str = DEV_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24h

    # --- LLM: which provider writes the answers -------------------------------
    # Only this setting picks the provider; having an API key set does not.
    LLM_PROVIDER: LLMProvider = "gemini"
    LLM_MAX_TOKENS: int = 16000  # upper limit on answer length (incl. Claude's thinking)
    LLM_TIMEOUT_SECONDS: int = 300

    # Google Gemini
    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Anthropic Claude
    ANTHROPIC_API_KEY: SecretStr = SecretStr("")
    CLAUDE_MODEL: str = "claude-opus-5-5"
    CLAUDE_EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # Ollama (local, free, offline)
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4"
    OLLAMA_NUM_CTX: int = 4096

    # --- Search: how many chunks are looked at for each question ---------------
    RETRIEVAL_CANDIDATES: int = 40  # fetched by meaning, then rescored and reranked
    RETRIEVAL_TOP_K: int = 5  # best chunks the LLM reads (each up to ~512 tokens)

    @model_validator(mode="after")
    def _check_secret_key(self) -> "Settings":
        """In production, refuse to start with the dev key or a short key:
        anyone who knows it could create valid login tokens."""
        if self.ENVIRONMENT == "production":
            key = self.SECRET_KEY.strip()
            if key == DEV_SECRET_KEY or len(key) < MIN_SECRET_KEY_LENGTH:
                raise ValueError(
                    "ENVIRONMENT=production needs a real SECRET_KEY of at least "
                    f"{MIN_SECRET_KEY_LENGTH} characters in backend/.env. Make one with: "
                    "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )
        return self

    @model_validator(mode="after")
    def _check_llm_settings(self) -> "Settings":
        """Fail at startup with a clear message instead of on the first question."""
        required = {
            "gemini": ("GEMINI_API_KEY", self.GEMINI_API_KEY),
            "claude": ("ANTHROPIC_API_KEY", self.ANTHROPIC_API_KEY),
        }
        if self.LLM_PROVIDER in required:
            name, value = required[self.LLM_PROVIDER]
            if not value.get_secret_value().strip():
                raise ValueError(
                    f"LLM_PROVIDER={self.LLM_PROVIDER} needs {name} in backend/.env "
                    f"(or switch LLM_PROVIDER to another provider)."
                )
        return self

    @property
    def llm_model(self) -> str:
        """Model name of the active provider (for logs and /health)."""
        return {
            "gemini": self.GEMINI_MODEL,
            "claude": self.CLAUDE_MODEL,
            "ollama": self.OLLAMA_MODEL,
        }[self.LLM_PROVIDER]

    # Storage
    DATA_DIR: Path = BASE_DIR / "data"
    MAX_UPLOAD_MB: int = 50

    # CORS — local dev tool; override in production.
    CORS_ORIGINS: list[str] = ["*"]

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.DATA_DIR / 'rag.db'}"

    @property
    def files_dir(self) -> Path:
        return self.DATA_DIR / "files"

    @property
    def pdf_dir(self) -> Path:
        return self.files_dir

    @property
    def chroma_dir(self) -> Path:
        return self.DATA_DIR / "chroma"


settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.files_dir.mkdir(parents=True, exist_ok=True)
settings.chroma_dir.mkdir(parents=True, exist_ok=True)
