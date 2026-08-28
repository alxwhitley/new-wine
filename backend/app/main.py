import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Rhemata", description="Theological knowledge base and AI chat tool")

allowed_origins = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Baseline security headers for API responses. The frontend gets its own set
# via frontend/next.config.ts; this origin (Railway) sent none at all.
#
# Deliberately minimal, because this origin serves JSON to a browser app on a
# different origin, not HTML documents:
#   - X-Frame-Options / Referrer-Policy / Permissions-Policy are omitted --
#     they govern document framing and navigation, which JSON responses don't
#     do. CORS (above) is what actually restricts who may read these responses.
#   - Content-Security-Policy is omitted for the same reason.
#   - HSTS is included because this origin serves over HTTPS and, unlike the
#     Vercel-hosted frontend, nothing upstream adds it. includeSubDomains and
#     preload are left OFF on purpose: this is a *.up.railway.app hostname, so
#     asserting a policy over sibling subdomains (or entering the preload list)
#     would reach beyond what this service owns.
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=63072000"
    )
    return response

from app.routers import search, document, ingest, ingest_queue, study, admin, feedback, library, pastors_notes, usage, account, quotes, answer_quotes, async_chat, corpus_inventory, analytics, admin_analytics

app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(document.router, prefix="/document", tags=["document"])
app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
app.include_router(ingest_queue.router, prefix="/ingest-queue", tags=["ingest-queue"])
app.include_router(study.router, prefix="/study", tags=["study"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
app.include_router(library.router, prefix="/library", tags=["library"])
app.include_router(pastors_notes.router, prefix="/pastors-notes", tags=["pastors-notes"])
app.include_router(usage.router, prefix="/usage", tags=["usage"])
app.include_router(account.router, prefix="/account", tags=["account"])
app.include_router(quotes.router, prefix="/quotes", tags=["quotes"])
# Reader-facing quote resolution (Project 3 wiring) -- deliberately separate
# from quotes.router above (that one is entirely require_admin_role-gated;
# this one is intentionally un-gated -- see answer_quotes.py's module
# docstring).
app.include_router(answer_quotes.router, prefix="/answer-quotes", tags=["answer-quotes"])

# Async answer path routes -- mounted unconditionally, same as every other
# router above. The ASYNC_ANSWER_ENABLED env gate that used to make this
# conditional was removed 2026-08-07 (mirror-unification batch 4, Alex's
# explicit decision): with chat.py deleted this same batch, this is now the
# ONLY answer path -- gating whether its routes even exist behind an env var
# that defaulted to "false" created a way to accidentally end up with zero
# answer paths mounted, with no visible error. The
# DB-driven async_answer_config.serving_enabled switch remains -- an
# emergency pause, not a rollback (there's no other path to roll back to;
# see async_chat.py's module docstring) -- unaffected by this change.
app.include_router(async_chat.router, prefix="/async-chat", tags=["async-chat"])

# Corpus inventory export (CORPUS-INV-001, 2026-08-17) -- a read-only,
# publicly reachable bibliography CSV (author/title/url) for an external
# AI agent's dedup use. Deliberately serves the full corpus regardless of
# license_status/visibility -- see corpus_inventory.py's module docstring
# for why that bypass is scoped to this bibliography-only surface and must
# never be extended to content. No auth of any kind (Alex's explicit call,
# 2026-08-17) -- include_in_schema=False just keeps it off /docs and
# /openapi.json, it is not a security boundary.
app.include_router(corpus_inventory.router, prefix="/corpus-inventory", tags=["corpus-inventory"])

# Search analytics and corpus-gap dashboard (docs/roadmap.md Horizon item
# 4; docs/superpowers/specs/2026-08-27-search-analytics-and-corpus-gap-
# dashboard.md). /analytics/consent is any-authenticated-user (own consent
# row, same posture as /account/delete-request); /admin/analytics/* is
# entirely require_admin_role-gated.
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(admin_analytics.router, prefix="/admin/analytics", tags=["admin-analytics"])

@app.get("/")
async def root():
    return {"message": "Rhemata API"}


# Liveness/readiness (B6 Task 5.3). Deliberately return only a status word and
# per-check booleans -- never a stack trace, DSN fragment, or exception
# message -- so this stays safe as a public, unauthenticated surface.

@app.get("/health")
async def health():
    """Liveness only: the process is up and serving HTTP. No dependency I/O."""
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    """Readiness: can this instance actually serve a request right now.

    Checks the two things that would make requests fail even though the
    process itself is alive: DB reachability and presence of the API keys
    every answer path depends on. Deliberately does NOT call out to
    Anthropic/OpenAI/Cohere/Groq -- Railway polls this on an interval, and a
    live call to every provider on each poll would be slow and non-free for
    zero real signal (a missing key is already caught by presence-checking
    it; a provider outage belongs in the answer-path's own error handling,
    not this probe).
    """
    checks = {}

    try:
        from app.services.async_answers.db import connect as _connect_db

        conn = _connect_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        checks["database"] = True
    except Exception:
        checks["database"] = False

    for key in (
        "SUPABASE_URL",
        "SUPABASE_DB_URL",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "COHERE_API_KEY",
        "GROQ_API_KEY",
    ):
        checks[key.lower()] = bool(os.environ.get(key))

    ok = all(checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "not_ready", "checks": checks},
    )