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

An optional override can replace this entire assembled text at runtime, via
the SKF Admin Console's config overlay (system="support", key="knowledge_text")
-- see config_overlay.py. This does NOT reintroduce the per-request cache
problem above: the override is either unset (nothing changes) or a stable
string that only changes when an operator edits it from the console, so the
prompt prefix is still byte-for-byte identical across requests between edits.
The overlay module does its own short-TTL caching per container, so this is
one extra read of an in-process cache on every load() call, not a DynamoDB
call every time.
"""

import functools
from pathlib import Path

from . import config_overlay

# knowledge/ sits beside src/ at the repo root, and is packaged into the Lambda
# bundle by deployment/build.sh.
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
PLACEHOLDERS = ("<LMS_URL>", "<SUPPORT_EMAIL>")


@functools.lru_cache(maxsize=1)
def _load_from_files():
    """The bundled knowledge base, read once per warm container. This is the
    fallback used whenever the console's override is unset."""
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


def load():
    """Return the full knowledge base as one markdown string: the console's
    override if one is set, otherwise the bundled files. Deliberately not
    cached itself (unlike _load_from_files) -- config_overlay.get() already
    caches for SKF_ADMIN_CONFIG_TTL_SECONDS (default 60s), which is how an
    edit from the console takes effect without a redeploy."""
    override = config_overlay.get("support", "knowledge_text", default=None)
    if override:
        return override
    return _load_from_files()


def topics():
    """Filenames currently loaded, for the health check and for logging."""
    if not KNOWLEDGE_DIR.is_dir():
        return []
    return [p.stem for p in sorted(KNOWLEDGE_DIR.glob("*.md"))]


def unresolved_placeholders():
    """Return deployment placeholders still present in the loaded knowledge."""
    text = load()
    return [placeholder for placeholder in PLACEHOLDERS if placeholder in text]
