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
