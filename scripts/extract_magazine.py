#!/usr/bin/env python3
"""
New Wine Magazine Extraction Pipeline (3-pass)

Pass 1: Vision extraction via Gemini Flash 2.0 (full issue, all pages)
Pass 2: Article segmentation via Groq Llama 3.3 70B
Pass 3: QA inspection via Groq Llama 3.3 70B

Input:  sources/magazine/01_to_extract/*.pdf
Output: sources/magazine/02_extracted/{issue_stem}/*.md
"""

import os
import re
import sys
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict

from google import genai
from groq import Groq
from pdf2image import convert_from_path
from openpyxl import Workbook, load_workbook
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# -- CONFIGURATION -----------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
TO_EXTRACT_DIR = ROOT / "sources" / "magazine" / "01_to_extract"
EXTRACTED_DIR = ROOT / "sources" / "magazine" / "02_extracted"
PDF_DONE_DIR = ROOT / "sources" / "magazine" / "05_archived"
TRACKER_PATH = ROOT / "sources" / "magazine" / "rhemata_tracker.xlsx"

GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "llama-3.3-70b-versatile"

MONTH_MAP = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}

VALID_TAGS = {
    "Baptism in the Spirit", "Speaking in Tongues", "Prophetic Ministry",
    "Word of Knowledge", "Word of Wisdom", "Discerning of Spirits",
    "Miracles and Signs", "The Nine Gifts", "Stirring Up Gifts",
    "Moving in the Spirit", "Fruit of the Spirit", "Fresh Anointing",
    "Filling of the Spirit", "Power for Service",
    "Hearing God's Voice", "Dreams and Visions", "Interpreting Your Dreams",
    "Encounters with God", "Divine Appointments", "Supernatural Peace",
    "Manifestations of God", "Intimacy with Jesus", "Atmosphere of Worship",
    "Spiritual Sight", "Knowing God's Heart", "Personal Revelation",
    "Walking in the Spirit", "Led by the Spirit",
    "Intercessory Prayer", "Authority of the Believer",
    "Tearing Down Strongholds", "Resisting the Enemy", "Victory in Christ",
    "Deliverance from Bondage", "Casting Out Demons", "Spiritual Weapons",
    "Breaking Negative Patterns", "Binding and Loosing", "Armor of God",
    "Warfare in Prayer", "Fasting and Prayer", "Protecting Your Mind",
    "Divine Healing", "Praying for the Sick", "Inner Healing",
    "Emotional Wholeness", "Healing of Memories", "Health and Vitality",
    "Overcoming Fear", "Freedom from Anxiety", "Restoration of Soul",
    "Physical Miracles", "The Will to Heal", "Faith for Healing",
    "God's Comfort", "Wholeness in Christ",
    "Biblical Leadership", "Fivefold Ministry", "Apostolic Oversight",
    "Prophetic Direction", "Pastoral Care", "Delegated Authority",
    "Spiritual Covering", "Accountability in Leadership",
    "Covenant Relationships", "Mentoring Relationships",
    "Leading with Integrity", "Servant Leadership", "Team Ministry",
    "Equipping the Saints", "Elders and Deacons",
    "Spiritual Maturity", "Walking with God", "Discipleship and Mentoring",
    "Accountability in Christ", "Knowing God's Will", "Character of Christ",
    "Honoring Biblical Authority", "Submission to God",
    "Faith and Perseverance", "Stewardship and Finances",
    "Spiritual Disciplines", "Dying to Self", "Holiness and Sanctification",
    "Body Ministry",
    "Kingdom of God", "Word and Spirit", "Biblical Authority",
    "The New Covenant", "The Lordship of Christ", "Grace and Mercy",
    "Salvation and Repentance", "End Times Prophecy", "The Rapture",
    "Second Coming", "The Trinity", "Blood of Jesus", "Heaven and Eternity",
    "Restoration of All Things",
    "Biblical Marriage", "Christian Parenting", "Family Life",
    "Relationship Restoration", "Communication in Marriage",
    "Raising Godly Children", "Singleness and Purity",
    "Friendship in Christ", "Honoring Your Parents", "Forgiving Others",
    "Love and Sacrifice", "Conflict Resolution", "The Christian Home",
}

# -- CLIENTS -----------------------------------------------------------------

_gemini_client = None
_groq_client = None


def get_gemini():
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _gemini_client


def get_groq():
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


# -- METADATA PARSING --------------------------------------------------------

def parse_issue_meta(filename: str) -> Dict[str, Optional[str]]:
    """Parse issue/year from filename like NewWineMagazine_Issue_02-1974.pdf"""
    match = re.search(r"Issue_(\d+)-(\d{4})", filename)
    if match:
        month_num = match.group(1)
        year = match.group(2)
        issue = f"{month_num}-{year}"
        month_name = MONTH_MAP.get(month_num, month_num)
        return {"issue": issue, "year": year, "month_num": month_num, "date": f"{month_name} {year}"}
    return {"issue": None, "year": None, "month_num": None, "date": None}


def slugify(text: str) -> str:
    """Convert title to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:60].rstrip("_")


# -- TRACKER -----------------------------------------------------------------

def init_tracker() -> None:
    if not TRACKER_PATH.exists():
        wb = Workbook()
        ws = wb.active
        ws.title = "Magazine Issues"
        ws.append([
            "Filename", "Issue", "Year", "Pages", "Pass1", "Pass2", "Pass3",
            "Articles", "Pass_Count", "Warn_Count", "Flag_Count", "Status",
        ])
        wb.save(str(TRACKER_PATH))
        wb.close()
        return
    EXPECTED_HEADERS = [
        "Filename", "Issue", "Year", "Pages", "Pass1", "Pass2", "Pass3",
        "Articles", "Pass_Count", "Warn_Count", "Flag_Count", "Status",
    ]
    wb = load_workbook(str(TRACKER_PATH))
    if "Extraction" not in wb.sheetnames:
        ws = wb.create_sheet("Extraction")
        ws.append(EXPECTED_HEADERS)
        wb.save(str(TRACKER_PATH))
    wb.close()


def update_tracker_row(filename: str, data: Dict) -> None:
    """Update or append a row in the tracker for the given filename."""
    wb = load_workbook(str(TRACKER_PATH))
    ws = wb["Extraction"]

    # Find existing row
    target_row = None
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=False), start=2):
        if row[0].value == filename:
            target_row = row_idx
            break

    col_map = {}
    for idx, cell in enumerate(ws[1], start=1):
        col_map[cell.value] = idx

    if target_row:
        for key, val in data.items():
            if key in col_map:
                ws.cell(row=target_row, column=col_map[key], value=val)
    else:
        row_data = [None] * len(col_map)
        row_data[col_map["Filename"] - 1] = filename
        for key, val in data.items():
            if key in col_map:
                row_data[col_map[key] - 1] = val
        ws.append(row_data)

    wb.save(str(TRACKER_PATH))
    wb.close()


# -- PASS 1: VISION EXTRACTION (Gemini Flash 2.0) ----------------------------

PASS1_PROMPT = """You are a faithful transcription assistant. Your only job is to \
read the text exactly as it appears on each page of this magazine scan.

Rules:
- Transcribe every word exactly as printed. Do not paraphrase, \
summarize, or add any text that is not on the page.
- Mark each page boundary with: === PAGE {page_start} === (use the page number provided)
- Skip these page types entirely (output nothing for them): \
cover page, back cover, full-page illustrations with no text, \
order forms, subscription cards, advertisement pages
- Include: article text, section headings, author names, pull quotes, \
sidebars, letters to editor, editorial, table of contents
- Preserve paragraph breaks with a blank line
- Do not add any commentary or notes"""

PASS1_BATCH_SIZE = 5


def pass1_extract(pdf_path: Path, issue_dir: Path) -> int:
    """Extract raw text from PDF via Gemini Vision in batches. Returns page count."""
    print(f"  PASS 1: Vision extraction via Gemini...")

    images = convert_from_path(str(pdf_path), dpi=200)
    page_count = len(images)
    print(f"  {page_count} pages converted at 200 DPI")

    client = get_gemini()
    all_text_parts = []

    for batch_start in range(0, page_count, PASS1_BATCH_SIZE):
        batch_end = min(batch_start + PASS1_BATCH_SIZE, page_count)
        batch_images = images[batch_start:batch_end]
        page_num_start = batch_start + 1
        page_num_end = batch_end

        print(f"  Batch: pages {page_num_start}-{page_num_end}...")

        prompt = PASS1_PROMPT.replace("{page_start}", str(page_num_start))
        prompt += (
            f"\n\nYou are processing pages {page_num_start} through {page_num_end}. "
            f"Number them === PAGE {page_num_start} === through === PAGE {page_num_end} ===."
        )

        content = [prompt] + list(batch_images)
        response = client.models.generate_content(model=GEMINI_MODEL, contents=content)
        all_text_parts.append(response.text)

    raw_text = "\n\n".join(all_text_parts)

    # Save raw transcription
    issue_dir.mkdir(parents=True, exist_ok=True)
    (issue_dir / "raw_text.txt").write_text(raw_text, encoding="utf-8")
    print(f"  Raw text saved ({len(raw_text)} chars)")

    return page_count


# -- PASS 2: ARTICLE SEGMENTATION (Groq Llama 3.3 70B) ----------------------

PASS2_TOC_SYSTEM = """You are an expert magazine editor. You will be given the full \
transcribed text of a New Wine Magazine issue and its table of contents.

Your job is to identify each article and return ONLY a metadata index. \
Do NOT include article body text.

Rules:
- Use the table of contents as ground truth - find exactly those articles
- Do not include: letters to editor, order forms, subscription info, \
staff boxes, ads, table of contents itself
- Exclude any article that is a Bible Study, Bible lesson, Scripture study, or study guide. \
These are reference materials not theological teaching articles. If an article title contains \
'Bible Study', 'Bible Lesson', or 'Study Guide' skip it entirely.
- Do include: main articles, editorial, forum sections
- Output as JSON array with this structure:
  [
    {"title": "Article Title", "author": "Author Name", "page_start": 4, "page_end": 10}
  ]
- page_start and page_end refer to the === PAGE N === markers in the text
- Return ONLY the JSON array, nothing else"""

PASS2_BODY_SYSTEM = """You are an expert magazine transcription editor. You will be \
given a section of raw transcribed magazine text that contains one specific article.

Your job is to extract and clean up ONLY the article specified, formatting it as markdown, \
and assign topic tags from the taxonomy below.

If this article is a Bible Study, Bible lesson, or study guide, \
return an empty JSON object: {} and do not extract it.

Rules:
- Extract the full article text for the specified title and author
- Do NOT include the article title or author name at the start — these are already in metadata
- Start the body text directly with the first paragraph of content
- Do not add, invent, or paraphrase any text
- Do not include text from other articles that may appear in the page range
- Format as markdown:
  - Section headings as ## H2
  - Any quoted scripture passages that are indented or set apart visually as > blockquote
  - Pull quotes as > *italic blockquote*
  - Normal paragraphs separated by blank lines
  - No H1 - that will be the title

After extracting the article body, assign 5-8 topic tags from the taxonomy below.

STRICT RULES for assigning tags:
- Only assign a tag if the article DIRECTLY teaches on that topic for at least one full paragraph
- Do NOT assign a tag for:
  - Passing mentions or single sentence references
  - Historical or biographical context
  - Tangential connections
  - Topics that are merely implied but not taught
- Ask yourself: 'Would a reader searching for this topic find substantial, helpful content on it \
in this article?' If no, do not assign the tag.
- It is better to assign 3 highly accurate tags than 8 loosely related ones
- Never assign a tag just because a word in the tag appears in the article
- You MUST only return tags from this exact list. Do not create new tags. Do not modify tag names. \
Copy them exactly.

TAXONOMY: Baptism in the Spirit, Speaking in Tongues, Prophetic Ministry, \
Word of Knowledge, Word of Wisdom, Discerning of Spirits, Miracles and Signs, \
The Nine Gifts, Stirring Up Gifts, Moving in the Spirit, Fruit of the Spirit, \
Fresh Anointing, Filling of the Spirit, Power for Service, Hearing God's Voice, \
Dreams and Visions, Interpreting Your Dreams, Encounters with God, Divine Appointments, \
Supernatural Peace, Manifestations of God, Intimacy with Jesus, Atmosphere of Worship, \
Spiritual Sight, Knowing God's Heart, Personal Revelation, Walking in the Spirit, \
Led by the Spirit, Intercessory Prayer, Authority of the Believer, \
Tearing Down Strongholds, Resisting the Enemy, Victory in Christ, \
Deliverance from Bondage, Casting Out Demons, Spiritual Weapons, \
Breaking Negative Patterns, Binding and Loosing, Armor of God, Warfare in Prayer, \
Fasting and Prayer, Protecting Your Mind, Divine Healing, Praying for the Sick, \
Inner Healing, Emotional Wholeness, Healing of Memories, Health and Vitality, \
Overcoming Fear, Freedom from Anxiety, Restoration of Soul, Physical Miracles, \
The Will to Heal, Faith for Healing, God's Comfort, Wholeness in Christ, \
Biblical Leadership, Fivefold Ministry, Apostolic Oversight, Prophetic Direction, \
Pastoral Care, Delegated Authority, Spiritual Covering, Accountability in Leadership, \
Covenant Relationships, Mentoring Relationships, Leading with Integrity, \
Servant Leadership, Team Ministry, Equipping the Saints, Elders and Deacons, \
Spiritual Maturity, Walking with God, Discipleship and Mentoring, \
Accountability in Christ, Knowing God's Will, Character of Christ, \
Honoring Biblical Authority, Submission to God, Faith and Perseverance, \
Stewardship and Finances, Spiritual Disciplines, Dying to Self, \
Holiness and Sanctification, Body Ministry, Kingdom of God, Word and Spirit, \
Biblical Authority, The New Covenant, The Lordship of Christ, Grace and Mercy, \
Salvation and Repentance, End Times Prophecy, The Rapture, Second Coming, \
The Trinity, Blood of Jesus, Heaven and Eternity, Restoration of All Things, \
Biblical Marriage, Christian Parenting, Family Life, Relationship Restoration, \
Communication in Marriage, Raising Godly Children, Singleness and Purity, \
Friendship in Christ, Honoring Your Parents, Forgiving Others, Love and Sacrifice, \
Conflict Resolution, The Christian Home

Return your response as JSON only:
{
  "topic_tags": ["Tag One", "Tag Two", ...],
  "body": "The full formatted article body text..."
}"""


def _extract_toc(raw_text: str) -> str:
    """Extract table of contents section from raw text."""
    # Look for PAGE 3 area where TOC usually lives
    toc_lines = []
    in_toc = False
    for line in raw_text.split("\n"):
        if "=== PAGE 3 ===" in line or "=== PAGE 2 ===" in line:
            in_toc = True
            continue
        if in_toc and line.startswith("=== PAGE"):
            break
        if in_toc:
            toc_lines.append(line)
    return "\n".join(toc_lines).strip() if toc_lines else "(No table of contents found)"


def _extract_page_range(raw_text: str, page_start: int, page_end: int) -> str:
    """Extract text between === PAGE page_start === and === PAGE page_end+1 ===."""
    lines = raw_text.split("\n")
    result = []
    capturing = False
    for line in lines:
        page_match = re.match(r"=== PAGE (\d+) ===", line)
        if page_match:
            page_num = int(page_match.group(1))
            if page_num >= page_start and page_num <= page_end:
                capturing = True
                continue
            elif page_num > page_end:
                break
        if capturing:
            result.append(line)
    return "\n".join(result).strip()


def _parse_groq_json(raw_response: str):
    """Parse JSON from Groq response, handling markdown code fences."""
    json_str = raw_response
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw_response, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()
    return json.loads(json_str)


def pass2_segment(issue_dir: Path, meta: Dict) -> int:
    """Segment raw text into individual article .md files. Returns article count."""
    print(f"  PASS 2: Article segmentation via Groq...")

    raw_text = (issue_dir / "raw_text.txt").read_text(encoding="utf-8")
    toc = _extract_toc(raw_text)

    # Step 1: Get article metadata index (small response, no body text)
    print(f"  Step 2a: Extracting article index from TOC...")
    toc_response = get_groq().chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": PASS2_TOC_SYSTEM},
            {"role": "user", "content": f"TABLE OF CONTENTS:\n{toc}\n\nFULL MAGAZINE TEXT:\n{raw_text}"},
        ],
    )

    toc_raw = (toc_response.choices[0].message.content or "").strip()
    articles_meta = _parse_groq_json(toc_raw)
    print(f"  Found {len(articles_meta)} articles in index")

    # Step 2: Extract each article body individually
    for idx, article in enumerate(articles_meta, start=1):
        title = article.get("title", "Untitled")
        author = article.get("author", "Unknown")
        page_start = article.get("page_start", 1)
        page_end = article.get("page_end", page_start)

        print(f"  Step 2b: Extracting [{idx}/{len(articles_meta)}] {title}...")

        # Get raw text for this article's page range
        page_text = _extract_page_range(raw_text, page_start, page_end)

        body_response = get_groq().chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": PASS2_BODY_SYSTEM},
                {"role": "user", "content": (
                    f"Extract the article titled \"{title}\" by {author} "
                    f"from the following magazine text (pages {page_start}-{page_end}):\n\n"
                    f"{page_text}"
                )},
            ],
        )

        body_raw = (body_response.choices[0].message.content or "").strip()

        # Parse JSON response for body + topic_tags
        try:
            body_json = _parse_groq_json(body_raw)
            body = body_json.get("body", "")
            topic_tags = body_json.get("topic_tags", [])
        except (json.JSONDecodeError, ValueError):
            # Fallback: treat entire response as body text, no tags
            body = body_raw
            topic_tags = []

        # Validate tags against taxonomy
        valid_tags = [t for t in topic_tags if t in VALID_TAGS]
        invalid_tags = [t for t in topic_tags if t not in VALID_TAGS]
        if invalid_tags:
            print(f"    Removed invalid tags: {invalid_tags}")
        topic_tags = valid_tags

        tags_str = ", ".join(topic_tags) if topic_tags else ""

        slug = slugify(title)
        filename = f"{idx:02d}_{slug}.md"

        frontmatter = (
            f"---\n"
            f"TITLE: {title}\n"
            f"AUTHOR: {author}\n"
            f"ISSUE: {meta.get('issue', '')}\n"
            f"DATE: {meta.get('date', '')}\n"
            f"PAGE_START: {page_start}\n"
            f"PAGE_END: {page_end}\n"
            f"SOURCE_TYPE: magazine_article\n"
            f"TOPIC_TAGS: {tags_str}\n"
            f"---\n\n"
            f"# {title}\n"
            f"*by {author}*\n\n"
            f"{body}"
        )

        (issue_dir / filename).write_text(frontmatter, encoding="utf-8")

    print(f"  {len(articles_meta)} articles segmented")
    return len(articles_meta)


# -- PASS 3: QA INSPECTION (Groq Llama 3.3 70B) -----------------------------

PASS3_SYSTEM = """You are a quality inspector for magazine article transcriptions.

Check this article for the following issues:
1. Does it start mid-sentence or mid-word? (truncation)
2. Does it end abruptly without a concluding sentence? (truncation)
3. Are there any duplicate sentences or paragraphs? (overlap)
4. Does the body text match the title and author? (mismatch)
5. Is the word count reasonable for a magazine article? (min 200 words)
6. Are there any obvious OCR errors or garbled text?

Respond with JSON only:
{
  "status": "PASS" or "WARN" or "FLAG",
  "issues": ["list of issues found, empty if none"],
  "confidence": 0.0 to 1.0,
  "word_count": number
}"""


def pass3_qa(issue_dir: Path) -> Dict[str, int]:
    """Run QA on each .md article file. Returns {pass, warn, flag} counts."""
    print(f"  PASS 3: QA inspection via Groq...")

    md_files = sorted(issue_dir.glob("*.md"))
    if not md_files:
        print(f"  No .md files found")
        return {"pass": 0, "warn": 0, "flag": 0}

    flagged_dir = issue_dir / "flagged"
    qa_results = []
    counts = {"pass": 0, "warn": 0, "flag": 0}

    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")

        try:
            response = get_groq().chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": PASS3_SYSTEM},
                    {"role": "user", "content": content},
                ],
            )
            raw = (response.choices[0].message.content or "").strip()
            # Parse JSON
            json_str = raw
            fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
            if fence_match:
                json_str = fence_match.group(1).strip()
            result = json.loads(json_str)
        except Exception as e:
            logger.warning("QA failed for %s: %s", md_path.name, e)
            result = {"status": "WARN", "issues": [f"QA parse error: {e}"], "confidence": 0.0, "word_count": 0}

        status = result.get("status", "WARN").upper()
        result["file"] = md_path.name

        if status == "FLAG":
            flagged_dir.mkdir(exist_ok=True)
            md_path.rename(flagged_dir / md_path.name)
            counts["flag"] += 1
        elif status == "WARN":
            # Prepend warning block to file
            issues_str = "\n".join(f"  - {i}" for i in result.get("issues", []))
            warning_block = f"<!-- QA WARNINGS:\n{issues_str}\n-->\n\n"
            md_path.write_text(warning_block + content, encoding="utf-8")
            counts["warn"] += 1
        else:
            counts["pass"] += 1

        qa_results.append(result)

    # Save QA report
    (issue_dir / "qa_report.json").write_text(
        json.dumps(qa_results, indent=2), encoding="utf-8"
    )

    print(f"  QA results: {counts['pass']} pass, {counts['warn']} warn, {counts['flag']} flag")
    return counts


# -- PROCESS SINGLE ISSUE ---------------------------------------------------

def process_issue(pdf_path: Path) -> str:
    """Run all 3 passes on a single PDF. Returns 'processed' or 'failed'."""
    filename = pdf_path.name
    issue_stem = pdf_path.stem
    meta = parse_issue_meta(filename)
    issue_dir = EXTRACTED_DIR / issue_stem

    print(f"\n{'='*60}")
    print(f"Processing: {filename}")
    print(f"  Issue: {meta.get('issue')}  Date: {meta.get('date')}")
    print(f"{'='*60}")

    init_tracker()

    try:
        # Pass 1: Vision extraction
        page_count = pass1_extract(pdf_path, issue_dir)
        update_tracker_row(filename, {
            "Issue": meta.get("issue"),
            "Year": meta.get("year"),
            "Pages": page_count,
            "Pass1": "complete",
            "Status": "pass1_done",
        })

        # Pass 2: Article segmentation
        article_count = pass2_segment(issue_dir, meta)
        update_tracker_row(filename, {
            "Articles": article_count,
            "Pass2": "complete",
            "Status": "pass2_done",
        })

        # Pass 3: QA inspection
        qa_counts = pass3_qa(issue_dir)
        update_tracker_row(filename, {
            "Pass3": "complete",
            "Pass_Count": qa_counts["pass"],
            "Warn_Count": qa_counts["warn"],
            "Flag_Count": qa_counts["flag"],
            "Status": "complete",
        })

        # Move PDF to done
        PDF_DONE_DIR.mkdir(parents=True, exist_ok=True)
        dest = PDF_DONE_DIR / filename
        pdf_path.rename(dest)
        print(f"  PDF moved to: {dest}")

        print(f"  DONE: {filename}")
        return "processed"

    except Exception as e:
        logger.exception("Failed processing %s", filename)
        update_tracker_row(filename, {"Status": f"failed: {str(e)[:100]}"})
        return "failed"


# -- MAIN --------------------------------------------------------------------

def run():
    """Scan 01_to_extract/ and process all PDFs."""
    TO_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DONE_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(TO_EXTRACT_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {TO_EXTRACT_DIR}")
        return

    print(f"Found {len(pdfs)} PDF(s) to process")

    processed = failed = 0
    for pdf_path in pdfs:
        result = process_issue(pdf_path)
        if result == "processed":
            processed += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"Done. {processed} processed, {failed} failed.")


if __name__ == "__main__":
    run()
