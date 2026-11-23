# Leo's Advent Terminal

An encrypted advent calendar. Every door's reward is encrypted with its answer; the published site only contains ciphertext.

## Your daily commands

Open a terminal in this folder, then:

| What | Command |
|---|---|
| Test the site on your laptop (all doors unlockable) | `python3 build.py --serve` then open http://localhost:8000 |
| Build the real site into `docs/` | `python3 build.py` |

In the test site, type `dev` for test commands: `dev unlock` (open all doors), `dev now 2026-12-19` (pretend it is that day), `dev reset` (forget progress).

## Your content

Everything lives in **`content/doors.yaml`** (private, never committed). `content/doors.example.yaml` explains every field. Photos and other files go in `content/` too.

## What never gets published

`content/*` is in `.gitignore`. The build also refuses to run if that protection is missing, and it scans its own output and fails if any answer or reward text shows up in plain text.

## Files

- `build.py` reads the content, encrypts it, writes `docs/` (real) or `.preview/` (test, never published)
- `site/` is the website code
- `docs/` is the built site that GitHub Pages serves
