-- Enable Row Level Security on all tables that currently lack it.
-- Tables that already have RLS (left untouched): feedback, interlinear_words,
-- jewish_perspectives, saved_words, source_toggles, user_daily_usage.
--
-- Backend uses SUPABASE_SERVICE_KEY (service_role, BYPASSRLS) so all server-side
-- reads/writes bypass these policies. The frontend uses the anon key + user JWT,
-- so corpus tables expose public read only, and conversations/messages are scoped
-- to the authenticated user.
--
-- Run manually in the Supabase SQL editor. Do not run via script.

-- CONVERSATIONS: users can only access their own
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can read own conversations" ON conversations
  FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own conversations" ON conversations
  FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own conversations" ON conversations
  FOR DELETE USING (auth.uid() = user_id);
CREATE POLICY "Users can update own conversations" ON conversations
  FOR UPDATE USING (auth.uid() = user_id);

-- MESSAGES: scoped through parent conversation ownership
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can read own messages" ON messages
  FOR SELECT USING (
    conversation_id IN (
      SELECT id FROM conversations WHERE user_id = auth.uid()
    )
  );
CREATE POLICY "Users can insert own messages" ON messages
  FOR INSERT WITH CHECK (
    conversation_id IN (
      SELECT id FROM conversations WHERE user_id = auth.uid()
    )
  );
CREATE POLICY "Users can delete own messages" ON messages
  FOR DELETE USING (
    conversation_id IN (
      SELECT id FROM conversations WHERE user_id = auth.uid()
    )
  );

-- CORPUS TABLES: public read, service_role write only
-- documents
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read documents" ON documents
  FOR SELECT USING (true);
CREATE POLICY "Service write documents" ON documents
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- chunks
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read chunks" ON chunks
  FOR SELECT USING (true);
CREATE POLICY "Service write chunks" ON chunks
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- verses
ALTER TABLE verses ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read verses" ON verses
  FOR SELECT USING (true);
CREATE POLICY "Service write verses" ON verses
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- books
ALTER TABLE books ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read books" ON books
  FOR SELECT USING (true);
CREATE POLICY "Service write books" ON books
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- book_quotes
ALTER TABLE book_quotes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read book_quotes" ON book_quotes
  FOR SELECT USING (true);
CREATE POLICY "Service write book_quotes" ON book_quotes
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- excerpts
ALTER TABLE excerpts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read excerpts" ON excerpts
  FOR SELECT USING (true);
CREATE POLICY "Service write excerpts" ON excerpts
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- background_topics
ALTER TABLE background_topics ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read background_topics" ON background_topics
  FOR SELECT USING (true);
CREATE POLICY "Service write background_topics" ON background_topics
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- GUEST SESSIONS: anon users can only access their own session
ALTER TABLE guest_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service manage guest_sessions" ON guest_sessions
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
