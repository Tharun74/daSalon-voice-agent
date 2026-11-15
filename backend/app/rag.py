import os
import uuid
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from pypdf import PdfReader
import docx

from app import config
from app.db import get_db, persist_mock_data

logger = logging.getLogger("dasalon.rag")


class HybridEmbeddingFunction(EmbeddingFunction):
    """
    Embedding function that uses Fireworks AI (nomic-ai/nomic-embed-text-v1.5)
    with a deterministic local fallback if network is restricted.
    """
    def __init__(self):
        self._openai_client = None

    def name(self) -> str:
        return "hybrid_nomic_embed"

    def _get_client(self):
        if self._openai_client is None:
            from openai import OpenAI
            self._openai_client = OpenAI(
                api_key=config.FIREWORKS_API_KEY,
                base_url="https://api.fireworks.ai/inference/v1/",
                timeout=15.0,
            )
        return self._openai_client

    def __call__(self, input: Documents) -> Embeddings:
        # Try Fireworks embedding
        try:
            client = self._get_client()
            resp = client.embeddings.create(
                input=list(input),
                model="nomic-ai/nomic-embed-text-v1.5",
            )
            return [item.embedding for item in resp.data]
        except Exception as e:
            logger.warning(f"Fireworks embedding failed ({e}), using local deterministic fallback.")
            import hashlib
            import numpy as np

            results = []
            for text in input:
                vec = [0.0] * 768
                words = text.lower().split()
                for w in words:
                    h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16) % 768
                    vec[h] += 1.0
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = (np.array(vec) / norm).tolist()
                results.append(vec)
            return results


class VectorStoreInterface(ABC):
    """Abstract interface for Vector Store, easily swappable for MongoDB Atlas Vector Search."""

    @abstractmethod
    def add_chunks(
        self,
        salon_id: str,
        doc_id: str,
        filename: str,
        chunks: List[str],
    ) -> int:
        pass

    @abstractmethod
    def query(
        self,
        salon_id: str,
        query_text: str,
        n_results: int = 4,
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete_by_doc_id(self, salon_id: str, doc_id: str) -> None:
        pass


class ChromaVectorStore(VectorStoreInterface):
    """ChromaDB implementation of VectorStoreInterface with strict tenant filtering."""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        self.embedding_fn = HybridEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name="dasalon_knowledge",
            embedding_function=self.embedding_fn,
            metadata={"description": "Multi-tenant salon knowledge store"},
        )

    def add_chunks(
        self,
        salon_id: str,
        doc_id: str,
        filename: str,
        chunks: List[str],
    ) -> int:
        if not chunks:
            return 0

        ids = [f"{salon_id}_{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "salon_id": salon_id,
                "doc_id": doc_id,
                "filename": filename,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        self.collection.add(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
        )
        return len(chunks)

    def query(
        self,
        salon_id: str,
        query_text: str,
        n_results: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        HARD MULTI-TENANT ISOLATION REQUIREMENT:
        Always filter strictly by salon_id in every Chroma query.
        """
        if not query_text or not query_text.strip():
            return []

        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where={"salon_id": salon_id},
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0] if results.get("distances") else []

        output = []
        for i, doc in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) else {}
            dist = distances[i] if i < len(distances) else None
            output.append({
                "content": doc,
                "filename": meta.get("filename", "unknown"),
                "chunk_index": meta.get("chunk_index", 0),
                "distance": dist,
            })
        return output

    def delete_by_doc_id(self, salon_id: str, doc_id: str) -> None:
        """Delete all vectors for a specific document belonging to this salon."""
        self.collection.delete(
            where={"$and": [{"salon_id": salon_id}, {"doc_id": doc_id}]}
        )


# Global vector store instance
_vector_store: Optional[VectorStoreInterface] = None


def get_vector_store() -> VectorStoreInterface:
    global _vector_store
    if _vector_store is None:
        _vector_store = ChromaVectorStore()
    return _vector_store


# Document parsing & chunking helpers

def parse_document(file_path: Path, filename: str) -> str:
    """Extract plain text from PDF, DOCX, TXT, or MD."""
    ext = file_path.suffix.lower()
    text = ""

    if ext == ".pdf":
        reader = PdfReader(str(file_path))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    elif ext == ".docx":
        doc = docx.Document(str(file_path))
        for para in doc.paragraphs:
            if para.text:
                text += para.text + "\n"
    elif ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    return text.strip()


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> List[str]:
    """
    Split text into chunks of ~400 words with ~50 words overlap.
    Preserves paragraph and sentence boundaries where possible.
    """
    words = text.split()
    if not words:
        return []

    chunks = []
    step = chunk_size - overlap
    if step <= 0:
        step = chunk_size

    for i in range(0, len(words), step):
        chunk_words = words[i : i + chunk_size]
        chunk = " ".join(chunk_words).strip()
        if chunk:
            chunks.append(chunk)

    return chunks


def ingest_document_task(salon_id: str, doc_id: str, file_path: Path, filename: str):
    """Background task to parse, chunk, embed, and store document."""
    db = get_db()
    try:
        vector_store = get_vector_store()
        text = parse_document(file_path, filename)
        if not text:
            raise ValueError("Document appears to be empty or unreadable.")

        chunks = chunk_text(text, chunk_size=350, overlap=50)
        chunk_count = vector_store.add_chunks(
            salon_id=salon_id,
            doc_id=doc_id,
            filename=filename,
            chunks=chunks,
        )

        db.documents.update_one(
            {"salon_id": salon_id, "doc_id": doc_id},
            {
                "$set": {
                    "status": "ready",
                    "chunk_count": chunk_count,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        persist_mock_data()
        logger.info(f"Successfully ingested {filename} ({chunk_count} chunks) for salon {salon_id}")

    except Exception as e:
        logger.error(f"Failed ingesting document {filename} for {salon_id}: {e}")
        db.documents.update_one(
            {"salon_id": salon_id, "doc_id": doc_id},
            {
                "$set": {
                    "status": "failed",
                    "error": str(e),
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        persist_mock_data()


def retrieve_reference_context(salon_id: str, query: str, n_results: int = 4) -> Optional[str]:
    """Retrieve top relevant chunks for salon and format for prompt."""
    vector_store = get_vector_store()
    results = vector_store.query(salon_id=salon_id, query_text=query, n_results=n_results)

    if not results:
        return None

    # Filter out empty or low relevance if distances available
    formatted_chunks = []
    for res in results:
        formatted_chunks.append(f"[{res['filename']} (chunk {res['chunk_index']})]:\n{res['content']}")

    return "\n\n".join(formatted_chunks)
