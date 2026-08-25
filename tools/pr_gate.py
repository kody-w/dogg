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
print(f"GATE PASS: {sorted(dims)[0]} — {len(paths)} file(s), all chains verify")
