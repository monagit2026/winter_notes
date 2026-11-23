#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Leo's Advent Terminal: build script.

  python3 build.py            real build   -> docs/      (this is what gets published)
  python3 build.py --preview  test build   -> .preview/  (dev commands, dates unlockable)
  python3 build.py --serve    test build + local web server on http://localhost:8000
  python3 build.py --serve --fill-todo   same, but every TODO gets a test value

Reads content/doors.yaml (private, never committed), encrypts every door's
reward with its answer, and writes only ciphertext + public puzzle text.
"""
import argparse
import functools
import hashlib
import html
import http.server
import json
import mimetypes
import os
import re
import shutil
import socketserver
import struct
import subprocess
import sys
import unicodedata
from base64 import b64encode

import yaml
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import puzzles
from puzzles import BuildError, is_todo

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
SITE = os.path.join(ROOT, "site")
DOCS = os.path.join(ROOT, "docs")
PREVIEW = os.path.join(ROOT, ".preview")
PRIVATE_YAML = os.path.join(CONTENT, "doors.yaml")
EXAMPLE_YAML = os.path.join(CONTENT, "doors.example.yaml")
PRIVATE_PATHS = ["content/doors.yaml", "worker/guard-prompt.private.txt"]

ITERATIONS = 600000  # PBKDF2-HMAC-SHA256 rounds; the browser must use the same number
DOORS = 24
DOOR_KEYS = {"day", "title", "prompt", "puzzle", "hints", "public", "answer", "reward"}
PUBLIC_KEYS = {"html_comment", "cookies", "files", "clue_contains_answer", "generate",
               "hidden_pages", "role_gate", "signal", "guard"}
REWARD_KEYS = {"title", "text", "physical", "media"}
TEXT_EXT = {".html", ".json", ".txt", ".md", ".csv", ".log", ".xml", ".svg"}
BROWSER_IMAGES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml", "image/avif"}
PREVIEW_BLOCK = re.compile(r"^[ \t]*//#PREVIEW\b.*?^[ \t]*//#END-PREVIEW[^\n]*\n?", re.S | re.M)
TODO_WORD = re.compile(r"\bTODO\b")
for _ext, _mime in ((".m4a", "audio/mp4"), (".mp3", "audio/mpeg"), (".wav", "audio/wav"),
                    (".mp4", "video/mp4"), (".mov", "video/quicktime"), (".webm", "video/webm")):
    mimetypes.add_type(_mime, _ext)
PAGE_PATH = re.compile(r"[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-]+)*")


def die(msg):
    print("\nERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def b64(data):
    return b64encode(data).decode("ascii")


def normalize(s):
    """Must match normalize() in site/js/shared.js exactly."""
    s = unicodedata.normalize("NFKD", str(s)).lower()
    return "".join(c for c in s if unicodedata.category(c)[0] in "LN")


# --------------------------------------------------------------------------
# Content loading
# --------------------------------------------------------------------------

_DROP = {"tag:yaml.org,2002:%s" % t for t in ("int", "float", "bool", "timestamp")}


class PlainLoader(yaml.SafeLoader):
    """Every plain value stays a string, so 01012020 or `no` are never
    silently turned into numbers or booleans."""


PlainLoader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in rules if tag not in _DROP]
    for ch, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def find_todo(obj, path=""):
    """Path of the first string that still says TODO, or None."""
    if isinstance(obj, str):
        return path if TODO_WORD.search(obj) else None
    if isinstance(obj, dict):
        for k, v in obj.items():
            hit = find_todo(v, "%s.%s" % (path, k) if path else str(k))
            if hit:
                return hit
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            hit = find_todo(v, "%s[%d]" % (path, i))
            if hit:
                return hit
    return None


def load_content(path, fill):
    with open(path, encoding="utf-8") as f:
        data = yaml.load(f, Loader=PlainLoader) or {}
    print("content: " + os.path.relpath(path, ROOT))

    s = data.get("settings") or {}
    site_path = "/" + (s.get("site_path") or "/").strip("/")
    settings = {
        "recipient": s.get("recipient") or "Leo",
        "year": int(s.get("year") or 2026),
        "month": int(s.get("month") or 12),
        "timezone": s.get("timezone") or "Europe/Berlin",
        "site_path": site_path if site_path.endswith("/") else site_path + "/",
    }
    doors, seen = [], set()
    for raw in data.get("doors") or []:
        try:
            day = int(raw.get("day"))
        except (TypeError, ValueError):
            die("a door has no valid 'day': %r" % (raw,))
        if not 1 <= day <= DOORS:
            die("door day must be 1-%d, got %d" % (DOORS, day))
        if day in seen:
            die("door %d appears twice in the content file" % day)
        seen.add(day)
        for k in set(raw) - DOOR_KEYS:
            die("door %d: unknown field '%s' (typo?)" % (day, k))
        raw.setdefault("public", None)
        raw["public"] = raw["public"] or {}
        for k in set(raw["public"]) - PUBLIC_KEYS:
            die("door %d: unknown public field '%s'" % (day, k))
        for k in set(raw.get("reward") or {}) - REWARD_KEYS:
            die("door %d: unknown reward field '%s'" % (day, k))
        if not raw.get("title") or not raw.get("puzzle"):
            die("door %d needs a 'title' and a 'puzzle'" % day)
        raw["day"] = day
        raw["_placeholder"] = find_todo(raw)

        answers = raw.get("answer")
        answers = answers if isinstance(answers, list) else [answers]
        answers = [str(a).strip() for a in answers if a is not None and str(a).strip()]
        raw["_auto"] = any(a.upper() == "AUTO" for a in answers)
        if fill:
            answers = ["test%d" % day if is_todo(a) else a for a in answers] or ["test%d" % day]
            raw["reward"] = rw = raw.get("reward") or {}
            for field in ("title", "text", "physical"):
                if is_todo(rw.get(field)):
                    rw[field] = "(placeholder)"
            guard = raw["public"].get("guard")
            if guard and is_todo(guard.get("url")):
                guard["url"] = "http://localhost:8787"
        raw["_answers"] = [] if raw["_auto"] else answers
        raw["_todo"] = (not raw["_auto"]) and (not answers or any(is_todo(a) for a in answers))
        doors.append(raw)
    doors.sort(key=lambda d: d["day"])
    return settings, doors


def ensure_private_content_is_ignored():
    """Refuse to build if git would let private files be committed."""
    for rel in PRIVATE_PATHS:
        if rel.startswith("worker/") and not os.path.isdir(os.path.join(ROOT, "worker")):
            continue
        try:
            r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT)
        except OSError:
            return
        if r.returncode == 1:
            die("%s is NOT listed in .gitignore. Fix .gitignore first, "
                "otherwise your secrets could be published." % rel)


def resolve_asset(rel, day):
    path = os.path.normpath(os.path.join(CONTENT, str(rel)))
    if not path.startswith(CONTENT + os.sep):
        die("door %d: file '%s' is outside the content/ folder" % (day, rel))
    if not os.path.isfile(path):
        die("door %d: file not found: content/%s" % (day, rel))
    return path


# --------------------------------------------------------------------------
# Encryption
# --------------------------------------------------------------------------

def pack_reward(door):
    """Reward -> one binary container: [4-byte length][manifest JSON][file bytes...]"""
    day = door["day"]
    rw = door.get("reward") or {}
    items, blobs = [], []
    for m in rw.get("media") or []:
        m = {"path": m} if isinstance(m, str) else dict(m)
        if is_todo(m.get("path")):
            continue  # placeholder: a real build refuses to run while this is TODO
        path = resolve_asset(m["path"], day)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if mime.startswith("image/") and mime not in BROWSER_IMAGES:
            die("door %d: %s is not a format browsers can show. Convert it to JPG or PNG "
                "(iPhone HEIC photos need converting)." % (day, os.path.basename(path)))
        with open(path, "rb") as f:
            data = f.read()
        kind = mime.split("/")[0] if mime.split("/")[0] in ("image", "audio", "video") else "file"
        items.append({"kind": kind, "name": os.path.basename(path), "mime": mime,
                      "length": len(data), "caption": m.get("caption")})
        blobs.append(data)
    manifest = {"title": rw.get("title"), "text": rw.get("text"),
                "physical": rw.get("physical"), "items": items}
    mj = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    return struct.pack(">I", len(mj)) + mj + b"".join(blobs)


def encrypt_door(door, out):
    day = door["day"]
    tag = "%02d" % day
    salt, dek = os.urandom(16), os.urandom(32)
    aad_wrap = ("leo-advent|%s|wrap" % tag).encode()
    aad_body = ("leo-advent|%s|body" % tag).encode()

    wraps, seen = [], set()
    for answer in door["_answers"]:
        norm = normalize(answer)
        if not norm:
            die("door %d: answer '%s' has no letters or digits" % (day, answer))
        if norm in seen:
            continue
        seen.add(norm)
        kek = hashlib.pbkdf2_hmac("sha256", norm.encode("utf-8"), salt, ITERATIONS, 32)
        iv = os.urandom(12)
        wraps.append({"iv": b64(iv), "ct": b64(AESGCM(kek).encrypt(iv, dek, aad_wrap))})

    iv = os.urandom(12)
    body = AESGCM(dek).encrypt(iv, pack_reward(door), aad_body)
    if len(body) > 95 * 1024 * 1024:
        die("door %d: reward is %d MB; GitHub allows 100 MB per file. Compress the video."
            % (day, len(body) // 1048576))
    # The file name carries a content hash, so a stale cached copy can never be
    # paired with a newer key file.
    bin_name = "%s-%s.bin" % (tag, hashlib.sha256(body).hexdigest()[:10])
    with open(os.path.join(out, "d", bin_name), "wb") as f:
        f.write(body)
    meta = {"v": 1, "iter": ITERATIONS, "salt": b64(salt), "wraps": wraps, "iv": b64(iv), "bin": bin_name}
    with open(os.path.join(out, "d", tag + ".json"), "w") as f:
        json.dump(meta, f)
    return len(body)


# --------------------------------------------------------------------------
# Site output
# --------------------------------------------------------------------------

def write_clue(out, name, data):
    dst = os.path.join(out, "clues", name)
    if os.path.exists(dst):
        die("two clue files are both called '%s'. Rename one." % name)
    with open(dst, "wb") as f:
        f.write(data)
    return {"name": name, "url": "clues/" + name}


def public_entry(door, out, ready):
    pub = door["public"]
    files = []
    for rel in pub.get("files") or []:
        src = resolve_asset(rel, door["day"])
        with open(src, "rb") as f:
            files.append(write_clue(out, os.path.basename(src), f.read()))
    for name, data in door["_gen"]:
        files.append(write_clue(out, name, data))
    entry = {
        "day": door["day"],
        "title": door["title"],
        "prompt": door.get("prompt") or "password:",
        "puzzle": door["puzzle"].strip("\n"),
        "hints": [str(h) for h in (door.get("hints") or [])],
        "files": files,
        "cookies": [{"name": c["name"], "value": str(c["value"])} for c in (pub.get("cookies") or [])],
        "ready": ready,
    }
    if door["_signal"]:
        entry["signal"] = door["_signal"]
    gate = pub.get("role_gate")
    if gate:
        entry["role_gate"] = {"name": gate.get("name") or "role", "start": gate.get("start") or "guest"}
    guard = pub.get("guard")
    if guard:
        entry["guard"] = {"url": str(guard.get("url") or ""), "name": guard.get("name") or "the guard",
                          "intro": guard.get("intro") or ""}
    return entry


def write_hidden_pages(out, doors):
    """Pages that robots.txt asks crawlers to stay away from."""
    disallow = []
    for d in doors:
        for page in d["_hidden"]:
            path = str(page.get("path") or "").strip("/")
            if not PAGE_PATH.fullmatch(path):
                die("door %d: hidden page path '%s' may only use letters, digits, - and _" % (d["day"], path))
            os.makedirs(os.path.join(out, path), exist_ok=True)
            body = html.escape(page["text"].strip("\n"))
            title = html.escape(str(page.get("title") or "restricted"))
            with open(os.path.join(out, path, "index.html"), "w", encoding="utf-8") as f:
                f.write(
                    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<meta name="robots" content="noindex"><title>%s</title></head>'
                    '<body style="background:#050a06;color:#39ff6a;font:16px/1.5 ui-monospace,Menlo,monospace;'
                    'padding:1.5rem"><pre style="white-space:pre-wrap">%s</pre></body></html>\n' % (title, body))
            disallow.append(path)
    return disallow


def copy_site(out, preview, settings, comments, build_id):
    for dirpath, _, names in os.walk(SITE):
        rel = os.path.relpath(dirpath, SITE)
        os.makedirs(os.path.join(out, rel), exist_ok=True)
        for name in names:
            if name == ".DS_Store":
                continue
            src, dst = os.path.join(dirpath, name), os.path.join(out, rel, name)
            if name.endswith(".js") or name.endswith(".html"):
                with open(src, encoding="utf-8") as f:
                    text = f.read()
                if not preview:
                    text = PREVIEW_BLOCK.sub("", text)
                if name == "index.html":
                    text = (text.replace("@@COMMENTS@@", comments)
                            .replace("@@V@@", build_id)
                            .replace("@@RECIPIENT@@", settings["recipient"]))
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(text)
            else:
                shutil.copyfile(src, dst)


def leak_check(out, doors):
    """Fail the build if any secret appears in plain text in the output."""
    haystacks = {}
    for dirpath, _, names in os.walk(out):
        for name in names:
            rel = os.path.relpath(os.path.join(dirpath, name), out)
            if rel.startswith("js" + os.sep) or os.path.splitext(name)[1].lower() not in TEXT_EXT:
                continue
            with open(os.path.join(dirpath, name), encoding="utf-8", errors="ignore") as f:
                haystacks[rel] = f.read().lower()

    problems = []

    def hunt(label, needle, day):
        needle = needle.strip().lower()
        if len(needle) < 3:
            return
        rx = re.compile(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])")
        for rel, text in haystacks.items():
            if rx.search(text):
                problems.append("door %d: %s '%s' appears in plain text in %s" % (day, label, needle[:40], rel))

    for door in doors:
        if door["_todo"]:
            continue
        day = door["day"]
        if not door["public"].get("clue_contains_answer"):
            for a in door["_answers"]:
                hunt("the answer", a, day)
                hunt("the answer", normalize(a), day)
        rw = door.get("reward") or {}
        for field in ("title", "text", "physical"):
            for ln in str(rw.get(field) or "").splitlines():
                if len(ln.strip()) >= 20:
                    hunt("reward " + field, ln, day)
        clue_names = {os.path.basename(str(p)) for p in door["public"].get("files") or []}
        for m in rw.get("media") or []:
            base = os.path.basename(m if isinstance(m, str) else m["path"])
            if base not in clue_names and not is_todo(base):
                hunt("reward file name", base, day)
    if problems:
        die("secrets would be published in plain text!\n  - " + "\n  - ".join(sorted(set(problems))) +
            "\n\nReword the puzzle text, or (only if it is on purpose) set "
            "public: clue_contains_answer: true on that door.")


def check_no_preview_leftovers(out):
    for dirpath, _, names in os.walk(out):
        for name in names:
            if os.path.splitext(name)[1] in (".js", ".html", ".css"):
                with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                    if "PREVIEW" in f.read():
                        die("preview code leaked into the real build (%s)" % name)


def build(args):
    preview = args.preview or args.serve
    if args.fill_todo and not preview:
        die("--fill-todo only works together with --preview or --serve (it invents test values).")
    out = PREVIEW if preview else DOCS
    if not args.example:
        ensure_private_content_is_ignored()
    path = EXAMPLE_YAML if args.example else PRIVATE_YAML
    if not os.path.exists(path):
        print("note: content/doors.yaml not found, using content/doors.example.yaml")
        path = EXAMPLE_YAML
    settings, doors = load_content(path, args.fill_todo)
    if args.fill_todo:
        print("note: --fill-todo is on, so every TODO is replaced by a test value")

    missing = [n for n in range(1, DOORS + 1) if n not in {d["day"] for d in doors}]
    if not preview:
        unfinished = ["door %d: %s" % (d["day"], d["_placeholder"]) for d in doors if d["_placeholder"]]
        if unfinished:
            die("these fields still say TODO:\n  - " + "\n  - ".join(unfinished) +
                "\n\nFill them in, or use --preview to test with placeholders.")
        if missing and not args.allow_missing:
            die("doors without any content: %s. Add them, or use --allow-missing."
                % ", ".join(map(str, missing)))

    if os.path.isdir(out):
        shutil.rmtree(out)
    for sub in ("d", "clues"):
        os.makedirs(os.path.join(out, sub))

    for d in doors:
        puzzles.prepare_door(d, lambda rel, day: resolve_asset(rel, day), args.fill_todo)

    comments = []
    for d in doors:
        c = d["public"].get("html_comment")
        if c:
            if "--" in c or ">" in c:
                die("door %d: html_comment must not contain '--' or '>'" % d["day"])
            comments.append("<!-- %s -->" % c)

    build_id = hashlib.sha256(os.urandom(8)).hexdigest()[:8]
    copy_site(out, preview, settings, "\n".join(comments), build_id)

    public, total = [], 0
    for d in doors:
        guard = d["public"].get("guard")
        if guard and not preview and not str(guard.get("url") or "").startswith("https://"):
            die("door %d: the guard url must start with https:// (your Cloudflare Worker address)" % d["day"])
        ready = not d["_todo"]
        public.append(public_entry(d, out, ready))
        if ready:
            size = encrypt_door(d, out)
            total += size
            print("  door %02d  encrypted  %7.1f KB" % (d["day"], size / 1024.0))
        else:
            print("  door %02d  TODO (placeholder)" % d["day"])
    hidden = write_hidden_pages(out, doors)
    with open(os.path.join(out, "doors.json"), "w", encoding="utf-8") as f:
        json.dump(public, f, ensure_ascii=False, indent=1)
    config = {k: v for k, v in settings.items() if k != "site_path"}
    config.update(preview=bool(preview), total=DOORS, build=build_id)
    with open(os.path.join(out, "config.json"), "w") as f:
        json.dump(config, f)
    with open(os.path.join(out, "robots.txt"), "w") as f:
        f.write("User-agent: *\nAllow: /\n" +
                "".join("Disallow: %s%s/\n" % (settings["site_path"], p) for p in hidden))
    open(os.path.join(out, ".nojekyll"), "w").close()

    leak_check(out, doors)
    if not preview:
        check_no_preview_leftovers(out)

    print("\nOK: %d doors built, %.1f MB of encrypted rewards -> %s"
          % (len(doors), total / 1048576.0, os.path.relpath(out, ROOT) + "/"))
    print("OK: leak check passed (no answers or rewards in plain text)")
    if preview:
        print("\nThis is a PREVIEW build. Do NOT publish it.")
    elif missing:
        print("note: doors with no content yet: %s" % ", ".join(map(str, missing)))
    return out


def serve(directory, port=8000):
    handler = functools.partial(NoCacheHandler, directory=directory)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), handler) as httpd:
        print("\nOpen http://localhost:%d in your browser (Ctrl+C to stop)" % port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", action="store_true", help="test build into .preview/")
    ap.add_argument("--serve", action="store_true", help="test build and serve it locally")
    ap.add_argument("--fill-todo", action="store_true", help="(test builds only) replace every TODO by a test value")
    ap.add_argument("--example", action="store_true", help="use content/doors.example.yaml")
    ap.add_argument("--allow-missing", action="store_true", help="real build even if some doors have no content")
    a = ap.parse_args()
    try:
        result = build(a)
    except BuildError as e:
        die(str(e))
    if a.serve:
        serve(result)
