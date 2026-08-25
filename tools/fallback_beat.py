#!/usr/bin/env python3
"""Fallback beat: the spine outlives any single machine.

The primary beat runs on dedicated hardware. This script (run by the fallback-beat
workflow on a schedule) mints a tick ONLY when the newest anchor is stale — so if the
primary's machine dies, the repo itself keeps the heartbeat going, and when the primary
returns it simply appends after the fallback's anchors. Same stream, same rules, one
writer at a time decided by staleness, history never rewritten.
"""
import json, sys, pathlib, datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import rapp as R
import chainio

ROOT = pathlib.Path(__file__).resolve().parent.parent
TICKS = ROOT / "ticks"
STREAM = "tick:@kody-w/global"
STALE_SECONDS = 25 * 60      # primary beats every ~10 min; two misses = dark

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

def fmt(n):
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"

def main():
    meta = json.loads((TICKS / "HEAD.json").read_text())
    updated = datetime.datetime.strptime(meta["updated"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=datetime.timezone.utc)
    age = (utc_now() - updated).total_seconds()
    if age < STALE_SECONDS:
        print(f"spine healthy: newest anchor is {int(age)}s old — standing down")
        return 0
    chain = chainio.load_chain(TICKS)
    head = chain[-1]
    payload = {"tick": head["seq"] + 1, "beat_utc": fmt(utc_now()),
               "minted_by": "fallback-beat (primary stale)"}
    f = R.build_frame("tick.anchor", STREAM, head["seq"] + 1, fmt(utc_now()),
                      payload, prev=head["payload_hash"])
    ok, step, why = R.verify_frame(f, head=head, stream_id_of_record=STREAM)
    if not ok:
        raise ValueError(f"refusing invalid fallback tick: {step}: {why}")
    chainio.append_frame(TICKS, f, STREAM)
    print(f"FALLBACK tick {f['seq']} minted (primary was {int(age)}s stale): "
          f"{f['frame_hash'][:16]}…")
    return 1

if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 0)
