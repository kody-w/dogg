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
  python3 dogg.py mission <stream-id>         10-word MISSION chant: tick + hash prefix + the
                                              dimension's mission-critical numbers, in the words
  python3 dogg.py recite W1 … W10             decode a mission chant OFFLINE — no data needed
  python3 dogg.py attest W1 … W10 <frame.json> prove a full frame against the words
  python3 dogg.py hotload W1 … W10 [--into DIR] drop the tile into a brainstem as a cartridge

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

# ── Mission chants: tiles that live in words (the Metroid password) ────────
# Physics: seven words (~64 bits) can name a stream; no chant can carry a frame's
# kilobytes of observations. What CAN ride in words is a LIMITED TILE — the
# mission-critical numbers — plus the tick and a hash prefix, so any full frame
# met later is provable against the same words. Squeezed like a cartridge:
#   10 words = 100 bits:
#   2 version | 12 dimension id | 20 tick seq | 18 frame-hash prefix | 3 × 14 log-quantized fields | 6 checksum
# A 14-bit LOG field spans 1 … 1e15 at ~0.21% relative precision (BTC ±$170 at
# $80k, ETH ±$5, market cap ±$5.7B) — one encoding for every magnitude, no scale tables.
MISSION_VERSION = 1
LOG_MAX = 1e15
FIELD_BITS = 14
FIELD_MAX = (1 << FIELD_BITS) - 1

def missions():
    d, _ = get_json("chants/MISSIONS.json")
    return d.get("missions", {})

def _dig(obj, path):
    for part in path.split("."):
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj

def _logq(v):
    """value -> 14-bit log code; 0 means zero/absent."""
    import math
    if isinstance(v, list): v = len(v)
    try: x = float(v)
    except (TypeError, ValueError): return 0
    if x <= 0: return 0
    x = min(x, LOG_MAX)
    return max(1, min(FIELD_MAX, int(round(math.log(x) / math.log(LOG_MAX) * FIELD_MAX))))

def _logd(code):
    import math
    if code == 0: return 0.0
    return math.exp(code / FIELD_MAX * math.log(LOG_MAX))

def _checksum6(bits94):
    return hashlib.sha256(bits94.to_bytes(12, "big")).digest()[0] & 63

def _sig(v):
    """present a decoded value at its honest precision (3 significant figures)."""
    if v == 0: return 0
    import math
    digits = 3 - int(math.floor(math.log10(abs(v)))) - 1
    return round(v, digits) if digits > 0 else int(round(v, digits))

def mission_encode(dimension, frame):
    fields = missions().get(dimension, {}).get("fields", [])[:3]
    dim_id = seed_of(dimension) >> 52                      # 12 bits
    seq = int(frame["seq"]) & ((1 << 20) - 1)
    hp = int(frame["frame_hash"][:5], 16) & ((1 << 18) - 1)  # 18 bits of the hash
    vals = [_logq(_dig(frame["payload"], f["path"])) for f in fields] + [0, 0, 0]
    bits = (MISSION_VERSION << 92) | (dim_id << 80) | (seq << 60) | (hp << 42) \
           | (vals[0] << 28) | (vals[1] << 14) | vals[2]
    packed = (bits << 6) | _checksum6(bits)
    WL = wordlist()
    return " ".join(WL[(packed >> (10 * i)) & 1023] for i in range(9, -1, -1))

def mission_decode(words):
    WL = wordlist(); idx = {w: i for i, w in enumerate(WL)}
    ws = [w.upper() for w in words]
    if len(ws) != 10 or any(w not in idx for w in ws):
        raise ValueError("a mission chant is exactly 10 words from the wordlist")
    packed = 0
    for w in ws: packed = (packed << 10) | idx[w]
    bits, chk = packed >> 6, packed & 63
    if _checksum6(bits) != chk:
        raise ValueError("checksum failed — a word was misheard, mistyped or forged")
    if (bits >> 92) != MISSION_VERSION:
        raise ValueError("unknown mission chant version")
    dim_id = (bits >> 80) & 0xFFF
    seq = (bits >> 60) & ((1 << 20) - 1)
    hp = (bits >> 42) & ((1 << 18) - 1)
    vals = [(bits >> 28) & FIELD_MAX, (bits >> 14) & FIELD_MAX, bits & FIELD_MAX]
    dimension = next((d for d in missions() if (seed_of(d) >> 52) == dim_id), None)
    if dimension is None:
        try: dimension = next((d["dimension"] for d in registry() if (seed_of(d["dimension"]) >> 52) == dim_id), None)
        except Exception: dimension = None
    fields = missions().get(dimension, {}).get("fields", [])[:3] if dimension else []
    tile = {"schema": "dogg/0-mission-tile", "dimension": dimension or f"unknown-dimension-id:{dim_id:03x}",
            "tick": seq, "frame_hash_prefix18": f"{hp:05x}", "fields": {},
            "limited": True, "offline_reconstructed": True, "precision": "log-quantized, ~0.21% relative",
            "note": "a mission tile is a quantized summary carried in words — attest any full frame against these words before trusting more than this"}
    for f, v in zip(fields, vals):
        tile["fields"][f["name"]] = {"value": _sig(_logd(v)), "unit": f.get("unit", "")}
    return tile

def mission_attest(words, frame):
    tile = mission_decode(words)
    same_tick = int(frame.get("seq", -1)) == tile["tick"] and \
        (int(frame.get("frame_hash", "0")[:5], 16) & ((1 << 18) - 1)) == int(tile["frame_hash_prefix18"], 16)
    if not same_tick:
        return ("DIFFERENT-TICK" if frame.get("stream_id") == tile["dimension"] else "FORGED-OR-FOREIGN"), tile
    if mission_encode(frame["stream_id"], frame).split() != [w.upper() for w in words]:
        return "FORGED", tile
    if R is not None:  # a lone frame: prove its own hashes (chain linkage needs the predecessor, which attest does not)
        pre = {k: frame[k] for k in frame if k not in ("frame_hash", "sig")}
        if R.H("rapp/1:particle", frame["payload"]) != frame.get("payload_hash") or R.H("rapp/1:wave", pre) != frame.get("frame_hash"):
            return "FRAME-INVALID(self-hash)", tile
    return "MATCH", tile

def mission_cartridge(tile):
    slug = "".join(ch if ch.isalnum() else "_" for ch in tile["dimension"].split(":@")[0]).lower() or "dimension"
    name = f"dogg_mission_{slug}_agent.py"
    lines = [
        '"""dogg mission cartridge — a limited tile hotloaded from a 10-word mission chant."""',
        "import json",
        "TILE = json.loads(" + repr(json.dumps(tile)) + ")",
        "",
        "class BasicAgent:",
        "    def __init__(self, name, metadata):",
        "        self.name = name; self.metadata = metadata",
        "",
        "class DoggMissionAgent(BasicAgent):",
        "    def __init__(self):",
        "        super().__init__(" + repr(slug + "_mission") + ", {",
        "            'name': " + repr(slug + "_mission") + ",",
        "            'description': " + repr(f"Answers from the mission tile of {tile['dimension']} at tick {tile['tick']} — a log-quantized summary reconstructed offline from a chant (frame hash prefix {tile['frame_hash_prefix18']}). Limited by design.") + ",",
        "            'parameters': {'field': 'string (optional)'}})",
        "    def perform(self, field=None, **kwargs):",
        "        if field and field in TILE['fields']:",
        "            f = TILE['fields'][field]",
        "            return f\"{field} = {f['value']} {f['unit']} (tick {TILE['tick']}, ~0.21% precision; limited tile)\"",
        "        return json.dumps(TILE)",
        "",
    ]
    return name, "\n".join(lines)


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
        d = next((x for x in registry() if x["dimension"] == dim), None)
        if d is None: raise SystemExit("unknown dimension")
        f, src = latest(d)
        print(mission_encode(dim, f))
    elif cmd == "recite":
        print(json.dumps(mission_decode(rest), indent=1))
    elif cmd == "attest":
        frame = json.loads(pathlib.Path(rest[-1]).read_text())
        verdict, tile = mission_attest(rest[:-1], frame)
        print(json.dumps({"verdict": verdict, "tile": tile}, indent=1))
        if verdict != "MATCH": raise SystemExit(2)
    elif cmd == "hotload":
        into = None
        if "--into" in rest:
            i = rest.index("--into"); into = pathlib.Path(rest[i + 1]).expanduser(); rest = rest[:i] + rest[i + 2:]
        tile = mission_decode(rest)
        name, src = mission_cartridge(tile)
        dest = into or pathlib.Path(os.path.expanduser("~/.brainstem/src/rapp_brainstem/agents"))
        dest.mkdir(parents=True, exist_ok=True)
        (dest / name).write_text(src)
        print(f"hotloaded: {dest / name}")
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
