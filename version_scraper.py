import hashlib
import requests
import os
import time

API_TAGS = "https://api.github.com/repos/moodle/moodle/tags"

FILES = [
    "admin/environment.xml",
    "composer.lock",
    "lib/upgrade.txt",
    "privacy/export_files/general.js",
    "composer.json",
    "question/upgrade.txt",
    "admin/tool/lp/tests/behat/course_competencies.feature",
]

RAW = "https://raw.githubusercontent.com/moodle/moodle/{}/{}"
DB_FILE = "version.txt"


def md5(data):
    return hashlib.md5(data).hexdigest()


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
        r = requests.get(API_TAGS, params={"per_page": 100, "page": page})
        data = r.json()

        if not data:
            break

        tags.extend(t["name"] for t in data)
        page += 1

    return tags


def fetch_hash(tag, path):
    url = RAW.format(tag, path)

    try:
        r = requests.get(url, timeout=20)

        if r.status_code != 200:
            return None

        return md5(r.content)

    except:
        return None


def main():
    tags_done = load_existing()
    print("Existing tags:", len(tags_done))

    tags = get_tags()
    print("Total tags:", len(tags))

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
            # time.sleep(0.15)


if __name__ == "__main__":
    main()
