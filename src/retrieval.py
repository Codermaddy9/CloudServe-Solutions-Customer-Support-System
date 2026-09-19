"""
Retrieval module for CloudServe Documentation Corpus.
Satisfies Acceptance Criterion A4.
"""
import os
import json
import re
from typing import List, Dict, Any, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from src.models import DocumentChunk, RetrievalResult


class KnowledgeBaseRetriever:
    """
    Indexes and retrieves passages from CloudServe documentation.
    Implements section-based chunking and similarity scoring.
    """
    def __init__(self, docs_path: Optional[str] = None, relevance_threshold: float = 0.12):
        self.relevance_threshold = relevance_threshold
        if docs_path is None:
            # Default lookup paths
            candidates = [
                os.path.join("05_Datasets", "documentation.json"),
                os.path.join("..", "05_Datasets", "documentation.json"),
                os.path.join("data", "documentation.json"),
                "documentation.json"
            ]
            for cand in candidates:
                if os.path.exists(cand):
                    docs_path = cand
                    break
        
        self.docs_path = docs_path
        self.raw_docs: List[Dict[str, Any]] = []
        self.chunks: List[DocumentChunk] = []
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        
        if docs_path and os.path.exists(docs_path):
            self.load_and_index(docs_path)

    def _chunk_document(self, doc: Dict[str, Any]) -> List[DocumentChunk]:
        """
        Hierarchical / Section-based chunking strategy.
        Chunks by Markdown H2 headers (## Symptoms, ## Resolution, etc.)
        while preserving document metadata for precise citations.
        """
        doc_id = doc.get("doc_id", "DOC-UNKNOWN")
        title = doc.get("title", "")
        category = doc.get("category", "")
        applies_to = doc.get("applies_to", "")
        content = doc.get("content", "")

        chunks = []
        # First: full document chunk for high-level semantic match
        chunks.append(DocumentChunk(
            doc_id=doc_id,
            chunk_id=f"{doc_id}#overview",
            title=title,
            category=category,
            applies_to=applies_to,
            content=f"Title: {title}. Category: {category}. {content[:500]}"
        ))

        # Split into sections based on '## ' headers
        sections = re.split(r'\n(?=##\s+)', content)
        for idx, sec in enumerate(sections):
            sec = sec.strip()
            if not sec:
                continue
            lines = sec.split("\n", 1)
            header = lines[0].replace("#", "").strip().lower()
            header_slug = re.sub(r'[^a-z0-9]+', '-', header).strip('-') or f"section-{idx}"
            
            chunk_text = f"Article: {title} ({doc_id}). Category: {category}. Section: {sec}"
            chunks.append(DocumentChunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}#{header_slug}",
                title=f"{title} - {lines[0].replace('#', '').strip()}",
                category=category,
                applies_to=applies_to,
                content=chunk_text
            ))

        return chunks

    def load_and_index(self, docs_path: str):
        """Loads JSON documentation and fits vectorizer on section chunks."""
        with open(docs_path, "r", encoding="utf-8") as f:
            self.raw_docs = json.load(f)

        self.chunks = []
        for doc in self.raw_docs:
            self.chunks.extend(self._chunk_document(doc))

        # Build TF-IDF index
        texts = [f"{c.title} {c.category} {c.content}" for c in self.chunks]
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            sublinear_tf=True
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)

    def retrieve(self, query: str, top_k: int = 3) -> List[RetrievalResult]:
        """
        Retrieves top_k ranked passages from documentation.
        Applies relevance threshold: returns empty list if query does not match.
        """
        if not self.vectorizer or self.tfidf_matrix is None or not query.strip():
            return []

        q_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self.tfidf_matrix)[0]

        # Filter by threshold and rank
        scored_indices = [
            (idx, float(sims[idx]))
            for idx in range(len(sims))
            if sims[idx] >= self.relevance_threshold
        ]
        scored_indices.sort(key=lambda x: x[1], reverse=True)

        results = []
        seen_docs = set()
        for idx, score in scored_indices:
            chunk = self.chunks[idx]
            # Prioritize distinct doc_ids to give diverse top-k coverage
            if chunk.doc_id in seen_docs and len(results) >= 1:
                continue
            seen_docs.add(chunk.doc_id)
            results.append(RetrievalResult(
                doc_id=chunk.doc_id,
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                score=round(score, 4),
                content=chunk.content
            ))
            if len(results) >= top_k:
                break

        return results

    def get_doc_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Finds raw document by its doc_id."""
        for d in self.raw_docs:
            if d.get("doc_id") == doc_id:
                return d
        return None
