-- removed_urls: blocklist for intentionally-removed documents with URLs
-- Prevents a deleted URL from being silently re-ingested on the next pipeline run
-- url is the PK so upsert is idempotent if the same URL is deleted twice

CREATE TABLE IF NOT EXISTS public.removed_urls (
  url            text PRIMARY KEY,
  document_id    uuid,
  title          text,
  original_title text,
  removed_at     timestamptz NOT NULL DEFAULT now(),
  reason         text
);
