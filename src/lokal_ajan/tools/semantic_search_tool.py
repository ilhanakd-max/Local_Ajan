"""Local semantic code search tool with definition-boundary chunking.

Uses Ollama embeddings if `LOCAI_EMBED_MODEL` is configured and reachable,
and automatically falls back to a fast pure-Python BM25/TF-IDF scorer so it
always works offline without extra downloads.
"""

import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from pydantic import BaseModel, Field

from lokal_ajan.safety.sandbox import get_safe_path
from lokal_ajan.tools.base import BaseTool
from lokal_ajan.tools.registry import registry

_IGNORE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
    ".lokal_ajan",
    "graphify-out",
}

_CODE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".sh", ".md",
}

_DEF_BOUNDARY_RE = re.compile(
    r"^\s*(?:async\s+)?(?:def|class|function|export\s+(?:default\s+)?(?:function|class|const)|fn|struct|impl|interface|type)\b"
)
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        # Split snake_case and camelCase for better semantic matching
        parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", raw).replace("_", " ").lower().split()
        tokens.extend(parts)
    return tokens


def _chunk_file(file_path: Path, max_chunk_lines: int = 60) -> list[dict]:
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    if not lines:
        return []

    chunks: list[dict] = []
    start = 0
    for idx, line in enumerate(lines):
        if idx > start and ((_DEF_BOUNDARY_RE.match(line) and (idx - start) >= 8) or (idx - start) >= max_chunk_lines):
            text = "\n".join(lines[start:idx])
            chunks.append({"line_start": start + 1, "line_end": idx, "text": text})
            start = idx
    if start < len(lines):
        chunks.append({"line_start": start + 1, "line_end": len(lines), "text": "\n".join(lines[start:])})
    return chunks


def _ollama_embed(texts: list[str], model: str, host: str) -> list[list[float]] | None:
    try:
        import httpx
        resp = httpx.post(
            f"{host.rstrip('/')}/api/embed",
            json={"model": model, "input": texts},
            timeout=15.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            embs = data.get("embeddings")
            if isinstance(embs, list) and len(embs) == len(texts):
                return embs
    except Exception:
        pass
    return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class SemanticCodeSearchArgs(BaseModel):
    query: str = Field(..., description="Natural-language description of what the code does")
    path: str = Field(".", description="Root directory to search")
    max_results: int = Field(5, ge=1, le=20, description="Maximum number of candidate files to return")


class SemanticCodeSearchTool(BaseTool):
    name = "semantic_code_search"
    description = "Searches code by behavior/meaning when you do not know exact symbol names; returns candidate files and line ranges"
    args_schema = SemanticCodeSearchArgs
    requires_confirm = False

    def __init__(self, workdir: str | None = None):
        self.workdir = workdir

    def run(self, query: str, path: str = ".", max_results: int = 5) -> str:
        try:
            root_str = get_safe_path(path, self.workdir) if self.workdir else path
        except ValueError as e:
            return f"Error: {e}"

        root = Path(root_str)
        if not root.exists():
            return f"Error: Path '{path}' does not exist."

        chunks: list[dict] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in sorted(dirnames) if d not in _IGNORE_DIRS and not d.startswith(".")]
            for fname in sorted(filenames):
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() not in _CODE_EXTS:
                    continue
                if fpath.stat().st_size > 512_000:
                    continue
                rel = str(fpath.relative_to(root)) if fpath != root else fpath.name
                for ch in _chunk_file(fpath):
                    ch["file"] = rel
                    chunks.append(ch)

        if not chunks:
            return f"No searchable code files found in '{path}'."

        embed_model = os.environ.get("LOCAI_EMBED_MODEL", "").strip()
        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        used_backend = "lexical-bm25"

        if embed_model and len(chunks) <= 200:
            q_emb = _ollama_embed([query], embed_model, ollama_host)
            c_embs = _ollama_embed([c["text"] for c in chunks], embed_model, ollama_host) if q_emb else None
            if q_emb and c_embs:
                used_backend = f"ollama:{embed_model}"
                for c, emb in zip(chunks, c_embs):
                    c["score"] = _cosine(q_emb[0], emb)

        if used_backend == "lexical-bm25":
            q_tokens = _tokenize(query)
            if not q_tokens:
                return "Error: Query produced no searchable terms."
            doc_tokens = [_tokenize(f"{c['file']} {c['text']}") for c in chunks]
            df = Counter()
            for toks in doc_tokens:
                for t in set(toks):
                    df[t] += 1
            n_docs = len(chunks)
            avg_len = sum(len(t) for t in doc_tokens) / max(n_docs, 1)
            k1, b = 1.5, 0.75
            for c, toks in zip(chunks, doc_tokens):
                tf = Counter(toks)
                dl = len(toks)
                score = 0.0
                for qt in q_tokens:
                    if qt not in tf:
                        continue
                    idf = math.log(1.0 + (n_docs - df[qt] + 0.5) / (df[qt] + 0.5))
                    freq = tf[qt]
                    denom = freq + k1 * (1.0 - b + b * (dl / max(avg_len, 1.0)))
                    score += idf * ((freq * (k1 + 1.0)) / max(denom, 1e-9))
                c["score"] = score

        # One best hit per file
        best_per_file: dict[str, dict] = {}
        for c in chunks:
            if c.get("score", 0.0) <= 0.0:
                continue
            prev = best_per_file.get(c["file"])
            if prev is None or c["score"] > prev["score"]:
                best_per_file[c["file"]] = c

        ranked = sorted(best_per_file.values(), key=lambda x: x["score"], reverse=True)[:max_results]
        if not ranked:
            return f"No semantic matches found for '{query}' in '{path}'."

        out = [f"Semantic search results ({used_backend}) — read candidate files with 'read_file' before concluding:"]
        for item in ranked:
            preview = " ".join(item["text"].splitlines()[:3])[:140]
            out.append(f"- {item['file']}:{item['line_start']}-{item['line_end']} (score={item['score']:.2f}): {preview}")
        return "\n".join(out)


registry.register(SemanticCodeSearchTool())
