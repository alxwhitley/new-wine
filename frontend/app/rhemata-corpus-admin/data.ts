import { CorpusCard } from "./types";

export const GROUPS = [
  "Pipelines",
  "Sermons & Transcripts",
  "Commentaries",
  "Public Domain Books",
  "Lexicons & Reference",
  "Maintenance",
] as const;

export const CARDS: CorpusCard[] = [
  // ── Pipelines ──
  {
    id: "magazine",
    name: "Magazine Pipeline",
    group: "Pipelines",
    status: "Ongoing",
    sourceKind: "magazine_article",
    description:
      "3-pass extraction (Gemini \u2192 Groq \u2192 QA) then ingest. ~300 issues pending.",
    steps: [
      { label: "Extract" },
      { label: "Manual Review" },
      { label: "Ingest" },
    ],
    commands: [
      {
        label: "Extract All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/extract_magazine.py --time-limit 480 > logs/magazine_overnight.log 2>&1 &",
      },
      {
        label: "Extract 2 Hour",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/extract_magazine.py --time-limit 120 > logs/magazine_2hr.log 2>&1 &",
      },
      {
        label: "Extract Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/extract_magazine.py --max-issues 1",
      },
      {
        label: "Ingest All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/ingest_magazine.py > logs/ingest_magazine_overnight.log 2>&1 &",
      },
      {
        label: "Ingest Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/ingest_magazine.py",
      },
      {
        label: "Monitor",
        command:
          "tail -f /Users/alexwhitley/Desktop/rhemata/logs/magazine_overnight.log",
      },
    ],
  },
  {
    id: "youtube-bevere",
    name: "YouTube \u2014 John Bevere TV",
    group: "Pipelines",
    status: "Ongoing",
    sourceKind: "sermon_transcript",
    extraFilter:
      "url ILIKE '%youtube%' AND (author ILIKE '%bevere%' OR source_name ILIKE '%bevere%')",
    description:
      "Scrape \u2192 Clean \u2192 Whisper \u2192 Ingest. Max 10 per run. Never complete.",
    steps: [
      { label: "Scrape" },
      { label: "Clean" },
      { label: "Whisper" },
      { label: "Ingest" },
    ],
    commands: [
      {
        label: "Full Pipeline All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup ./scripts/youtube_pipeline.sh > logs/youtube_overnight.log 2>&1 &",
      },
      {
        label: "Scrape Only",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/scrape_youtube.py",
      },
      {
        label: "Clean Only",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/clean_transcripts.py",
      },
      {
        label: "Whisper Only",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/whisper_transcribe.py",
      },
      {
        label: "Ingest Only",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/ingest.py",
      },
      {
        label: "Monitor",
        command:
          "tail -f /Users/alexwhitley/Desktop/rhemata/logs/youtube_overnight.log",
      },
    ],
  },
  {
    id: "precept-greek",
    name: "Precept Austin \u2014 Greek Word Studies",
    group: "Pipelines",
    status: "Partial",
    sourceKind: "word_study",
    description:
      "Scrape \u2192 Ingest \u2192 Generate Excerpts. 1,779 docs ingested. 66 excerpts remaining.",
    steps: [
      { label: "Scrape" },
      { label: "Ingest" },
      { label: "Generate Excerpts" },
    ],
    commands: [
      {
        label: "Scrape",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scrape_preceptaustin.py --language greek --fetch",
      },
      {
        label: "Scrape Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scrape_preceptaustin.py --language greek --test",
      },
      {
        label: "Ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 ingest_preceptaustin.py --language greek > logs/precept_greek.log 2>&1 &",
      },
      {
        label: "Generate Excerpts All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/generate_excerpts.py --time-limit 480 > logs/excerpts_overnight.log 2>&1 &",
      },
      {
        label: "Generate Excerpts 2 Hour",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/generate_excerpts.py --time-limit 120 > logs/excerpts_2hr.log 2>&1 &",
      },
      {
        label: "Generate Excerpts Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/generate_excerpts.py --test",
      },
      {
        label: "Monitor",
        command:
          "tail -f /Users/alexwhitley/Desktop/rhemata/logs/excerpts_overnight.log",
      },
    ],
  },
  {
    id: "precept-hebrew",
    name: "Hebrew Word Studies",
    group: "Pipelines",
    status: "Not Started",
    sourceKind: "word_study",
    extraFilter: "title ILIKE '%hebrew%'",
    description:
      "Scrape Precept Austin Hebrew pages \u2192 Ingest \u2192 Generate Excerpts.",
    steps: [
      { label: "Scrape" },
      { label: "Ingest" },
      { label: "Generate Excerpts" },
    ],
    commands: [
      {
        label: "Scrape All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scrape_preceptaustin.py --language hebrew --fetch > logs/hebrew_scrape.log 2>&1 &",
      },
      {
        label: "Scrape Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scrape_preceptaustin.py --language hebrew --test",
      },
      {
        label: "Ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 ingest_preceptaustin.py --language hebrew > logs/hebrew_ingest.log 2>&1 &",
      },
      {
        label: "Generate Excerpts All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/generate_excerpts.py --time-limit 480 > logs/excerpts_overnight.log 2>&1 &",
      },
      {
        label: "Monitor",
        command:
          "tail -f /Users/alexwhitley/Desktop/rhemata/logs/hebrew_scrape.log",
      },
    ],
  },

  // ── Sermons & Transcripts ──
  {
    id: "derek-prince",
    name: "Derek Prince Sermons",
    group: "Sermons & Transcripts",
    status: "Complete",
    sourceKind: "sermon_transcript",
    extraFilter:
      "author ILIKE '%derek prince%' OR source_name ILIKE '%derek prince%'",
    description: "493 sermons scraped from derekprince.com and ingested.",
    commands: [
      {
        label: "Scrape",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/scrape_derek_prince.py",
      },
      {
        label: "Ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/ingest.py",
      },
      {
        label: "Monitor",
        command:
          "tail -f /Users/alexwhitley/Desktop/rhemata/logs/derek_prince_scrape.log",
      },
    ],
  },

  // ── Commentaries ──
  {
    id: "helloao-henry",
    name: "HelloAO \u2014 Matthew Henry",
    group: "Commentaries",
    status: "Complete",
    sourceKind: "commentary",
    extraFilter: "author ILIKE '%matthew henry%'",
    description:
      "Full Matthew Henry commentary \u2014 66 books ingested via HelloAO Bible API.",
    commands: [
      {
        label: "Ingest All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/ingest_helloao.py --commentary matthew-henry > logs/helloao_henry.log 2>&1 &",
      },
      {
        label: "Ingest Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/ingest_helloao.py --commentary matthew-henry --test",
      },
      {
        label: "Monitor",
        command:
          "tail -f /Users/alexwhitley/Desktop/rhemata/logs/helloao_henry.log",
      },
    ],
  },
  {
    id: "helloao-clarke",
    name: "HelloAO \u2014 Adam Clarke",
    group: "Commentaries",
    status: "Complete",
    sourceKind: "commentary",
    extraFilter: "author ILIKE '%adam clarke%'",
    description:
      "Full Adam Clarke commentary \u2014 66 books ingested via HelloAO Bible API.",
    commands: [
      {
        label: "Ingest All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/ingest_helloao.py --commentary adam-clarke > logs/helloao_clarke.log 2>&1 &",
      },
      {
        label: "Ingest Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/ingest_helloao.py --commentary adam-clarke --test",
      },
      {
        label: "Monitor",
        command:
          "tail -f /Users/alexwhitley/Desktop/rhemata/logs/helloao_clarke.log",
      },
    ],
  },
  {
    id: "helloao-jfb",
    name: "HelloAO \u2014 Jamieson-Fausset-Brown",
    group: "Commentaries",
    status: "Complete",
    sourceKind: "commentary",
    extraFilter: "author ILIKE '%jamieson%'",
    description:
      "Full JFB commentary \u2014 66 books ingested via HelloAO Bible API.",
    commands: [
      {
        label: "Ingest All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/ingest_helloao.py --commentary jamieson > logs/helloao_jfb.log 2>&1 &",
      },
      {
        label: "Ingest Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/ingest_helloao.py --commentary jamieson --test",
      },
      {
        label: "Monitor",
        command:
          "tail -f /Users/alexwhitley/Desktop/rhemata/logs/helloao_jfb.log",
      },
    ],
  },
  {
    id: "historicalchristianfaith",
    name: "HistoricalChristianFaith Commentaries",
    group: "Commentaries",
    status: "Not Started",
    sourceKind: "commentary",
    extraFilter:
      "source_name ILIKE '%historicalchristianfaith%' OR source_name ILIKE '%historical christian%'",
    description:
      "325 church fathers. SQLite DB at /tmp/commentaries-db/data.out. Not yet run.",
    commands: [
      {
        label: "Ingest All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/ingest_commentaries.py > logs/commentaries_overnight.log 2>&1 &",
      },
      {
        label: "Ingest 2 Hour",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/ingest_commentaries.py > logs/commentaries_2hr.log 2>&1 &",
      },
      {
        label: "Dry Run",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/ingest_commentaries.py --dry-run",
      },
      {
        label: 'Single Father Test',
        command:
          'cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/ingest_commentaries.py --father "Augustine"',
      },
      {
        label: "Monitor",
        command:
          "tail -f /Users/alexwhitley/Desktop/rhemata/logs/commentaries_overnight.log",
      },
    ],
  },

  // ── Public Domain Books ──
  {
    id: "public-domain-books",
    name: "Public Domain Books (CCEL + Archive.org)",
    group: "Public Domain Books",
    status: "Complete",
    sourceKind: "book",
    description:
      "56 titles across 27 authors downloaded and ingested via ingest.py.",
    bookList: [
      {
        author: "Andrew Murray",
        titles: [
          "With Christ in the School of Prayer",
          "The Deeper Christian Life",
          "New Life",
          "Waiting on God",
        ],
      },
      {
        author: "E.M. Bounds",
        titles: [
          "Power Through Prayer",
          "The Weapon of Prayer",
          "Prayer and Praying Men",
          "The Necessity of Prayer",
          "The Essentials of Prayer",
          "The Purpose in Prayer",
          "The Reality of Prayer",
        ],
      },
      {
        author: "R.A. Torrey",
        titles: [
          "The Person and Work of the Holy Spirit",
          "How to Pray",
        ],
      },
      {
        author: "Charles Finney",
        titles: [
          "Power from on High",
          "Lectures on Revivals",
          "Lectures to Professing Christians",
        ],
      },
      { author: "Abraham Kuyper", titles: ["The Work of the Holy Spirit"] },
      {
        author: "John Owen",
        titles: ["Pneumatologia (The Holy Spirit)"],
      },
      {
        author: "F.B. Meyer",
        titles: ["The Secret of Guidance", "The Way into the Holiest"],
      },
      {
        author: "S.D. Gordon",
        titles: ["Quiet Talks on Prayer", "Quiet Talks on Power"],
      },
      {
        author: "Jonathan Edwards",
        titles: ["Religious Affections", "Works Vol. 1", "Works Vol. 2"],
      },
      { author: "John Wesley", titles: ["Sermons", "Journal"] },
      { author: "A.B. Bruce", titles: ["The Training of the Twelve"] },
      { author: "J.C. Ryle", titles: ["Holiness"] },
      { author: "Horace Bushnell", titles: ["Christian Nurture"] },
      {
        author: "Brother Lawrence",
        titles: ["The Practice of the Presence of God"],
      },
      { author: "A.B. Simpson", titles: ["The Gospel of Healing"] },
      { author: "Unknown", titles: ["The Kneeling Christian"] },
      {
        author: "Smith Wigglesworth",
        titles: ["Ever Increasing Faith"],
      },
      {
        author: "Jessie Penn-Lewis",
        titles: ["War on the Saints", "Warfare with Satan"],
      },
      { author: "F.F. Bosworth", titles: ["Christ the Healer"] },
      {
        author: "George M\u00fcller",
        titles: ["Autobiography", "How God Answers Prayer"],
      },
      { author: "Phoebe Palmer", titles: ["The Way of Holiness"] },
      {
        author: "A.J. Gordon",
        titles: ["The Ministry of the Spirit", "The Twofold Life"],
      },
      {
        author: "Catherine Booth",
        titles: ["Aggressive Christianity"],
      },
      {
        author: "William Booth",
        titles: ["In Darkest England", "Salvation Soldiery"],
      },
      {
        author: "Hannah Whitall Smith",
        titles: ["Everyday Religion", "The God of All Comfort"],
      },
      {
        author: "A.W. Pink",
        titles: [
          "The Attributes of God",
          "The Sovereignty of God",
          "Profiting from the Word",
        ],
      },
      {
        author: "J.R. Miller",
        titles: [
          "The Marriage Altar",
          "Weekday Religion",
          "Personal Friendships of Jesus",
        ],
      },
      {
        author: "Maria Woodworth-Etter",
        titles: ["Acts of the Holy Ghost"],
      },
      { author: "John G. Lake", titles: ["Adventures in God"] },
      { author: "R.C. Horner", titles: ["Pentecost"] },
    ],
    commands: [
      {
        label: "Download",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/download_corpus_batch3.py",
      },
      {
        label: "Download Fixes Only",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/download_corpus_batch3.py --fixes",
      },
      {
        label: "Ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/ingest.py",
      },
    ],
  },

  // ── Lexicons & Reference ──
  {
    id: "lexicon-tbesg",
    name: "Lexicon \u2014 TBESG (Greek NT)",
    group: "Lexicons & Reference",
    status: "Complete",
    sourceKind: "lexicon",
    extraFilter: "source_name ILIKE '%TBESG%' OR title ILIKE '%TBESG%'",
    description: "Abbott-Smith Greek NT lexicon. 11,034 chunks.",
    commands: [
      {
        label: "Ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_lexicon.py --lexicon TBESG",
      },
      {
        label: "Delete + Re-ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_lexicon.py --lexicon TBESG --delete",
      },
      {
        label: "Sample Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_lexicon.py --lexicon TBESG --sample 10",
      },
    ],
  },
  {
    id: "lexicon-tbesh",
    name: "Lexicon \u2014 TBESH (Hebrew OT)",
    group: "Lexicons & Reference",
    status: "Complete",
    sourceKind: "lexicon",
    extraFilter: "source_name ILIKE '%TBESH%' OR title ILIKE '%TBESH%'",
    description: "STEPBible Hebrew OT lexicon. 10,258 chunks.",
    commands: [
      {
        label: "Ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_lexicon.py --lexicon TBESH",
      },
      {
        label: "Delete + Re-ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_lexicon.py --lexicon TBESH --delete",
      },
      {
        label: "Sample Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_lexicon.py --lexicon TBESH --sample 10",
      },
    ],
  },
  {
    id: "lexicon-tflsj",
    name: "Lexicon \u2014 TFLSJ (Liddell-Scott)",
    group: "Lexicons & Reference",
    status: "Complete",
    sourceKind: "lexicon",
    extraFilter: "source_name ILIKE '%TFLSJ%' OR title ILIKE '%TFLSJ%'",
    description: "Liddell-Scott-Jones Greek lexicon. 15,767 chunks.",
    commands: [
      {
        label: "Ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_lexicon.py --lexicon TFLSJ",
      },
      {
        label: "Delete + Re-ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_lexicon.py --lexicon TFLSJ --delete",
      },
      {
        label: "Sample Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_lexicon.py --lexicon TFLSJ --sample 10",
      },
    ],
  },
  {
    id: "bible-verses",
    name: "Bible Verses \u2014 WEB",
    group: "Lexicons & Reference",
    status: "Complete",
    specialTable: "verses",
    description: "World English Bible. 31,098 verses across 66 books.",
    commands: [
      {
        label: "Ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_bible.py",
      },
      {
        label: "Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_bible.py --test",
      },
    ],
  },
  {
    id: "interlinear-tagnt",
    name: "Interlinear \u2014 TAGNT",
    group: "Lexicons & Reference",
    status: "Complete",
    specialTable: "interlinear_words",
    description: "Greek NT interlinear word data. 142,096 rows.",
    commands: [
      {
        label: "Ingest",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_interlinear.py",
      },
      {
        label: "Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_interlinear.py --test",
      },
      {
        label: "Single Book",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 ingest_interlinear.py --book JHN",
      },
    ],
  },
  {
    id: "word-study-excerpts",
    name: "Word Study Excerpts",
    group: "Lexicons & Reference",
    status: "Partial",
    specialTable: "excerpts",
    specialWhere: "excerpt_type=eq.word_study_article",
    description:
      "AI-generated word study articles from Precept Austin chunks. 1,713/1,779 complete.",
    progressTarget: 1779,
    commands: [
      {
        label: "All Night",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/generate_excerpts.py --time-limit 480 > logs/excerpts_overnight.log 2>&1 &",
      },
      {
        label: "2 Hour",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && nohup python3 scripts/generate_excerpts.py --time-limit 120 > logs/excerpts_2hr.log 2>&1 &",
      },
      {
        label: "Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/generate_excerpts.py --test",
      },
      {
        label: "Quality Test",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/generate_excerpts.py --test-quality",
      },
      {
        label: "Monitor",
        command:
          "tail -f /Users/alexwhitley/Desktop/rhemata/logs/excerpts_overnight.log",
      },
    ],
  },

  // ── Maintenance ──
  {
    id: "bible-refs-backfill",
    name: "Bible Refs Backfill",
    group: "Maintenance",
    status: "Complete",
    isMaintenance: true,
    description:
      "Backfill bible_references on all documents. Re-run for docs ingested before auto-population.",
    commands: [
      {
        label: "Run",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 extract_bible_refs.py",
      },
      {
        label: "Dry Run",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 extract_bible_refs.py --dry-run",
      },
      {
        label: "Force Re-process All",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 extract_bible_refs.py --force",
      },
    ],
  },
  {
    id: "tag-backfill-magazine",
    name: "Tag Backfill \u2014 Magazine",
    group: "Maintenance",
    status: "Complete",
    isMaintenance: true,
    description:
      "Re-tag all magazine articles via Groq. Overwrites existing tags.",
    commands: [
      {
        label: "Run",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/tag_existing_articles.py",
      },
    ],
  },
  {
    id: "tag-backfill-sermons",
    name: "Tag Backfill \u2014 Sermons & Transcripts",
    group: "Maintenance",
    status: "Complete",
    isMaintenance: true,
    description:
      "Re-tag all sermon/transcript/paper documents via Groq. Overwrites existing tags.",
    commands: [
      {
        label: "Run",
        command:
          "cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/tag_sermons_transcripts.py",
      },
    ],
  },
];
