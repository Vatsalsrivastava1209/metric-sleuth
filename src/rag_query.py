"""
rag_query.py
============
Query engine for the MetricSleuth RAG (Retrieval-Augmented Generation) system.

Flow
----
1. User asks a natural-language question (e.g. "Did we have a similar
   traffic drop last quarter?")
2. Question is embedded with the same sentence-transformers model used
   during indexing.
3. Top-K most similar historical RCA reports are retrieved from ChromaDB.
4. Retrieved documents + user question are assembled into a prompt.
5. LLM (Gemini / OpenAI) generates a grounded answer.
6. If no LLM is configured, a structured text answer is returned from
   the retrieved chunks alone.
"""

from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_INDEX_DIR = Path("data/rag_index")
_DEFAULT_TOP_K     = 3


@dataclass
class RAGResult:
    """The result of a RAG query."""

    question:   str
    answer:     str
    sources:    list[dict] = field(default_factory=list)   # retrieved doc metadata
    context:    str = ""                                    # raw retrieved text

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer":   self.answer,
            "sources":  self.sources,
        }


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve(
    question: str,
    top_k: int = _DEFAULT_TOP_K,
    index_dir: str | Path = _DEFAULT_INDEX_DIR,
) -> list[dict[str, Any]]:
    """Retrieve the *top_k* most relevant historical RCA chunks for *question*.

    Parameters
    ----------
    question:
        Natural-language query from the user.
    top_k:
        Maximum number of results to return.
    index_dir:
        ChromaDB persistence directory (same one used by indexer).

    Returns
    -------
    list[dict]
        Each entry has keys ``document``, ``metadata``, ``distance``.
        Sorted by ascending cosine distance (most relevant first).
    """
    from src.rag_indexer import get_collection
    collection = get_collection(index_dir)

    total = collection.count()
    if total == 0:
        logger.warning("RAG index is empty — no documents to query.")
        return []

    k = min(top_k, total)
    results = collection.query(
        query_texts=[question],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    output: list[dict] = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append({
            "document": doc,
            "metadata": meta,
            "distance": round(float(dist), 4),
        })

    logger.info("Retrieved %d documents for query: '%s'", len(output), question[:60])
    return output


# ── Prompt assembly ───────────────────────────────────────────────────────────

def _build_rag_prompt(question: str, retrieved: list[dict]) -> str:
    """Assemble an LLM prompt from the question and retrieved context."""
    context_parts: list[str] = []
    for i, r in enumerate(retrieved, 1):
        meta = r.get("metadata", {})
        header = (
            f"[Document {i}] "
            f"Anomaly date: {meta.get('anomaly_date', 'N/A')} | "
            f"Metric: {meta.get('primary_metric', 'N/A')}"
        )
        context_parts.append(f"{header}\n{r['document']}")

    context = "\n\n---\n\n".join(context_parts) or "No relevant historical data found."

    prompt = textwrap.dedent(f"""
    You are MetricSleuth's AI analyst. You have access to a database of historical
    Root Cause Analysis (RCA) reports from previous metric anomaly events.

    A user has asked the following question about past anomalies:
    "{question}"

    Below are the most relevant historical RCA reports retrieved from the database:

    {context}

    Instructions:
    - Answer the user's question based ONLY on the retrieved reports above.
    - Be specific: mention dates, metrics, segments, and causes from the data.
    - If the retrieved reports are not relevant to the question, say so clearly.
    - Keep the answer concise (3-5 sentences).
    - Do NOT invent data not present in the retrieved documents.

    Answer:
    """).strip()

    return prompt


# ── LLM answer generation ─────────────────────────────────────────────────────

def _llm_answer(prompt: str) -> str:
    """Call the configured LLM backend to generate an answer."""
    from utils.config import LLM_BACKEND, LLM_MODEL, LLM_API_KEY, LLM_MAX_TOKENS, LLM_TEMPERATURE

    if not LLM_API_KEY:
        return None  # type: ignore  — caller checks for None

    backend = (LLM_BACKEND or "").lower()
    try:
        if backend == "gemini":
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=LLM_API_KEY)
            model = genai.GenerativeModel(LLM_MODEL or "gemini-1.5-flash")
            resp = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=LLM_MAX_TOKENS,
                    temperature=LLM_TEMPERATURE,
                ),
            )
            return resp.text.strip()

        elif backend == "openai":
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=LLM_API_KEY)
            resp = client.chat.completions.create(
                model=LLM_MODEL or "gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
            )
            return resp.choices[0].message.content.strip()

    except Exception as exc:
        logger.error("LLM call failed: %s", exc)

    return None  # type: ignore


def _fallback_answer(question: str, retrieved: list[dict]) -> str:
    """Return a structured plain-text answer without an LLM (no API key needed)."""
    if not retrieved:
        return (
            "No historical RCA reports are indexed yet. "
            "Run an RCA analysis from the RCA Report tab to populate the knowledge base."
        )

    lines = [
        f"Found {len(retrieved)} relevant historical event(s) for: '{question}'\n"
    ]
    for i, r in enumerate(retrieved, 1):
        meta = r.get("metadata", {})
        sim  = round((1 - r["distance"]) * 100, 1)
        lines.append(
            f"**Event {i}** — {meta.get('anomaly_date', 'N/A')} "
            f"({meta.get('primary_metric', 'N/A')}) — {sim}% similarity"
        )
        # First 3 lines of the document as a snippet
        snippet = "\n".join(r["document"].split("\n")[:3])
        lines.append(f"  {snippet}\n")

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def query(
    question: str,
    top_k: int = _DEFAULT_TOP_K,
    index_dir: str | Path = _DEFAULT_INDEX_DIR,
) -> RAGResult:
    """Answer a natural-language question using retrieved RCA history.

    Parameters
    ----------
    question:
        The user's question (e.g. "Did we have a similar traffic drop last quarter?").
    top_k:
        Number of historical reports to retrieve.
    index_dir:
        ChromaDB persistence directory.

    Returns
    -------
    RAGResult
        Contains the ``answer``, raw ``context``, and ``sources`` metadata.
    """
    retrieved = retrieve(question, top_k, index_dir)

    context = "\n\n".join(r["document"] for r in retrieved)
    sources = [r.get("metadata", {}) for r in retrieved]

    # Try LLM first
    if retrieved:
        prompt = _build_rag_prompt(question, retrieved)
        llm_resp = _llm_answer(prompt)
    else:
        llm_resp = None

    answer = llm_resp or _fallback_answer(question, retrieved)

    return RAGResult(
        question=question,
        answer=answer,
        sources=sources,
        context=context,
    )


def get_index_stats(index_dir: str | Path = _DEFAULT_INDEX_DIR) -> dict:
    """Return basic stats about the current index.

    Returns
    -------
    dict
        Keys: ``total_documents``, ``index_dir``, ``is_empty``.
    """
    try:
        from src.rag_indexer import get_collection
        col = get_collection(index_dir)
        total = col.count()
        return {"total_documents": total, "index_dir": str(index_dir), "is_empty": total == 0}
    except Exception as exc:
        return {"total_documents": 0, "index_dir": str(index_dir), "is_empty": True, "error": str(exc)}


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib, logging
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    logging.basicConfig(level=logging.INFO)

    result = query("Did we have a traffic drop similar to last month?")
    print(f"\nQ: {result.question}")
    print(f"\nA: {result.answer}")
    print(f"\nSources: {result.sources}")
