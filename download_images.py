#!/usr/bin/env python3
"""
Download images from the Wellcome Collection API.

This script fetches image metadata and downloads full-resolution images
for the SB Lucas pathology collection and Museum Objects collection.

Usage:
  python download_images.py                    # Download all
  python download_images.py --collection sb_lucas
  python download_images.py --collection museum
  python download_images.py --check-commons    # Skip images already on Commons
"""

import urllib.request
import urllib.parse
import json
import csv
import os
import re
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed


def fetch_images_from_api(query_params, include_fields):
    """Fetch all image records from the Wellcome Collection API."""
    base_url = "https://api.wellcomecollection.org/catalogue/v2/images"
    all_images = []
    page = 1

    while True:
        url = f"{base_url}?{query_params}&pageSize=100&page={page}&include={include_fields}"
        print(f"  Fetching page {page}...", end=" ")
        req = urllib.request.Request(url, headers={"User-Agent": "WellcomeDownloader/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        results = data.get("results", [])
        all_images.extend(results)
        print(f"got {len(results)} (total: {len(all_images)})")
        if len(results) < 100:
            break
        page += 1
        time.sleep(0.3)

    return all_images


def fetch_work_details(work_ids):
    """Fetch detailed metadata for each work."""
    work_details = {}

    def fetch_one(work_id):
        url = f"https://api.wellcomecollection.org/catalogue/v2/works/{work_id}?include=contributors,subjects,genres,identifiers,production"
        req = urllib.request.Request(url, headers={"User-Agent": "WellcomeDownloader/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return work_id, json.loads(resp.read().decode())

    batch_size = 50
    for start in range(0, len(work_ids), batch_size):
        batch = work_ids[start : start + batch_size]
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_one, wid): wid for wid in batch}
            for future in as_completed(futures):
                try:
                    wid, data = future.result()
                    work_details[wid] = data
                except Exception as e:
                    wid = futures[future]
                    print(f"  Error fetching {wid}: {e}")
                    work_details[wid] = {}
        done = min(start + batch_size, len(work_ids))
        print(f"  [{done}/{len(work_ids)}] work details fetched")
        time.sleep(0.5)

    return work_details


def make_commons_filename(title, miro_number):
    """Convert title to Commons-style filename."""
    name = title.strip()
    name = re.sub(r'[:()/\\,\.\'\"\[\]{}!?;]', " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace(" ", "_")
    name = re.sub(r"_+", "_", name).strip("_")
    max_len = 200 - len(f"_Wellcome_{miro_number}.jpg")
    if len(name) > max_len:
        name = name[:max_len].rstrip("_")
    return f"{name}_Wellcome_{miro_number}.jpg"


def check_commons_existence(miro_ids):
    """Check which images already exist on Wikimedia Commons."""
    found = {}

    def search_one(miro_id):
        params = urllib.parse.urlencode({
            "action": "query", "list": "search", "srnamespace": "6",
            "srsearch": f'intitle:"{miro_id}"', "srlimit": "5", "format": "json",
        })
        url = f"https://commons.wikimedia.org/w/api.php?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "WellcomeCommonsCheck/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        titles = [r["title"] for r in data.get("query", {}).get("search", [])]
        return [t for t in titles if miro_id in t]

    batch_size = 30
    for start in range(0, len(miro_ids), batch_size):
        batch = miro_ids[start : start + batch_size]
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(search_one, mid): mid for mid in batch}
            for future in as_completed(futures):
                mid = futures[future]
                try:
                    results = future.result()
                    if results:
                        found[mid] = results
                except Exception:
                    pass
        done = min(start + batch_size, len(miro_ids))
        if done % 120 == 0 or done == len(miro_ids):
            print(f"  [{done}/{len(miro_ids)}] checked — {len(found)} found on Commons")
        time.sleep(0.5)

    return found


def build_csv_rows(images, work_details):
    """Build CSV rows from API data."""
    rows = []
    for img in images:
        work_id = img["source"]["id"]
        work = work_details.get(work_id, {})

        loc_url = img.get("locations", [{}])[0].get("url", "")
        iiif_id = loc_url.split("/image/")[1].split("/")[0] if "/image/" in loc_url else ""

        identifiers = work.get("identifiers", [])
        miro_number = ""
        for ident in identifiers:
            if ident.get("identifierType", {}).get("id") == "miro-image-number":
                miro_number = ident.get("value", "")
                break
        if not miro_number:
            miro_number = iiif_id

        subjects = "; ".join([s.get("label", "") for s in work.get("subjects", [])])
        genres = "; ".join([g.get("label", "") for g in work.get("genres", [])])
        contributors = "; ".join([c.get("agent", {}).get("label", "") for c in work.get("contributors", [])])
        license_info = img.get("locations", [{}])[0].get("license", {})
        credit = img.get("locations", [{}])[0].get("credit", "")

        filename = make_commons_filename(img.get("source", {}).get("title", ""), miro_number)

        rows.append({
            "image_id": img.get("id", ""),
            "work_id": work_id,
            "miro_image_number": miro_number,
            "title": img.get("source", {}).get("title", ""),
            "description": (work.get("description", "") or ""),
            "work_type": work.get("workType", {}).get("label", ""),
            "contributors": contributors,
            "subjects": subjects,
            "genres": genres,
            "license_id": license_info.get("id", ""),
            "license_label": license_info.get("label", ""),
            "license_url": license_info.get("url", ""),
            "credit": credit,
            "iiif_image_id": iiif_id,
            "full_image_url": f"https://iiif.wellcomecollection.org/image/{iiif_id}/full/full/0/default.jpg",
            "work_page_url": f"https://wellcomecollection.org/works/{work_id}",
            "image_page_url": f"https://wellcomecollection.org/works/{work_id}/images?id={img['id']}",
            "filename": filename,
        })

    return rows


def download_images(rows, output_dir):
    """Download images in parallel batches."""
    os.makedirs(output_dir, exist_ok=True)

    # Write URL list
    url_list = []
    for row in rows:
        filepath = os.path.join(output_dir, row["filename"])
        if not os.path.exists(filepath) or os.path.getsize(filepath) < 1000:
            url_list.append((row["full_image_url"], row["filename"]))

    if not url_list:
        print("  All images already downloaded")
        return

    print(f"  Downloading {len(url_list)} images...")

    def download_one(url, filename):
        filepath = os.path.join(output_dir, filename)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(filepath, "wb") as f:
                f.write(resp.read())
        return filename

    batch_size = 50
    downloaded = 0
    for start in range(0, len(url_list), batch_size):
        batch = url_list[start : start + batch_size]
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {executor.submit(download_one, url, fn): fn for url, fn in batch}
            for future in as_completed(futures):
                try:
                    future.result()
                    downloaded += 1
                except Exception as e:
                    fn = futures[future]
                    print(f"  Failed: {fn}: {e}")
        done = min(start + batch_size, len(url_list))
        print(f"  [{done}/{len(url_list)}] downloaded")
        time.sleep(0.5)

    print(f"  Done: {downloaded} images downloaded to {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Download Wellcome Collection images")
    parser.add_argument("--collection", choices=["sb_lucas", "museum", "all"], default="all")
    parser.add_argument("--check-commons", action="store_true", help="Skip images already on Commons")
    parser.add_argument("--skip-download", action="store_true", help="Only generate CSV, skip image download")
    args = parser.parse_args()

    include = "source.contributors,source.subjects,source.languages,source.genres"

    if args.collection in ("sb_lucas", "all"):
        print("\n=== SB Lucas Pathology Collection ===")
        print("Fetching from API...")
        images = fetch_images_from_api(
            'source.contributors.agent.label=%22SB+Lucas%22', include
        )
        print(f"Found {len(images)} images")

        print("Fetching work details...")
        work_ids = list(set(img["source"]["id"] for img in images))
        details = fetch_work_details(work_ids)

        rows = build_csv_rows(images, details)

        if args.check_commons:
            print("Checking Commons for existing uploads...")
            miro_ids = [r["miro_image_number"] for r in rows]
            existing = check_commons_existence(miro_ids)
            before = len(rows)
            rows = [r for r in rows if r["miro_image_number"] not in existing]
            print(f"  {before - len(rows)} already on Commons, {len(rows)} to upload")

        csv_path = "sb_lucas_wellcome_images.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"CSV saved: {csv_path} ({len(rows)} rows)")

        if not args.skip_download:
            download_images(rows, "images/sb_lucas")

    if args.collection in ("museum", "all"):
        print("\n=== Museum Objects Collection ===")
        print("Fetching from API...")
        images = fetch_images_from_api(
            'source.genres.label=%22Museum+object%22&sortOrder=desc&sort=source.production.dates', include
        )
        print(f"Found {len(images)} images")

        print("Fetching work details...")
        work_ids = list(set(img["source"]["id"] for img in images))
        details = fetch_work_details(work_ids)

        rows = build_csv_rows(images, details)

        if args.check_commons:
            print("Checking Commons for existing uploads...")
            miro_ids = [r["miro_image_number"] for r in rows]
            existing = check_commons_existence(miro_ids)
            before = len(rows)
            rows = [r for r in rows if r["miro_image_number"] not in existing]
            print(f"  {before - len(rows)} already on Commons, {len(rows)} to upload")

        csv_path = "museum_objects.csv"
        if rows:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            print(f"CSV saved: {csv_path} ({len(rows)} rows)")

            if not args.skip_download:
                download_images(rows, "images/museum_objects")
        else:
            print("No new images to download")

    print("\nDone!")


if __name__ == "__main__":
    main()
