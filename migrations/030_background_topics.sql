CREATE TABLE IF NOT EXISTS background_topics (
  id serial PRIMARY KEY,
  topic_key text UNIQUE NOT NULL,
  document_id uuid NOT NULL REFERENCES documents(id),
  aliases text[] DEFAULT '{}',
  title text NOT NULL
);

INSERT INTO background_topics (topic_key, document_id, aliases, title) VALUES
('baptism_holy_spirit', 'a3884084-46f8-40be-929f-e34cb63ba8ac',
 ARRAY['baptism of the holy spirit','spirit baptism','baptized in the spirit',
       'filled with the spirit','spirit filled','pentecost','upper room','acts 2'],
 'Baptism of the Holy Spirit'),
('speaking_in_tongues', 'b884a5e1-d786-452f-8bf8-454bca0ab129',
 ARRAY['speaking in tongues','gift of tongues','prayer language','glossolalia',
       'tongues','praying in the spirit','pray in tongues','private prayer language'],
 'Speaking in Tongues'),
('gift_of_prophecy', '52a4f7fd-252d-4b99-94a0-1e2a1055fcaa',
 ARRAY['gift of prophecy','prophetic gift','prophecy','prophesy',
       'prophetic word','word of prophecy'],
 'The Gift of Prophecy');
