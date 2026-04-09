#!/usr/bin/env python3
"""
Tag Sermons & Transcripts

Backfills topic_tags for all non-magazine documents (sermons, papers, books, other).
Uses Groq Llama 3.3 70B to assign 3-6 tags from the Rhemata taxonomy.
Stricter than the magazine tagger — only tags that are a main theme of the document.
Validates tags against the taxonomy and retries if fewer than 2 valid tags.
"""

import os
import re
import json
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_CONTENT_CHARS = 4000

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

TAXONOMY_LIST = ", ".join(sorted(VALID_TAGS))

SYSTEM_PROMPT = f"""You are a theological taxonomy classifier. Based on this document, assign 3-6 topic tags from the taxonomy below.

STRICT RULES:
- Only assign a tag if the document CENTERS on that topic as a MAIN THEME — the topic must be a core subject the author is teaching, not a passing reference
- A single sentence or brief mention does NOT qualify. The topic must be developed across multiple paragraphs or be a clear structural focus of the document
- Ask yourself: 'Is this topic one of the 3-6 things this document is primarily ABOUT?' If no, do not assign it
- Prefer fewer, highly accurate tags over more loosely related ones
- 3-4 tags is ideal for a focused document. Only use 5-6 if the document genuinely covers that many distinct themes in depth
- Never assign a tag just because a keyword from the tag appears in the text
- You MUST only return tags from the exact list below. Do not create new tags. Do not modify tag names. Copy them exactly as written.

Return JSON only: {{"topic_tags": ["tag1", "tag2", ...]}}

TAXONOMY (use ONLY these exact tags):
{TAXONOMY_LIST}"""


def _parse_groq_json(raw):
    """Parse JSON from Groq response, handling code fences and trailing text."""
    json_str = raw
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    obj_match = re.search(r"\{[\s\S]*?\}", json_str)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("No valid JSON found", json_str, 0)


def _call_groq(groq, system_prompt, content):
    """Call Groq and return raw response text."""
    response = groq.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=512,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"DOCUMENT:\n{content}"},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def run():
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    groq = Groq(api_key=os.environ["GROQ_API_KEY"])

    # Fetch all non-magazine documents
    docs_result = (
        db.table("documents")
        .select("id, title, author, source_type, source_kind, topic_tags")
        .neq("source_kind", "magazine_article")
        .execute()
    )

    docs = docs_result.data
    if not docs:
        print("No non-magazine documents found.")
        return

    print(f"Found {len(docs)} document(s) to tag\n")

    tagged_count = 0
    retried_count = 0

    for doc in docs:
        doc_id = doc["id"]
        title = doc.get("title", "Unknown")
        source_type = doc.get("source_type", "?")

        # Fetch all chunks ordered by chunk_index
        chunks_result = (
            db.table("chunks")
            .select("chunk_index, content")
            .eq("document_id", doc_id)
            .order("chunk_index")
            .execute()
        )

        if not chunks_result.data:
            print(f"  Skipped: {title} — no chunks found")
            continue

        # Join all chunks, truncate to MAX_CONTENT_CHARS
        content = "\n\n".join(c["content"] for c in chunks_result.data)
        content = content[:MAX_CONTENT_CHARS]

        # First attempt
        raw = ""
        try:
            raw = _call_groq(groq, SYSTEM_PROMPT, content)
            result = _parse_groq_json(raw)
            tags = result.get("topic_tags", [])
        except Exception as e:
            print(f"  Failed: {title} — {e}")
            if raw:
                print(f"  Raw response: {raw[:500]}")
            continue

        # Validate tags against taxonomy
        valid_tags = [t for t in tags if t in VALID_TAGS]
        invalid_tags = [t for t in tags if t not in VALID_TAGS]
        if invalid_tags:
            print(f"  Removed invalid tags: {invalid_tags}")

        # Retry once if fewer than 2 valid tags
        if len(valid_tags) < 2:
            retried_count += 1
            print(f"  Only {len(valid_tags)} valid tag(s) for '{title}', retrying...")
            try:
                raw = _call_groq(groq, SYSTEM_PROMPT, content)
                result = _parse_groq_json(raw)
                retry_tags = result.get("topic_tags", [])
                retry_valid = [t for t in retry_tags if t in VALID_TAGS]
                retry_invalid = [t for t in retry_tags if t not in VALID_TAGS]
                if retry_invalid:
                    print(f"  Retry removed invalid: {retry_invalid}")
                if len(retry_valid) > len(valid_tags):
                    valid_tags = retry_valid
            except Exception as e:
                print(f"  Retry failed: {e}")

        if not valid_tags:
            print(f"  Skipped: {title} — no valid tags after retry")
            continue

        # Cap at 6 tags
        valid_tags = valid_tags[:6]

        # Update document in Supabase
        db.table("documents").update({"topic_tags": valid_tags}).eq("id", doc_id).execute()

        tagged_count += 1
        print(f"  [{source_type}] Tagged: {title} → {valid_tags}")

    print(f"\n{'='*60}")
    print(f"Done. {tagged_count}/{len(docs)} document(s) tagged. {retried_count} retried.")


if __name__ == "__main__":
    run()
