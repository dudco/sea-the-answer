"""Pinned, explicitly prepared, CPU-only E5 embeddings. No runtime downloads."""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from threading import RLock

MODEL_ID = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
DIMENSION = 384
MAX_TOKENS = 512


class VectorUnavailable(RuntimeError):
    """Only static, non-sensitive reason codes may cross the diagnostics boundary."""


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def contract() -> dict:
    return {"model": MODEL_ID, "revision": REVISION, "dimension": DIMENSION,
            "input": "labelled-title-reference-heading-text-v1", "windows": "lossless-mean-v1",
            "normalization": "l2", "prefixes": ["query: ", "passage: "],
            "libraries": {name: version(name).split("+")[0] for name in
                          ("sentence-transformers", "transformers", "torch")}}


def content_hash(chunk: dict) -> str:
    return digest({key: chunk.get(key) for key in
                   ("id", "document_id", "title", "reference", "heading", "text", "page")})


def passage(chunk: dict) -> str:
    return "\n".join(f"{key}: {chunk.get(key) or ''}" for key in
                     ("title", "reference", "heading", "text"))


def model_directory() -> Path:
    return Path(os.getenv("HAEDAP_EMBED_MODEL_DIR", ".rag-models/e5-small"))


def prepare_model(directory: Path | None = None) -> Path:
    """Explicit network operation, called only by the developer prepare command."""
    from huggingface_hub import snapshot_download
    directory = directory or model_directory()
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_download(MODEL_ID, revision=REVISION, local_dir=str(directory),
                      allow_patterns=["config.json", "modules.json", "sentence_bert_config.json",
                                      "config_sentence_transformers.json", "tokenizer*",
                                      "special_tokens_map.json", "model.safetensors",
                                      "sentencepiece.bpe.model", "1_Pooling/config.json"],
                      max_workers=1)
    # Loading locally verifies that the pinned snapshot is complete before readiness.
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(str(directory), device="cpu", local_files_only=True,
                                trust_remote_code=False)
    if model.get_embedding_dimension() != DIMENSION or model.max_seq_length != MAX_TOKENS:
        raise VectorUnavailable("model_contract_mismatch")
    (directory / "haedap-ready.json").write_text(
        json.dumps({"model": MODEL_ID, "revision": REVISION}), encoding="utf-8")
    return directory


def split_passage(text: str, token_count, limit: int = MAX_TOKENS) -> list[str]:
    """Lossless character partition; prefix and special tokens count toward limit."""
    if token_count("passage: " + text) <= limit:
        return [text]
    if len(text) < 2:
        raise VectorUnavailable("passage_too_long")
    middle = len(text) // 2
    cut = max(text.rfind("\n", middle // 2, middle + 1),
              text.rfind(" ", middle // 2, middle + 1))
    cut = cut + 1 if cut >= 0 else middle
    return (split_passage(text[:cut], token_count, limit)
            + split_passage(text[cut:], token_count, limit))


class LocalEmbedder:
    def __init__(self, directory: str):
        path = Path(directory)
        try:
            marker = json.loads((path / "haedap-ready.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise VectorUnavailable("model_not_prepared") from None
        if marker != {"model": MODEL_ID, "revision": REVISION}:
            raise VectorUnavailable("model_contract_mismatch")
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(str(path), device="cpu", local_files_only=True,
                                         trust_remote_code=False)
        if self.model.get_embedding_dimension() != DIMENSION or self.model.max_seq_length != MAX_TOKENS:
            raise VectorUnavailable("model_contract_mismatch")
        self.lock = RLock()

    def count(self, text: str) -> int:
        # Counting is deliberately allowed past 512; it is NOT a model forward pass.
        return len(self.model.tokenizer.encode(text, add_special_tokens=True, truncation=False, verbose=False))

    def documents(self, chunks: list[dict], batch_size: int = 16) -> list[list[float]]:
        import numpy as np
        windows = [split_passage(passage(row), self.count) for row in chunks]
        if any(len(parts) > 256 for parts in windows):
            raise VectorUnavailable("passage_too_long")
        inputs = ["passage: " + part for parts in windows for part in parts]
        if not inputs:
            return []
        with self.lock:
            vectors = self.model.encode(inputs, batch_size=batch_size, normalize_embeddings=True,
                                        show_progress_bar=False, convert_to_numpy=True)
        result, offset = [], 0
        for parts in windows:
            mean = vectors[offset:offset + len(parts)].mean(axis=0)
            norm = float(np.linalg.norm(mean))
            if not norm or not np.isfinite(norm):
                raise VectorUnavailable("invalid_embedding")
            result.append((mean / norm).tolist())
            offset += len(parts)
        return result

    def query(self, text: str) -> list[float]:
        if self.count("query: " + text) > MAX_TOKENS:
            raise VectorUnavailable("query_too_long")
        with self.lock:
            return self.model.encode(["query: " + text], normalize_embeddings=True,
                                     show_progress_bar=False)[0].tolist()


_MODEL_LOCK = RLock()


@lru_cache(maxsize=1)
def _embedder(directory: str) -> LocalEmbedder:
    return LocalEmbedder(directory)


def embedder() -> LocalEmbedder:
    with _MODEL_LOCK:
        return _embedder(str(model_directory().resolve()))
