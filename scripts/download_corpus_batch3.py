#!/usr/bin/env python3
"""Download public-domain PDFs (batches 1-3) into sources/inbox/."""

import requests
from pathlib import Path

DEST_DIR = Path(__file__).resolve().parent.parent / "sources" / "inbox"

BOOKS = [
    # --- BATCH 1 (CCEL - Murray, Bounds, Torrey, Finney) ---
    {"filename": "murray_with_christ_in_school_of_prayer.pdf", "url": "https://www.ccel.org/ccel/m/murray/prayer/cache/prayer.pdf"},
    {"filename": "murray_deeper_christian_life.pdf", "url": "https://ccel.org/ccel/m/murray/deeper/cache/deeper.pdf"},
    {"filename": "murray_new_life.pdf", "url": "https://ccel.org/ccel/m/murray/new_life/cache/new_life.pdf"},
    {"filename": "murray_waiting_on_god.pdf", "url": "https://ccel.org/ccel/m/murray/waiting/cache/waiting.pdf"},
    {"filename": "bounds_power_through_prayer.pdf", "url": "https://ccel.org/ccel/b/bounds/power/cache/power.pdf"},
    {"filename": "bounds_weapon_of_prayer.pdf", "url": "https://ccel.org/ccel/b/bounds/weapon/cache/weapon.pdf"},
    {"filename": "bounds_prayer_and_praying_men.pdf", "url": "https://www.ccel.org/ccel/b/bounds/prayingmen/cache/prayingmen.pdf"},
    {"filename": "bounds_necessity_of_prayer.pdf", "url": "https://ccel.org/ccel/b/bounds/necessity/cache/necessity.pdf"},
    {"filename": "bounds_essentials_of_prayer.pdf", "url": "https://www.ccel.org/ccel/b/bounds/essentials/cache/essentials.pdf"},
    {"filename": "torrey_person_and_work_of_holy_spirit.pdf", "url": "https://ccel.org/ccel/t/torrey/work_holy_spirit/cache/work_holy_spirit.pdf"},
    {"filename": "torrey_how_to_pray.pdf", "url": "https://www.ccel.org/t/torrey/pray/cache/pray.pdf"},
    {"filename": "finney_power_from_on_high.pdf", "url": "https://www.ccel.org/ccel/f/finney/power/cache/power.pdf"},
    {"filename": "finney_lectures_on_revivals.pdf", "url": "https://ccel.org/ccel/f/finney/revivals/cache/revivals.pdf"},

    # --- BATCH 2 (CCEL - Kuyper, Owen, Meyer, Gordon, Finney, Bounds, Edwards, Wesley, Bruce, Ryle, Bushnell, Lawrence) ---
    {"filename": "kuyper_work_of_the_holy_spirit.pdf", "url": "https://www.ccel.org/ccel/k/kuyper/holy_spirit/cache/holy_spirit.pdf"},
    {"filename": "owen_pneumatologia_holy_spirit.pdf", "url": "https://ccel.org/ccel/o/owen/pneum/cache/pneum.pdf"},
    {"filename": "meyer_secret_of_guidance.pdf", "url": "https://ccel.org/ccel/m/meyer/guidance/cache/guidance.pdf"},
    {"filename": "meyer_way_into_the_holiest.pdf", "url": "https://ccel.org/ccel/m/meyer/into_holiest/cache/into_holiest.pdf"},
    {"filename": "gordon_quiet_talks_on_prayer.pdf", "url": "https://ccel.org/ccel/g/gordon/prayer/cache/prayer.pdf"},
    {"filename": "gordon_quiet_talks_on_power.pdf", "url": "https://ccel.org/ccel/g/gordon/talkspower/cache/talkspower.pdf"},
    {"filename": "finney_lectures_to_professing_christians.pdf", "url": "https://ccel.org/ccel/f/finney/professing/cache/professing.pdf"},
    {"filename": "bounds_purpose_in_prayer.pdf", "url": "https://ccel.org/ccel/b/bounds/purpose/cache/purpose.pdf"},
    {"filename": "bounds_reality_of_prayer.pdf", "url": "https://ccel.org/ccel/b/bounds/reality/cache/reality.pdf"},
    {"filename": "edwards_religious_affections.pdf", "url": "https://ccel.org/ccel/e/edwards/affections/cache/affections.pdf"},
    {"filename": "edwards_works_vol1.pdf", "url": "https://ccel.org/ccel/e/edwards/works1/cache/works1.pdf"},
    {"filename": "edwards_works_vol2.pdf", "url": "https://www.ccel.org/ccel/e/edwards/works2/cache/works2.pdf"},
    {"filename": "wesley_sermons.pdf", "url": "https://ccel.org/ccel/w/wesley/sermons/cache/sermons.pdf"},
    {"filename": "wesley_journal.pdf", "url": "https://www.ccel.org/w/wesley/journal/cache/journal.pdf"},
    {"filename": "bruce_training_of_the_twelve.pdf", "url": "https://www.ccel.org/ccel/b/bruce/twelve/cache/twelve.pdf"},
    {"filename": "ryle_holiness.pdf", "url": "https://ccel.org/ccel/r/ryle/holiness/cache/holiness.pdf"},
    {"filename": "bushnell_christian_nurture.pdf", "url": "https://www.ccel.org/ccel/b/bushnell/nurture/cache/nurture.pdf"},
    {"filename": "lawrence_practice_of_presence.pdf", "url": "https://ccel.org/ccel/l/lawrence/practice/cache/practice.pdf"},
    {"filename": "simpson_gospel_of_healing.pdf", "url": "https://ccel.org/ccel/s/simpson/gospel_of_healing/cache/gospel_of_healing.pdf"},
    {"filename": "unknown_kneeling_christian.pdf", "url": "https://www.ccel.org/ccel/u/unknown/kneeling/cache/kneeling.pdf"},

    # --- BATCH 3 (Archive.org - Gemini verified clean PDFs only) ---
    {"filename": "wigglesworth_ever_increasing_faith.pdf", "url": "https://archive.org/download/everincreasingfa00wigg_0/everincreasingfa00wigg_0.pdf"},
    {"filename": "penn_lewis_war_on_the_saints.pdf", "url": "https://archive.org/download/WarOnTheSaints-ATextBookForBelieversOnTheWorkOfDeceivingSpirits_697/WarOnTheSaints-ATextBookForBelieversOnTheWorkOfDeceivingSpirits.pdf"},
    {"filename": "penn_lewis_warfare_with_satan.pdf", "url": "https://archive.org/download/warfarewithsatan0000jess/warfarewithsatan0000jess.pdf"},
    {"filename": "bosworth_christ_the_healer.pdf", "url": "https://archive.org/download/DivineHealingGeneral34DivineHealingBooksInEpubFormat/DivHEAL%20Christ%20The%20Healer%20-%20Fred%20Bosworth.pdf"},
    {"filename": "muller_autobiography.pdf", "url": "https://archive.org/download/georgemllerofb00pier/georgemllerofb00pier.pdf"},
    {"filename": "muller_how_god_answers_prayer.pdf", "url": "https://archive.org/download/howgodanswerspra0000mlle/howgodanswerspra0000mlle.pdf"},
    {"filename": "palmer_way_of_holiness.pdf", "url": "https://archive.org/download/wayofholinesswit01palm/wayofholinesswit01palm.pdf"},
    {"filename": "gordon_aj_ministry_of_the_spirit.pdf", "url": "https://archive.org/download/ministryofspirit00gord/ministryofspirit00gord.pdf"},
    {"filename": "gordon_aj_twofold_life.pdf", "url": "https://archive.org/download/twofoldlifeorch00gordgoog/twofoldlifeorch00gordgoog.pdf"},
    {"filename": "booth_catherine_aggressive_christianity.pdf", "url": "https://archive.org/download/aggressivechrist00boot/aggressivechrist00boot.pdf"},
    {"filename": "booth_william_in_darkest_england.pdf", "url": "https://archive.org/download/indarkestengland00boot/indarkestengland00boot.pdf"},
    {"filename": "booth_william_salvation_soldiery.pdf", "url": "https://archive.org/download/salvationsoldier00bootuoft/salvationsoldier00bootuoft.pdf"},
    {"filename": "smith_hannah_everyday_religion.pdf", "url": "https://ia801507.us.archive.org/2/items/everydayreligion00smitiala/everydayreligion00smitiala.pdf"},
    {"filename": "smith_hannah_god_of_all_comfort.pdf", "url": "https://archive.org/download/godallcomfortan00smitgoog/godallcomfortan00smitgoog.pdf"},
    {"filename": "pink_attributes_of_god.pdf", "url": "https://archive.org/download/TheAttributesOfGod_69/The%20Attributes%20of%20God.pdf"},
    {"filename": "pink_sovereignty_of_god.pdf", "url": "https://archive.org/download/ArthurW.PinkTheSovereigntyOfGod/Arthur%20W.%20Pink%20-%20The%20Sovereignty%20of%20God.pdf"},
    {"filename": "pink_profiting_from_the_word.pdf", "url": "https://www.chapellibrary.org/api/books/download?code=pftw&format=pdf"},
    {"filename": "miller_jr_marriage_altar.pdf", "url": "https://archive.org/download/marriagealtar00mill/marriagealtar00mill.pdf"},
    {"filename": "miller_jr_weekday_religion.pdf", "url": "https://archive.org/download/weekdayreligion00millgoog/weekdayreligion00millgoog.pdf"},
    {"filename": "miller_jr_personal_friendships_of_jesus.pdf", "url": "https://archive.org/download/personalfriende00millgoog/personalfriende00millgoog.pdf"},
    {"filename": "woodworth_etter_acts_of_holy_ghost.pdf", "url": "https://archive.org/download/marvelsmiraclesg00wood/marvelsmiraclesg00wood.pdf"},
    {"filename": "lake_john_g_adventures_in_god.pdf", "url": "https://archive.org/download/adventuresingod0000lake/adventuresingod0000lake.pdf"},
    {"filename": "horner_rc_pentecost.pdf", "url": "https://archive.org/download/pentecost00horn/pentecost00horn.pdf"},
]

FIXES = [
    # Corrected CCEL URLs (404 fixes)
    {"filename": "gordon_quiet_talks_on_prayer.pdf", "url": "https://www.ccel.org/ccel/g/gordon/talksprayer/cache/talksprayer.pdf"},
    {"filename": "finney_lectures_to_professing_christians.pdf", "url": "https://www.ccel.org/ccel/f/finney/toprofessingchristians/cache/toprofessingchristians.pdf"},

    # Archive.org Penn-Lewis (404 fix — try alternate)
    {"filename": "penn_lewis_war_on_the_saints.pdf", "url": "https://archive.org/download/war-on-the-saints-jessie-penn-lewis/War%20on%20the%20Saints%20-%20Jessie%20Penn-Lewis.pdf"},

    # A.J. Gordon Ministry of the Spirit (403 fix — try alternate)
    {"filename": "gordon_aj_ministry_of_the_spirit.pdf", "url": "https://archive.org/download/ministryofspirit00gordrich/ministryofspirit00gordrich.pdf"},

    # John G. Lake (401 lending library — try alternate identifier)
    {"filename": "lake_john_g_adventures_in_god.pdf", "url": "https://archive.org/download/adventuresingod00lake/adventuresingod00lake.pdf"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def download_list(book_list, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0
    failed_files = []

    for i, book in enumerate(book_list, 1):
        dest = dest_dir / book["filename"]

        if dest.exists():
            print(f"  [{i}/{len(book_list)}] SKIPPED  {book['filename']} (already exists)")
            skipped += 1
            continue

        print(f"  [{i}/{len(book_list)}] DOWNLOADING  {book['filename']} ...")
        try:
            resp = requests.get(book["url"], headers=HEADERS, timeout=30)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
                reason = f"non-PDF content type: {content_type}"
                print(f"  [{i}/{len(book_list)}] FAILED  {book['filename']}: {reason}")
                failed += 1
                failed_files.append((book["filename"], reason))
                continue

            dest.write_bytes(resp.content)
            size_kb = len(resp.content) / 1024
            print(f"  [{i}/{len(book_list)}] OK  {book['filename']} ({size_kb:.0f} KB)")
            downloaded += 1
        except Exception as e:
            reason = str(e)
            print(f"  [{i}/{len(book_list)}] FAILED  {book['filename']}: {reason}")
            failed += 1
            failed_files.append((book["filename"], reason))

    print(f"\n{'='*60}")
    print(f"Total: {len(book_list)} | Downloaded: {downloaded} | Skipped: {skipped} | Failed: {failed}")
    if failed_files:
        print(f"\nFailed files:")
        for name, reason in failed_files:
            print(f"  - {name}: {reason}")


def main():
    import sys
    if "--fixes" in sys.argv:
        print("Running FIXES only...\n")
        download_list(FIXES, DEST_DIR)
    else:
        download_list(BOOKS, DEST_DIR)


if __name__ == "__main__":
    main()
