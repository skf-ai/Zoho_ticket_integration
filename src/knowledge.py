"""Loads the LMS support knowledge base that grounds every agent answer.

The knowledge lives in `knowledge/*.md` as plain markdown so support staff can
edit it without touching Python or redeploying anything but the file. Each file
is one topic; the agent is instructed to answer ONLY from this text and to raise
a ticket when the answer isn't here.

Why files rather than a database or a vector store: the whole corpus is a few
thousand tokens, which fits comfortably in the model's context on every call.
A retrieval service would add monthly cost, a failure mode, and latency, and buy
nothing at this size. Revisit only if the corpus outgrows the context window.

The assembled text is cached per warm Lambda container and is deliberately
stable byte-for-byte, because it forms the cacheable prefix of the prompt --
see llm.py. Any per-request value interpolated in here would silently destroy
that cache and multiply the running cost.
"""

import functools
from pathlib import Path

# knowledge/ sits beside src/ at the repo root, and is packaged into the Lambda
# bundle by deployment/build.sh.
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


@functools.lru_cache(maxsize=1)
def load():
    """Return the full knowledge base as one markdown string.

    Files are concatenated in sorted filename order so the result is identical
    on every container -- non-deterministic ordering would break prompt caching.
    """
    if not KNOWLEDGE_DIR.is_dir():
        print(f"[knowledge] directory not found: {KNOWLEDGE_DIR}")
        return ""

    parts = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(text)

    if not parts:
        print(f"[knowledge] no .md files in {KNOWLEDGE_DIR}")
    return "\n\n---\n\n".join(parts)


def topics():
    """Filenames currently loaded, for the health check and for logging."""
    if not KNOWLEDGE_DIR.is_dir():
        return []
    return [p.stem for p in sorted(KNOWLEDGE_DIR.glob("*.md"))]
