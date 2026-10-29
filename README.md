# Moodle version finder

Estimate a Moodle site's version by comparing public file hashes with release
tags. Several releases can share the same files, so the result may be a range.
Modified files or blocked requests can make the result less reliable.

## Usage

Install Python 3 and the dependency:

```sh
python -m pip install -r requirements.txt
python version_finder.py https://moodle.example.com
```

Use the Moodle base URL, including a subdirectory if needed. Run
`python version_finder.py --help` for timeout, TLS, and output options.

If several tags remain, probe files that changed between them:

```sh
python version_refiner.py https://moodle.example.com v4.5.13 v4.5.14
```

`version.txt` contains the reference hashes. To collect missing release tags:

> [!NOTE]
> The included `version.txt` may be outdated and missing newer Moodle releases.
> Run `version_scraper.py` to add hashes for release tags not yet in the database.

```sh
python version_scraper.py
```

The scraper reads public Moodle releases from GitHub and updates `version.txt`
in the current directory. The refiner also uses GitHub; set `GITHUB_TOKEN` if
you run into its API rate limit.

Only check sites you own or have permission to test.
