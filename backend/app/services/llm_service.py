"""LLM providers behind one interface.

Pick the provider with LLM_PROVIDER in backend/.env ("gemini", "claude" or
"ollama"). Every provider exposes the same two calls, so the rest of the app
never needs to know which one is active:

    generate_answer(prompt)        -> full answer as one string
    generate_answer_stream(prompt) -> answer piece by piece (for live chat)
"""

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from functools import lru_cache

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMUnavailableError(Exception):
    """Raised when the LLM provider cannot be reached or fails."""


OllamaUnavailableError = LLMUnavailableError  # backward-compatible name


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def stream(self, prompt: str) -> Iterator[str]:
        """Yield the answer text piece by piece."""

    def generate(self, prompt: str) -> str:
        return "".join(self.stream(prompt)).strip()


# --- Google Gemini ------------------------------------------------------------


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self) -> None:
        from google import genai
        from google.genai import types

        self.model = settings.GEMINI_MODEL
        self._client = genai.Client(
            api_key=settings.GEMINI_API_KEY.get_secret_value(),
            http_options=types.HttpOptions(timeout=settings.LLM_TIMEOUT_SECONDS * 1000),
        )
        self._config = types.GenerateContentConfig(max_output_tokens=settings.LLM_MAX_TOKENS)

    def stream(self, prompt: str) -> Iterator[str]:
        from google.genai import errors

        try:
            for chunk in self._client.models.generate_content_stream(
                model=self.model, contents=prompt, config=self._config
            ):
                if chunk.text:
                    yield chunk.text
        except errors.APIError as e:
            if e.code == 429:
                raise LLMUnavailableError(
                    "Gemini usage limit reached (free tier allows only a few requests per "
                    "day). Try again later, enable billing in Google AI Studio, or switch "
                    "LLM_PROVIDER in backend/.env."
                ) from e
            if e.code in (401, 403):
                raise LLMUnavailableError("GEMINI_API_KEY in backend/.env is not valid.") from e
            raise LLMUnavailableError(f"Gemini error ({e.code}): {e.message}") from e
        except Exception as e:
            raise LLMUnavailableError(f"Could not reach Gemini: {e}") from e


# --- Anthropic Claude ---------------------------------------------------------

# Models that support server-side refusal fallbacks (Haiku does not).
_FALLBACK_MODEL_PREFIXES = ("claude-fable-5", "claude-opus-5", "claude-sonnet-5-5")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self) -> None:
        import anthropic

        self.model = settings.CLAUDE_MODEL
        self._client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY.get_secret_value(),
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=2,
        )

    def _params(self, prompt: str) -> dict:
        params = {
            "model": self.model,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": settings.CLAUDE_EFFORT},
        }
        if self.model.startswith(_FALLBACK_MODEL_PREFIXES):
            # If a safety check declines the request, the API retries it on
            # Anthropic's recommended fallback model inside the same call.
            params["betas"] = [_FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def stream(self, prompt: str) -> Iterator[str]:
        import anthropic

        try:
            with self._client.beta.messages.stream(**self._params(prompt)) as s:
                yield from s.text_stream
                final = s.get_final_message()
        except anthropic.AuthenticationError as e:
            raise LLMUnavailableError("ANTHROPIC_API_KEY in backend/.env is not valid.") from e
        except anthropic.PermissionDeniedError as e:
            raise LLMUnavailableError(f"Claude API access denied: {e.message}") from e
        except anthropic.NotFoundError as e:
            raise LLMUnavailableError(
                f"Claude model '{self.model}' not found. Check CLAUDE_MODEL in backend/.env."
            ) from e
        except anthropic.RateLimitError as e:
            raise LLMUnavailableError(
                "Claude rate limit or credit limit reached. Check your balance at "
                "platform.claude.com, or try again shortly."
            ) from e
        except anthropic.BadRequestError as e:
            raise LLMUnavailableError(f"Claude rejected the request: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise LLMUnavailableError(f"Claude error ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMUnavailableError("Could not reach the Claude API (network error).") from e

        if final.stop_reason == "refusal":
            raise LLMUnavailableError("Claude declined to answer this question.")
        if final.stop_reason == "max_tokens":
            logger.warning(
                "Claude answer was cut off at LLM_MAX_TOKENS=%s", settings.LLM_MAX_TOKENS
            )


# --- Ollama (local) -----------------------------------------------------------


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        self.model = settings.OLLAMA_MODEL

    def stream(self, prompt: str) -> Iterator[str]:
        try:
            resp = requests.post(
                f"{settings.OLLAMA_URL}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "num_ctx": settings.OLLAMA_NUM_CTX,
                        "num_predict": settings.LLM_MAX_TOKENS,
                    },
                },
                stream=True,
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise LLMUnavailableError(
                f"Could not reach Ollama at {settings.OLLAMA_URL}. Start it with "
                f"`ollama serve` and run `ollama pull {self.model}`."
            ) from e
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                raise LLMUnavailableError(
                    f"Ollama model '{self.model}' is not installed. Run `ollama pull "
                    f"{self.model}` or change OLLAMA_MODEL in backend/.env (see `ollama list`)."
                ) from e
            raise LLMUnavailableError(f"Ollama request failed: {e}") from e
        except requests.exceptions.RequestException as e:
            raise LLMUnavailableError(f"Ollama request failed: {e}") from e

        try:
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise LLMUnavailableError(f"Ollama error: {chunk['error']}")
                if chunk.get("response"):
                    yield chunk["response"]
                if chunk.get("done"):
                    break
        except requests.exceptions.RequestException as e:
            raise LLMUnavailableError(f"Ollama stream failed: {e}") from e


# --- Provider selection -------------------------------------------------------

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "gemini": GeminiProvider,
    "claude": ClaudeProvider,
    "ollama": OllamaProvider,
}


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    """Create the provider chosen by LLM_PROVIDER once and reuse it."""
    try:
        provider = _PROVIDERS[settings.LLM_PROVIDER]()
    except ImportError as e:
        raise LLMUnavailableError(
            f"The Python package for LLM_PROVIDER={settings.LLM_PROVIDER} is not installed "
            f"({e.name}). Run: pip install -r requirements.txt"
        ) from e
    logger.info("LLM provider: %s (model %s)", provider.name, provider.model)
    return provider


def generate_answer(prompt: str) -> str:
    """Return the full answer from the configured provider."""
    return get_provider().generate(prompt)


def generate_answer_stream(prompt: str) -> Iterator[str]:
    """Yield the answer piece by piece from the configured provider."""
    yield from get_provider().stream(prompt)
