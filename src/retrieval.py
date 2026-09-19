"""
Retrieval over the CloudServe documentation corpus.
Satisfies Acceptance Criterion A4.

Why retrieval is hybrid
-----------------------
Ines Varga, technical writer, interview four, describing why her articles go
unused:

    "Our internal search matches on titles and exact terms, and customers do not
     describe problems in the words I used for the title. Someone writes 'my
     deployment keeps dying' and my article is called 'resolving container
     health check failures'. There is no path between those two phrases in a
     keyword search."

That is a direct account of lexical retrieval failing, and it is the mechanism
behind the delivery gap the discovery analysis measures: 71.4% of tickets are
answerable from the documentation while only 43.8% were resolved on first
contact. Building the replacement on TF-IDF alone would reproduce the fault we
were hired to remove.

Embeddings alone are not the answer either. Customers quote document ids,
error codes, HTTP statuses and CLI flags, and a dense vector is poor at exact
token matching. So a lexical and a dense ranking both run, and are fused.

There are three tiers, tried in order, and `backend_description()` always states
which one is live so that no result is ever reported without saying how it was
produced:

  1. Chroma with all-MiniLM-L6-v2, as the Project Brief recommends. Best
     semantic matching, but it needs `chromadb`, `sentence-transformers` and a
     one-off model download.
  2. Latent semantic indexing: truncated SVD over the TF-IDF matrix. A genuine
     dense representation that captures some synonymy, computed locally in
     under a second from dependencies the project already has. No download and
     no network.
  3. TF-IDF alone.

Tier 2 exists because tier 1 cannot be assumed. The assessor's machine may have
no access to the model host, and a clean-checkout run that fails because a
2 GB download was refused would fail A1 for a reason that has nothing to do
with the system. Tier 2 means the dense half of retrieval is present and
measurable in every environment, and tier 1 improves on it where available.

Chunking
--------
Articles are split on Markdown H2 headings, plus one whole-article chunk for
topical matching. Support articles are written as Symptoms / Common causes /
Resolution, so a section boundary is a genuine semantic boundary, and a
resolution step retrieved on its own is still intelligible. Every chunk keeps
its `doc_id`, so a citation always resolves to a real article and Ines can tell
whether a wrong answer came from a wrong article or a misread one.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import Normalizer

from src.models import DocumentChunk, RetrievalResult

# Below this fused score a result is treated as no match at all. Retrieval
# returning nothing is a valid and often correct outcome; always returning
# something hides failure, which the Build Specification calls out explicitly.
DEFAULT_RELEVANCE_THRESHOLD = 0.12

# Reciprocal rank fusion constant. 60 is the value from the original Cormack
# et al. formulation and is not tuned here, because tuning it against the
# development set would be fitting a constant to 500 tickets.
RRF_K = 60

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Dimensions for the latent semantic fallback. 128 sits comfortably below the
# number of chunks the corpus produces, so the decomposition is well determined.
LSA_COMPONENTS = 128


def _candidate_paths(filename: str) -> List[str]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [
        os.path.join(root, "05_Datasets", filename),
        os.path.join(root, "data", filename),
        os.path.join("05_Datasets", filename),
        filename,
    ]


class KnowledgeBaseRetriever:
    """
    Indexes the corpus and returns ranked, citable passages.

    `use_semantic=False` forces the lexical-only path, which the evaluation uses
    to measure what the dense half is actually contributing rather than assuming
    it helps.
    """

    def __init__(
        self,
        docs_path: Optional[str] = None,
        relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
        use_semantic: bool = True,
        chroma_path: Optional[str] = None,
    ):
        self.relevance_threshold = relevance_threshold
        self.use_semantic = use_semantic
        self.chroma_path = chroma_path or os.getenv("CHROMA_PATH", "")

        self.raw_docs: List[Dict[str, Any]] = []
        self.chunks: List[DocumentChunk] = []
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None

        self._collection = None
        self._embedder = None
        self.semantic_available = False
        self.semantic_error: Optional[str] = None

        self._svd = None
        self._svd_matrix = None
        self._normalizer = None
        self.lsa_available = False

        if docs_path is None:
            for candidate in _candidate_paths("documentation.json"):
                if os.path.exists(candidate):
                    docs_path = candidate
                    break

        self.docs_path = docs_path
        if docs_path and os.path.exists(docs_path):
            self.load_and_index(docs_path)

    # ------------------------------------------------------------- chunking

    def _chunk_document(self, doc: Dict[str, Any]) -> List[DocumentChunk]:
        doc_id = doc.get("doc_id", "DOC-UNKNOWN")
        title = doc.get("title", "")
        category = doc.get("category", "")
        applies_to = doc.get("applies_to", "")
        content = doc.get("content", "") or ""

        chunks = [DocumentChunk(
            doc_id=doc_id,
            chunk_id=f"{doc_id}#overview",
            title=title,
            category=category,
            applies_to=applies_to,
            content=f"{title}. {category}. {applies_to}. {content[:600]}",
        )]

        for index, section in enumerate(re.split(r"\n(?=##\s+)", content)):
            section = section.strip()
            if not section:
                continue
            heading = section.split("\n", 1)[0].replace("#", "").strip()
            slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-") or f"s{index}"
            chunks.append(DocumentChunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}#{slug}",
                title=f"{title} — {heading}" if heading else title,
                category=category,
                applies_to=applies_to,
                # The article title is prepended to every section so that a
                # section retrieved alone still carries the topic it belongs to.
                content=f"{title}. {category}. {section}",
            ))
        return chunks

    # -------------------------------------------------------------- indexing

    def load_and_index(self, docs_path: str) -> None:
        with open(docs_path, "r", encoding="utf-8") as fh:
            self.raw_docs = json.load(fh)

        self.chunks = []
        for doc in self.raw_docs:
            self.chunks.extend(self._chunk_document(doc))

        texts = [c.content for c in self.chunks]
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), stop_words="english", sublinear_tf=True)
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)

        if self.use_semantic:
            self._build_semantic_index(texts)
            if not self.semantic_available:
                self._build_lsa_index()

    def _build_lsa_index(self) -> None:
        """
        Latent semantic index over the TF-IDF matrix.

        Cheap, local, and it gives the dense half of the hybrid something to
        contribute when the transformer model is not reachable.
        """
        try:
            n_components = min(LSA_COMPONENTS, max(2, self.tfidf_matrix.shape[1] - 1),
                               max(2, self.tfidf_matrix.shape[0] - 1))
            self._svd = TruncatedSVD(n_components=n_components, random_state=42)
            reduced = self._svd.fit_transform(self.tfidf_matrix)
            self._normalizer = Normalizer(copy=False)
            self._svd_matrix = self._normalizer.fit_transform(reduced)
            self.lsa_available = True
        except Exception as exc:  # noqa: BLE001
            self.semantic_error = f"{self.semantic_error or ''} LSA unavailable ({exc})".strip()
            self.lsa_available = False

    def _build_semantic_index(self, texts: List[str]) -> None:
        """
        Build the Chroma index. Any failure here leaves the retriever working
        on TF-IDF alone rather than breaking the run.
        """
        try:
            import chromadb
            from chromadb.utils import embedding_functions
        except ImportError as exc:
            self.semantic_error = (
                f"chromadb/sentence-transformers not installed ({exc}); "
                "running on lexical retrieval only")
            return

        try:
            embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL)

            if self.chroma_path:
                client = chromadb.PersistentClient(path=self.chroma_path)
            else:
                client = chromadb.EphemeralClient()

            name = "cloudserve_docs"
            try:
                client.delete_collection(name)
            except Exception:  # noqa: BLE001 — absent collection is fine
                pass

            collection = client.create_collection(
                name=name,
                embedding_function=embedder,
                metadata={"hnsw:space": "cosine"},
            )
            collection.add(
                ids=[c.chunk_id for c in self.chunks],
                documents=texts,
                metadatas=[{"doc_id": c.doc_id, "title": c.title} for c in self.chunks],
            )
            self._collection = collection
            self._embedder = embedder
            self.semantic_available = True
        except Exception as exc:  # noqa: BLE001
            self.semantic_error = f"semantic index unavailable ({exc}); using lexical only"
            self._collection = None
            self.semantic_available = False

    def backend_description(self) -> str:
        if self.semantic_available:
            return f"hybrid tier 1: Chroma/{EMBEDDING_MODEL} fused with TF-IDF"
        if not self.use_semantic:
            return "lexical only: TF-IDF (dense ranking disabled by configuration)"
        if self.lsa_available:
            return (f"hybrid tier 2: latent semantic indexing "
                    f"({self._svd.n_components} dims) fused with TF-IDF "
                    f"— {self.semantic_error or 'transformer model not available'}")
        return f"lexical only: TF-IDF ({self.semantic_error or 'dense ranking unavailable'})"

    # ------------------------------------------------------------- retrieval

    def _lexical_ranking(self, query: str, depth: int):
        """Return (ranked indices, raw cosine similarities keyed by index)."""
        if self.vectorizer is None or self.tfidf_matrix is None:
            return [], {}
        similarities = cosine_similarity(
            self.vectorizer.transform([query]), self.tfidf_matrix)[0]
        ranked = sorted(range(len(similarities)),
                        key=lambda i: similarities[i], reverse=True)
        ranked = [i for i in ranked if similarities[i] > 0][:depth]
        return ranked, {i: float(similarities[i]) for i in ranked}

    def _semantic_ranking(self, query: str, depth: int):
        """
        Dense ranking from whichever tier is live.

        Returns (ranked indices, raw similarities). The raw similarity matters:
        it is the evidence a candidate is judged on, and discarding it in favour
        of rank alone is how a retriever ends up confidently returning its least
        bad match for a query that matches nothing.
        """
        if self.semantic_available and self._collection is not None:
            try:
                response = self._collection.query(query_texts=[query], n_results=depth)
                ids = response.get("ids", [[]])[0]
                distances = response.get("distances", [[]])[0]
                index_of = {c.chunk_id: i for i, c in enumerate(self.chunks)}
                ranked, scores = [], {}
                for cid, distance in zip(ids, distances):
                    if cid not in index_of:
                        continue
                    i = index_of[cid]
                    ranked.append(i)
                    # Chroma reports cosine distance; convert back to similarity.
                    scores[i] = max(0.0, 1.0 - float(distance))
                return ranked, scores
            except Exception:  # noqa: BLE001 — a query failure degrades to LSA/lexical
                pass

        if self.lsa_available and self._svd is not None:
            try:
                q = self._normalizer.transform(
                    self._svd.transform(self.vectorizer.transform([query])))
                sims = (self._svd_matrix @ q[0])
                ranked = [int(i) for i in np.argsort(-sims)[:depth] if sims[i] > 0]
                # Deliberately no scores returned. Cosine similarity in a
                # 128-dimensional projection is not on the same scale as TF-IDF
                # cosine and runs high even for a near-meaningless query, so
                # admitting candidates on it would reintroduce exactly the
                # "confidently returns its least bad match" behaviour the
                # relevance gate exists to prevent. LSA is a projection of the
                # TF-IDF matrix in any case, so it has no independent evidence
                # to offer about whether a passage is relevant — only about how
                # the admitted candidates should be ordered.
                return ranked, {}
            except Exception:  # noqa: BLE001
                return [], {}

        return [], {}

    def retrieve(self, query: str, top_k: int = 3) -> List[RetrievalResult]:
        """
        Return up to `top_k` passages, or nothing when nothing is relevant.

        Rankings from each backend are fused by reciprocal rank fusion, then
        deduplicated so that top_k covers distinct articles rather than three
        sections of the same one.
        """
        if not query or not query.strip() or not self.chunks:
            return []

        depth = max(top_k * 8, 24)

        lexical, lexical_scores = self._lexical_ranking(query, depth)
        semantic, semantic_scores = self._semantic_ranking(query, depth)

        if not lexical and not semantic:
            return []

        # The relevance gate is applied to raw similarity, before fusion.
        #
        # Fusion ranks candidates against each other; it says nothing about
        # whether any of them is relevant in absolute terms. Normalising fused
        # scores would hand the best candidate a perfect score even when the
        # query matches nothing at all, so a query of pure gibberish would come
        # back with a confident top result. The Build Specification is explicit
        # that retrieval must return nothing rather than something irrelevant,
        # so a candidate must clear the threshold on its own similarity before
        # fusion is allowed to order it.
        evidence: Dict[int, float] = {}
        for index in set(lexical) | set(semantic):
            evidence[index] = max(lexical_scores.get(index, 0.0),
                                  semantic_scores.get(index, 0.0))

        admitted = {i for i, score in evidence.items()
                    if score >= self.relevance_threshold}
        if not admitted:
            return []

        fused: Dict[int, float] = {}
        for ranking in (lexical, semantic):
            for rank, index in enumerate(ranking):
                if index in admitted:
                    fused[index] = fused.get(index, 0.0) + 1.0 / (RRF_K + rank + 1)

        ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)

        results: List[RetrievalResult] = []
        seen_docs = set()
        for index, _ in ordered:
            chunk = self.chunks[index]
            if chunk.doc_id in seen_docs:
                continue
            seen_docs.add(chunk.doc_id)
            results.append(RetrievalResult(
                doc_id=chunk.doc_id,
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                # The reported score is the raw similarity, not the fusion
                # weight, because it is what a person checking a citation can
                # actually interpret.
                score=round(evidence[index], 4),
                content=chunk.content,
            ))
            if len(results) >= top_k:
                break
        return results

    def get_doc_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        for doc in self.raw_docs:
            if doc.get("doc_id") == doc_id:
                return doc
        return None
