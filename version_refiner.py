#!/usr/bin/env python3
"""
Narrow down a list of candidate Moodle tags by probing files that changed
between them.

Usage:
    python version_refiner.py https://moodle.example.com v4.5.13 v4.5.14 v4.5.15
    python version_refiner.py https://moodle.example.com v4.5.13 v4.5.15 --max-probes 40

Optional: set GITHUB_TOKEN to avoid the 60 requests/hour GitHub API limit.
Only use it against sites you own or are authorized to test.
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from version_common import HEADERS, RAW, md5, version_key

API_CMP = "https://api.github.com/repos/moodle/moodle/compare/{}...{}"

# Extensions a web server normally serves untouched (PHP is executed, so no).
# Lower number = tried first.
PRIORITY = {
    ".txt": 0,
    ".xml": 0,
    ".json": 1,
    ".md": 1,
    ".js": 2,
    ".css": 2,
    ".svg": 3,
    ".mustache": 3,
    ".feature": 3,
    ".html": 3,
    ".yml": 3,
    ".map": 4,
}


def get_hash(url, timeout=20, verify=True):
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout, verify=verify)
        if response.status_code == 200 and response.content:
            return md5(response.content)
    except requests.RequestException:
        pass
    return None


def changed_files(a, b):
    """Files added/modified between tag a and tag b."""
    session = requests.Session()
    session.headers.update(HEADERS)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        session.headers["Authorization"] = f"Bearer {token}"

    files, page = [], 1
    while True:
        response = session.get(
            API_CMP.format(a, b),
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        if response.status_code != 200:
            msg = response.json().get("message", "") if response.content else ""
            sys.exit(
                f"[!] GitHub API {response.status_code}: {msg}\n"
                "    (set GITHUB_TOKEN to raise the rate limit)"
            )
        data = response.json().get("files", [])
        files += [
            entry["filename"] for entry in data
            if entry["status"] in ("modified", "added", "renamed")
        ]
        if len(data) < 100:
            break
        page += 1
    return files


def servable(path):
    ext = os.path.splitext(path)[1].lower()
    return PRIORITY.get(ext)


def main():
    parser = argparse.ArgumentParser(description="Refine Moodle version candidates")
    parser.add_argument("url")
    parser.add_argument("tags", nargs="+", help="Candidate tags, e.g. v4.5.13 v4.5.14 v4.5.15")
    parser.add_argument(
        "--max-probes", type=int, default=30,
        help="Max requests to the target (default 30)",
    )
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between target requests")
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = "https://" + base

    candidates = sorted(set(args.tags), key=version_key)
    if len(candidates) < 2:
        sys.exit("[!] Need at least two candidate tags.")

    # 1. Collect files that changed between neighbouring candidates
    pool = {}
    for a, b in zip(candidates, candidates[1:]):
        paths = changed_files(a, b)
        print(f"[*] {a} -> {b}: {len(paths)} changed files")
        for f in paths:
            priority = servable(f)
            if priority is not None:
                pool[f] = priority

    probe_list = sorted(pool, key=lambda p: (pool[p], len(p)))
    print(f"[*] {len(probe_list)} servable candidates to test\n")
    if not probe_list:
        sys.exit("[!] Nothing to probe.")

    remaining = list(candidates)
    probes = anomalies = 0

    for path in probe_list:
        if len(remaining) == 1 or probes >= args.max_probes:
            break

        # 2. Hash this file at every remaining tag (GitHub, not the target)
        with ThreadPoolExecutor(max_workers=len(remaining)) as executor:
            results = executor.map(lambda tag: get_hash(RAW.format(tag, path)), remaining)
            hashes = dict(zip(remaining, results))

        if len(set(hashes.values())) <= 1:
            continue  # does not distinguish the remaining candidates

        # 3. Ask the target
        time.sleep(args.delay)
        probes += 1
        target_hash = get_hash(f"{base}/{path}", verify=not args.insecure)
        if not target_hash:
            print(f"  [-] {path}  (not reachable)")
            continue

        keep = [t for t in remaining if hashes[t] == target_hash]
        if not keep:
            anomalies += 1
            print(f"  [?] {path}  (matches none of {remaining})")
            continue

        print(f"  [+] {path}  -> {', '.join(keep)}")
        remaining = keep

    print("\n" + "=" * 70)
    if len(remaining) == 1:
        print(f"[✓] Version: {remaining[0]}")
    else:
        print(f"[~] Still ambiguous: {', '.join(remaining)}")
        if probes >= args.max_probes:
            print("    (hit --max-probes, raise it to keep trying)")
        else:
            print("    (no reachable file distinguishes them)")
    if anomalies:
        print(
            f"[!] {anomalies} file(s) matched no candidate: the site may be patched, "
            "customised, or behind a CDN that rewrites assets."
        )
    print("=" * 70)


if __name__ == "__main__":
    main()
