#!/usr/bin/env python3
"""dogg — the reference client. One file, stdlib only, every verb of dogg/0.

  python3 dogg.py orient                      the world in one call
  python3 dogg.py summon "markets fees"       chant in, tile out (keywords or stream id)
  python3 dogg.py incant TAUNT ZOOM HUNTER JADE TORCH QUAKE FORGE
  python3 dogg.py words  <stream-id>          the 7-word incantation for any stream
  python3 dogg.py mirror <stream-id|repo>     clone a dimension's repo into ./pantry/
  python3 dogg.py pack   <pantry-name>        one AirDroppable .dogg file (git bundle)
  python3 dogg.py receive <file.dogg>         accept a traded .dogg — VERIFIED or bounced
  python3 dogg.py verify [dir]                re-check every chain in a repo/pantry entry
  python3 dogg.py mission <stream-id> [--fields a,b,…]
                                              MISSION chant: tick + hash prefix + the numbers you
                                              choose, in words — longer spell, more fields
  python3 dogg.py inscribe <tile.json>        BOOK chant: an entire tile, exact, in words
  python3 dogg.py recite W1 … Wn              decode ANY chant OFFLINE — no data needed
  python3 dogg.py attest W1 … Wn <frame.json> prove a full frame against a mission chant
  python3 dogg.py hotload W1 … Wn [--into DIR] drop the tile into a brainstem as a cartridge
  python3 dogg.py lens select|delta|alarm <stream-id> [--fields a,b] [--above f=v | --below f=v]
                                              4-word LENS chant: a key that opens an algorithm
  python3 dogg.py seed <stream-id> <op args>… SEED chant: a program in words — select f, delta f,
                                              ratio a b, sum a b, max_of a b, change_pct f,
                                              above f=v, below f=v — any length, every seed valid
  python3 dogg.py wear W1 … Wn <frame.json> [prev.json]  run a lens or seed on the frame you hold
  python3 dogg.py uri W1 … Wn                 the same chant as a dense dogg: URI (any verb accepts either)
  python3 dogg.py book <out.html> "W1 … Wn" … a printable chant book: one QR per chant, words under it
  python3 dogg.py ndef [--hex] [--web] W1 … Wn  NDEF record(s) for an NFC/RFID tag; --web = tap opens recite.html
  python3 dogg.py kit <dir>                   export the cacheable machinery (SDK + codebook + lock)
  python3 dogg.py lock | check                re-issue / verify chants/CODEBOOK.lock (append-only codebook)

Offline-first: run inside a clone of kody-w/dogg (or with a ./pantry/) and everything
resolves from disk; otherwise the public raw URLs are used. Every borrowed or received
chain passes the gate — frame-by-frame re-verification plus tick-reference agreement
with your copy of the spine — or it bounces. Protocol: ../PROTOCOL.md
"""
import json, sys, os, hashlib, pathlib, subprocess, urllib.request

TOOLS = pathlib.Path(__file__).resolve().parent
ROOT = TOOLS.parent                    # a clone of kody-w/dogg, when run in place
PANTRY = pathlib.Path.cwd() / "pantry"
RAW = "https://raw.githubusercontent.com/kody-w/dogg/main"
PAGES = "https://kody-w.github.io/dogg"
UA = {"User-Agent": "dogg-client"}

sys.path.insert(0, str(TOOLS))
try:
    import rapp as R
    import chainio
except ImportError:
    R = chainio = None                 # network-only mode still works for reads

def http(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10) as r:
        return r.read().decode()

def get_json(rel):
    p = ROOT / rel
    if p.exists():
        return json.loads(p.read_text()), "local"
    return json.loads(http(f"{RAW}/{rel}")), "network"

def wordlist():
    p = ROOT / "chants" / "WORDLIST.txt"
    words = p.read_text().split() if p.exists() else http(f"{RAW}/chants/WORDLIST.txt").split()
    assert len(words) == 1024
    return words

def seed_of(s):
    return int.from_bytes(hashlib.sha256(s.encode()).digest()[:8], "big")

def seed_to_words(seed, WL):
    out = []
    for _ in range(7):
        out.append(WL[seed & 1023]); seed >>= 10
    return " ".join(out)

def words_to_seed(words, WL):
    idx = {w: i for i, w in enumerate(WL)}
    ws = [w.upper() for w in words]
    if len(ws) != 7: raise SystemExit("an incantation is exactly 7 words")
    seed = 0
    for i, w in enumerate(ws):
        if w not in idx: raise SystemExit(f"unknown word: {w}")
        seed |= idx[w] << (10 * i)
    return seed

def registry():
    meta, src = get_json("registry/HEAD.json")
    dims = []
    for i in range(meta["count"]):
        f, _ = get_json(f"registry/{i}.json")
        if f["kind"] == "registry.dimension":
            dims.append(f["payload"])
    return dims

def latest(d):
    theme = d["dimension"].split(":@", 1)[0]
    path = d.get("path", theme + "/").rstrip("/")
    name = d["repo"].split("/", 1)[1]
    for base in (PANTRY / name, ROOT if d["repo"] == "kody-w/dogg" else None):
        if base and (base / path / "HEAD.json").exists():
            meta = json.loads((base / path / "HEAD.json").read_text())
            return json.loads((base / path / f"{meta['count']-1}.json").read_text()), "local"
    raw = RAW if d["repo"] == "kody-w/dogg" else f"https://raw.githubusercontent.com/{d['repo']}/main"
    meta = json.loads(http(f"{raw}/{path}/HEAD.json"))
    return json.loads(http(f"{raw}/{path}/{meta['count']-1}.json")), "network"

# ── Chants of any length: the harder the spell, the longer the chant ──────
# One codec for every chant. Words are 10-bit symbols from the permanent 1024-word
# list. A chant is a self-describing bitstream:
#   word 0 (header): 2 version | 3 kind | 5 reserved
#   word 1 (length): 10 bits = number of BODY words (up to 1023; a chant book is many chants)
#   body words     : kind-specific, packed big-endian, zero-padded to a word boundary
#   last word      : 10-bit checksum = sha256(header|length|body) — one misheard word refuses
# Kinds: 1 MISSION (a lens plus a snapshot — tiles that live in words),
#        2 LENS    (a key that opens an algorithm — the frame you hold is the ore),
#        3 BOOK    (an entire tile, zlib-compressed — a page in a chant book).
# Physics, stated plainly: no chant carries data it does not contain; a MISSION carries
# quantized numbers, a BOOK carries exact bytes, a LENS carries no data at all.
CHANT_VERSION = 1
KIND_MISSION, KIND_LENS, KIND_BOOK = 1, 2, 3
BOOK_MAX_BYTES = 1 << 20   # a page is at most 1 MiB decompressed — a chant is never a bomb
VERSION_EXTENDED = 3       # reserved: header version 3 = extended header follows
LOG_MAX = 1e15
FIELD_BITS = 14
FIELD_MAX = (1 << FIELD_BITS) - 1
MISSION_VERSION = CHANT_VERSION       # kept for callers

def missions():
    d, _ = get_json("chants/MISSIONS.json")
    return d.get("missions", {})

def lenses():
    d, _ = get_json("chants/LENSES.json")
    return d.get("lenses", {})

def _dig(obj, path):
    for part in path.split("."):
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj

LOG_MIN = 1e-6      # 21 decades from a micro-unit to a quadrillion: ~0.3% relative precision in 14 bits

def _logq(v):
    import math
    if isinstance(v, list): v = len(v)
    try: x = float(v)
    except (TypeError, ValueError): return 0
    if x <= 0: return 0
    x = min(max(x, LOG_MIN), LOG_MAX)
    return max(1, min(FIELD_MAX, int(round(math.log(x / LOG_MIN) / math.log(LOG_MAX / LOG_MIN) * FIELD_MAX))))

def _logd(code):
    import math
    return 0.0 if code == 0 else LOG_MIN * math.exp(code / FIELD_MAX * math.log(LOG_MAX / LOG_MIN))

def _sig(v):
    import math
    if v == 0: return 0
    digits = 3 - int(math.floor(math.log10(abs(v)))) - 1
    return round(v, digits) if digits > 0 else int(round(v, digits))

class Bits:
    """append-only big-endian bit writer / sequential reader."""
    def __init__(self, n=0, val=0): self.n, self.val, self.pos = n, val, 0
    def put(self, width, x): self.val = (self.val << width) | (x & ((1 << width) - 1)); self.n += width; return self
    def get(self, width):
        if self.pos + width > self.n: raise ValueError("chant body ended early")
        x = (self.val >> (self.n - self.pos - width)) & ((1 << width) - 1); self.pos += width; return x

def chant_pack(kind, body):
    WL = wordlist()
    pad = (-body.n) % 10
    body_bits = body.val << pad; nwords = (body.n + pad) // 10
    if nwords > 1023: raise ValueError("a single chant holds at most 1023 body words — split it into a chant book")
    header = (CHANT_VERSION << 8) | (kind << 5)
    stream = Bits().put(10, header).put(10, nwords)
    stream.val = (stream.val << (nwords * 10)) | body_bits; stream.n += nwords * 10
    chk = int.from_bytes(hashlib.sha256(stream.val.to_bytes((stream.n + 7) // 8, "big")).digest()[:2], "big") & 1023
    stream.put(10, chk)
    total = stream.n // 10
    return " ".join(WL[(stream.val >> (10 * (total - 1 - i))) & 1023] for i in range(total))

def chant_unpack(words):
    WL = wordlist(); idx = {w: i for i, w in enumerate(WL)}
    ws = [w.upper() for w in words]
    bad = [w for w in ws if w not in idx]
    if bad: raise ValueError(f"not chant words: {bad[:3]}")
    if len(ws) < 3: raise ValueError("a chant is at least three words")
    syms = [idx[w] for w in ws]
    header, nwords = syms[0], syms[1]
    if header >> 8 != CHANT_VERSION: raise ValueError("unknown chant version")
    if len(syms) != nwords + 3: raise ValueError(f"this chant declares {nwords} body words; {len(syms) - 3} given")
    val = 0
    for x in syms[:-1]: val = (val << 10) | x
    n = (nwords + 2) * 10
    chk = int.from_bytes(hashlib.sha256(val.to_bytes((n + 7) // 8, "big")).digest()[:2], "big") & 1023
    if chk != syms[-1]: raise ValueError("checksum failed — a word was misheard, mistyped or forged")
    body = Bits(nwords * 10, val & ((1 << (nwords * 10)) - 1))
    return (header >> 5) & 7, body

# ── MISSION: a lens plus a snapshot ─────────────────────────────────────────
# body: 12 dimension id | 20 tick | 18 frame-hash prefix | 12 field mask | 14 bits per selected field
def _dim_id(dimension): return seed_of(dimension) >> 52

def codebook_check():
    """The gate: no two known dimensions may share a 12-bit id; the codebook must match its lock."""
    problems = []
    known = set(missions())
    try: known |= {d["dimension"] for d in registry()}
    except Exception: pass
    seen = {}
    for d in sorted(known):
        i = _dim_id(d)
        if i in seen: problems.append(f"dimension id collision {i:03x}: {seen[i]} vs {d}")
        seen[i] = d
    lock_p = ROOT / "chants" / "CODEBOOK.lock"
    if lock_p.exists():
        lock = json.loads(lock_p.read_text()); now = codebook_fingerprint()
        for k, v in lock["sha256"].items():
            if now["sha256"].get(k) != v: problems.append(f"codebook drift: {k} changed but CODEBOOK.lock was not re-issued")
    return problems

def codebook_fingerprint():
    wl = "\n".join(wordlist())
    fields = {d: [f["name"] + "|" + f["path"] for f in _fields_for(d)] for d in missions()}
    ops = json.dumps({str(k): v for k, v in OPS.items()}, sort_keys=True)
    return {"schema": "dogg/0-codebook-lock", "version": CHANT_VERSION,
            "rule": "append-only: never reorder or remove a word, an op, or a field; a change here re-means every chant ever spoken",
            "sha256": {"wordlist": hashlib.sha256(wl.encode()).hexdigest(), "ops": hashlib.sha256(ops.encode()).hexdigest(),
                       "fields": hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()}}
def _fields_for(dimension): return missions().get(dimension, {}).get("fields", [])[:12]
def _mask_for(dimension, fields):
    names = [f["name"] for f in _fields_for(dimension)]
    if not fields: return sum(1 << i for i in range(min(3, len(names))))
    mask = 0
    for n in fields:
        if n not in names: raise ValueError(f"unknown field {n!r} for {dimension}; known: {names}")
        mask |= 1 << names.index(n)
    return mask

def mission_encode(dimension, frame, fields=None):
    mask = _mask_for(dimension, fields); table = _fields_for(dimension)
    for i, f in enumerate(table):
        if mask >> i & 1:
            v = _dig(frame["payload"], f["path"])
            try:
                if not isinstance(v, list) and v is not None and float(v) < 0:
                    raise ValueError(f"field {f['name']!r} is negative ({v}); mission fields are positive magnitudes until a signed field type exists — refused rather than encoded as absent")
            except (TypeError, ValueError) as exc:
                if "negative" in str(exc): raise
    b = Bits().put(12, _dim_id(dimension)).put(20, int(frame["seq"])).put(18, int(frame["frame_hash"][:5], 16) & ((1 << 18) - 1)).put(12, mask)
    for i, f in enumerate(table):
        if mask >> i & 1: b.put(FIELD_BITS, _logq(_dig(frame["payload"], f["path"])))
    return chant_pack(KIND_MISSION, b)

def _resolve_dim(dim_id):
    d = next((d for d in missions() if _dim_id(d) == dim_id), None)
    if d is None:
        try: d = next((x["dimension"] for x in registry() if _dim_id(x["dimension"]) == dim_id), None)
        except Exception: d = None
    return d

def mission_decode_body(body):
    dim_id, seq, hp, mask = body.get(12), body.get(20), body.get(18), body.get(12)
    dimension = _resolve_dim(dim_id); table = _fields_for(dimension) if dimension else []
    tile = {"schema": "dogg/0-mission-tile", "dimension": dimension or f"unknown-dimension-id:{dim_id:03x}",
            "tick": seq, "frame_hash_prefix18": f"{hp:05x}", "fields": {}, "limited": True,
            "offline_reconstructed": True, "precision": "log-quantized, ~0.3% relative (1e-6 … 1e15)",
            "note": "a mission tile is a quantized summary carried in words — attest any full frame against these words before trusting more than this"}
    for i in range(12):
        if mask >> i & 1:
            v = body.get(FIELD_BITS)
            if i < len(table): tile["fields"][table[i]["name"]] = {"value": _sig(_logd(v)), "unit": table[i].get("unit", "")}
            else: tile["fields"][f"field_{i}"] = {"value": _sig(_logd(v)), "unit": ""}
    return tile

def mission_decode(words):
    kind, body = chant_unpack(words)
    if kind != KIND_MISSION: raise ValueError("not a mission chant")
    return mission_decode_body(body)

def mission_attest(words, frame):
    tile = mission_decode(words)
    same = int(frame.get("seq", -1)) == tile["tick"] and (int(frame.get("frame_hash", "0")[:5], 16) & ((1 << 18) - 1)) == int(tile["frame_hash_prefix18"], 16)
    if not same:
        return ("DIFFERENT-TICK" if frame.get("stream_id") == tile["dimension"] else "FORGED-OR-FOREIGN"), tile
    fields = [n for n in tile["fields"]]
    if mission_encode(frame["stream_id"], frame, fields).split() != [w.upper() for w in words]:
        return "FORGED", tile
    if R is not None:
        pre = {k: frame[k] for k in frame if k not in ("frame_hash", "sig")}
        if R.H("rapp/1:particle", frame["payload"]) != frame.get("payload_hash") or R.H("rapp/1:wave", pre) != frame.get("frame_hash"):
            return "FRAME-INVALID(self-hash)", tile
    return "MATCH", tile

# ── LENS: a key that opens an algorithm ─────────────────────────────────────
# body: 12 dimension id | 6 lens id | params (select/delta: 12 mask; alarm: 4 idx | 1 dir | 14 log threshold)
LENS_SELECT, LENS_DELTA, LENS_ALARM = 1, 2, 3

def lens_make(kind, dimension, fields=None, above=None, below=None):
    b = Bits().put(12, _dim_id(dimension))
    names = [f["name"] for f in _fields_for(dimension)]
    if kind in ("select", "delta"):
        b.put(6, LENS_SELECT if kind == "select" else LENS_DELTA).put(12, _mask_for(dimension, fields))
    elif kind == "alarm":
        spec = above or below
        if not spec or "=" not in spec: raise ValueError("alarm needs --above field=value or --below field=value")
        n, v = spec.split("=", 1)
        if n not in names: raise ValueError(f"unknown field {n!r}; known: {names}")
        b.put(6, LENS_ALARM).put(4, names.index(n)).put(1, 1 if above else 0).put(FIELD_BITS, _logq(v))
    else:
        raise ValueError("lens kind must be select, delta or alarm")
    return chant_pack(KIND_LENS, b)

def wear(words, frame, prev=None):
    kind, body = chant_unpack(words)
    if kind == KIND_SEED:
        dim_id, prog = seed_compile(body)
        dimension = frame.get("stream_id", "")
        if _dim_id(dimension) != dim_id:
            raise ValueError(f"this seed was cut for {_resolve_dim(dim_id) or 'another dimension'}, not for a {dimension} frame")
        table = _fields_for(dimension)
        return {"schema": "dogg/0-seed-tile", "dimension": dimension, "tick": frame.get("seq"), "frame_hash": frame.get("frame_hash"),
                "exact": True, "program": seed_listing(prog, table), "results": seed_run(prog, table, frame, prev)}
    if kind != KIND_LENS: raise ValueError("not a lens chant — recite it instead")
    dim_id, lens_id = body.get(12), body.get(6)
    dimension = frame.get("stream_id", "")
    if _dim_id(dimension) != dim_id:
        raise ValueError(f"this key was cut for {_resolve_dim(dim_id) or 'another dimension'}, not for a {dimension} frame")
    table = _fields_for(dimension)
    tile = {"schema": "dogg/0-lens-tile", "lens": lenses().get(str(lens_id), {}).get("name", f"lens-{lens_id}"),
            "dimension": dimension, "tick": frame.get("seq"), "frame_hash": frame.get("frame_hash"), "exact": True, "fields": {}}
    if lens_id in (LENS_SELECT, LENS_DELTA):
        mask = body.get(12)
        for i, f in enumerate(table):
            if mask >> i & 1:
                cur = _dig(frame["payload"], f["path"])
                if lens_id == LENS_SELECT:
                    tile["fields"][f["name"]] = {"value": cur, "unit": f.get("unit", "")}
                else:
                    if prev is None: raise ValueError("a delta lens needs the previous frame too")
                    old = _dig(prev["payload"], f["path"])
                    try: change = float(cur) - float(old)
                    except (TypeError, ValueError): change = None
                    tile["fields"][f["name"]] = {"now": cur, "was": old, "change": change, "unit": f.get("unit", ""), "since_tick": prev.get("seq")}
    elif lens_id == LENS_ALARM:
        i, above, code = body.get(4), body.get(1), body.get(FIELD_BITS)
        f = table[i]; cur = _dig(frame["payload"], f["path"]); thr = _logd(code)
        try: fired = (float(cur) > thr) if above else (float(cur) < thr)
        except (TypeError, ValueError): fired = None
        tile["alarm"] = {"field": f["name"], "direction": "above" if above else "below", "threshold": _sig(thr), "value": cur, "fired": fired, "unit": f.get("unit", "")}
    else:
        raise ValueError(f"no such lens {lens_id}")
    return tile

# ── SEED: a grammar where every bit sequence is a program ───────────────────
# The chant is the seed; the cached SDK is the generator; the program it derives is
# worn on the frame you hold. Every bit sequence parses (a Minecraft seed is never
# "invalid"), so short seeds are simple spells and long seeds are composed ones:
#   body: 12 dimension id | ops…   op = 3-bit code + operands; the body ends at the last full op
#   0 SELECT f(4)        1 DELTA f(4)         2 RATIO a(4) b(4)      3 ABOVE f(4) thr(14)
#   4 BELOW f(4) thr(14) 5 SUM f(4) g(4)      6 CHANGE_PCT f(4)      7 MAX_OF f(4) g(4)
KIND_SEED = 4
OPS = {0: ("select", [4]), 1: ("delta", [4]), 2: ("ratio", [4, 4]), 3: ("above", [4, 14]),
       4: ("below", [4, 14]), 5: ("sum", [4, 4]), 6: ("change_pct", [4]), 7: ("max_of", [4, 4])}
OP_CODE = {name: code for code, (name, _) in OPS.items()}

def _guard(dimension):
    for pr in codebook_check():
        if "collision" in pr and dimension in pr: raise ValueError(pr)

def seed_make(dimension, program):
    """program: list of (op, *operands) using field NAMES; thresholds as numbers."""
    _guard(dimension)
    names = [f["name"] for f in _fields_for(dimension)]
    b = Bits().put(12, _dim_id(dimension))
    for op, *args in program:
        code = OP_CODE[op]; widths = OPS[code][1]
        b.put(3, code)
        for w, a in zip(widths, args):
            if w == 4:
                if a not in names: raise ValueError(f"unknown field {a!r}; known: {names}")
                b.put(4, names.index(a))
            else:
                b.put(14, _logq(a))
    return chant_pack(KIND_SEED, b)

def seed_compile(body):
    """decode ops until the body cannot hold another full op — every seed is a valid program."""
    dim_id = body.get(12); prog = []
    while body.n - body.pos >= 3:
        code = body.get(3); widths = OPS[code][1]
        if body.n - body.pos < sum(widths): break
        prog.append((OPS[code][0], [body.get(w) for w in widths]))
    return dim_id, prog

def seed_run(prog, table, frame, prev=None):
    def val(i):
        f = table[i] if i < len(table) else None
        v = _dig(frame["payload"], f["path"]) if f else None
        try: return float(v)
        except (TypeError, ValueError): return None
    def old(i):
        f = table[i] if i < len(table) else None
        v = _dig(prev["payload"], f["path"]) if (f and prev) else None
        try: return float(v)
        except (TypeError, ValueError): return None
    def name(i): return table[i]["name"] if i < len(table) else f"field_{i}"
    out = {}
    for op, a in prog:
        if op == "select": out[name(a[0])] = val(a[0])
        elif op == "delta": out[f"delta({name(a[0])})"] = (None if old(a[0]) is None or val(a[0]) is None else val(a[0]) - old(a[0]))
        elif op == "change_pct": out[f"change_pct({name(a[0])})"] = (None if not old(a[0]) or val(a[0]) is None else (val(a[0]) - old(a[0])) / old(a[0]) * 100)
        elif op == "ratio": out[f"ratio({name(a[0])}/{name(a[1])})"] = (None if not val(a[1]) or val(a[0]) is None else val(a[0]) / val(a[1]))
        elif op == "sum": out[f"sum({name(a[0])}+{name(a[1])})"] = (None if val(a[0]) is None or val(a[1]) is None else val(a[0]) + val(a[1]))
        elif op == "max_of": out[f"max_of({name(a[0])},{name(a[1])})"] = max(x for x in (val(a[0]), val(a[1])) if x is not None) if any(x is not None for x in (val(a[0]), val(a[1]))) else None
        elif op in ("above", "below"):
            thr = _logd(a[1]); v = val(a[0])
            out[f"{op}({name(a[0])},{_sig(thr)})"] = (None if v is None else (v > thr if op == "above" else v < thr))
    return out

def seed_listing(prog, table):
    def name(i): return table[i]["name"] if i < len(table) else f"field_{i}"
    lines = []
    for op, a in prog:
        if op in ("above", "below"): lines.append(f"{op} {name(a[0])} {_sig(_logd(a[1]))}")
        else: lines.append(op + " " + " ".join(name(x) for x in a))
    return lines

# ── Carriers: words, URI, QR, a printed book ────────────────────────────────
# The same bits, four ways to carry them: spoken/memorized WORDS; a dogg: URI (dense text);
# a QR (one square holds a whole BOOK chant); a printed chant book (QR + the words under it,
# so a phone scans it and a human can still read it aloud). Worst case: paper.
def to_uri(words):
    WL = wordlist(); idx = {w: i for i, w in enumerate(WL)}
    syms = [idx[w.upper()] for w in words]
    val = 0
    for x in syms: val = (val << 10) | x
    nbytes = (len(syms) * 10 + 7) // 8
    import base64
    return f"dogg:{CHANT_VERSION}:{len(syms)}:" + base64.urlsafe_b64encode(val.to_bytes(nbytes, "big")).decode().rstrip("=")

def from_uri(text):
    import base64
    parts = text.strip().split(":")
    if len(parts) != 4 or parts[0] != "dogg": raise ValueError("not a dogg: chant URI")
    n = int(parts[2]); raw = base64.urlsafe_b64decode(parts[3] + "=" * (-len(parts[3]) % 4))
    val = int.from_bytes(raw, "big")          # to_bytes right-aligns: no shift on the way back
    WL = wordlist()
    return [WL[(val >> (10 * (n - 1 - i))) & 1023] for i in range(n)]

def as_words(args):
    """accept words, a single dogg: URI, or several page URIs anywhere a chant is expected."""
    if args and all(a.startswith("dogg:") for a in args): return from_uri(join_pages(list(args)))
    return list(args)

QR_PAGE_CHARS = 300   # a phone scans a ~300-char square reliably; longer chants are paged

def uri_pages(uri):
    """split a dogg: URI into scannable pages: dogg:1:<n>:<p>/<t>:<chunk> — reassemble in order."""
    head, payload = uri.rsplit(":", 1)
    if len(payload) <= QR_PAGE_CHARS: return [uri]
    chunks = [payload[i:i + QR_PAGE_CHARS] for i in range(0, len(payload), QR_PAGE_CHARS)]
    return [f"{head}:{i + 1}/{len(chunks)}:{c}" for i, c in enumerate(chunks)]

def join_pages(pages):
    """reassemble page URIs (any order) into the single dogg: URI."""
    if len(pages) == 1 and "/" not in pages[0].split(":")[3 if pages[0].count(":") > 3 else 0]: return pages[0]
    parts = {}
    head = None
    for pg in pages:
        h, pt, chunk = pg.rsplit(":", 2)
        i, t = pt.split("/"); parts[int(i)] = chunk; head = h; total = int(t)
    if sorted(parts) != list(range(1, total + 1)): raise ValueError(f"missing pages: have {sorted(parts)} of {total}")
    return head + ":" + "".join(parts[i] for i in range(1, total + 1))

def qr_png_data_uri(text):
    """PNG data URI via the optional `qrcode` package; None when it is not installed."""
    try:
        import qrcode, io, base64
    except ImportError:
        return None
    ec = qrcode.constants.ERROR_CORRECT_M if len(text) <= 120 else qrcode.constants.ERROR_CORRECT_L
    q = qrcode.QRCode(error_correction=ec, box_size=8, border=4); q.add_data(text); q.make(fit=True)
    img = q.make_image()
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def book_page(chants, title="dogg chant book"):
    """A printable page: one QR per chant, its words under it, its meaning beside it."""
    cards = []
    for words in chants:
        words = as_words(words); uri = to_uri(words)
        try: meaning = recite(words)
        except Exception as ex: meaning = {"error": str(ex)[:80]}
        kind = meaning.get("schema", "").replace("dogg/0-", "")
        label = meaning.get("dimension") or meaning.get("tile", {}).get("dimension", "") or ""
        pages = uri_pages(uri)
        imgs = [qr_png_data_uri(pg) for pg in pages]
        if all(imgs):
            qr_html = "".join(f'<figure><img alt="QR page {i + 1}" src="{im}"><figcaption>page {i + 1} of {len(pages)}</figcaption></figure>' for i, im in enumerate(imgs)) if len(pages) > 1 else f'<img alt="QR" src="{imgs[0]}">'
        else:
            qr_html = f'<pre class="uri">{uri}</pre><p class="hint">(install the qrcode package to print squares; the URI above scans as text)</p>'
        summary = json.dumps({k: v for k, v in meaning.items() if k in ("tick", "fields", "program", "alarm")}, indent=None)[:300]
        cards.append(f'<section class="card">{qr_html}<div class="txt"><h2>{kind} · {label}</h2><p class="words">{" ".join(words)}</p><p class="meta">{len(words)} words · {summary}</p></div></section>')
    return ("<!doctype html><meta charset=utf-8><title>" + title + "</title><style>body{font:14px/1.4 -apple-system,system-ui,sans-serif;margin:24px;color:#111}"
            ".card{display:flex;gap:18px;align-items:flex-start;border:1px solid #ccc;border-radius:10px;padding:14px;margin:0 0 14px;page-break-inside:avoid}"
            ".card img{width:200px;height:200px;image-rendering:pixelated}figure{display:inline-block;margin:0 8px 0 0;text-align:center;font-size:11px;color:#555}.words{font:700 15px/1.5 ui-monospace,Menlo,monospace;letter-spacing:.02em}"
            ".meta{color:#555;font-size:12px;word-break:break-all}.uri{font-size:11px;word-break:break-all}h2{margin:0 0 6px;font-size:14px}.hint{color:#777;font-size:11px}"
            "@media print{.card{border-color:#000}}</style><h1>" + title + "</h1><p>Scan a square, or read the words aloud. Every code is one chant; the words under it are the same bits. Cache the machinery, never the ore.</p>"
            + "".join(cards))


# ── Worn tiles: NFC / RFID ──────────────────────────────────────────────────
# A tag is a carrier like paper: it holds the dogg: URI as an NDEF URI record (NFC Forum
# RTD-URI). Tap it and the reader has the chant — a wristband, a ring, a sticker on a door.
# Sizing is real: NTAG213 ≈ 144 usable bytes (a mission or seed), NTAG215 ≈ 504, NTAG216 ≈ 888
# (a whole BOOK frame), ICODE/ISO15693 up to ~8 KB (a chant book on one tag); UHF RFID user
# memory 64 B–8 KB. Longer chants page exactly like QR, one page per tag.
TAGS = [("NTAG213", 144), ("NTAG215", 504), ("NTAG216", 888), ("ICODE SLIX2 (ISO15693)", 2528), ("MIFARE DESFire 8K", 8192)]

def ndef_uri(uri):
    """NDEF message bytes carrying one well-known URI record (no prefix abbreviation: 0x00)."""
    payload = b"\x00" + uri.encode()
    if len(payload) < 256:
        header = bytes([0xD1, 0x01, len(payload)]) + b"U"      # MB|ME|SR, type len 1, payload len, type 'U'
    else:
        header = bytes([0xC1, 0x01]) + len(payload).to_bytes(4, "big") + b"U"
    return header + payload

def ndef_pages(words):
    """one NDEF message per QR-style page; returns [(page_uri, ndef_bytes, fits)]"""
    out = []
    for pg in uri_pages(to_uri(words)):
        msg = ndef_uri(pg)
        fits = [name for name, cap in TAGS if len(msg) + 5 <= cap]     # +5: TLV wrapper the tag adds
        out.append((pg, msg, fits))
    return out

# ── BOOK: an entire tile in words — exact bytes, any size ───────────────────
def inscribe(obj):
    import zlib
    raw = zlib.compress(json.dumps(obj, separators=(",", ":"), sort_keys=True).encode(), 9)
    b = Bits().put(16, len(raw))
    for byte in raw: b.put(8, byte)
    return chant_pack(KIND_BOOK, b)

def recite(words):
    """decode ANY chant offline: mission -> tile, lens -> the key described, book -> the exact object."""
    import zlib
    kind, body = chant_unpack(words)
    if kind == KIND_MISSION: return mission_decode_body(body)
    if kind == KIND_LENS:
        dim_id, lens_id = body.get(12), body.get(6)
        return {"schema": "dogg/0-lens-key", "dimension": _resolve_dim(dim_id), "lens": lenses().get(str(lens_id), {}).get("name", f"lens-{lens_id}"),
                "note": "a lens carries no data — wear it on a frame you hold"}
    if kind == KIND_SEED:
        dim_id, prog = seed_compile(body); dimension = _resolve_dim(dim_id)
        return {"schema": "dogg/0-seed-key", "dimension": dimension, "program": seed_listing(prog, _fields_for(dimension) if dimension else []),
                "note": "a seed carries no data — the cached SDK compiles it into this program; wear it on a frame you hold"}
    if kind == KIND_BOOK:
        n = body.get(16); raw = bytes(body.get(8) for _ in range(n))
        d = zlib.decompressobj(); out = d.decompress(raw, BOOK_MAX_BYTES)
        if d.unconsumed_tail: raise ValueError(f"book tile exceeds {BOOK_MAX_BYTES} bytes decompressed — refused")
        obj = json.loads(out)
        return {"schema": "dogg/0-book-tile", "exact": True, "words": len(words), "tile": obj}
    raise ValueError(f"unknown chant kind {kind}")

def mission_cartridge(tile):
    slug = "".join(ch if ch.isalnum() else "_" for ch in str(tile.get("dimension", "tile")).split(":@")[0]).lower() or "dimension"
    name = f"dogg_mission_{slug}_agent.py"
    lines = ['"""dogg cartridge — a tile hotloaded from a chant."""', "import json",
             "TILE = json.loads(" + repr(json.dumps(tile)) + ")", "",
             "class BasicAgent:", "    def __init__(self, name, metadata):", "        self.name = name; self.metadata = metadata", "",
             "class DoggMissionAgent(BasicAgent):", "    def __init__(self):",
             "        super().__init__(" + repr(slug + "_mission") + ", {", "            'name': " + repr(slug + "_mission") + ",",
             "            'description': " + repr(f"Answers from a chant-hotloaded tile of {(tile.get('tile') or tile).get('dimension')} (tick {(tile.get('tile') or tile).get('tick')}). Limits are stated in the tile.") + ",",
             "            'parameters': {'field': 'string (optional)'}})",
             "    def perform(self, field=None, **kwargs):",
             "        fields = TILE.get('fields') or (TILE.get('tile') or {}).get('fields') or {}",
             "        if field and field in fields:",
             "            f = fields[field]; return f\"{field} = {f.get('value', f)} {f.get('unit', '') if isinstance(f, dict) else ''} (tick {(TILE.get('tile') or TILE).get('tick')})\"",
             "        return json.dumps(TILE)", ""]
    return name, "\n".join(lines)


def chant_inscribe_file(path):
    obj = json.loads(pathlib.Path(path).read_text())
    return inscribe(obj)

def summon(chant, take=3):
    dims = registry()
    tick, _ = get_json("ticks/HEAD.json")
    if ":@" in chant:
        chosen = [d for d in dims if d["dimension"] == chant]
    else:
        words = set(chant.lower().split())
        chosen = sorted(dims, key=lambda d: sum(1 for w in words
                        if w in (d["dimension"] + " " + d.get("outlook", "")).lower()),
                        reverse=True)[:take]
    tile = {"schema": "dogg/0-tile", "tick": tick["count"] - 1,
            "tick_frame": tick["head_frame"], "chant": chant, "dimensions": {}}
    for d in chosen:
        try:
            f, src = latest(d)
            tile["dimensions"][d["dimension"]] = {"frame_hash": f["frame_hash"],
                                                  "seq": f["seq"], "via": src,
                                                  "data": f["payload"]}
        except Exception as ex:
            tile["dimensions"][d["dimension"]] = {"unreachable": str(ex)[:80]}
    return tile

def gate(dest):
    """Frame-by-frame re-verification + tick agreement with OUR spine. Needs rapp.py."""
    if R is None:
        return False, "gate needs tools/rapp.py + chainio.py beside this script"
    for headf in pathlib.Path(dest).glob("*/HEAD.json"):
        meta = json.loads(headf.read_text())
        head = None
        try:
            frames = chainio.load_chain(headf.parent)
        except Exception as ex:
            return False, f"storage: {ex}"
        for fr in frames:
            ok, step, why = R.verify_frame(fr, head=head, stream_id_of_record=meta["stream_id"])
            if not ok:
                return False, f"frame {fr.get('seq')}: step {step}"
            tn, tref = fr["payload"].get("tick"), fr["payload"].get("tick_frame")
            if tn is not None and tref is not None:
                lt = ROOT / "ticks" / f"{tn}.json"
                if lt.exists() and json.loads(lt.read_text())["frame_hash"] != tref:
                    return False, f"frame {fr.get('seq')} contradicts the spine @ tick {tn}"
            head = fr
    return True, ""

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    cmd, rest = args[0], args[1:]
    if cmd == "orient":
        try:
            print(json.dumps(json.loads(http(f"{PAGES}/orient.json")), indent=1))
        except Exception:
            print(json.dumps({"tick": get_json("ticks/HEAD.json")[0]}, indent=1))
    elif cmd == "summon":
        print(json.dumps(summon(" ".join(rest) or "world"), indent=1))
    elif cmd == "words":
        print(seed_to_words(seed_of(rest[0]), wordlist()))
    elif cmd == "incant":
        WL = wordlist()
        seed = words_to_seed(rest, WL)
        for d in registry():
            if seed_of(d["dimension"]) == seed:
                print(json.dumps(summon(d["dimension"]), indent=1)); return
        print("nothing registered answers that incantation")
    elif cmd == "mission":
        dim = rest[0]
        fields = rest[rest.index("--fields") + 1].split(",") if "--fields" in rest else None
        d = next((x for x in registry() if x["dimension"] == dim), None)
        if d is None: raise SystemExit("unknown dimension")
        f, src = latest(d)
        print(mission_encode(dim, f, fields))
    elif cmd == "recite":
        print(json.dumps(recite(as_words(rest)), indent=1))
    elif cmd == "inscribe":
        print(chant_inscribe_file(rest[0]))
    elif cmd == "attest":
        frame = json.loads(pathlib.Path(rest[-1]).read_text())
        verdict, tile = mission_attest(as_words(rest[:-1]), frame)
        print(json.dumps({"verdict": verdict, "tile": tile}, indent=1))
        if verdict != "MATCH": raise SystemExit(2)
    elif cmd == "hotload":
        into = None
        if "--into" in rest:
            i = rest.index("--into"); into = pathlib.Path(rest[i + 1]).expanduser(); rest = rest[:i] + rest[i + 2:]
        tile = recite(as_words(rest))
        name, src = mission_cartridge(tile)
        dest = into or pathlib.Path(os.path.expanduser("~/.brainstem/src/rapp_brainstem/agents"))
        dest.mkdir(parents=True, exist_ok=True)
        (dest / name).write_text(src)
        print(f"hotloaded: {dest / name}")
    elif cmd == "lens":
        kind, dim = rest[0], rest[1]
        opts = rest[2:]
        fields = opts[opts.index("--fields") + 1].split(",") if "--fields" in opts else None
        above = opts[opts.index("--above") + 1] if "--above" in opts else None
        below = opts[opts.index("--below") + 1] if "--below" in opts else None
        print(lens_make(kind, dim, fields, above, below))
    elif cmd == "seed":
        dim = rest[0]; toks = rest[1:]; prog = []; i = 0
        while i < len(toks):
            op = toks[i]; n = len(OPS[OP_CODE[op]][1]); args = toks[i + 1:i + 1 + n]
            if op in ("above", "below"):
                f, v = args[0].split("="); args = [f, float(v)]; n = 1
            prog.append((op, *args)); i += 1 + n
        print(seed_make(dim, prog))
    elif cmd == "uri":
        print(to_uri(as_words(rest)))
    elif cmd == "book":
        # book <out.html> then one chant per remaining arg: a quoted word string or a dogg: URI
        out = pathlib.Path(rest[0]); chants = [a.split() if not a.startswith("dogg:") else [a] for a in rest[1:]]
        out.write_text(book_page(chants)); print(f"chant book written: {out} ({len(chants)} chants) — print it; the codes and the words are the same bits")
    elif cmd == "ndef":
        # ndef [--hex] [--web] W… : the NDEF record(s) to write on a tag (one message per page).
        # --web wraps each page as https://…/recite.html#<uri>: phones open https records from a
        # background tap with no app installed, and the page recites the tile on the spot.
        hexout = "--hex" in rest; web = "--web" in rest
        words = as_words([a for a in rest if a not in ("--hex", "--web")])
        for i, (pg, msg, fits) in enumerate(ndef_pages(words), 1):
            if web:
                pg = f"{PAGES}/recite.html#{pg}"; msg = ndef_uri(pg)
                fits = [name for name, cap in TAGS if len(msg) + 5 <= cap]
            print(f"# page {i}: {len(msg)} bytes — fits: {', '.join(fits) or 'no listed tag; use a larger tag or split'}")
            print(msg.hex() if hexout else pg)
    elif cmd == "kit":
        dest = pathlib.Path(rest[0]).expanduser(); (dest / "tools").mkdir(parents=True, exist_ok=True); (dest / "chants").mkdir(exist_ok=True)
        import shutil
        for f in ("dogg.py", "rapp.py", "chainio.py"):
            src = TOOLS / f
            if src.exists(): shutil.copy(src, dest / "tools" / f)
        for f in ("WORDLIST.txt", "MISSIONS.json", "LENSES.json", "CODEBOOK.lock"):
            src = ROOT / "chants" / f
            if src.exists(): shutil.copy(src, dest / "chants" / f)
        print(f"kit written to {dest}: the machinery (cache it forever); the ore never has to be")
    elif cmd == "lock":
        (ROOT / "chants" / "CODEBOOK.lock").write_text(json.dumps(codebook_fingerprint(), indent=1) + "\n"); print("CODEBOOK.lock re-issued")
    elif cmd == "check":
        problems = codebook_check()
        print("\n".join(problems) if problems else "codebook OK: no id collisions, lock matches"); sys.exit(1 if problems else 0)
    elif cmd == "wear":
        files = [a for a in rest if a.endswith(".json")]; words = as_words([a for a in rest if not a.endswith(".json")])
        frame = json.loads(pathlib.Path(files[0]).read_text())
        prev = json.loads(pathlib.Path(files[1]).read_text()) if len(files) > 1 else None
        print(json.dumps(wear(words, frame, prev), indent=1))
    elif cmd == "mirror":
        target = rest[0]
        repo = target.split(":@", 1)[1] if ":@" in target else target
        name = repo.split("/", 1)[1]
        PANTRY.mkdir(exist_ok=True)
        subprocess.run(["git", "clone", "-q", f"https://github.com/{repo}.git",
                        str(PANTRY / name)], check=True)
        print(f"mirrored: pantry/{name}")
    elif cmd == "pack":
        src = PANTRY / rest[0]
        out = pathlib.Path.cwd() / f"{rest[0]}.dogg"
        subprocess.run(["git", "-C", str(src), "bundle", "create", str(out), "--all"],
                       check=True, capture_output=True)
        print(f"packed: {out.name} ({out.stat().st_size:,} bytes) — AirDrop it")
    elif cmd == "receive":
        src = pathlib.Path(rest[0]).expanduser()
        dest = PANTRY / src.stem
        PANTRY.mkdir(exist_ok=True)
        if dest.exists(): raise SystemExit(f"{src.stem} already in pantry")
        subprocess.run(["git", "clone", "-q", str(src), str(dest)], check=True,
                       capture_output=True)
        ok, why = gate(dest)
        if ok:
            print(f"✓ {src.stem}: verified + spine-consistent — pooled into pantry/")
        else:
            import shutil; shutil.rmtree(dest)
            print(f"✗ {src.stem}: REJECTED ({why})")
    elif cmd == "verify":
        d = pathlib.Path(rest[0]) if rest else ROOT
        ok, why = gate(d)
        print("OK — every chain verifies" if ok else f"FAIL: {why}")
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
