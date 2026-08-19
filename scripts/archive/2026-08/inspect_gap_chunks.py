#!/usr/bin/env python3
"""Inspect ch231/ch233 (SOP) and ch182 (NL) for structural signals."""
import psycopg2

url = [l.split("=", 1)[1].strip().strip('"').strip("'") for l in open("backend/app/.env") if l.startswith("SUPABASE_DB_URL")][0]
SOP = "a8e2ead2-7bdf-4f90-9b49-22835800f72a"
NL = "9fb66238-fe97-47da-88df-56f3e4b5602d"


def show(title, doc_id, chunk_index):
    conn = psycopg2.connect(url, connect_timeout=25)
    cur = conn.cursor()
    cur.execute(
        "SELECT id::text, content FROM chunks WHERE document_id = %s::uuid AND chunk_index = %s",
        (doc_id, chunk_index),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        print(f"\n{title}: not found")
        return
    cid, content = row
    print(f"\n{'='*80}\n{title} | chunk_index={chunk_index} | {cid}\n{'='*80}")
    print(content)
    # Print quote mark positions
    import re
    print("\n--- quote marks ---")
    for m in re.finditer(r"[\u2018\u2019\u201c\u201d\"']", content):
        ctx = content[max(0, m.start() - 50) : m.start() + 50].replace("\n", " ")
        print(f"  {m.group()!r} @ {m.start():4d}: ...{ctx}...")


show("SOP Müller inline", SOP, 231)
show("SOP Müller inline", SOP, 233)
show("NL catechism answer", NL, 182)
