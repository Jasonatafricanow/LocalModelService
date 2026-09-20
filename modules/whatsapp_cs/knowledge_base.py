"""Knowledge base (RAG) module.

Loads customer-service training scripts from a directory, generates
embeddings via Ollama, and provides cosine-similarity search so the
LLM can ground its responses in established procedures.

Supports both Portuguese and English knowledge base entries.
"""
import glob
import json
import logging
import math
import os
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KNOWLEDGE_DIR = os.path.join(_HERE, "knowledge")
OLLAMA_BASE_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_documents: list[dict] = []          # {"id": str, "text": str, "source": str}
_embeddings: list[list[float]] = []  # parallel to _documents
_embed_available: bool = False


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_knowledge(source_dir: str = DEFAULT_KNOWLEDGE_DIR) -> int:
    """Load all knowledge documents from *source_dir*.

    Supported file formats: ``.md``, ``.txt``, ``.json``.

    - **.md / .txt**: ``##`` headings delimit separate Q&A sections.
      Files without headings are treated as a single document.
    - **.json**: expects a list of ``{"question": …, "answer": …}``
      objects.

    Returns the number of documents loaded.
    """
    global _documents, _embeddings, _embed_available

    _documents.clear()
    _embeddings.clear()

    if not os.path.isdir(source_dir):
        logger.warning("Knowledge directory does not exist: %s", source_dir)
        return 0

    files = sorted(
        glob.glob(os.path.join(source_dir, "**", "*.md"), recursive=True)
        + glob.glob(os.path.join(source_dir, "**", "*.txt"), recursive=True)
        + glob.glob(os.path.join(source_dir, "**", "*.json"), recursive=True)
    )
    # Keep repository navigation and operational metadata out of RAG results.
    source_root = Path(source_dir).resolve()
    files = [
        f for f in files
        if not any(part.startswith(".") for part in Path(f).resolve().relative_to(source_root).parts)
        and not os.path.basename(f).lower().startswith("readme")
        and os.path.basename(f).lower() not in {"dev_log.md", "_index.md"}
    ]

    docs: list[dict] = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            logger.warning("Could not read %s: %s", fp, e)
            continue

        ext = os.path.splitext(fp)[1]
        if ext == ".json":
            docs.extend(_load_json_docs(fp, content))
        else:
            docs.extend(_load_text_docs(fp, content))

    _documents = docs
    logger.info("Loaded %d knowledge documents from %s", len(docs), source_dir)

    # Pre-compute embeddings so search is fast at query time
    _embed_available = _check_embed_model()
    if _embed_available:
        _embeddings = [_embed(doc["text"]) for doc in _documents]
        logger.info("Generated embeddings for %d documents", len(_documents))
    else:
        logger.info("Embedding model not available — will use keyword fallback")

    return len(docs)


def _load_json_docs(fp: str, content: str) -> list[dict]:
    """Parse a JSON knowledge file into document entries."""
    try:
        entries = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in %s", fp)
        return []

    if not isinstance(entries, list):
        logger.warning("JSON root in %s is not a list — skipping", fp)
        return []

    docs: list[dict] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        q = entry.get("question", "")
        a = entry.get("answer", "")
        if q and a:
            docs.append({
                "id": f"{fp}:{i}",
                "text": f"Q: {q}\nA: {a}",
                "source": fp,
            })
    return docs


def _load_text_docs(fp: str, content: str) -> list[dict]:
    """Parse a Markdown / plain-text knowledge file into document entries."""
    sections = _split_sections(content)
    if sections:
        return [
            {
                "id": f"{fp}:{i}",
                "text": f"{heading}\n{body}" if heading else body,
                "source": fp,
            }
            for i, (heading, body) in enumerate(sections)
        ]

    # No headings — treat the whole file as one document
    text = content.strip()
    return [{"id": fp, "text": text, "source": fp}] if text else []


def _split_sections(content: str) -> list[tuple[str, str]]:
    """Split markdown content into ``(heading, body)`` pairs by ``##``."""
    lines = content.splitlines()
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_heading or any(l.strip() for l in current_body):
                sections.append((
                    current_heading,
                    "\n".join(current_body).strip(),
                ))
            current_heading = line.lstrip("#").strip()
            current_body = []
        else:
            current_body.append(line)

    if current_heading or any(l.strip() for l in current_body):
        sections.append((
            current_heading,
            "\n".join(current_body).strip(),
        ))

    return sections


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def _check_embed_model() -> bool:
    """Check whether the Ollama embedding model is available."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        for m in resp.json().get("models", []):
            if EMBED_MODEL in m.get("name", ""):
                return True
        return False
    except requests.RequestException:
        return False


def embed(text: str) -> Optional[list[float]]:
    """Generate an embedding vector for *text* via Ollama ``/api/embed``.

    Returns ``None`` if the embedding model is not available or the
    request fails.
    """
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": text},
            timeout=10,
        )
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [])
        return embeddings[0] if embeddings else None
    except requests.RequestException as e:
        logger.warning("Embedding request failed: %s", e)
        return None


def _embed(text: str) -> list[float]:
    """Internal embedding — returns empty list on failure."""
    result = embed(text)
    return result or []


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if not a or not b:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def _keyword_score(query: str, text: str) -> int:
    """Simple keyword-matching score used as fallback when embeddings
    are unavailable."""
    query_lower = query.lower()
    text_lower = text.lower()
    words = query_lower.split()
    return sum(1 for w in words if w in text_lower)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def search(query: str, top_k: int = 3) -> list[dict]:
    """Search the knowledge base and return the *top_k* most relevant documents.

    Uses cosine similarity over pre-computed embeddings when available;
    falls back to keyword matching otherwise.

    Each result dict has keys ``id``, ``text``, ``source``, ``score``.
    Returns an empty list if no documents match.
    """
    if not _documents:
        return []

    if _embed_available and _embeddings:
        query_emb = _embed(query)
        if not query_emb:
            return _keyword_search(query, top_k)

        scored = [
            (i, _cosine_similarity(query_emb, _embeddings[i]))
            for i in range(len(_documents))
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            {**_documents[i], "score": round(score, 4)}
            for i, score in scored[:top_k]
            if score > 0
        ]

    return _keyword_search(query, top_k)


def _keyword_search(query: str, top_k: int = 3) -> list[dict]:
    """Fallback keyword-based search when embeddings are unavailable."""
    scored = [
        (i, _keyword_score(query, doc["text"]))
        for i, doc in enumerate(_documents)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [
        {**_documents[i], "score": score}
        for i, score in scored[:top_k]
        if score > 0
    ]


def retrieve(query: str, top_k: int = 3) -> str:
    """Convenience method — search and return concatenated relevant passages.

    Returns an empty string when no relevant documents are found so
    callers can simply append the result to a prompt.
    """
    results = search(query, top_k=top_k)
    if not results:
        return ""

    passages = [
        f"[Fonte: {os.path.basename(r['source'])}]\n{r['text']}"
        for r in results
    ]
    return "\n\n---\n\n".join(passages)



