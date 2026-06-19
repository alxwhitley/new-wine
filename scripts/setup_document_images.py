#!/usr/bin/env python3
"""
One-off: create document-images Storage bucket, upload test image, assign to Mumford doc.
Run from repo root: python3 scripts/setup_document_images.py
"""
import os
import sys
import requests
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
BUCKET = "document-images"
IMAGE_PATH = "mumford-life-of-worship.jpg"
UNSPLASH_URL = "https://unsplash.com/photos/78A265wPiO4/download"

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ── 1. Create bucket ──────────────────────────────────────────────────────────
print("Creating bucket...")
try:
    supabase.storage.create_bucket(BUCKET, options={"public": True})
    print(f"  ✓ Bucket '{BUCKET}' created")
except Exception as e:
    msg = str(e).lower()
    if "already exists" in msg or "duplicate" in msg:
        print(f"  ✓ Bucket '{BUCKET}' already exists — skipping")
    else:
        print(f"  ✗ Bucket creation failed: {e}", file=sys.stderr)
        sys.exit(1)

# ── 2. Download image ─────────────────────────────────────────────────────────
print("Downloading image from Unsplash...")
resp = requests.get(
    UNSPLASH_URL,
    allow_redirects=True,
    timeout=30,
    headers={"User-Agent": "Mozilla/5.0"},
)
resp.raise_for_status()
image_bytes = resp.content
content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
print(f"  ✓ Downloaded {len(image_bytes):,} bytes ({content_type})")

# ── 3. Upload to Storage ──────────────────────────────────────────────────────
print(f"Uploading to {BUCKET}/{IMAGE_PATH}...")
try:
    supabase.storage.from_(BUCKET).upload(
        IMAGE_PATH,
        image_bytes,
        {"content-type": content_type, "upsert": "true"},
    )
    print("  ✓ Upload complete")
except Exception as e:
    print(f"  ✗ Upload failed: {e}", file=sys.stderr)
    sys.exit(1)

public_url = supabase.storage.from_(BUCKET).get_public_url(IMAGE_PATH)
print(f"  Public URL: {public_url}")

# ── 4. Find document ──────────────────────────────────────────────────────────
print("Looking up 'Maintaining a Life of Worship' by Bob Mumford...")
result = (
    supabase.table("documents")
    .select("id, title, author")
    .ilike("title", "%Maintaining a Life of Worship%")
    .ilike("author", "%Mumford%")
    .limit(1)
    .execute()
)
if not result.data:
    print("  ✗ Document not found — check title/author spelling", file=sys.stderr)
    sys.exit(1)
doc = result.data[0]
print(f"  ✓ Found: {doc['id']} — {doc['title']} by {doc['author']}")

# ── 5. Assign image_url ───────────────────────────────────────────────────────
print("Setting image_url on document...")
supabase.table("documents").update({"image_url": public_url}).eq("id", doc["id"]).execute()
print("  ✓ image_url set")

print(f"\nDone.\n  Bucket : {BUCKET}\n  URL    : {public_url}")
