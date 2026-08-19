"""Seed the books table with curated book data."""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

import psycopg2
from psycopg2.extras import execute_values

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    sys.exit(1)

_parsed_db = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host": _parsed_db.hostname,
    "port": _parsed_db.port or 5432,
    "user": unquote(_parsed_db.username or ""),
    "password": unquote(_parsed_db.password or ""),
    "dbname": _parsed_db.path.lstrip("/"),
}

BOOKS = [
    # Derek Prince
    ("Blessing or Curse: You Can Choose", "Derek Prince", "Explores how blessings and curses operate in Scripture and how believers can break free from inherited patterns of darkness."),
    ("They Shall Expel Demons", "Derek Prince", "A practical, comprehensive guide to deliverance ministry drawing on Prince\u2019s decades of personal experience."),
    ("Shaping History Through Prayer and Fasting", "Derek Prince", "A call to intercessory prayer as a force that changes nations and governments."),
    ("Spiritual Warfare", "Derek Prince", "Explains the reality of the invisible battle between God\u2019s kingdom and Satan\u2019s, and how believers engage it."),
    ("Foundational Truths for Christian Living", "Derek Prince", "A comprehensive study of the six foundational doctrines of the Christian faith drawn from Hebrews 6."),
    ("God\u2019s Medicine Bottle", "Derek Prince", "A practical guide to receiving physical and spiritual healing through the Word of God."),
    ("Holy Spirit in You", "Derek Prince", "A clear biblical overview of the person and work of the Holy Spirit in the life of every believer."),
    # Bob Mumford
    ("Agape Road", "Bob Mumford", "A journey into the unconditional love of the Father and how it transforms the believer\u2019s walk with God."),
    ("Take Another Look at Guidance", "Bob Mumford", "A foundational teaching on discerning God\u2019s will across the three ways he guides his people."),
    ("The Purpose of Temptation", "Bob Mumford", "Explores how God uses temptation redemptively to build character and deepen faith."),
    ("The King and You", "Bob Mumford", "Teaches how the Kingdom of God practically transforms character, conduct, and influence."),
    ("Fifteen Steps Out", "Bob Mumford", "A practical guide to breaking free from cycles of sin and stepping into freedom."),
    # Ern Baxter
    ("Thy Kingdom Come", "Ern Baxter", "A landmark teaching on the Kingdom of God and the church\u2019s mandate in the earth, delivered live to 5,000 leaders."),
    # Charles Simpson
    ("The Challenge to Care", "Charles Simpson", "Explores the call to covenant community and authentic pastoral relationship in the local church."),
    ("Courageous Living", "Charles Simpson", "A call to bold, uncompromising Christian discipleship in the face of cultural pressure."),
    ("Straight Answers to 21 Honest Questions About Prayer", "Charles Simpson", "Practical and pastoral answers to the most common questions believers have about prayer."),
    # Don Basham
    ("Face Up with a Miracle", "Don Basham", "Basham\u2019s autobiographical account of encountering the Holy Spirit and entering charismatic ministry."),
    ("Deliver Us from Evil", "Don Basham", "A foundational book on deliverance ministry covering demonic activity and the believer\u2019s authority."),
    ("A Handbook on Holy Spirit Baptism", "Don Basham", "A clear, accessible guide to understanding and receiving the baptism of the Holy Spirit."),
    ("True and False Prophets", "Don Basham", "A discerning look at how to test prophetic ministry and recognize authentic vs. deceptive spiritual voices."),
    # John Bevere
    ("The Bait of Satan", "John Bevere", "Exposes how offense and unforgiveness become the enemy\u2019s primary trap, and how to walk free."),
    ("Under Cover", "John Bevere", "A challenging study on submission to God-ordained authority and the protection it provides."),
    ("Driven by Eternity", "John Bevere", "Calls believers to live in light of eternity and the coming judgment seat of Christ."),
    ("Good or God?", "John Bevere", "Asks the provocative question: is the good life we\u2019re pursuing actually God\u2019s will, or a counterfeit?"),
    ("The Awe of God", "John Bevere", "Reclaims the fear of the Lord as the foundation of wisdom, holiness, and intimacy with God."),
    ("Killing Kryptonite", "John Bevere", "Identifies the subtle sins that drain spiritual power and shows how to walk in sustained strength."),
    # Michael Brown
    ("Our Hands Are Stained with Blood", "Michael Brown", "A sobering account of the church\u2019s historic mistreatment of the Jewish people and a call to repentance."),
    ("Answering Jewish Objections to Jesus", "Michael Brown", "A scholarly yet accessible series responding to the most common objections Jewish people raise against Jesus as Messiah."),
    ("Whatever Happened to the Power of God?", "Michael Brown", "A prophetic challenge to the church to recover the signs, wonders, and power of the New Testament."),
    ("Authentic Fire", "Michael Brown", "A theological response to cessationism and a defense of the ongoing gifts of the Spirit."),
    ("Hyper-Grace", "Michael Brown", "A careful examination of the modern grace movement and where it veers into dangerous distortion."),
    ("Revolution in the Church", "Michael Brown", "A call to radical, Spirit-empowered Christianity that transforms culture rather than accommodating it."),
    # Jack Deere
    ("Surprised by the Power of the Spirit", "Jack Deere", "Deere\u2019s landmark account of moving from cessationism to continuationism, with a biblical case for ongoing miracles."),
    ("Surprised by the Voice of God", "Jack Deere", "A companion volume making the case for contemporary prophecy and God speaking today."),
    ("Even in Our Darkness", "Jack Deere", "A memoir weaving personal tragedy into a story of God\u2019s faithfulness in suffering."),
    ("Why I Am Still Surprised by the Power of the Spirit", "Jack Deere", "An updated and expanded edition revisiting his original arguments with decades of additional evidence."),
    # Oswald J. Smith
    ("The Passion for Souls", "Oswald J. Smith", "A stirring call to evangelism and missions rooted in a broken heart for the lost."),
    ("The Man God Uses", "Oswald J. Smith", "A portrait of the kind of person God moves through and what it takes to be fully available to him."),
    ("The Enduement of Power", "Oswald J. Smith", "An exploration of the Holy Spirit\u2019s empowering work and how believers can be filled and remain filled."),
    ("The Revival We Need", "Oswald J. Smith", "A prophetic cry for genuine spiritual awakening and the conditions that make revival possible."),
]


def main():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()

    # Check which books already exist
    existing = set()
    cur.execute("SELECT title, author FROM books")
    for row in cur.fetchall():
        existing.add((row[0], row[1]))

    to_insert = [
        (title, author, desc)
        for title, author, desc in BOOKS
        if (title, author) not in existing
    ]

    if not to_insert:
        print("All books already seeded.")
    else:
        execute_values(
            cur,
            "INSERT INTO books (title, author, description) VALUES %s",
            to_insert,
            template="(%s, %s, %s)",
        )
        conn.commit()
        print(f"Inserted {len(to_insert)} books ({len(existing)} already existed).")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
