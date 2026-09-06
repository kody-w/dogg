#!/usr/bin/env python3
"""Regenerate a bounded public orientation projection; unchanged inputs are a no-op.

No producers or external APIs are invoked. See SUBSCRIPTIONS.md for refresh wiring.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys

from public_data import Chain, fingerprint, read_bytes, require, strict_json

ROOT = Path(__file__).resolve().parent.parent
ROSTER_URL = "https://kody-w.github.io/dogg/subscriptions.json"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def previous_view(path):
    try:
        value = strict_json(read_bytes(path))
        if type(value) is not dict or value.get("schema") != "dogg/0-orient" or value.get("projection_version") != 1:
            return {}
        semantic = {key: item for key, item in value.items() if key not in ("generated_utc", "input_fingerprint")}
        if value.get("input_fingerprint") != fingerprint(semantic):
            return {}
        if type(value.get("status")) is not dict or type(value["status"].get("world")) is not dict:
            return {}
        return value
    except (OSError, UnicodeError, ValueError):
        return {}


def build(root, previous=None, world_refresh="not-attempted"):
    previous = previous or {}
    ticks = Chain(root / "ticks", "tick:@kody-w/global")
    tick = ticks.tail()[-1]
    out = {
        "schema": "dogg/0-orient",
        "projection_version": 1,
        "protocol": "https://github.com/kody-w/dogg/blob/main/PROTOCOL.md",
        "subscriptions_url": ROSTER_URL,
        "tick": {"seq": tick["seq"], "frame_hash": tick["frame_hash"], "utc": tick["utc"]},
        "status": {
            "scope": "derived native data; bounded latest/predecessor integrity, not signatures or RAPP1 conformance",
            "world": {}, "registry": {},
        },
        "sources": {"ticks": {"count": ticks.meta["count"], "head_frame": ticks.meta["head_frame"]}},
    }
    old_world = previous.get("world") if type(previous.get("world")) is dict else None
    old_status = previous.get("status", {}).get("world", {})
    try:
        world_chain = Chain(root / "world", "world:@kody-w/dogg")
        world = world_chain.tail()[-1]
        payload = world["payload"]
        require(type(payload.get("tick")) is int and 0 <= payload["tick"] <= tick["seq"], "world tick outside spine")
        require(type(payload.get("world")) is dict and type(payload.get("sources_failed")) is list, "world payload shape")
        require(all(type(value) is str and len(value) <= 100 for value in payload["sources_failed"]), "world failures shape")
        require(payload["tick"] != tick["seq"] or payload.get("tick_frame") == tick["frame_hash"], "world/spine mismatch")
        out["world"] = {
            "frame_hash": world["frame_hash"], "seq": world["seq"], "utc": world["utc"],
            "tick": payload["tick"], "tick_frame": payload.get("tick_frame"), "data": payload["world"],
        }
        state = "stale" if payload["tick"] < tick["seq"] else ("partial" if payload["sources_failed"] else "current")
        out["status"]["world"] = {
            "state": state, "ticks_behind": tick["seq"] - payload["tick"],
            "sources_failed": payload["sources_failed"],
            "last_refresh": world_refresh,
            "retained_last_good": False,
        }
        if world_refresh == "not-attempted" and old_world and old_world.get("frame_hash") == world["frame_hash"]:
            out["status"]["world"]["last_refresh"] = old_status.get("last_refresh", "not-attempted")
        out["sources"]["world"] = {"count": world_chain.meta["count"], "head_frame": world_chain.meta["head_frame"]}
    except (OSError, UnicodeError, ValueError):
        out["world"] = old_world
        out["status"]["world"] = {
            "state": "error", "code": "world-source-unavailable-or-invalid",
            "last_refresh": world_refresh, "retained_last_good": old_world is not None,
        }
        if world_refresh == "not-attempted":
            out["status"]["world"]["last_refresh"] = old_status.get("last_refresh", "not-attempted")
        out["sources"]["world"] = None
    if world_refresh == "failed":
        out["status"]["world"]["last_refresh"] = "failed"
    try:
        registry = Chain(root / "registry", "registry:@kody-w/global")
        records = registry.all()
        dimensions = {}
        for frame in records:
            if frame["kind"] == "registry.dimension":
                item = frame["payload"]
                require(type(item.get("dimension")) is str and len(item["dimension"]) <= 256, "registry dimension shape")
                dimensions[item["dimension"]] = item
        out["dimensions"] = list(dimensions.values())
        out["status"]["registry"] = {"state": "current", "records": len(records), "dimensions": len(dimensions)}
        out["sources"]["registry"] = {"count": registry.meta["count"], "head_frame": registry.meta["head_frame"]}
    except (OSError, UnicodeError, ValueError):
        old = previous.get("dimensions")
        out["dimensions"] = old if type(old) is list else []
        out["status"]["registry"] = {"state": "error", "code": "registry-unavailable-or-invalid", "retained_last_good": bool(old)}
        out["sources"]["registry"] = None
    chants = {}
    if (root / "chants").is_dir():
        paths = []
        for path in (root / "chants").glob("*.chant.json"):
            paths.append(path)
            require(len(paths) <= 128, "chant file limit")
        for path in sorted(paths):
            value = strict_json(read_bytes(path, 16384))
            require(type(value.get("streams")) is list and value["streams"]
                    and type(value["streams"][0]) is str and type(value.get("incantation")) is str, "chant shape")
            chants[value["streams"][0]] = value["incantation"]
    out["chants"] = chants
    out["input_fingerprint"] = fingerprint(out)
    return out


def regenerate(root=ROOT, check=False, world_refresh="not-attempted", clock=now):
    root = Path(root)
    output = root / "orient.json"
    previous = previous_view(output)
    out = build(root, previous, world_refresh)
    old_semantic = {key: value for key, value in previous.items() if key != "generated_utc"}
    if old_semantic == out:
        return "unchanged", previous
    if check:
        raise ValueError("orient.json is missing or stale; run python3 tools/orient.py")
    out = {"schema": out.pop("schema"), "generated_utc": clock(), **out}
    raw = (json.dumps(out, indent=2, ensure_ascii=False) + "\n").encode()
    require(len(raw) <= 256 * 1024 and not output.is_symlink(), "invalid orientation output")
    staging = output.with_name("orient.json.new")
    with staging.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(staging, output)
    return "updated", out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="local public checkout or deterministic fixture root")
    parser.add_argument("--check", action="store_true", help="fail if derived semantic inputs changed; never write")
    parser.add_argument("--world-refresh", choices=("not-attempted", "ok", "failed"), default="not-attempted")
    args = parser.parse_args()
    try:
        state, out = regenerate(args.root, args.check, args.world_refresh)
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
        print(f"orientation refused: {exc}", file=sys.stderr)
        return 1
    print(f"orient.json: {state}; tick {out['tick']['seq']}; {len(out['dimensions'])} dimensions; "
          f"world {out['status']['world']['state']}; no native writes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
