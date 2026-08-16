#!/usr/bin/env python3
"""API regression for the fixed queued-source retention policy."""

import asyncio
import os
import unittest
from types import SimpleNamespace


os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.test/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.test")

from app.routers import ingest_queue  # noqa: E402


class FakeTable:
    def __init__(self, name, owner):
        self.name = name
        self.owner = owner
        self.payload = None

    def insert(self, payload):
        self.payload = dict(payload)
        self.owner.inserts.append((self.name, self.payload))
        return self

    def upsert(self, payload, on_conflict=None):
        self.owner.upserts.append((self.name, dict(payload), on_conflict))
        return self

    def execute(self):
        if self.name == "source_ingest_queue":
            return SimpleNamespace(data=[{"id": "row-1", **self.payload}])
        return SimpleNamespace(data=[])


class FakeSupabase:
    def __init__(self):
        self.inserts = []
        self.upserts = []

    def table(self, name):
        return FakeTable(name, self)


class QueueRetentionTests(unittest.TestCase):
    def test_create_persists_true_retention_without_changing_response_or_memory(self):
        fake = FakeSupabase()
        original = ingest_queue.get_supabase
        ingest_queue.get_supabase = lambda: fake
        try:
            body = ingest_queue.QueueCreateBody(
                url="https://www.example.com/book.pdf",
                source_format="pdf",
                source_scope="single",
                attribute_to="Derek Prince",
                attribution_mode="declared",
            )
            result = asyncio.run(
                ingest_queue.create_queue_row(body, user_id="admin-1")
            )
        finally:
            ingest_queue.get_supabase = original

        self.assertEqual(len(fake.inserts), 1)
        table, inserted_row = fake.inserts[0]
        self.assertEqual(table, "source_ingest_queue")
        self.assertIs(inserted_row["retain_original_text"], True)
        self.assertEqual(result["id"], "row-1")
        self.assertIs(result["retain_original_text"], True)
        self.assertEqual(
            fake.upserts[0][0:2],
            (
                "source_ingest_domain_memory",
                {
                    "domain": "example.com",
                    "attribute_to": "Derek Prince",
                    "attribution_mode": "declared",
                    "updated_at": fake.upserts[0][1]["updated_at"],
                },
            ),
        )
        self.assertEqual(fake.upserts[0][2], "domain")


if __name__ == "__main__":
    unittest.main()
