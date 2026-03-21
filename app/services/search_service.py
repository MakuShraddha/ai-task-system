"""
AI Search Service
─────────────────
• Uses sentence-transformers (all-MiniLM-L6-v2) to create embeddings locally.
• Stores vectors in a FAISS flat index (no external API required).
• DocumentChunk metadata is kept in MySQL; FAISS holds the raw float32 vectors.
• The index is rebuilt on startup from stored chunks, so it survives restarts.
"""

from __future__ import annotations

import os
import logging
from typing import List, Tuple

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
MODEL_NAME = "all-MiniLM-L6-v2"   # 384-dim, fast, good quality
CHUNK_SIZE = 512                   # characters per chunk
CHUNK_OVERLAP = 64                 # overlap between adjacent chunks
FAISS_INDEX_PATH = "faiss_index.bin"
FAISS_ID_MAP_PATH = "faiss_id_map.npy"   # maps faiss row → (doc_id, chunk_db_id)


class VectorSearchService:
    """Singleton-style service; call get_service() instead of __init__."""

    def __init__(self):
        logger.info("Loading sentence-transformer model: %s", MODEL_NAME)
        self.model = SentenceTransformer(MODEL_NAME)
        self.dim = self.model.get_sentence_embedding_dimension()

        # FAISS index – IndexFlatIP uses inner product (cosine after normalise)
        self.index = faiss.IndexFlatIP(self.dim)

        # id_map[i] = (document_id, chunk_db_id)
        # We keep this as a plain Python list so it never gets out of sync.
        self.id_map: List[Tuple[int, int]] = []

        self._load_persisted_index()

    # ──────────────────────────────────────────────────────────────────────────
    # Persistence helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _load_persisted_index(self):
        if os.path.exists(FAISS_INDEX_PATH) and os.path.exists(FAISS_ID_MAP_PATH):
            try:
                self.index = faiss.read_index(FAISS_INDEX_PATH)
                raw = np.load(FAISS_ID_MAP_PATH, allow_pickle=True)
                self.id_map = [tuple(x) for x in raw.tolist()]
                logger.info("Loaded FAISS index (%d vectors) from disk.", self.index.ntotal)
            except Exception as exc:
                logger.warning("Could not load persisted FAISS index: %s", exc)
                self._reset_index()
        else:
            logger.info("No persisted FAISS index found – starting fresh.")

    def _persist_index(self):
        faiss.write_index(self.index, FAISS_INDEX_PATH)
        np.save(FAISS_ID_MAP_PATH, np.array(self.id_map, dtype=object))

    def _reset_index(self):
        self.index = faiss.IndexFlatIP(self.dim)
        self.id_map = []

    # ──────────────────────────────────────────────────────────────────────────
    # Embedding helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _embed(self, texts: List[str]) -> np.ndarray:
        """Return L2-normalised float32 embeddings, shape (N, dim)."""
        vecs = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        vecs = vecs.astype(np.float32)
        faiss.normalize_L2(vecs)
        return vecs

    # ──────────────────────────────────────────────────────────────────────────
    # Chunking
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def chunk_text(text: str) -> List[str]:
        """Split text into overlapping character-level chunks."""
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            chunks.append(text[start:end].strip())
            if end == len(text):
                break
            start += CHUNK_SIZE - CHUNK_OVERLAP
        return [c for c in chunks if c]   # drop empty

    # ──────────────────────────────────────────────────────────────────────────
    # Indexing
    # ──────────────────────────────────────────────────────────────────────────

    def index_document(
        self,
        document_id: int,
        chunk_texts: List[str],
        chunk_db_ids: List[int],
    ) -> int:
        """
        Embed and add chunks to FAISS.

        Returns the number of vectors added.
        """
        if not chunk_texts:
            return 0

        vecs = self._embed(chunk_texts)
        self.index.add(vecs)

        for chunk_db_id in chunk_db_ids:
            self.id_map.append((document_id, chunk_db_id))

        self._persist_index()
        logger.info("Indexed %d chunks for document %d.", len(chunk_texts), document_id)
        return len(chunk_texts)

    def remove_document(self, document_id: int):
        """
        Remove all vectors belonging to document_id.
        FAISS FlatIP doesn't support direct deletion, so we rebuild the index
        without the target document's vectors.
        """
        keep_positions = [
            i for i, (doc_id, _) in enumerate(self.id_map) if doc_id != document_id
        ]
        if len(keep_positions) == self.index.ntotal:
            return  # nothing to remove

        if not keep_positions:
            self._reset_index()
            self._persist_index()
            return

        # Reconstruct vectors we want to keep
        all_vecs = np.zeros((self.index.ntotal, self.dim), dtype=np.float32)
        for i in range(self.index.ntotal):
            all_vecs[i] = self.index.reconstruct(i)

        kept_vecs = all_vecs[keep_positions]
        kept_map = [self.id_map[i] for i in keep_positions]

        self._reset_index()
        self.index.add(kept_vecs)
        self.id_map = kept_map
        self._persist_index()

    # ──────────────────────────────────────────────────────────────────────────
    # Searching
    # ──────────────────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        """
        Return top_k most-similar chunks.

        Each result dict contains:
            document_id, chunk_db_id, score
        """
        if self.index.ntotal == 0:
            return []

        q_vec = self._embed([query])                      # (1, dim)
        k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(q_vec, k)     # (1, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            doc_id, chunk_db_id = self.id_map[idx]
            results.append(
                {"document_id": doc_id, "chunk_db_id": chunk_db_id, "score": float(score)}
            )
        return results

    # ──────────────────────────────────────────────────────────────────────────
    # Stats
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def total_vectors(self) -> int:
        return self.index.ntotal


# ── Module-level singleton ─────────────────────────────────────────────────────
_service: VectorSearchService | None = None


def get_search_service() -> VectorSearchService:
    global _service
    if _service is None:
        _service = VectorSearchService()
    return _service
