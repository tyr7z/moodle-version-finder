#!/usr/bin/env python3
"""Shared settings and helpers for the Moodle version tools."""

import hashlib
import re

DEFAULT_DB = "version.txt"
HEADERS = {"User-Agent": "Mozilla/5.0"}
RAW = "https://raw.githubusercontent.com/moodle/moodle/{}/{}"

FILES = [
    "admin/environment.xml",
    "composer.lock",
    "lib/upgrade.txt",
    "privacy/export_files/general.js",
    "composer.json",
    "question/upgrade.txt",
    "admin/tool/lp/tests/behat/course_competencies.feature",
]


def md5(data):
    """Return the content hash used by the version database."""
    return hashlib.md5(data).hexdigest()


def version_key(tag):
    """Sort Moodle tags by version, release stage, and prerelease number."""
    base, _, suffix = tag.partition("-")
    numbers = tuple(int(number) for number in re.findall(r"\d+", base))
    lower_tag = tag.lower()
    if "alpha" in lower_tag:
        stage = 0
    elif "beta" in lower_tag:
        stage = 1
    elif "rc" in lower_tag:
        stage = 2
    elif tag.endswith("+"):
        stage = 4
    else:
        stage = 3
    suffix_numbers = tuple(int(number) for number in re.findall(r"\d+", suffix))
    return numbers, stage, suffix_numbers
