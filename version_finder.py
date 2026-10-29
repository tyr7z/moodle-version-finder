#!/usr/bin/env python3
"""
Fingerprint the Moodle version of a site by hashing publicly reachable files
and comparing them with the hashes collected in version.txt.

Only use it against sites you own or are authorized to test.

Usage:
    python version_finder.py https://moodle.example.com
    python version_finder.py https://example.com/moodle --db version.txt --top 10
"""

import argparse
import hashlib
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests

DEFAULT_DB = "version.txt"

# Same list as the scraper (must match the paths stored in version.txt)
FILES = [
    "admin/environment.xml",
    "composer.lock",
    "lib/upgrade.txt",
    "privacy/export_files/general.js",
    "composer.json",
    "question/upgrade.txt",
    "admin/tool/lp/tests/behat/course_competencies.feature",
]

HEADERS = {"User-Agent": "Mozilla/5.0"}


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
def load_db(path):
    """
    Returns:
        by_file: {path: {hash: set(tags)}}
        by_tag:  {tag: {path: hash}}
    """
    by_file = defaultdict(lambda: defaultdict(set))
    by_tag = defaultdict(dict)

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",", 2)
                if len(parts) != 3:
                    continue
                tag, h, p = parts
                p = p.lstrip("/")
                by_file[p][h].add(tag)
                by_tag[tag][p] = h
    except FileNotFoundError:
        sys.exit(f"[!] Database '{path}' not found. Run the scraper first.")

    if not by_tag:
        sys.exit(f"[!] Database '{path}' is empty.")

    return by_file, by_tag


def version_key(tag):
    """Sort key so that v4.1.2 > v4.1.2-rc1 > v4.1.2-beta > v4.1.1 ..."""
    nums = tuple(int(n) for n in re.findall(r"\d+", tag.split("-")[0]))
    low = tag.lower()
    if "alpha" in low:
        stage = 0
    elif "beta" in low:
        stage = 1
    elif "rc" in low:
        stage = 2
    elif tag.endswith("+"):
        stage = 4
    else:
        stage = 3
    suffix = tuple(int(n) for n in re.findall(r"\d+", "-".join(tag.split("-")[1:])))
    return nums, stage, suffix


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
def fetch_hash(base, path, timeout, verify):
    url = f"{base}/{path}"
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            verify=verify,
            allow_redirects=True,
        )
        if r.status_code != 200 or not r.content:
            return path, None, r.status_code
        return path, hashlib.md5(r.content).hexdigest(), 200
    except requests.RequestException as e:
        return path, None, type(e).__name__


def fingerprint_target(base, timeout, verify, threads):
    found = {}
    with ThreadPoolExecutor(max_workers=threads) as ex:
        results = ex.map(lambda p: fetch_hash(base, p, timeout, verify), FILES)
        for path, h, status in results:
            if h:
                print(f"  [+] {path:<58} {h}")
                found[path] = h
            else:
                print(f"  [-] {path:<58} ({status})")
    return found


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
def score_tags(found, by_file, by_tag):
    """
    For every tag count:
      matches    - files whose hash equals the target's hash
      mismatches - files that exist in the tag AND on the target but differ
    Files missing on the target (404/blocked) are ignored.
    """
    scores = {}
    for tag, files in by_tag.items():
        matches = mismatches = 0
        for path, h in found.items():
            tag_hash = files.get(path)
            if tag_hash is None:
                continue
            if tag_hash == h:
                matches += 1
            else:
                mismatches += 1
        scores[tag] = (matches, mismatches)
    return scores


def summarize(tags):
    tags = sorted(tags, key=version_key)
    return tags[0] if len(tags) == 1 else f"{tags[0]}  ->  {tags[-1]}"


def main():
    ap = argparse.ArgumentParser(description="Moodle version fingerprinter")
    ap.add_argument("url", help="Base URL of the Moodle site")
    ap.add_argument("--db", default=DEFAULT_DB, help="Hash database (default: version.txt)")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--threads", type=int, default=5)
    ap.add_argument("--top", type=int, default=15, help="Max candidates to list")
    ap.add_argument("--insecure", action="store_true", help="Do not verify TLS certificates")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    if not re.match(r"^https?://", base):
        base = "https://" + base

    by_file, by_tag = load_db(args.db)
    print(f"[*] Database: {len(by_tag)} tags loaded")
    print(f"[*] Target:   {base}\n")

    if args.insecure:
        requests.packages.urllib3.disable_warnings()

    found = fingerprint_target(base, args.timeout, not args.insecure, args.threads)

    if not found:
        sys.exit("\n[!] No fingerprint files reachable. The server probably blocks them.")

    # Which fetched files are actually known to the DB?
    known = {p: h for p, h in found.items() if h in by_file.get(p, {})}
    unknown = [p for p in found if p not in known]
    if unknown:
        print(f"\n[!] {len(unknown)} file(s) have hashes not in the DB "
              f"(custom/patched install, newer release, or soft-404 page):")
        for p in unknown:
            print(f"      {p}")

    if not known:
        sys.exit("\n[!] None of the hashes match a known release.")

    scores = score_tags(found, by_file, by_tag)
    best = max((m - mm, m) for m, mm in scores.values())
    best_tags = [t for t, (m, mm) in scores.items() if (m - mm, m) == best]
    matches, _ = best
    # `best` is (m - mm, m); recompute for display
    m_best = scores[best_tags[0]][0]
    mm_best = scores[best_tags[0]][1]

    exact = mm_best == 0 and m_best == len(known)

    print("\n" + "=" * 70)
    if exact:
        print(f"[✓] All {m_best} recognised file(s) agree.")
    else:
        print(f"[~] Best partial match: {m_best} matching, {mm_best} differing file(s).")
    print(f"[✓] Version range: {summarize(best_tags)}")
    print("=" * 70)

    ordered = sorted(best_tags, key=version_key, reverse=True)
    print(f"\nCandidates ({len(ordered)}):")
    for t in ordered[: args.top]:
        print(f"  - {t}")
    if len(ordered) > args.top:
        print(f"  ... and {len(ordered) - args.top} more (use --top)")

    # Per-file hint: which tags does each individual hash point to?
    print("\nPer-file breakdown:")
    for p, h in known.items():
        tags = by_file[p][h]
        print(f"  {p}\n      -> {summarize(tags)}  ({len(tags)} tags)")


if __name__ == "__main__":
    main()