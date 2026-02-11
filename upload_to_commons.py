#!/usr/bin/env python3
"""
Upload SB Lucas Wellcome Collection pathology images to Wikimedia Commons.

SETUP:
  1. pip install pywikibot
  2. Create a bot password at https://commons.wikimedia.org/wiki/Special:BotPasswords
     - Grant permissions: Edit existing pages, Create/edit/move pages, Upload new files, Upload/replace files
  3. Edit the CONFIG section below with your credentials
  4. Place this script in the same folder as:
     - sb_lucas_wellcome_images.csv
     - The 'images/' folder containing the JPG files
  5. Run: python upload_to_commons.py

OPTIONS:
  python upload_to_commons.py                    # Upload all images
  python upload_to_commons.py --dry-run          # Preview without uploading
  python upload_to_commons.py --start 10         # Start from row 10 (for resuming)
  python upload_to_commons.py --limit 5          # Upload only 5 images (pilot test)
  python upload_to_commons.py --limit 5 --dry-run  # Preview 5 images
"""

import csv
import os
import sys
import re
import time
import argparse
import json
from pathlib import Path

# ============================================================
# CONFIG — Edit these values
# ============================================================
COMMONS_USERNAME = "YourUsername"                              # Your Wikimedia username
BOT_USERNAME     = "YourUsername@botname"              # Bot username (from Special:BotPasswords)
BOT_PASSWORD     = "your-bot-password"           # Bot password

# Paths (relative to this script's location)
CSV_FILE   = "sb_lucas_wellcome_images.csv"
IMAGES_DIR = "images"

# Upload settings
UPLOAD_COMMENT = "Batch upload of pathology images from the Wellcome Collection (SB Lucas), CC0 licensed"
DELAY_SECONDS  = 2  # Pause between uploads to avoid rate limiting
# ============================================================


def setup_pywikibot():
    """Configure pywikibot for Wikimedia Commons."""
    script_dir = Path(__file__).parent.resolve()
    user_config = script_dir / "user-config.py"

    if not user_config.exists():
        config_text = f"""
family = 'commons'
mylang = 'commons'
usernames['commons']['commons'] = '{COMMONS_USERNAME}'
password_file = '{script_dir / "user-password.py"}'
put_throttle = {DELAY_SECONDS}
maxlag = 5
"""
        user_config.write_text(config_text.strip())
        print(f"[setup] Created {user_config}")

    pw_file = script_dir / "user-password.py"
    if not pw_file.exists():
        pw_text = f"""
("{BOT_USERNAME}", "{BOT_PASSWORD}")
"""
        pw_file.write_text(pw_text.strip())
        pw_file.chmod(0o600)
        print(f"[setup] Created {pw_file}")

    os.environ["PYWIKIBOT_DIR"] = str(script_dir)


def build_wikitext(row):
    """Build the full wikitext for a Commons file page."""
    title = row["title"]
    desc = row["description"] or title
    miro = row["miro_image_number"]
    credit = row["credit"] or row["contributors"]
    work_url = row["work_page_url"]

    # Clean HTML tags from description
    desc_clean = re.sub(r"<[^>]+>", "", desc)

    # Single disease-specific category
    title_lower = title.lower()
    disease_cat = None
    if "leprosy" in title_lower or "lepromatous" in title_lower:
        disease_cat = "Leprosy"
    elif "schistosomiasis" in title_lower:
        disease_cat = "Schistosomiasis"
    elif "amoebiasis" in title_lower or "amoebic" in title_lower:
        disease_cat = "Amoebiasis"
    elif "leishmaniasis" in title_lower or "kala azar" in title_lower:
        disease_cat = "Leishmaniasis"
    elif "histoplasmosis" in title_lower:
        disease_cat = "Histoplasmosis"
    elif "tuberculosis" in title_lower or "tuberculous" in title_lower:
        disease_cat = "Tuberculosis"
    elif "donovanosis" in title_lower or "granuloma inguinale" in title_lower:
        disease_cat = "Donovanosis"
    elif "mycetoma" in title_lower:
        disease_cat = "Mycetoma"
    elif "pneumonia" in title_lower or "pneumocystis" in title_lower:
        disease_cat = "Pneumonia"
    elif "aspergillosis" in title_lower:
        disease_cat = "Aspergillosis"
    elif "cryptococcosis" in title_lower:
        disease_cat = "Cryptococcosis"
    elif "trypanosomiasis" in title_lower:
        disease_cat = "Trypanosomiasis"
    elif "filariasis" in title_lower:
        disease_cat = "Filariasis"
    elif "malaria" in title_lower:
        disease_cat = "Malaria"
    elif "sickle cell" in title_lower:
        disease_cat = "Sickle cell disease"
    else:
        disease_cat = "Pathology"

    cat_text = f"[[Category:{disease_cat}]]"

    wikitext = (
        "== {{int:filedesc}} ==\n"
        "{{Information\n"
        f"|description={{{{en|1={desc_clean}}}}}\n"
        "|date=\n"
        f"|source={{{{Wellcome Images}}}}<br/>Source: [{work_url} Wellcome Collection]\n"
        f"|author={credit}\n"
        "|permission=\n"
        "|other versions=\n"
        "}}\n\n"
        "== {{int:license-header}} ==\n"
        "{{cc-zero}}\n\n"
        f"{cat_text}\n"
    )

    return wikitext


def load_progress(progress_file):
    """Load upload progress from file."""
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            return json.load(f)
    return {"uploaded": [], "failed": [], "skipped": []}


def save_progress(progress_file, progress):
    """Save upload progress to file."""
    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Upload SB Lucas images to Wikimedia Commons")
    parser.add_argument("--dry-run", action="store_true", help="Preview uploads without actually uploading")
    parser.add_argument("--start", type=int, default=0, help="Row number to start from (0-indexed)")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of images to upload (0 = all)")
    parser.add_argument("--resume", action="store_true", help="Resume from last progress checkpoint")
    args = parser.parse_args()

    script_dir = Path(__file__).parent.resolve()
    csv_path = script_dir / CSV_FILE
    images_dir = script_dir / IMAGES_DIR
    progress_file = script_dir / "upload_progress.json"

    # Validate paths
    if not csv_path.exists():
        print(f"[error] CSV not found: {csv_path}")
        sys.exit(1)
    if not images_dir.exists():
        print(f"[error] Images directory not found: {images_dir}")
        sys.exit(1)

    # Load CSV
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    print(f"[info] Loaded {len(rows)} images from CSV")

    # Load progress
    progress = load_progress(progress_file)
    already_uploaded = set(progress["uploaded"])

    if args.resume:
        print(f"[info] Resuming: {len(already_uploaded)} already uploaded, {len(progress['failed'])} failed")

    # Setup pywikibot (skip for dry-run to avoid dependency requirement)
    if not args.dry_run:
        setup_pywikibot()
        import pywikibot
        site = pywikibot.Site("commons", "commons")
        site.login()
        print(f"[info] Logged in as: {site.user()}")

    # Process rows
    start = args.start
    limit = args.limit if args.limit > 0 else len(rows)
    to_process = rows[start : start + limit]

    uploaded_count = 0
    failed_count = 0
    skipped_count = 0

    print(f"\n{'='*60}")
    print(f"{'DRY RUN - ' if args.dry_run else ''}Uploading {len(to_process)} images")
    print(f"{'='*60}\n")

    for i, row in enumerate(to_process):
        filename = row["filename"]
        miro = row["miro_image_number"]
        filepath = images_dir / filename
        commons_title = f"File:{filename}"

        print(f"[{i+1}/{len(to_process)}] {filename}")

        # Skip if already uploaded
        if filename in already_uploaded:
            print(f"  → Skipped (already uploaded)")
            skipped_count += 1
            continue

        # Check file exists locally
        if not filepath.exists():
            print(f"  → FAILED: File not found at {filepath}")
            progress["failed"].append({"filename": filename, "error": "File not found"})
            failed_count += 1
            continue

        # Build wikitext
        wikitext = build_wikitext(row)

        if args.dry_run:
            print(f"  Title:  {commons_title}")
            print(f"  Size:   {filepath.stat().st_size / 1024 / 1024:.1f} MB")
            print(f"  Wikitext preview:")
            for line in wikitext.split("\n")[:8]:
                print(f"    {line}")
            print(f"    ...")
            uploaded_count += 1
            continue

        # Check if already exists on Commons
        try:
            page = pywikibot.FilePage(site, commons_title)
            if page.exists():
                print(f"  → Skipped (already exists on Commons)")
                progress["skipped"].append(filename)
                skipped_count += 1
                save_progress(progress_file, progress)
                continue
        except Exception as e:
            print(f"  → Warning checking existence: {e}")

        # Upload
        try:
            page = pywikibot.FilePage(site, commons_title)
            page.text = wikitext

            success = page.upload(
                str(filepath),
                comment=UPLOAD_COMMENT,
                text=wikitext,
                ignore_warnings=False,
                report_success=True,
            )

            if success:
                print(f"  → Uploaded successfully")
                progress["uploaded"].append(filename)
                uploaded_count += 1
            else:
                print(f"  → Upload returned False")
                progress["failed"].append({"filename": filename, "error": "Upload returned False"})
                failed_count += 1

        except Exception as e:
            error_msg = str(e)
            print(f"  → FAILED: {error_msg}")
            progress["failed"].append({"filename": filename, "error": error_msg})
            failed_count += 1

            # If rate-limited, wait longer
            if "rate" in error_msg.lower() or "throttle" in error_msg.lower():
                print(f"  → Rate limited, waiting 30s...")
                time.sleep(30)

        # Save progress after each upload
        if not args.dry_run:
            save_progress(progress_file, progress)

        # Delay between uploads
        if i < len(to_process) - 1:
            time.sleep(DELAY_SECONDS)

    # Summary
    print(f"\n{'='*60}")
    print(f"UPLOAD {'PREVIEW ' if args.dry_run else ''}COMPLETE")
    print(f"{'='*60}")
    print(f"  Uploaded: {uploaded_count}")
    print(f"  Skipped:  {skipped_count}")
    print(f"  Failed:   {failed_count}")
    print(f"  Total:    {uploaded_count + skipped_count + failed_count}")

    if not args.dry_run:
        print(f"\n  Progress saved to: {progress_file}")

    if failed_count > 0 and not args.dry_run:
        print(f"\n  Failed uploads:")
        for item in progress["failed"][-10:]:
            print(f"    {item['filename']}: {item['error']}")
        print(f"\n  To retry failed uploads, fix the issues and run again with --resume")


if __name__ == "__main__":
    main()
