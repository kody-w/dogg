#!/usr/bin/env python3
"""The contribution gate: a branch may merge ONLY if it proves itself.

Rules (fail closed):
  1. Every changed path is inside exactly ONE witness-*/ directory — a contribution
     touches its own stream and nothing else (no tools, no workflows, no other chains).
  2. After the change, EVERY chain in the repo still verifies (tools/verify_thread.py).
Usage (CI): python3 tools/pr_gate.py origin/main
"""
import subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"

r = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", f"{base}...HEAD"],
                   capture_output=True, text=True)
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
# ticks/<tick>.json actually has that hash — corroboration is worthless on a fake key
import json
checked = 0
for p in paths:
    if not p.endswith(".json") or p.endswith("HEAD.json"):
        continue
    try:
        frame = json.loads((ROOT / p).read_text())
        payload = frame.get("payload", {})
    except Exception:
        continue
    if "tick_frame" in payload:
        tickf = ROOT / "ticks" / f"{payload.get('tick')}.json"
        if not tickf.exists():
            # older ticks live in sealed bundles; resolve through the chain reader
            sys.path.insert(0, str(ROOT / "tools"))
            import chainio
            ticks = chainio.load_chain(ROOT / "ticks")
            anchor = ticks[payload["tick"]] if 0 <= payload.get("tick", -1) < len(ticks) else None
        else:
            anchor = json.loads(tickf.read_text())
        if anchor is None or anchor["frame_hash"] != payload["tick_frame"]:
            print(f"GATE FAIL: {p} claims tick {payload.get('tick')} with hash "
                  f"{str(payload.get('tick_frame'))[:16]}… but the spine disagrees")
            sys.exit(1)
        checked += 1
print(f"GATE PASS: {sorted(dims)[0]} — {len(paths)} file(s), all chains verify, "
      f"{checked} tick reference(s) confirmed against the spine")
