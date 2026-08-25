#!/usr/bin/env python3
"""CI oracle: re-verify the whole DOGG chain with the rapp/1 reference implementation.
Red CI = the chain is broken; fix the frames, never bypass the oracle."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import rapp as R
frames_dir = pathlib.Path(__file__).parent.parent / "frames"
head_meta = json.loads((frames_dir/"HEAD.json").read_text())
head = None
for i in range(head_meta["count"]):
    f = json.loads((frames_dir/f"{i}.json").read_text())
    ok, step, why = R.verify_frame(f, head=head, stream_id_of_record=head_meta["stream_id"])
    if not ok:
        print(f"FAIL frame {i}: step {step}: {why}"); sys.exit(1)
    head = f
assert head["frame_hash"] == head_meta["head_frame"], "HEAD.json head_frame mismatch"
print(f"OK: {head_meta['count']} frames verify as one chain on stream {head_meta['stream_id'][:40]}…")
ticks = pathlib.Path(__file__).parent.parent / "ticks"
if (ticks/"HEAD.json").exists():
    tm = json.loads((ticks/"HEAD.json").read_text()); th = None
    for i in range(tm["count"]):
        f = json.loads((ticks/f"{i}.json").read_text())
        ok, step, why = R.verify_frame(f, head=th, stream_id_of_record=tm["stream_id"])
        if not ok: print(f"FAIL tick {i}: {step}: {why}"); sys.exit(1)
        th = f
    assert th["frame_hash"] == tm["head_frame"], "ticks HEAD mismatch"
    print(f"OK: {tm['count']} tick anchors verify as the global spine")
