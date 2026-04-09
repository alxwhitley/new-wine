#!/usr/bin/env python3
"""
Tag Existing Articles

Backfills topic_tags for magazine articles that don't have them yet.
Uses Groq Llama 3.3 70B to assign 5-8 tags from the Rhemata taxonomy.
"""

import os
import re
import json
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent / "backend" / "app" / ".env")

GROQ_MODEL = "llama-3.3-70b-versatile"

TAXONOMY = (
    "Baptism in the Spirit, Speaking in Tongues, Prophetic Ministry, "
    "Word of Knowledge, Word of Wisdom, Discerning of Spirits, "
    "Miracles and Signs, The Nine Gifts, Stirring Up Gifts, "
    "Moving in the Spirit, Fruit of the Spirit, Fresh Anointing, "
    "Filling of the Spirit, Power for Service, "
    "Hearing God's Voice, Dreams and Visions, Interpreting Your Dreams, "
    "Encounters with God, Divine Appointments, Supernatural Peace, "
    "Manifestations of God, Intimacy with Jesus, Atmosphere of Worship, "
    "Spiritual Sight, Knowing God's Heart, Personal Revelation, "
    "Walking in the Spirit, Led by the Spirit, "
    "Intercessory Prayer, Authority of the Believer, "
    "Tearing Down Strongholds, Resisting the Enemy, Victory in Christ, "
    "Deliverance from Bondage, Casting Out Demons, Spiritual Weapons, "
    "Breaking Negative Patterns, Binding and Loosing, Armor of God, "
    "Warfare in Prayer, Fasting and Prayer, Protecting Your Mind, "
    "Divine Healing, Praying for the Sick, Inner Healing, "
    "Emotional Wholeness, Healing of Memories, Health and Vitality, "
    "Overcoming Fear, Freedom from Anxiety, Restoration of Soul, "
    "Physical Miracles, The Will to Heal, Faith for Healing, "
    "God's Comfort, Wholeness in Christ, "
    "Biblical Leadership, Fivefold Ministry, Apostolic Oversight, "
    "Prophetic Direction, Pastoral Care, Delegated Authority, "
    "Spiritual Covering, Accountability in Leadership, "
    "Covenant Relationships, Mentoring Relationships, "
    "Leading with Integrity, Servant Leadership, Team Ministry, "
    "Equipping the Saints, Elders and Deacons, "
    "Spiritual Maturity, Walking with God, Discipleship and Mentoring, "
    "Accountability in Christ, Knowing God's Will, Character of Christ, "
    "Honoring Biblical Authority, Submission to God, "
    "Faith and Perseverance, Stewardship and Finances, "
    "Spiritual Disciplines, Dying to Self, Holiness and Sanctification, "
    "Body Ministry, "
    "Kingdom of God, Word and Spirit, Biblical Authority, "
    "The New Covenant, The Lordship of Christ, Grace and Mercy, "
    "Salvation and Repentance, End Times Prophecy, The Rapture, "
    "Second Coming, The Trinity, Blood of Jesus, Heaven and Eternity, "
    "Restoration of All Things, "
    "Biblical Marriage, Christian Parenting, Family Life, "
    "Relationship Restoration, Communication in Marriage, "
    "Raising Godly Children, Singleness and Purity, "
    "Friendship in Christ, Honoring Your Parents, Forgiving Others, "
    "Love and Sacrifice, Conflict Resolution, The Christian Home"
)

SYSTEM_PROMPT = f"""Based on this article excerpt, assign 5-8 topic tags from the taxonomy below \
that genuinely match the content. Choose only tags that appear in the taxonomy — do not invent new ones.

Return JSON only: {{"topic_tags": ["tag1", "tag2", ...]}}

TAXONOMY:
{TAXONOMY}"""


def run():
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    groq = Groq(api_key=os.environ["GROQ_API_KEY"])

    # Fetch magazine articles with no topic_tags
    docs_result = (
        db.table("documents")
        .select("id, title, author, topic_tags")
        .eq("source_kind", "magazine_article")
        .execute()
    )

    # Filter to docs where topic_tags is null or empty
    docs = [
        d for d in docs_result.data
        if not d.get("topic_tags") or d["topic_tags"] == []
    ]

    if not docs:
        print("No untagged magazine articles found.")
        return

    print(f"Found {len(docs)} untagged magazine article(s)\n")

    tagged_count = 0

    for doc in docs:
        doc_id = doc["id"]
        title = doc.get("title", "Unknown")

        # Fetch first 3 chunks
        chunks_result = (
            db.table("chunks")
            .select("chunk_index, content")
            .eq("document_id", doc_id)
            .order("chunk_index")
            .limit(3)
            .execute()
        )

        if not chunks_result.data:
            print(f"  Skipped: {title} — no chunks found")
            continue

        content = "\n\n".join(c["content"] for c in chunks_result.data)

        # Call Groq
        try:
            response = groq.chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=512,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"ARTICLE:\n{content}"},
                ],
            )
            raw = (response.choices[0].message.content or "").strip()

            # Parse JSON — handle markdown code fences
            json_str = raw
            fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
            if fence_match:
                json_str = fence_match.group(1).strip()
            result = json.loads(json_str)
            tags = result.get("topic_tags", [])
        except Exception as e:
            print(f"  Failed: {title} — {e}")
            continue

        if not tags:
            print(f"  Skipped: {title} — no tags returned")
            continue

        # Update document in Supabase
        db.table("documents").update({"topic_tags": tags}).eq("id", doc_id).execute()

        tagged_count += 1
        print(f"  Tagged: {title} → {tags}")

    print(f"\n{'='*60}")
    print(f"Done. {tagged_count} article(s) tagged.")


if __name__ == "__main__":
    run()
