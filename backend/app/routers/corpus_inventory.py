"""Corpus inventory export -- read-only, publicly reachable bibliography CSV.

CORPUS-INV-001 (2026-08-17). Serves author/title/canonical-URL for the FULL
corpus, as CSV, so an external AI agent can run dedup checks against what
this corpus already holds before proposing new ingest candidates.

--- Deliberate license/visibility gate bypass -- read before touching this file ---

(a) This endpoint deliberately serves every row in `documents` regardless of
`license_status` or `visibility`. Every other content-serving surface in
this codebase applies the license/visibility gate (CLAUDE.md Invariant 2:
`license_status IN ('public_domain','owned') OR (NOT safe_mode_on AND
visibility='shown')`) before returning anything derived from a document.
This endpoint does not apply that gate, by Alex's explicit decision -- it is
a bibliography/inventory surface (author, title, URL only), not a
content-serving surface. Knowing a document with a given title/author/URL
exists in the corpus is not the same disclosure as serving its text.

(b) This must NEVER be extended to serve chunk text, excerpts, proposition
content, or any other corpus content without revisiting that decision first.
Doing so would reopen exactly the hole the license gate exists to close --
the gate exists precisely to stop unlicensed/hidden source content from
reaching an unauthenticated or under-authenticated caller. Adding a `select()`
column beyond `author, title, url`, or joining in chunk/proposition text, is
a policy change, not an implementation detail -- it needs a fresh decision,
not a quiet edit to this file.

Access: deliberately no auth of any kind (Alex's explicit call, 2026-08-17,
reversing this endpoint's original secret-key-gated design) -- the payload
(author/title/URL only, no license/visibility filter) is judged not
sensitive. Anyone with the URL gets the CSV; there is no key, no admin
check, nothing to rotate. `include_in_schema=False` keeps it out of /docs
and /openapi.json purely so it isn't advertised to every API browser --
that is NOT a security boundary, just an unlisted link, and must not be
treated as one if this decision is ever revisited.

Read-only: GET only, no other HTTP verb defined in this file, and no
write-method call (insert, update, delete, upsert) anywhere in this
module -- verified by a static grep in
scripts/test_corpus_inventory_endpoint.py.
"""
from __future__ import annotations

import csv
import io
from typing import List

from fastapi import APIRouter
from fastapi.responses import Response

from app.db.supabase import get_supabase

router = APIRouter()

# PostgREST's default row cap (commonly 1000) means a single unpaginated
# .select() call would silently truncate a 3,600+ row corpus. Page size is
# comfortably under that cap; the loop below continues until a page returns
# fewer rows than requested.
_PAGE_SIZE = 500


def _fetch_all_documents() -> List[dict]:
    """Paginate documents(author, title, url) to completion.

    No filter on license_status/visibility/source_id -- see the module
    docstring for why that is deliberate here, and only here. Ordered by
    `id` so pagination is deterministic across pages.
    """
    db = get_supabase()
    rows: List[dict] = []
    offset = 0
    while True:
        resp = (
            db.table("documents")
            .select("author, title, url")
            .order("id")
            .range(offset, offset + _PAGE_SIZE - 1)
            .execute()
        )
        page = resp.data or []
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return rows


def _rows_to_csv(rows: List[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["author", "title", "canonical_url"])
    for row in rows:
        writer.writerow(
            [
                row.get("author") or "",
                row.get("title") or "",
                row.get("url") or "",
            ]
        )
    return buf.getvalue()


@router.get("/export", include_in_schema=False)
async def export_corpus_inventory():
    rows = _fetch_all_documents()
    csv_text = _rows_to_csv(rows)
    return Response(content=csv_text, media_type="text/csv")
