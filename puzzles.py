# -*- coding: utf-8 -*-
"""Puzzle helpers for build.py: text templates ({{caesar 9 HELLO}}) and file
generators (Morse audio, log files, number lists, splits, JPEGs with EXIF).

Everything here is deterministic, so rebuilding never changes a puzzle."""
import array
import base64
import hashlib
import io
import json
import math
import random
import re
import struct
import wave
from datetime import datetime, timedelta


class BuildError(Exception):
    """A mistake in the content file; build.py prints it and stops."""


class TodoInput(Exception):
    """A generator input is still TODO, so the door cannot be built yet."""


def is_todo(v):
    return isinstance(v, str) and v.strip().upper() == "TODO"


# --------------------------------------------------------------------------
# Text templates
# --------------------------------------------------------------------------

MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.",
    "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.",
    "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.", "S": "...", "T": "-", "U": "..-",
    "V": "...-", "W": ".--", "X": "-..-", "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
}


def _shift(text, k):
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 + k) % 26 + 97))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 + k) % 26 + 65))
        else:
            out.append(ch)
    return "".join(out)


def t_caesar(shift, text):
    return _shift(text, int(shift))


def t_vigenere(key, text):
    ks = [ord(c) - 97 for c in key.lower() if "a" <= c <= "z"]
    if not ks:
        raise BuildError("vigenere needs a key made of letters")
    out, i = [], 0
    for ch in text:
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
            out.append(_shift(ch, ks[i % len(ks)]))
            i += 1
        else:
            out.append(ch)
    return "".join(out)


def t_rot13(text):
    return _shift(text, 13)


def t_reverse(text):
    return text[::-1]


def t_revrot13(text):
    return _shift(text[::-1], 13)


def t_base64(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def t_hex(text):
    return text.encode("utf-8").hex()


def t_binary(text):
    return " ".join(format(b, "08b") for b in text.encode("utf-8"))


def t_morse(text):
    words = []
    for w in text.upper().split():
        words.append(" ".join(MORSE[c] for c in w if c in MORSE))
    return " / ".join(words)


def t_anagram(text):
    letters = [c for c in text.upper() if c.isalnum()]
    rng = random.Random("anagram:" + text)
    for _ in range(100):
        shuffled = letters[:]
        rng.shuffle(shuffled)
        if shuffled != letters or len(set(letters)) < 2:
            break
    return "".join(shuffled)


def t_sha256(text):
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def t_ascii(shift, text):
    return " ".join(str(ord(c) + int(shift)) for c in text)


# name -> (number of fixed arguments before the text, function)
TEMPLATES = {
    "caesar": (1, t_caesar), "vigenere": (1, t_vigenere), "ascii": (1, t_ascii),
    "rot13": (0, t_rot13), "reverse": (0, t_reverse), "revrot13": (0, t_revrot13),
    "base64": (0, t_base64), "hex": (0, t_hex), "binary": (0, t_binary),
    "morse": (0, t_morse), "anagram": (0, t_anagram), "sha256": (0, t_sha256),
}

_TEMPLATE_RE = re.compile(r"\{\{\s*([a-z0-9_]+)\s+(.*?)\s*\}\}", re.S)


def with_answer(text, answer):
    return str(text).replace("@answer", answer if answer else "TODO")


def expand(text, answer, day, fill):
    """Replace @answer and {{template ...}} in a piece of text."""
    text = str(text)

    def sub(m):
        name, rest = m.group(1), m.group(2)
        if name not in TEMPLATES:
            raise BuildError("door %d: unknown template {{%s ...}}. Known: %s"
                             % (day, name, ", ".join(sorted(TEMPLATES))))
        nfixed, fn = TEMPLATES[name]
        parts = rest.split(None, nfixed)
        if len(parts) < nfixed + 1:
            raise BuildError("door %d: {{%s}} is missing something" % (day, name))
        args, body = parts[:nfixed], with_answer(parts[nfixed], answer)
        if is_todo(body):
            if not fill:
                return "[TODO]"
            body = "TESTWORD"
        try:
            return fn(*(args + [body]))
        except (ValueError, KeyError) as e:
            raise BuildError("door %d: {{%s %s}} failed: %s" % (day, name, rest, e))

    return _TEMPLATE_RE.sub(sub, with_answer(text, answer))


# --------------------------------------------------------------------------
# Signals (light / sound sequences) and Morse audio
# --------------------------------------------------------------------------

def signal_pattern(text, mode):
    """[[1, ms_on], [0, ms_off], ...] for a lamp. mode: 'binary' or 'morse'."""
    p = []
    if mode == "morse":
        for wi, word in enumerate(text.upper().split()):
            if wi:
                p.append([0, 1400])
            for li, ch in enumerate(word):
                if ch not in MORSE:
                    continue
                if li:
                    p.append([0, 600])
                for si, sym in enumerate(MORSE[ch]):
                    if si:
                        p.append([0, 200])
                    p.append([1, 200 if sym == "." else 600])
    elif mode == "binary":
        for ci, ch in enumerate(text.encode("utf-8")):
            if ci:
                p.append([0, 1000])
            for bi, bit in enumerate(format(ch, "08b")):
                if bi:
                    p.append([0, 300])
                p.append([1, 700 if bit == "1" else 250])
    else:
        raise BuildError("signal mode must be 'binary' or 'morse'")
    return p


def morse_wav(text, wpm=12, freq=650, repeats=2):
    rate = 8000
    unit = 1.2 / float(wpm)
    samples = array.array("h")

    def silence(units):
        samples.extend([0] * int(rate * unit * units))

    def tone(units):
        n = int(rate * unit * units)
        fade = int(rate * 0.006)
        for i in range(n):
            env = min(1.0, i / float(fade), (n - i) / float(fade))
            samples.append(int(0.5 * env * 32767 * math.sin(2 * math.pi * freq * i / rate)))

    silence(7)
    for rep in range(repeats):
        for wi, word in enumerate(text.upper().split()):
            if wi:
                silence(7)
            for li, ch in enumerate(word):
                if ch not in MORSE:
                    continue
                if li:
                    silence(3)
                for si, sym in enumerate(MORSE[ch]):
                    if si:
                        silence(1)
                    tone(1 if sym == "." else 3)
        if rep < repeats - 1:
            silence(28)
    silence(7)
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(samples.tobytes())
    w.close()
    return buf.getvalue()


# --------------------------------------------------------------------------
# Generators. Each returns (file name, bytes, computed answers or None)
# --------------------------------------------------------------------------

def _need(spec, key, day):
    if key not in spec:
        raise BuildError("door %d: generator '%s' needs '%s'" % (day, spec.get("type"), key))
    v = spec[key]
    if is_todo(v):
        raise TodoInput(key)
    return v


def gen_text(spec, day, ctx):
    text = expand(_need(spec, "text", day), ctx["first"], day, ctx["fill"])
    return _need(spec, "name", day), (text.rstrip("\n") + "\n").encode("utf-8"), None


def gen_wordlist(spec, day, ctx):
    words = [str(w).strip() for w in (spec.get("words") or []) if str(w).strip()]
    if not words or any(is_todo(w) for w in words):
        if not ctx["fill"]:
            raise TodoInput("words")
        words = ["alpha", "bravo", "charlie"]
    if ctx["answers"]:
        norm = {w.lower() for w in words}
        missing = [a for a in ctx["answers"] if a.lower() not in norm]
        if missing:
            if not ctx["fill"]:
                raise BuildError("door %d: the answer '%s' must be one of the words in the list"
                                 % (day, missing[0]))
            words.append(missing[0])
    return _need(spec, "name", day), ("\n".join(w.lower() for w in words) + "\n").encode("utf-8"), None


def gen_morse(spec, day, ctx):
    text = with_answer(_need(spec, "text", day), ctx["first"])
    if is_todo(text):
        raise TodoInput("text")
    return (_need(spec, "name", day),
            morse_wav(text, spec.get("wpm") or 12), None)


def gen_log(spec, day, ctx):
    n = int(spec.get("lines") or 900)
    odd = expand(_need(spec, "odd_line", day), ctx["first"], day, ctx["fill"])
    rng = random.Random("log:%d" % day)
    deer = ["dasher", "dancer", "prancer", "vixen", "comet", "cupid", "donner", "blitzen"]
    services = {
        "sleigh-fleet": [lambda r: "reindeer=%s status=OK load=%.2f" % (r.choice(deer), r.random()),
                         lambda r: "runway check passed, wind=%dkt" % r.randint(1, 30),
                         lambda r: "fuel level nominal (%d%%)" % r.randint(60, 100)],
        "workshop-7": [lambda r: "toy batch #%d completed" % r.randint(100, 999),
                       lambda r: "conveyor belt %d restarted" % r.randint(1, 12),
                       lambda r: "elf shift %d clocked in" % r.randint(1, 40)],
        "chimney-scanner": [lambda r: "chimney %d scanned: clear" % r.randint(1, 99),
                            lambda r: "soot level low at stack %d" % r.randint(1, 99),
                            lambda r: "flue %d inspected" % r.randint(1, 99)],
        "cookie-monitor": [lambda r: "cookie count=%d (within tolerance)" % r.randint(200, 900),
                           lambda r: "milk supply at %d%%" % r.randint(40, 100),
                           lambda r: "plate %d refilled" % r.randint(1, 60)],
        "gift-sorter": [lambda r: "parcel batch %d routed" % r.randint(1, 500),
                        lambda r: "label printer %d ready" % r.randint(1, 9),
                        lambda r: "sorted %d gifts in the last minute" % r.randint(20, 400)],
        "north-pole-gw": [lambda r: "heartbeat ok seq=%d" % r.randint(1000, 99999),
                          lambda r: "tls handshake completed peer=elf-%d" % r.randint(1, 99),
                          lambda r: "dns lookup ok (%d ms)" % r.randint(1, 80)],
    }
    names = sorted(services)
    t = datetime(2026, 12, 5, 18, 0, 0)
    lines = []
    for _ in range(n):
        t += timedelta(seconds=rng.randint(3, 40))
        svc = rng.choice(names)
        msg = rng.choice(services[svc])(rng)
        r = rng.random()
        level = "WARN" if r < 0.07 else ("DEBUG" if r < 0.12 else "INFO")
        lines.append("%s %-5s %-16s %s" % (t.strftime("%Y-%m-%d %H:%M:%S"), level, svc, msg))
    pos = rng.randint(n // 4, (3 * n) // 4)
    t_odd = datetime(2026, 12, 6, 6, 0, 0)
    lines.insert(pos, "%s %-5s %-16s %s" % (t_odd.strftime("%Y-%m-%d %H:%M:%S"), "NOTICE", "nikolaus-daemon", odd))
    return _need(spec, "name", day), ("\n".join(lines) + "\n").encode("utf-8"), None


def gen_numbers(spec, day, ctx):
    """AoC-2020-day-1 style: exactly one triple sums to the target."""
    target = int(spec.get("target") or 2005)
    count = int(spec.get("count") or 1000)
    rng = random.Random("numbers:%d" % day)
    for _ in range(500):
        a, b = rng.randint(300, 700), rng.randint(300, 900)
        c = target - a - b
        if not (1 <= c <= 999) or len({a, b, c}) < 3:
            continue
        smalls = {a, b, c}
        while len(smalls) < 24:
            smalls.add(rng.randint(10, 999))
        # anything above target-20 can never be part of a triple
        bigs = set()
        while len(bigs) < count - 24:
            bigs.add(rng.randint(target - 15, target + 7000))
        nums = sorted(smalls | bigs)
        small = sorted(v for v in nums if v < target)
        found = [(x, y, z) for i, x in enumerate(small) for j, y in enumerate(small[i + 1:], i + 1)
                 for z in small[j + 1:] if x + y + z == target]
        if len(found) == 1:
            rng.shuffle(nums)
            product = found[0][0] * found[0][1] * found[0][2]
            name = spec.get("name") or "input.txt"
            return name, ("\n".join(map(str, nums)) + "\n").encode("utf-8"), [str(product)]
    raise BuildError("door %d: could not generate a unique number puzzle" % day)


SEGMENTS = ["swim", "t1", "bike", "t2", "run"]
FILL_SPLITS = {
    "leo": ["1:00:00", "0:03:00", "5:30:00", "0:02:00", "3:30:00"],
    "lange": ["0:50:00", "0:02:00", "4:45:00", "0:02:00", "2:40:00"],
}


def _hms(v, default, fill):
    if is_todo(v):
        if not fill:
            raise TodoInput("splits")
        v = default
    parts = [int(p) for p in str(v).strip().split(":")]
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs


def gen_splits(spec, day, ctx):
    event = spec.get("event") or "Ironman World Championship, Kona"
    totals, athletes = {}, []
    for key in ("leo", "lange"):
        data = spec.get(key)
        if not isinstance(data, dict):
            raise BuildError("door %d: splits needs '%s' with swim, t1, bike, t2, run" % (day, key))
        secs = [_hms(data.get(seg, "TODO"), FILL_SPLITS[key][i], ctx["fill"]) for i, seg in enumerate(SEGMENTS)]
        totals[key] = sum(secs)
        entry = {"name": data.get("name") or {"leo": "Leo", "lange": "Patrick Lange"}[key]}
        for seg, s in zip(SEGMENTS, secs):
            entry[seg] = "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)
        athletes.append(entry)
    diff = totals["leo"] - totals["lange"]
    if diff <= 0:
        raise BuildError("door %d: Lange must be faster than Leo for this question" % day)
    mins = diff / 60.0
    answers = []
    for v in (str(int(round(mins))), str(int(mins))):
        if v not in answers:
            answers.append(v)
    doc = json.dumps({"event": event, "athletes": athletes}, indent=2, ensure_ascii=False)
    return spec.get("name") or "splits.json", (doc + "\n").encode("utf-8"), answers


# ---- JPEG + EXIF -----------------------------------------------------------

def jpeg_with_description(jpeg, description):
    """Insert an EXIF ImageDescription. Drops any old EXIF (and its GPS data)."""
    if jpeg[:2] != b"\xff\xd8":
        raise BuildError("EXIF image must be a JPEG file")
    segs, i = [], 2
    while i + 4 <= len(jpeg) and jpeg[i] == 0xFF and jpeg[i + 1] != 0xDA:
        length = struct.unpack(">H", jpeg[i + 2:i + 4])[0]
        seg = jpeg[i:i + 2 + length]
        if not (jpeg[i + 1] == 0xE1 and seg[4:10] == b"Exif\x00\x00"):
            segs.append(seg)
        i += 2 + length
    rest = jpeg[i:]
    data = description.encode("ascii", "replace") + b"\x00"
    data += b"\x00" * max(0, 5 - len(data))
    entry = struct.pack("<HHII", 0x010E, 2, len(data), 26)
    tiff = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 1) + entry + struct.pack("<I", 0) + data
    payload = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    at = 1 if segs and segs[0][1] == 0xE0 else 0
    segs.insert(at, app1)
    return b"\xff\xd8" + b"".join(segs) + rest


def gen_exif_image(spec, day, ctx):
    src = spec.get("source")
    if is_todo(src):
        if not ctx["fill"]:
            raise TodoInput("source")
        src = "example/example.jpg"
    desc = with_answer(_need(spec, "description", day), ctx["first"])
    if is_todo(desc):
        raise TodoInput("description")
    with open(ctx["resolve"](src, day), "rb") as f:
        data = f.read()
    return _need(spec, "name", day), jpeg_with_description(data, desc), None


GENERATORS = {
    "text": gen_text, "wordlist": gen_wordlist, "morse": gen_morse, "log": gen_log,
    "numbers": gen_numbers, "splits": gen_splits, "exif_image": gen_exif_image,
}
ANSWER_GENERATORS = ("numbers", "splits")


# --------------------------------------------------------------------------
# Per-door preparation
# --------------------------------------------------------------------------

def prepare_door(door, resolve, fill):
    """Run generators, work out AUTO answers, and expand templates in place.

    Sets door['_gen'] (files to publish), door['_signal'], door['_hidden'].
    Marks door['_todo'] if something it needs is still TODO."""
    day = door["day"]
    pub = door.setdefault("public", {})
    gens = pub.get("generate") or []
    door["_gen"], door["_signal"], door["_hidden"] = [], None, []
    ctx = {"fill": fill, "resolve": resolve, "answers": door["_answers"], "first": ""}
    for g in gens:
        if g.get("type") not in GENERATORS:
            raise BuildError("door %d: unknown generator type '%s'. Known: %s"
                             % (day, g.get("type"), ", ".join(sorted(GENERATORS))))
    try:
        if door["_auto"]:
            computed = None
            for g in gens:
                if g["type"] in ANSWER_GENERATORS:
                    computed = GENERATORS[g["type"]](g, day, ctx)[2]
            if not computed:
                raise BuildError("door %d: answer is AUTO, but the door has no 'numbers' or 'splits' generator" % day)
            door["_answers"] = ctx["answers"] = computed
            door["_todo"] = False
        ctx["first"] = ctx["answers"][0] if ctx["answers"] and not door["_todo"] else ""
        door["puzzle"] = expand(door["puzzle"], ctx["first"], day, fill)
        door["hints"] = [expand(h, ctx["first"], day, fill) for h in (door.get("hints") or [])]
        if pub.get("html_comment"):
            pub["html_comment"] = expand(pub["html_comment"], ctx["first"], day, fill)
        for c in pub.get("cookies") or []:
            c["value"] = expand(c.get("value") or "", ctx["first"], day, fill)
        for page in pub.get("hidden_pages") or []:
            page["text"] = expand(page.get("text") or "", ctx["first"], day, fill)
            door["_hidden"].append(page)
        sig = pub.get("signal")
        if sig:
            text = with_answer(sig.get("text") or "@answer", ctx["first"])
            if is_todo(text):
                raise TodoInput("signal")
            door["_signal"] = {"mode": sig.get("mode") or "binary",
                               "pattern": signal_pattern(text, sig.get("mode") or "binary")}
        if door["_todo"] and not fill:
            return
        for g in gens:
            name, data, _ = GENERATORS[g["type"]](g, day, ctx)
            door["_gen"].append((name, data))
    except TodoInput:
        door["_todo"] = True
        door["_gen"] = []
