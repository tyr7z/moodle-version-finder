#!/usr/bin/env python3
"""Collect public Moodle release file hashes in version.txt.

Usage:
    python version_scraper.py
"""

import os

import requests

from version_common import DEFAULT_DB, FILES, HEADERS, RAW, md5, version_key

API_TAGS = "https://api.github.com/repos/moodle/moodle/tags"
DB_FILE = DEFAULT_DB


def sort_db():
    """Sort DB newest tag first. Order inside a tag is kept (stable sort)."""
    if not os.path.exists(DB_FILE):
        return

    with open(DB_FILE, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]

    entries = []
    seen = set()

    for line in lines:
        parts = line.split(",", 2)

        if len(parts) != 3:
            continue

        # Keep the first entry for each tag and path.
        key = (parts[0], parts[2])
        if key in seen:
            continue
        seen.add(key)

        entries.append(parts)

    entries.sort(key=lambda p: version_key(p[0]), reverse=True)

    tmp = DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for tag, h, path in entries:
            f.write(f"{tag},{h},{path}\n")

    os.replace(tmp, DB_FILE)
    print(f"Sorted {len(entries)} entries in {DB_FILE}")


def load_existing():
    tags_done = set()

    if not os.path.exists(DB_FILE):
        return tags_done

    with open(DB_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",", 2)

            if len(parts) != 3:
                continue

            tag = parts[0]
            tags_done.add(tag)

    return tags_done


def get_tags():
    tags = []
    page = 1

    while True:
        response = requests.get(
            API_TAGS, headers=HEADERS, params={"per_page": 100, "page": page}, timeout=30
        )
        response.raise_for_status()
        data = response.json()

        if not data:
            break

        tags.extend(t["name"] for t in data)
        page += 1

    return tags


def fetch_hash(tag, path):
    url = RAW.format(tag, path)

    try:
        response = requests.get(url, headers=HEADERS, timeout=20)

        if response.status_code != 200:
            return None

        return md5(response.content)

    except requests.RequestException:
        return None


def main():
    tags_done = load_existing()
    print("Existing tags:", len(tags_done))

    tags = get_tags()
    print("Total tags:", len(tags))

    try:
        with open(DB_FILE, "a", encoding="utf-8") as db:
            for tag in tags:
                if tag in tags_done:
                    print("Skip tag", tag)
                    continue

                print("Processing", tag)

                for path in FILES:
                    h = fetch_hash(tag, path)

                    if not h:
                        continue

                    line = f"{tag},{h},/{path}"

                    db.write(line + "\n")

                db.flush()
    finally:
        # runs on normal finish and on Ctrl+C / errors
        sort_db()


if __name__ == "__main__":
    main()