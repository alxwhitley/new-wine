create table if not exists verses (
  id uuid default gen_random_uuid() primary key,
  verse_id text not null unique,
  book text not null,
  book_num int not null,
  chapter int not null,
  verse int not null,
  text text not null,
  translation text not null default 'WEB',
  created_at timestamptz default now()
);

create index if not exists verses_verse_id_idx on verses (verse_id);
create index if not exists verses_book_chapter_verse_idx on verses (book, chapter, verse);
