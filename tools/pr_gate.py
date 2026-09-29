#!/usr/bin/env python3
"""The contribution gate: a branch may merge ONLY if it proves itself.

Rules (fail closed):
  1. Every changed path, counting both sides of a rename, is inside exactly ONE
     witness-*/ directory — a contribution touches its own stream and nothing else
     (no tools, no workflows, no other chains).
  2. After the change, EVERY chain in the repo still verifies (tools/verify_thread.py).
  3. Every changed frame that claims a tick_frame — flat <seq>.json or inside a sealed
     epochs/<k>.jsonl bundle — names a real tick: its integer tick indexes the spine
     and the spine's frame there has exactly that hash.
Usage (CI): python3 tools/pr_gate.py origin/main
"""
import subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"

# --no-renames: a detected rename is listed by its new path alone, which would let a
# contribution move any file (or another chain's HEAD.json) into its own directory unseen.
r = subprocess.run(["git", "-C", str(ROOT), "diff", "--no-renames", "--name-only",
                    f"{base}...HEAD"], capture_output=True, text=True)
paths = [p for p in r.stdout.splitlines() if p.strip()]
if not paths:
    print("GATE: no changes vs base — nothing to merge")
    sys.exit(1)

dims = set()
for p in paths:
    top = p.split("/")[0]
    if not top.startswith("witness-"):
        print(f"GATE FAIL: '{p}' is outside a witness-*/ dimension — contributions may "
              "only append to their own stream")
        sys.exit(1)
    dims.add(top)
if len(dims) != 1:
    print(f"GATE FAIL: one contribution, one dimension — touched {sorted(dims)}")
    sys.exit(1)

v = subprocess.run([sys.executable, str(ROOT / "tools" / "verify_thread.py")],
                   capture_output=True, text=True)
print(v.stdout.strip())
if v.returncode != 0:
    print("GATE FAIL: a chain does not verify")
    sys.exit(1)

# the join key must be REAL: a frame claiming tick_frame X merges only if the spine's
# frame at that tick actually has that hash — corroboration is worthless on a fake key.
# The tick is an index into the spine, never a path built from contributor input.
import json
sys.path.insert(0, str(ROOT / "tools"))
import chainio
spine = None
checked = 0
for p in paths:
    if not p.endswith((".json", ".jsonl")) or p.endswith("HEAD.json"):
        continue
    try:
        text = (ROOT / p).read_text()
        frames = ([json.loads(l) for l in text.splitlines() if l.strip()]
                  if p.endswith(".jsonl") else [json.loads(text)])
    except Exception:
        continue
    for frame in frames:
        payload = frame.get("payload") if isinstance(frame, dict) else None
        if not isinstance(payload, dict) or "tick_frame" not in payload:
            continue
        if spine is None:
            spine = [t["frame_hash"] for t in chainio.load_chain(ROOT / "ticks")]
        tick = payload.get("tick")
        if not (isinstance(tick, int) and not isinstance(tick, bool)
                and 0 <= tick < len(spine) and spine[tick] == payload["tick_frame"]):
            print(f"GATE FAIL: {p} claims tick {tick!r} with hash "
                  f"{str(payload.get('tick_frame'))[:16]}… but the spine disagrees")
            sys.exit(1)
        checked += 1
print(f"GATE PASS: {sorted(dims)[0]} — {len(paths)} file(s), all chains verify, "
      f"{checked} tick reference(s) confirmed against the spine")
