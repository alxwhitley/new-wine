-- Fix interlinear_words RLS: restrict INSERT to service_role
DROP POLICY IF EXISTS "Service role can insert" ON interlinear_words;
CREATE POLICY "Service role can insert" ON interlinear_words
  FOR INSERT WITH CHECK (auth.role() = 'service_role');
