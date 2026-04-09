#!/usr/bin/env python3
"""
Tag Existing Articles

Backfills topic_tags for all magazine articles.
Uses Groq Llama 3.3 70B to assign 5-8 tags from the Rhemata taxonomy.
Validates tags against the taxonomy and retries if too few valid tags.
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
MAX_CONTENT_CHARS = 3000

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

SYSTEM_PROMPT = f"""Based on this article excerpt, assign 5-8 topic tags from the taxonomy below.

STRICT RULES for assigning tags:
- Only assign a tag if the article DIRECTLY teaches on that topic for at least one full paragraph
- Do NOT assign a tag for passing mentions, historical context, tangential connections, or merely implied topics
- Ask yourself: 'Would a reader searching for this topic find substantial, helpful content in this article?' If no, do not assign the tag.
- It is better to assign 3 highly accurate tags than 8 loosely related ones
- Never assign a tag just because a word in the tag appears in the article
- You MUST only return tags from this exact list. Do not create new tags. Do not modify tag names. Copy them exactly.

Return JSON only: {{"topic_tags": ["tag1", "tag2", ...]}}

TAXONOMY (use ONLY these exact tags):
{TAXONOMY_LIST}"""


def _parse_groq_json(raw):
    """Parse JSON from Groq response, handling code fences and trailing text."""
    json_str = raw
    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()
    # Try parsing as-is first
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    # Extract first JSON object {...}
    obj_match = re.search(r"\{[\s\S]*?\}", json_str)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("No valid JSON found", json_str, 0)


def _call_groq(groq, content):
    """Call Groq and return raw response text."""
    response = groq.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=512,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"ARTICLE:\n{content}"},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def run():
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    groq = Groq(api_key=os.environ["GROQ_API_KEY"])

    # Fetch all magazine articles
    docs_result = (
        db.table("documents")
        .select("id, title, author, topic_tags")
        .eq("source_kind", "magazine_article")
        .execute()
    )

    SKIP_PATTERNS = ["bible study", "bible lesson", "study guide"]
    docs = [
        d for d in docs_result.data
        if not any(p in (d.get("title") or "").lower() for p in SKIP_PATTERNS)
    ]
    skipped = len(docs_result.data) - len(docs)

    if not docs:
        print("No magazine articles found.")
        return

    if skipped:
        print(f"Skipped {skipped} Bible Study/lesson article(s)")
    print(f"Found {len(docs)} magazine article(s) to tag\n")

    tagged_count = 0

    for doc in docs:
        doc_id = doc["id"]
        title = doc.get("title", "Unknown")

        # Fetch ALL chunks, ordered by chunk_index
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

        # Call Groq — first attempt
        try:
            raw = _call_groq(groq, content)
            result = _parse_groq_json(raw)
            tags = result.get("topic_tags", [])
        except Exception as e:
            print(f"  Failed: {title} — {e}")
            print(f"  Raw response: {raw[:500]}")
            continue

        # Validate tags against taxonomy
        valid_tags = [t for t in tags if t in VALID_TAGS]
        invalid_tags = [t for t in tags if t not in VALID_TAGS]
        if invalid_tags:
            print(f"  Removed invalid tags: {invalid_tags}")

        # Retry if fewer than 3 valid tags
        if len(valid_tags) < 3:
            print(f"  Only {len(valid_tags)} valid tag(s), retrying...")
            try:
                raw = _call_groq(groq, content)
                result = _parse_groq_json(raw)
                retry_tags = result.get("topic_tags", [])
                retry_valid = [t for t in retry_tags if t in VALID_TAGS]
                if len(retry_valid) > len(valid_tags):
                    valid_tags = retry_valid
            except Exception as e:
                print(f"  Retry failed: {e}")

        if not valid_tags:
            print(f"  Skipped: {title} — no valid tags")
            continue

        # Update document in Supabase
        db.table("documents").update({"topic_tags": valid_tags}).eq("id", doc_id).execute()

        tagged_count += 1
        print(f"  Tagged: {title} → {valid_tags}")

    print(f"\n{'='*60}")
    print(f"Done. {tagged_count} article(s) tagged.")


if __name__ == "__main__":
    run()
