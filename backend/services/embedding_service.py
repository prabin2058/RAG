"""SentenceTransformer wrapper — loads the model once, lazily."""

from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"

_model = None


def _get_model() -> SentenceTransformer:
    """Load the embedding model on first use and cache it."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Encode a list of texts into dense vectors."""
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True).tolist()