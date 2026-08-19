#!/usr/bin/env python3
"""Apply Alex-approved non-teacher-material quote-source exclusions (2026-08-06).

Basis: docs/audits/non_teacher_material_audit_2026-08-06.md (the follow-up audit)
plus Alex's confirmed judgment calls (session 2026-08-06). Marks WHOLE non-teacher
chunks ineligible for quote sourcing via chunks.quote_ineligible_reason (the same
mechanism migration 082 seeded for "The New Life" 0-5). Does NOT alter any source
text. Idempotent: only writes where the reason is currently NULL. Run once, 2026-08-06;
62 chunks written (corpus total then 68, incl. the 6 pre-existing New Life chunks).

WHOLE-CHUNK ONLY. The mechanism has one granularity: the chunk. Third-party material
that shares a chunk with the teacher's own words CANNOT be isolated here and is
deliberately left eligible and FLAGGED for Alex instead of forcing a split (per the
task's "flag rather than guess" instruction). Flagged, not excluded:
  - The Lord's Table: one-line translator footnote at ch54 (rest of chunk is Murray).
  - The School of Obedience: the entire John R. Mott "morning watch" quotation
    (ch86-88) is interwoven with Murray's own prayer/commentary in every chunk;
    NO chunk is purely Mott, so none could be cleanly excluded. ch89 is pure Murray.
  - With Christ in the School of Prayer: George Muller boundary chunks ch232/233/245
    (Muller fragment abuts Murray narration). The clean Muller chunks ARE excluded.
  - The New Life body: translator footnotes ch84/97/101/146/194 and the Heidelberg
    Catechism Q76 quote at ch182 are all one-line/few-sentence inserts inside Murray's
    own chapters -- none is a pure non-Murray chunk. (This is the "second problem area"
    beyond the already-excluded 0-5; it could not be applied at chunk granularity.)
  - Waiting On God!: the frontispiece poem (ch3-4) is now CONFIRMED third-party
    (signed "Freda Hanbury"), but interwoven with Murray's dedication + Introduction
    opening -> flagged, not excluded.
  - The Bride Prepares Herself: ch11 boundary (Derek's own teaching + intro of Gary,
    Gary's answer only begins at the tail) -> kept eligible; ch12-13 (guest testimony)
    excluded.
  - Magazine mastheads (5 Prince New Wine articles) are a one-line running header at
    the top of EVERY chunk -> cannot exclude without killing Derek's articles; flagged.
  - Tape-ID / speaker-tag header lines on a few transcripts are one-line labels sharing
    ch0 with Derek's opening words -> flagged. (Deliverance And Demonology's study-note
    header/copyright is explicitly out of scope per Alex -- low-risk, left as-is.)
"""
import psycopg2

url=[l.split("=",1)[1].strip().strip('"').strip("'") for l in open("backend/app/.env") if l.startswith("SUPABASE_DB_URL")][0]

AS ="1da1afb1-78b2-4eec-be57-01426d676266"  # Absolute Surrender
DCL="42098c1c-2ea5-42fc-9d7b-8b4a8f617af4"  # The Deeper Christian Life
LT ="6345f2ad-e9ec-4807-9fc1-489f7c828c4a"  # The Lord's Table
MI ="96c648f6-3222-4a66-a465-4eb2812bca75"  # The Master's Indwelling
SO ="08b3ccf5-5c95-435e-9884-8f0b433c0487"  # The School of Obedience
TV ="6daf6671-e386-4103-998e-1fb42914300b"  # The True Vine
TC ="3645b220-edc5-48bd-b758-e714f19be022"  # The Two Covenants
WOG="740f915d-0a9e-47f1-b2e8-75ce5e4a5631"  # Waiting On God!
SOP="a8e2ead2-7bdf-4f90-9b49-22835800f72a"  # With Christ in the School of Prayer
BRIDE="b99b54e9-f5e4-4c23-9272-20bec71ffd5d"  # The Bride Prepares Herself (Derek Prince)

FM     ="ccel_editorial_front_matter_not_teacher_authored"
APX    ="catechism_and_worship_manual_quotation_not_teacher_authored"
MULLER ="third_party_quotation_george_muller_not_teacher_authored"
ADV    ="ccel_related_books_advertisement_not_teacher_authored"
IDX    ="scripture_index_auto_generated_not_teacher_authored"
GUEST  ="guest_speaker_not_derek_prince_authored"

EXCL=[
 (AS ,[0,1,2],        FM,  "Absolute Surrender front matter"),
 (DCL,[0,1,2],        FM,  "Deeper Christian Life front matter"),
 (LT ,[0,1,2,3],      FM,  "Lord's Table front matter"),
 (MI ,[0,1,2],        FM,  "Master's Indwelling front matter"),
 (SO ,[0,1,2],        FM,  "School of Obedience front matter"),
 (TV ,[0,1,2,3],      FM,  "True Vine front matter (incl. unsigned frontispiece poem, ch3)"),
 (TC ,[0,1,2],        FM,  "Two Covenants front matter"),
 (WOG,[0,1,2,5,6],    FM,  "Waiting On God front matter (0-2) + scrambled contents listing (5-6)"),
 (SOP,[0,1,2,3],      FM,  "School of Prayer front matter"),
 (LT ,[76,77],        APX, "Lord's Table back appendix (Heidelberg Catechism + Directory of Public Worship)"),
 (SOP,[229,230,235,236,238,239,240,241,242,243,244,246,247,248,249,250,251], MULLER,
                            "School of Prayer George Muller verbatim chunks (Murray framing 227/228/231/234/237 kept)"),
 (SOP,[255,256],      ADV, "School of Prayer CCEL Related-Books advertisement (E.M. Bounds etc.)"),
 (BRIDE,[12,13],      GUEST,"Bride Prepares Herself guest-speaker Q&A testimony (ch11 boundary flagged)"),
 (AS ,[123],          IDX, "Absolute Surrender scripture index"),
 (MI ,[143],          IDX, "Master's Indwelling scripture index"),
 (TC ,[153],          IDX, "Two Covenants scripture index"),
 (WOG,[103],          IDX, "Waiting On God scripture index"),
 (SOP,[252,253,254],  IDX, "School of Prayer scripture indexes"),
 # No clean pure-index chunk exists for Deeper Christian Life, Lord's Table,
 # School of Obedience, or True Vine (index absent or a tail fragment of a Murray chunk).
]

def main():
    conn=psycopg2.connect(url, connect_timeout=25); conn.autocommit=False; cur=conn.cursor()
    cur.execute("select count(*) from chunks where quote_ineligible_reason is not null")
    before=cur.fetchone()[0]; print(f"BEFORE: {before} excluded")
    total=0
    for did,idxs,reason,label in EXCL:
        cur.execute("""update chunks set quote_ineligible_reason=%s
                       where document_id=%s and chunk_index = any(%s) and quote_ineligible_reason is null""",
                    (reason,did,idxs))
        total+=cur.rowcount; print(f"  +{cur.rowcount:2d}  {label}")
    cur.execute("select count(*) from chunks where quote_ineligible_reason is not null")
    after=cur.fetchone()[0]
    if after==before+total:
        conn.commit(); print(f"COMMITTED. {total} written, {after} total excluded.")
    else:
        conn.rollback(); print("MISMATCH -> ROLLED BACK")
    conn.close()

if __name__=="__main__":
    main()
