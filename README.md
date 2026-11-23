# Leo's Advent Terminal

An encrypted advent calendar. Every door's reward is encrypted with its answer; the published site only contains ciphertext.

## Your commands

Open a terminal in this folder, then:

| What | Command |
|---|---|
| Test the whole site, with fake values for everything still marked TODO | `python3 build.py --serve --fill-todo` then open http://localhost:8000 |
| Test with only what you have filled in so far | `python3 build.py --serve` |
| Build the real site into `docs/` | `python3 build.py` (refuses to run while any TODO is left) |

In the test site, type `dev` for test commands: `dev unlock` (open all doors), `dev now 2026-12-19` (pretend it is that day), `dev reset` (forget progress).

To publish: build, then open GitHub Desktop, commit and click "Push origin".

## Your content

Everything lives in **`content/doors.yaml`** (private, never committed). Search it for `TODO`: those are the things only you can fill in. `content/doors.example.yaml` explains every field and every puzzle shortcut. Photos and other files go in `content/` too (JPG or PNG, not HEIC).

## Door 19

The AI guard lives in `worker/` (private). Follow `worker/README.md`.

## What never gets published

`content/*` and `worker/` are in `.gitignore`. The build refuses to run if that protection is missing, and it scans its own output and fails if any answer or reward text shows up in plain text.

## Back up

`content/` and `worker/` are not on GitHub on purpose. Copy them to a cloud drive or USB stick now and then.

## Files

- `build.py` and `puzzles.py`: read the content, encrypt it, write `docs/` (real) or `.preview/` (test, never published)
- `site/`: the website code
- `docs/`: the built site that GitHub Pages serves
