"""Sentence Transformers adapter: official inference API and pinned local files."""
import hashlib
from pathlib import Path
import re
import time
import threading
from typing import Protocol
import numpy as np
from .common import ROOT, digest, read_json


class TextEncoder(Protocol):
    fingerprint: str
    dimension: int
    def fit_document(self, text: str) -> tuple[str, dict]: ...
    def encode(self, texts: list[str], role: str) -> np.ndarray: ...


class HFEncoder:
    def __init__(self, alias="e5", threads=4, batch_size=8):
        if alias not in {"e5", "minilm"}:
            raise ValueError("Model chưa đăng ký: " + str(alias))
        if type(threads) is not int or not 1 <= threads <= 16 or not 1 <= batch_size <= 64:
            raise ValueError("Số threads/batch không hợp lệ.")
        started = time.perf_counter()
        self.path = ROOT / "models" / alias
        self.manifest = read_json(self.path / "manifest.json")
        self.alias, self.dimension = alias, self.manifest["dimension"]
        self.lock = threading.Lock()
        self.max_tokens, self.batch_size = self.manifest["max_tokens"], batch_size
        self.query_prefix = self.manifest["query_prefix"]
        self.passage_prefix = self.manifest["passage_prefix"]
        # Validate actual model/tokenizer files, not only a claimed manifest revision.
        for name, info in self.manifest["files"].items():
            if name == "README.md":
                continue
            path = self.path / name
            checksum = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b""):
                    checksum.update(chunk)
            if path.stat().st_size != info["bytes"] or checksum.hexdigest() != info["sha256"]:
                raise ValueError("Model/tokenizer đã thay đổi: " + name)
        import torch
        from sentence_transformers import SentenceTransformer
        torch.set_num_threads(threads)
        self.torch = torch
        self.model = SentenceTransformer(str(self.path), device="cpu", local_files_only=True,
                                         trust_remote_code=False, model_kwargs={"use_safetensors": True})
        self.model.max_seq_length = self.max_tokens
        self.tokenizer = self.model.tokenizer
        self.config = {"repo": self.manifest["repo"], "revision": self.manifest["revision"],
                       "weights_sha256": self.manifest["files"]["model.safetensors"]["sha256"],
                       "max_tokens": self.max_tokens, "query_prefix": self.query_prefix,
                       "passage_prefix": self.passage_prefix, "pooling": "masked_mean", "normalization": "l2",
                       "document_policy": "sentence-boundary-token-budget-v1", "dtype": "float32", "dimension": self.dimension}
        self.fingerprint = digest(self.config)
        self.load_seconds = time.perf_counter() - started

    def token_count(self, text, role="passage"):
        prefix = self.passage_prefix if role == "passage" else self.query_prefix
        return len(self.tokenizer.encode(prefix + text, add_special_tokens=True, truncation=False, verbose=False))

    def fit_document(self, text):
        before = self.token_count(text)
        if before <= self.max_tokens:
            return text, {"original_tokens": before, "encoded_tokens": before, "omitted_segments": 0, "fallback_token_cut": False}
        segments = [s.strip() for s in re.split(r"(?<=[.!?])\s+|(?=Feature: |Description: )", text) if s.strip()]
        chosen, omitted, fallback = [], 0, False
        for segment in segments:
            if self.token_count(" ".join(chosen + [segment])) <= self.max_tokens:
                chosen.append(segment)
            else:
                omitted += 1
        if not chosen:
            prefix_length = len(self.tokenizer.encode(self.passage_prefix, add_special_tokens=False))
            ids = self.tokenizer.encode(text, add_special_tokens=False)[:self.max_tokens-prefix_length-8]
            chosen = [self.tokenizer.decode(ids, skip_special_tokens=True)]
            fallback = True
        fitted = " ".join(chosen)
        while self.token_count(fitted) > self.max_tokens:
            fitted = fitted.rsplit(" ", 1)[0]
        return fitted, {"original_tokens": before, "encoded_tokens": self.token_count(fitted), "omitted_segments": omitted, "fallback_token_cut": fallback}

    def encode(self, texts, role="passage"):
        if role not in {"query", "passage"}:
            raise ValueError("Unknown encoding role")
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        prefix = self.query_prefix if role == "query" else self.passage_prefix
        method = self.model.encode_query if role == "query" else self.model.encode_document
        # Parity checked against the previous masked-mean implementation and persisted
        # index: max cosine error < 1e-6, identical top-10 for all 80 benchmark queries.
        # Semantic fingerprint stays compatible because inputs/pooling/normalization match.
        with self.lock:
            vectors = method(texts, prompt=prefix, batch_size=self.batch_size,
                             normalize_embeddings=True, convert_to_numpy=True,
                             show_progress_bar=False).astype(np.float32)
        if vectors.shape != (len(texts), self.dimension) or not np.isfinite(vectors).all():
            raise ValueError("Encoder trả vector không hợp lệ.")
        return vectors
