"""Ollama HTTP wrapper — calls the local Ollama server."""

import os

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4")


class OllamaUnavailableError(Exception):
    """Raised when the local Ollama server cannot be reached."""


def generate_answer(prompt: str) -> str:
    """Send a prompt to Ollama's /api/generate and return the full response text."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=300,  # local models can be slow on CPU
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise OllamaUnavailableError(
            f"Could not reach Ollama at {OLLAMA_URL}. Is it running? "
            f"Start it with `ollama serve` and pull a model with `ollama pull {OLLAMA_MODEL}`."
        ) from e
    except requests.exceptions.RequestException as e:
        raise OllamaUnavailableError(f"Ollama request failed: {e}") from e

    data = resp.json()
    if "response" not in data:
        raise OllamaUnavailableError(f"Unexpected Ollama response: {data}")
    return data["response"].strip()