import type { CorpusCard, FutureTarget } from "./corpus-types";

// Single source of truth for the repo path these commands assume when pasted
// into a terminal. Update this one line if the repo ever moves.
const REPO_ROOT = "/Users/alexwhitley/rhemata";

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
      "3-pass extraction (Gemini → Groq → QA) then ingest. ~300 issues pending.",
    steps: [
      { label: "Extract" },
      { label: "Manual Review" },
      { label: "Ingest" },
    ],
    commands: [
      {
        label: "Extract All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/extract_magazine.py --time-limit 480 > logs/magazine_overnight.log 2>&1 &`,
      },
      {
        label: "Extract 2 Hour",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/extract_magazine.py --time-limit 120 > logs/magazine_2hr.log 2>&1 &`,
      },
      {
        label: "Extract Test",
        command:
          `cd ${REPO_ROOT} && python3 scripts/extract_magazine.py --max-issues 1`,
      },
      {
        label: "Ingest All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/ingest_magazine.py > logs/ingest_magazine_overnight.log 2>&1 &`,
      },
      {
        label: "Ingest Test",
        command:
          `cd ${REPO_ROOT} && python3 scripts/ingest_magazine.py`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/magazine_overnight.log`,
      },
    ],
  },
  {
    id: "youtube-bevere",
    name: "YouTube — John Bevere TV",
    group: "Pipelines",
    status: "Ongoing",
    sourceKind: "sermon_transcript",
    extraFilter:
      "url ILIKE '%youtube%' AND (author ILIKE '%bevere%' OR source_name ILIKE '%bevere%')",
    description:
      "Scrape → Clean → Whisper → Ingest. Max 10 per run. Never complete.",
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
          `cd ${REPO_ROOT} && nohup ./scripts/youtube_pipeline.sh > logs/youtube_overnight.log 2>&1 &`,
      },
      {
        label: "Scrape Only",
        command:
          `cd ${REPO_ROOT} && python3 scripts/scrape_youtube.py`,
      },
      {
        label: "Clean Only",
        command:
          `cd ${REPO_ROOT} && python3 scripts/clean_transcripts.py`,
      },
      {
        label: "Whisper Only",
        command:
          `cd ${REPO_ROOT} && python3 scripts/whisper_transcribe.py`,
      },
      {
        label: "Ingest Only",
        command:
          `cd ${REPO_ROOT} && python3 scripts/ingest.py`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/youtube_overnight.log`,
      },
    ],
  },
  {
    id: "precept-greek",
    name: "Precept Austin — Greek Word Studies",
    group: "Pipelines",
    status: "Partial",
    sourceKind: "word_study",
    notFilter: [
      { col: "source_name", val: "%hebrew%" },
      { col: "title", val: "%hebrew%" },
    ],
    description:
      "Scrape → Ingest → Generate Excerpts. Greek word studies from Precept Austin.",
    steps: [
      { label: "Scrape" },
      { label: "Ingest" },
      { label: "Generate Excerpts" },
    ],
    commands: [
      {
        label: "Scrape",
        command:
          `cd ${REPO_ROOT} && python3 scrape_preceptaustin.py --language greek --fetch`,
      },
      {
        label: "Scrape Test",
        command:
          `cd ${REPO_ROOT} && python3 scrape_preceptaustin.py --language greek --test`,
      },
      {
        label: "Ingest",
        command:
          `cd ${REPO_ROOT} && nohup python3 ingest_preceptaustin.py --language greek > logs/precept_greek.log 2>&1 &`,
      },
      {
        label: "Generate Excerpts All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/generate_excerpts.py --time-limit 480 > logs/excerpts_overnight.log 2>&1 &`,
      },
      {
        label: "Generate Excerpts 2 Hour",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/generate_excerpts.py --time-limit 120 > logs/excerpts_2hr.log 2>&1 &`,
      },
      {
        label: "Generate Excerpts Test",
        command:
          `cd ${REPO_ROOT} && python3 scripts/generate_excerpts.py --test`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/excerpts_overnight.log`,
      },
    ],
  },
  {
    id: "precept-hebrew",
    name: "Hebrew Word Studies",
    group: "Pipelines",
    status: "Not Started",
    sourceKind: "word_study",
    // TODO: confirm filter once Hebrew ingestion runs
    extraFilter: "source_name ILIKE '%hebrew%' OR title ILIKE '%hebrew%'",
    description:
      "Scrape Precept Austin Hebrew pages → Ingest → Generate Excerpts.",
    steps: [
      { label: "Scrape" },
      { label: "Ingest" },
      { label: "Generate Excerpts" },
    ],
    commands: [
      {
        label: "Scrape All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scrape_preceptaustin.py --language hebrew --fetch > logs/hebrew_scrape.log 2>&1 &`,
      },
      {
        label: "Scrape Test",
        command:
          `cd ${REPO_ROOT} && python3 scrape_preceptaustin.py --language hebrew --test`,
      },
      {
        label: "Ingest",
        command:
          `cd ${REPO_ROOT} && nohup python3 ingest_preceptaustin.py --language hebrew > logs/hebrew_ingest.log 2>&1 &`,
      },
      {
        label: "Generate Excerpts All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/generate_excerpts.py --time-limit 480 > logs/excerpts_overnight.log 2>&1 &`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/hebrew_scrape.log`,
      },
    ],
  },
  {
    id: "individual-videos",
    name: "Individual Videos",
    group: "Pipelines",
    status: "Ongoing",
    sourceKind: "sermon_transcript",
    extraFilter: "source_name ILIKE '%Individual Videos%'",
    description:
      "One-off YouTube videos from various speakers. yt-dlp captions → Whisper fallback → Groq clean → ingest.",
    steps: [
      { label: "Captions / Whisper" },
      { label: "Clean" },
      { label: "Ingest" },
    ],
    commands: [
      {
        label: "Run Pipeline",
        command:
          `cd ${REPO_ROOT} && python3 scripts/scrape_individual_videos.py`,
      },
      {
        label: "Run All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/scrape_individual_videos.py > logs/individual_videos.log 2>&1 &`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/individual_videos.log`,
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
    description: "Scraped from derekprince.com and ingested via ingest.py.",
    commands: [
      {
        label: "Scrape",
        command:
          `cd ${REPO_ROOT} && python3 scripts/scrape_derek_prince.py`,
      },
      {
        label: "Ingest",
        command:
          `cd ${REPO_ROOT} && python3 scripts/ingest.py`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/derek_prince_scrape.log`,
      },
    ],
  },

  // ── Commentaries ──
  {
    id: "helloao-henry",
    name: "HelloAO — Matthew Henry",
    group: "Commentaries",
    status: "Complete",
    sourceKind: "commentary",
    extraFilter: "author ILIKE '%matthew henry%'",
    description: "Matthew Henry commentary ingested via HelloAO Bible API.",
    commands: [
      {
        label: "Ingest All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/ingest_helloao.py --commentary matthew-henry > logs/helloao_henry.log 2>&1 &`,
      },
      {
        label: "Ingest Test",
        command:
          `cd ${REPO_ROOT} && python3 scripts/ingest_helloao.py --commentary matthew-henry --test`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/helloao_henry.log`,
      },
    ],
  },
  {
    id: "helloao-clarke",
    name: "HelloAO — Adam Clarke",
    group: "Commentaries",
    status: "Complete",
    sourceKind: "commentary",
    extraFilter: "author ILIKE '%adam clarke%'",
    description: "Adam Clarke commentary ingested via HelloAO Bible API.",
    commands: [
      {
        label: "Ingest All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/ingest_helloao.py --commentary adam-clarke > logs/helloao_clarke.log 2>&1 &`,
      },
      {
        label: "Ingest Test",
        command:
          `cd ${REPO_ROOT} && python3 scripts/ingest_helloao.py --commentary adam-clarke --test`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/helloao_clarke.log`,
      },
    ],
  },
  {
    id: "helloao-jfb",
    name: "HelloAO — Jamieson-Fausset-Brown",
    group: "Commentaries",
    status: "Complete",
    sourceKind: "commentary",
    extraFilter: "author ILIKE '%jamieson%'",
    description:
      "Jamieson-Fausset-Brown commentary ingested via HelloAO Bible API.",
    commands: [
      {
        label: "Ingest All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/ingest_helloao.py --commentary jamieson > logs/helloao_jfb.log 2>&1 &`,
      },
      {
        label: "Ingest Test",
        command:
          `cd ${REPO_ROOT} && python3 scripts/ingest_helloao.py --commentary jamieson --test`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/helloao_jfb.log`,
      },
    ],
  },
  {
    id: "historicalchristianfaith",
    name: "HistoricalChristianFaith Commentaries",
    group: "Commentaries",
    status: "Complete",
    sourceKind: "commentary",
    extraFilter:
      "source_name ILIKE '%historicalchristianfaith%' OR source_name ILIKE '%historical christian%'",
    description:
      "Church fathers from HistoricalChristianFaith.com. Document count shown.",
    commands: [
      {
        label: "Ingest All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/ingest_commentaries.py > logs/commentaries_overnight.log 2>&1 &`,
      },
      {
        label: "Ingest 2 Hour",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/ingest_commentaries.py > logs/commentaries_2hr.log 2>&1 &`,
      },
      {
        label: "Dry Run",
        command:
          `cd ${REPO_ROOT} && python3 scripts/ingest_commentaries.py --dry-run`,
      },
      {
        label: "Single Father Test",
        command:
          `cd ${REPO_ROOT} && python3 scripts/ingest_commentaries.py --father "Augustine"`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/commentaries_overnight.log`,
      },
    ],
  },

  // ── Public Domain Books ──
  {
    id: "public-domain-books",
    name: "Public Domain Books (CCEL + Archive.org)",
    group: "Public Domain Books",
    status: "Complete",
    sourceType: "book",
    description:
      "49 titles across 27 authors downloaded and ingested via ingest.py.",
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
        titles: ["The Person and Work of the Holy Spirit", "How to Pray"],
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
      { author: "John Owen", titles: ["Pneumatologia (The Holy Spirit)"] },
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
      { author: "Smith Wigglesworth", titles: ["Ever Increasing Faith"] },
      {
        author: "Jessie Penn-Lewis",
        titles: ["War on the Saints", "Warfare with Satan"],
      },
      { author: "F.F. Bosworth", titles: ["Christ the Healer"] },
      {
        author: "George Müller",
        titles: ["Autobiography", "How God Answers Prayer"],
      },
      { author: "Phoebe Palmer", titles: ["The Way of Holiness"] },
      {
        author: "A.J. Gordon",
        titles: ["The Ministry of the Spirit", "The Twofold Life"],
      },
      { author: "Catherine Booth", titles: ["Aggressive Christianity"] },
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
          `cd ${REPO_ROOT} && python3 scripts/download_corpus_batch3.py`,
      },
      {
        label: "Download Fixes Only",
        command:
          `cd ${REPO_ROOT} && python3 scripts/download_corpus_batch3.py --fixes`,
      },
      {
        label: "Ingest",
        command:
          `cd ${REPO_ROOT} && python3 scripts/ingest.py`,
      },
    ],
  },

  // ── Lexicons & Reference ──
  {
    id: "lexicon-tbesg",
    name: "Lexicon — TBESG (Greek NT)",
    group: "Lexicons & Reference",
    status: "Complete",
    sourceKind: "lexicon",
    extraFilter: "source_name ILIKE '%TBESG%' OR title ILIKE '%TBESG%'",
    countChunks: true,
    countLabel: "chunks",
    description: "Abbott-Smith Greek NT lexicon.",
    commands: [
      {
        label: "Ingest",
        command:
          `cd ${REPO_ROOT} && python3 ingest_lexicon.py --lexicon TBESG`,
      },
      {
        label: "Delete + Re-ingest",
        command:
          `cd ${REPO_ROOT} && python3 ingest_lexicon.py --lexicon TBESG --delete`,
      },
      {
        label: "Sample Test",
        command:
          `cd ${REPO_ROOT} && python3 ingest_lexicon.py --lexicon TBESG --sample 10`,
      },
    ],
  },
  {
    id: "lexicon-tbesh",
    name: "Lexicon — TBESH (Hebrew OT)",
    group: "Lexicons & Reference",
    status: "Complete",
    sourceKind: "lexicon",
    extraFilter: "source_name ILIKE '%TBESH%' OR title ILIKE '%TBESH%'",
    countChunks: true,
    countLabel: "chunks",
    description: "STEPBible Hebrew OT lexicon.",
    commands: [
      {
        label: "Ingest",
        command:
          `cd ${REPO_ROOT} && python3 ingest_lexicon.py --lexicon TBESH`,
      },
      {
        label: "Delete + Re-ingest",
        command:
          `cd ${REPO_ROOT} && python3 ingest_lexicon.py --lexicon TBESH --delete`,
      },
      {
        label: "Sample Test",
        command:
          `cd ${REPO_ROOT} && python3 ingest_lexicon.py --lexicon TBESH --sample 10`,
      },
    ],
  },
  {
    id: "lexicon-tflsj",
    name: "Lexicon — TFLSJ (Liddell-Scott)",
    group: "Lexicons & Reference",
    status: "Complete",
    sourceKind: "lexicon",
    extraFilter: "source_name ILIKE '%TFLSJ%' OR title ILIKE '%TFLSJ%'",
    countChunks: true,
    countLabel: "chunks",
    description: "Liddell-Scott-Jones Greek lexicon.",
    commands: [
      {
        label: "Ingest",
        command:
          `cd ${REPO_ROOT} && python3 ingest_lexicon.py --lexicon TFLSJ`,
      },
      {
        label: "Delete + Re-ingest",
        command:
          `cd ${REPO_ROOT} && python3 ingest_lexicon.py --lexicon TFLSJ --delete`,
      },
      {
        label: "Sample Test",
        command:
          `cd ${REPO_ROOT} && python3 ingest_lexicon.py --lexicon TFLSJ --sample 10`,
      },
    ],
  },
  {
    id: "bible-verses",
    name: "Bible Verses — WEB",
    group: "Lexicons & Reference",
    status: "Complete",
    specialTable: "verses",
    description: "World English Bible. 31,098 verses across 66 books.",
    commands: [
      {
        label: "Ingest",
        command:
          `cd ${REPO_ROOT} && python3 ingest_bible.py`,
      },
      {
        label: "Test",
        command:
          `cd ${REPO_ROOT} && python3 ingest_bible.py --test`,
      },
    ],
  },
  {
    id: "interlinear-tagnt",
    name: "Interlinear — TAGNT (Greek NT)",
    group: "Lexicons & Reference",
    status: "Complete",
    specialTable: "interlinear_words",
    specialWhere: "language=eq.greek",
    description:
      "Greek NT interlinear word data from STEPBible TAGNT. Full NT coverage.",
    commands: [
      {
        label: "Ingest",
        command:
          `cd ${REPO_ROOT} && python3 ingest_interlinear.py`,
      },
      {
        label: "Test",
        command:
          `cd ${REPO_ROOT} && python3 ingest_interlinear.py --test`,
      },
      {
        label: "Single Book",
        command:
          `cd ${REPO_ROOT} && python3 ingest_interlinear.py --book JHN`,
      },
    ],
  },
  {
    id: "interlinear-tahot",
    name: "Interlinear — TAHOT (Hebrew OT)",
    group: "Lexicons & Reference",
    status: "Complete",
    specialTable: "interlinear_words",
    specialWhere: "language=eq.hebrew",
    description:
      "Hebrew OT interlinear word data from STEPBible TAHOT. Full OT coverage.",
    commands: [
      {
        label: "Ingest",
        command:
          `cd ${REPO_ROOT} && python3 ingest_tahot.py`,
      },
      {
        label: "Test",
        command:
          `cd ${REPO_ROOT} && python3 ingest_tahot.py --test`,
      },
      {
        label: "Single Book",
        command:
          `cd ${REPO_ROOT} && python3 ingest_tahot.py --book GEN`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/tahot_ingest.log`,
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
      "AI-generated word study articles from Precept Austin chunks. Nearly complete.",
    progressTarget: 2175,
    commands: [
      {
        label: "All Night",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/generate_excerpts.py --time-limit 480 > logs/excerpts_overnight.log 2>&1 &`,
      },
      {
        label: "2 Hour",
        command:
          `cd ${REPO_ROOT} && nohup python3 scripts/generate_excerpts.py --time-limit 120 > logs/excerpts_2hr.log 2>&1 &`,
      },
      {
        label: "Test",
        command:
          `cd ${REPO_ROOT} && python3 scripts/generate_excerpts.py --test`,
      },
      {
        label: "Quality Test",
        command:
          `cd ${REPO_ROOT} && python3 scripts/generate_excerpts.py --test-quality`,
      },
      {
        label: "Monitor",
        command:
          `tail -f ${REPO_ROOT}/logs/excerpts_overnight.log`,
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
          `cd ${REPO_ROOT} && python3 extract_bible_refs.py`,
      },
      {
        label: "Dry Run",
        command:
          `cd ${REPO_ROOT} && python3 extract_bible_refs.py --dry-run`,
      },
      {
        label: "Force Re-process All",
        command:
          `cd ${REPO_ROOT} && python3 extract_bible_refs.py --force`,
      },
    ],
  },
  {
    id: "tag-backfill-magazine",
    name: "Tag Backfill — Magazine",
    group: "Maintenance",
    status: "Complete",
    isMaintenance: true,
    description:
      "Re-tag all magazine articles via Groq. Overwrites existing tags.",
    commands: [
      {
        label: "Run",
        command:
          `cd ${REPO_ROOT} && python3 scripts/tag_existing_articles.py`,
      },
    ],
  },
  {
    id: "tag-backfill-sermons",
    name: "Tag Backfill — Sermons & Transcripts",
    group: "Maintenance",
    status: "Complete",
    isMaintenance: true,
    description:
      "Re-tag all sermon/transcript/paper documents via Groq. Overwrites existing tags.",
    commands: [
      {
        label: "Run",
        command:
          `cd ${REPO_ROOT} && python3 scripts/tag_sermons_transcripts.py`,
      },
    ],
  },
];

export const FUTURE_TARGETS: FutureTarget[] = [
  {
    id: "andrew-murray-extra",
    name: "Andrew Murray — Additional Titles",
    description:
      "More Andrew Murray works beyond the 4 already ingested. Available on olddeadguys.com and Internet Archive.",
    urls: [
      "https://www.olddeadguys.com/andrew-murray",
      "https://archive.org/search?query=andrew+murray&mediatype=texts",
    ],
  },
  {
    id: "azusa-apostolic-faith",
    name: "Azusa Street — Apostolic Faith Magazine",
    description:
      "13 issues of the original Apostolic Faith newsletter from the Azusa Street Revival (1906–1908). Primary source documents of the Pentecostal movement.",
    urls: ["https://place.asburyseminary.edu/apostolicfaith/"],
  },
  {
    id: "pentecostal-archives",
    name: "Consortium of Pentecostal Archives",
    description:
      "Digital archives from Pentecostal and charismatic institutions. Explore for freely downloadable primary source documents.",
    urls: ["https://www.pentecostalarchives.org"],
  },
  {
    id: "frank-bartleman",
    name: "Frank Bartleman — Azusa Street Writings",
    description:
      "Frank Bartleman’s firsthand accounts of the Azusa Street Revival. Multiple titles available on Internet Archive.",
    urls: [
      "https://archive.org/search?query=frank+bartleman&mediatype=texts",
    ],
  },
  {
    id: "stepbible-tipnr",
    name: "STEPBible — TIPNR (Proper Names)",
    description:
      "Every proper noun in the Bible with exhaustive references, family relationships, geolocation, and descriptions. CC BY 4.0.",
    urls: ["https://github.com/STEPBible/STEPBible-Data"],
  },
  {
    id: "stepbible-tahot-ref",
    name: "STEPBible — TAHOT (Hebrew OT) Additional Books",
    description:
      "Already ingested full OT. This card is for reference if re-ingestion or updates are needed.",
    urls: [
      "https://github.com/STEPBible/STEPBible-Data/tree/master/Translators%20Amalgamated%20OT%2BNT",
    ],
  },
];
