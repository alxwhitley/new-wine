create table if not exists saved_words (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade,
  strongs_number text not null,
  greek_word text not null,
  transliteration text not null,
  english_gloss text,
  created_at timestamptz default now(),
  unique(user_id, strongs_number)
);

alter table saved_words enable row level security;

create policy "Users can manage their own saved words"
  on saved_words for all
  using (auth.uid() = user_id);
