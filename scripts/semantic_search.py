from __future__ import annotations

import re
import time
import numpy as np
import faiss
from rank_bm25 import BM25Okapi


class SemanticSearcher:
    def __init__(self, model=None, model_name: str = "all-MiniLM-L6-v2"):
        if model is None:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(model_name)
        self.model = model
        self.index = None
        self.listings = None

    def build_index(self, remarks_list):
        print(f"Encoding {len(remarks_list)} listings...")
        embeddings = np.asarray(self.model.encode(remarks_list), dtype="float32")

        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings)
        self.listings = remarks_list

    def search(self, query, top_k=10):
        t0 = time.perf_counter()
        query_emb = np.asarray(self.model.encode([query]), dtype="float32")
        faiss.normalize_L2(query_emb)
        scores, indices = self.index.search(query_emb, top_k)
        elapsed = time.perf_counter() - t0
        results = [(self.listings[i], float(scores[0][j]))
                   for j, i in enumerate(indices[0]) if i != -1]
        return results, elapsed


def _tokenize(text: str):
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25Searcher:
    def __init__(self):
        self.bm25 = None
        self.listings = None

    def build_index(self, remarks_list):
        tokenized = [_tokenize(t) for t in remarks_list]
        self.bm25 = BM25Okapi(tokenized)
        self.listings = remarks_list

    def search(self, query, top_k=10):
        t0 = time.perf_counter()
        scores = self.bm25.get_scores(_tokenize(query))
        top_indices = scores.argsort()[::-1][:top_k]
        elapsed = time.perf_counter() - t0
        results = [(self.listings[i], float(scores[i])) for i in top_indices]
        return results, elapsed


# ===========================================================================
# Tests
# ===========================================================================

LISTINGS = [
    "Charming home in Irvine with a sparkling pool and two-car garage.",
    "Modern condo in Seattle with panoramic city views.",
    "Waterfront property in Miami with a private pool.",
    "Craftsman house in Portland with a cozy fireplace and hardwood floors.",
    "Spacious ranch home in Denver with a large fenced backyard.",
    "Contemporary home in Austin with solar panels and an updated kitchen.",
    "Colonial house in Chicago with a finished basement.",
    "Mediterranean villa in Miami with an in-ground swimming pool.",
    "Home in Raleigh with a two car garage and mountain views.",
    "Lakefront cottage in Denver with a stone fireplace.",
    "Renovated kitchen and hardwood floors in this Seattle bungalow.",
    "Austin home with a chef's kitchen and a spacious yard.",
    "Chicago townhouse with attached garage parking.",
    "Portland property with breathtaking mountain views and a garage.",
    "Eco-friendly Denver home with solar power and a fireplace.",
]

CASES = [
    ("home with a pool", ["pool"]),
    ("house with a garage", ["garage"]),
    ("waterfront property", ["Waterfront", "Lakefront"]),
    ("home with a fireplace", ["fireplace"]),
    ("home with solar panels", ["solar"]),
    ("house with hardwood floors", ["hardwood"]),
    ("property with mountain views", ["views"]),
    ("home with a finished basement", ["basement"]),
    ("house with an updated kitchen", ["kitchen"]),
    ("home with a large backyard", ["backyard", "yard"]),
]


def _build_searchers():
    semantic = SemanticSearcher()
    semantic.build_index(LISTINGS)
    bm25 = BM25Searcher()
    bm25.build_index(LISTINGS)
    return semantic, bm25


def test_build_index_and_search_return_results():
    semantic, bm25 = _build_searchers()
    for query, _ in CASES:
        sem_results, _ = semantic.search(query, top_k=5)
        bm25_results, _ = bm25.search(query, top_k=5)
        assert len(sem_results) > 0, f"semantic returned nothing for {query!r}"
        assert len(bm25_results) > 0, f"bm25 returned nothing for {query!r}"


def test_bm25_top_result_matches_keywords():
    _, bm25 = _build_searchers()
    hits = 0
    for query, expected_substrings in CASES:
        results, _ = bm25.search(query, top_k=1)
        top_text = results[0][0]
        if any(s.lower() in top_text.lower() for s in expected_substrings):
            hits += 1
    accuracy = hits / len(CASES)
    assert accuracy >= 0.8, f"BM25 top-1 keyword accuracy {accuracy:.0%} below 80%"


def test_semantic_scores_are_normalized_cosine_similarity():
    semantic, _ = _build_searchers()
    results, _ = semantic.search("home with a pool", top_k=5)
    for _, score in results:
        assert -1.0001 <= score <= 1.0001, f"cosine similarity out of range: {score}"


def test_faiss_index_size_matches_corpus():
    semantic, _ = _build_searchers()
    assert semantic.index.ntotal == len(LISTINGS)


if __name__ == "__main__":
    semantic, bm25 = _build_searchers()

    for query, _ in CASES:
        sem_results, sem_t = semantic.search(query, top_k=1)
        bm25_results, bm25_t = bm25.search(query, top_k=1)
        print(f"\nQuery: {query!r}")
        print(f"  semantic ({sem_t*1000:.2f}ms): {sem_results[0][0]}  [score={sem_results[0][1]:.3f}]")
        print(f"  bm25     ({bm25_t*1000:.2f}ms): {bm25_results[0][0]}  [score={bm25_results[0][1]:.3f}]")

    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  PASS: {name}")
    print("\nAll tests passed.")