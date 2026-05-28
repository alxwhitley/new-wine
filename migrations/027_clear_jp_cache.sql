-- Migration 027: Clear stale jewish_perspectives cache.
-- Section keys changed from (hebrew_root, targumic_usage, rabbinic_context, messianic_fulfillment)
-- to (jewish_background, messianic_perspective, cultural_context).
-- Run in Supabase SQL Editor.
-- Created: 2026-05-27

DELETE FROM jewish_perspectives;
