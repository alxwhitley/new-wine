-- Migration 043: Sources and license audit tables
-- Adds the per-rights-holder entity table (sources) and an immutable audit log.
-- This migration is INERT: no existing table, RPC, or code path is changed.
-- Linking documents to sources and the retrieval gate are separate later steps.
-- Created: 2026-06-23

-- ── sources ────────────────────────────────────────────────────────────────
-- One row per licensable rights holder.
-- license_status drives the computed `retrievable` column; new rows default
-- to 'unlicensed' => retrievable = false (fail-closed by construction).

CREATE TABLE sources (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name                  text        NOT NULL UNIQUE,
  slug                  text        UNIQUE,
  license_status        text        NOT NULL DEFAULT 'unlicensed'
                          CHECK (license_status IN (
                            'public_domain', 'owned', 'licensed', 'unlicensed'
                          )),
  retrievable           boolean     NOT NULL GENERATED ALWAYS AS (
                          license_status IN ('public_domain', 'owned', 'licensed')
                        ) STORED,
  permission_granted_at timestamptz,
  permission_contact    text,
  permission_terms      text,
  notes                 text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);

-- ── source_license_audit ───────────────────────────────────────────────────
-- Immutable audit log of every license_status change on a source row.
-- Populated by admin toggle logic in a future step; no trigger yet.

CREATE TABLE source_license_audit (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id   uuid        NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  old_status  text,
  new_status  text        NOT NULL,
  changed_by  text,
  note        text,
  changed_at  timestamptz NOT NULL DEFAULT now()
);

-- Index for efficient per-source audit lookups
CREATE INDEX idx_source_license_audit_source_id
  ON source_license_audit (source_id, changed_at DESC);

-- ── RLS ────────────────────────────────────────────────────────────────────
-- Admin-only: no public read. FastAPI uses SUPABASE_SERVICE_KEY which
-- bypasses RLS; the service_role policy keeps future direct-client access safe.
-- Pattern matches user_roles / pastors_cards in migration 038.

ALTER TABLE sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "sources: service role full access"
  ON sources FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

ALTER TABLE source_license_audit ENABLE ROW LEVEL SECURITY;

CREATE POLICY "source_license_audit: service role full access"
  ON source_license_audit FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
