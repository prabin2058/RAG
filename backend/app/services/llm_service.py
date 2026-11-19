"""LLM wrapper supporting Google Gemini and local Ollama."""

import json
import logging

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# Smaller context = faster generation for Ollama.
OLLAMA_NUM_CTX = 4096

_gemini_client = None


class LLMUnavailableError(Exception):
    """Raised when the LLM provider cannot be reached or fails."""


OllamaUnavailableError = LLMUnavailableError  # Backward compatibility


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_gemini_api_key_here":
            raise LLMUnavailableError(
                "GEMINI_API_KEY is not configured in backend/.env. "
                "Please add your API key from https://aistudio.google.com/app/apikey"
            )
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        except Exception as e:
            raise LLMUnavailableError(f"Failed to initialize Gemini client: {e}") from e
    return _gemini_client


def _is_gemini() -> bool:
    has_valid_key = bool(
        settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here"
    )
    return settings.LLM_PROVIDER.lower() == "gemini" or has_valid_key


def generate_answer(prompt: str) -> str:
    """Generate a response using Gemini or Ollama."""
    if _is_gemini():
        try:
            client = _get_gemini_client()
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
            )
            return (response.text or "").strip()
        except Exception as e:
            raise LLMUnavailableError(f"Gemini generation error: {e}") from e

    # Ollama fallback
    try:
        resp = requests.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_ctx": OLLAMA_NUM_CTX},
            },
            timeout=300,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise LLMUnavailableError(
            f"Could not reach Ollama at {settings.OLLAMA_URL}. Is it running? "
            f"Start with `ollama serve` and run `ollama pull {settings.OLLAMA_MODEL}`."
        ) from e
    except requests.exceptions.RequestException as e:
        raise LLMUnavailableError(f"Ollama request failed: {e}") from e

    data = resp.json()
    if "response" not in data:
        raise LLMUnavailableError(f"Unexpected Ollama response: {data}")
    return data["response"].strip()


def generate_answer_stream(prompt: str):
    """Stream response tokens using Gemini or Ollama."""
    if _is_gemini():
        try:
            client = _get_gemini_client()
            response = client.models.generate_content_stream(
                model=settings.GEMINI_MODEL,
                contents=prompt,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            return
        except Exception as e:
            raise LLMUnavailableError(f"Gemini streaming error: {e}") from e

    # Ollama streaming
    try:
        resp = requests.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": True,
                "options": {"num_ctx": OLLAMA_NUM_CTX},
            },
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise LLMUnavailableError(
            f"Could not reach Ollama at {settings.OLLAMA_URL}. Is it running?"
        ) from e
    except requests.exceptions.RequestException as e:
        raise LLMUnavailableError(f"Ollama request failed: {e}") from e

    for line in resp.iter_lines():
        if line:
            chunk = json.loads(line)
            if "response" in chunk:
                yield chunk["response"]


def generate_hyde_answer(question: str) -> str:
    """Generate a hypothetical answer for HyDE."""
    hyde_prompt = f"""Write a short, factual paragraph that would answer this question.
Do NOT make up information — write as if you're quoting from a document.
Keep it under 100 words.

Question: {question}

Hypothetical answer:"""

    if _is_gemini():
        try:
            client = _get_gemini_client()
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=hyde_prompt,
            )
            return (response.text or "").strip()
        except Exception as e:
            raise LLMUnavailableError(f"Gemini HyDE error: {e}") from e

    # Ollama HyDE
    try:
        resp = requests.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": hyde_prompt,
                "stream": False,
                "options": {"num_ctx": 1024, "temperature": 0.3},
            },
            timeout=120,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise LLMUnavailableError(
            f"Could not reach Ollama at {settings.OLLAMA_URL}. Is it running?"
        ) from e
    except requests.exceptions.RequestException as e:
        raise LLMUnavailableError(f"Ollama request failed: {e}") from e

    data = resp.json()
    return data.get("response", "").strip()
