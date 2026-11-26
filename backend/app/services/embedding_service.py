"""SentenceTransformer wrapper — loads the model once, lazily."""

from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"

# bge models search better when the *question* (not the stored text) starts
# with this instruction. See the model card for BAAI/bge-small-en-v1.5.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model = None


def _get_model() -> SentenceTransformer:
    """Load the embedding model on first use and cache it."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def max_tokens() -> int:
    """Longest input the model reads; anything longer is cut off."""
    return _get_model().max_seq_length


def count_tokens(text: str) -> int:
    """Tokens the model sees for this text, including its start/end tokens."""
    return len(_get_model().tokenizer(text, add_special_tokens=True)["input_ids"])


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Encode document chunks into dense vectors."""
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True).tolist()


def embed_query(question: str) -> list[float]:
    """Encode a search question (with the bge query instruction)."""
    return embed_texts([QUERY_PREFIX + question])[0]
