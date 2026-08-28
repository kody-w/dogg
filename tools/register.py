#!/usr/bin/env python3
"""register.py — make a dimension summonable.

A dogg is ORIENTABLE the moment it is on the registry. It is SUMMONABLE only when it has
declared its reduction: which few positive magnitudes of its frame are mission-critical, in
what order (the first three ride a default mission chant), plus any procedures that ride as
BOOK chants. The node owns that declaration (mission.json at its repo root); this registrar
appends the registry frame on the spine and folds the node's reduction into the kit's
chants/MISSIONS.json (append-only per dimension — the codebook law), then re-issues the lock.

  python3 tools/register.py nodes.json     # [{dimension, repo, path, outlook, fields:[{name,path,unit}]}, …]
  python3 tools/register.py --sync         # re-read every registered node's mission.json into the kit
"""
import json, sys, pathlib, urllib.request, datetime
TOOLS = pathlib.Path(__file__).resolve().parent; ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import rapp as R
import dogg

REG_DIR = ROOT / "registry"
REG_STREAM = "registry:@kody-w/global"


def utc():
    n = datetime.datetime.now(datetime.timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


def reg_frames():
    metas = sorted(REG_DIR.glob("*.json"), key=lambda p: int(p.stem) if p.stem.isdigit() else -1)
    return [json.loads(p.read_text()) for p in metas if p.stem.isdigit()]


def append_registry(dimension, repo, path, outlook):
    frames = reg_frames()
    if any(f["payload"].get("dimension") == dimension for f in frames):
        return None
    head = frames[-1] if frames else None
    f = R.build_frame("registry.dimension", REG_STREAM, (head["seq"] + 1) if head else 0, utc(),
                      {"dimension": dimension, "repo": repo, "path": path, "outlook": outlook},
                      prev=head["payload_hash"] if head else None)
    ok, step, why = R.verify_frame(f, head=head)
    assert ok, (dimension, step, why)
    (REG_DIR / f"{f['seq']}.json").write_text(json.dumps(f, indent=2) + "\n")
    hp = REG_DIR / "HEAD.json"; meta = json.loads(hp.read_text()) if hp.exists() else {"stream_id": REG_STREAM, "epoch_size": 288, "sealed_epochs": 0}
    meta.update({"count": f["seq"] + 1, "head_frame": f["frame_hash"], "updated": utc()})
    hp.write_text(json.dumps(meta, indent=2) + "\n")
    return f


def fold_mission(dimension, fields, default=None):
    """append-only: a dimension's fields may be extended, never reordered or removed."""
    mp = ROOT / "chants" / "MISSIONS.json"
    doc = json.loads(mp.read_text())
    cur = doc["missions"].get(dimension, {"fields": []})
    have = [f["name"] for f in cur["fields"]]
    for f in fields:
        if f["name"] not in have and len(cur["fields"]) < 12:
            cur["fields"].append({"name": f["name"], "path": f["path"], "unit": f.get("unit", "")})
    if default: cur["default"] = default[:3]
    doc["missions"][dimension] = cur
    mp.write_text(json.dumps(doc, indent=2) + "\n")
    return cur


def node_mission_json(repo):
    try:
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/{repo}/main/mission.json", timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def main():
    if "--sync" in sys.argv:
        n = 0
        for d in dogg.registry():
            m = node_mission_json(d["repo"])
            if m and m.get("fields"):
                fold_mission(d["dimension"], m["fields"], m.get("default")); n += 1
        print(f"synced {n} node reductions into chants/MISSIONS.json")
    else:
        nodes = json.loads(pathlib.Path(sys.argv[1]).read_text())
        for nd in nodes:
            f = append_registry(nd["dimension"], nd["repo"], nd["path"], nd["outlook"])
            fold_mission(nd["dimension"], nd.get("fields", []), nd.get("default"))
            print(("registered " if f else "already registered ") + nd["dimension"])
    (ROOT / "chants" / "CODEBOOK.lock").write_text(json.dumps(dogg.codebook_fingerprint(), indent=1) + "\n")
    print("CODEBOOK.lock re-issued (append-only extension)")


if __name__ == "__main__":
    main()
