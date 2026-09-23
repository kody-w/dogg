#!/usr/bin/env python3
"""Primary beat: the spine's own heart, run on dedicated hardware.

PROTOCOL.md §1 promises a tick anchor roughly every ten minutes, and this is the beat that keeps
that promise. Each run makes its clone exactly origin/main. If the newest anchor is ten minutes
old, the run mints the next one, records the world dimension under it, re-derives orient.json,
holds every chain to the oracle, and pushes one commit. It never forces a push. If the push is
refused because main moved (the fallback beat, the orientation projection, a witness merge, a
registration), the run starts over from the new main and decides again. A tick minted by anyone
else in the meantime means this run stands down.

The fallback beat (tools/fallback_beat.py) mints only when the newest anchor is more than 25
minutes old. So while this beat runs, the fallback stands down; when this machine goes dark, the
fallback takes over; and when this machine returns, it appends after the fallback's anchors.
Same stream, same rules, one writer at a time decided by staleness, history never rewritten.

Run it from a clone of kody-w/dogg that nothing else uses, because each run discards anything
that is not on origin/main. The beat refuses any clone not marked for it, so it can never wipe a
working checkout: mark the service's own clone with `git config dogg.primaryBeat true`. On macOS,
keep that clone outside ~/Documents: a launchd agent cannot read TCC-protected folders. Run it
as a launchd agent rather than cron, since only a job in the user session can reach the keychain
that holds the push credential.

  python3 tools/primary_beat.py [--every 600] [--label "primary-beat (host)"] [--no-push]
  exit 0: a tick was minted (and pushed) · 10: not due, nothing written · 1: refused or failed
"""
import argparse
import datetime
import json
import pathlib
import subprocess
import sys
import time

TOOLS = pathlib.Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import rapp as R  # noqa: E402
import chainio  # noqa: E402

STREAM = "tick:@kody-w/global"
EVERY = 600            # PROTOCOL.md §1: roughly every ten minutes
SLACK = 30             # a scheduler that wakes a little early still keeps the cadence
ATTEMPTS = 4           # a main that keeps moving under us is a reason to stop, not to force
WORLD_TIMEOUT = 180    # twelve optional sources at six seconds each, with room to spare
STEP_TIMEOUT = 300
NOT_DUE = 10


class Refused(Exception):
    """Something this beat will not do. Nothing has been pushed."""


def fmt(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def parse(stamp):
    return datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=datetime.timezone.utc)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def git(root, *args, check=True, timeout=120):
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout)
    if check and done.returncode != 0:
        raise Refused(f"git {' '.join(args[:2])} failed: {(done.stderr or done.stdout).strip()[-400:]}")
    return done


def sync(root, remote, branch):
    """This clone becomes exactly the remote's main: a beat never builds on anything unpublished."""
    marked = git(root, "config", "--get", "dogg.primaryBeat", check=False).stdout.strip()
    if marked != "true":
        raise Refused(f"{root} is not marked as a beat clone; every run resets it to {remote}/{branch} and "
                      "deletes untracked files, so only a clone nothing else uses may be marked "
                      "(git config dogg.primaryBeat true)")
    git(root, "fetch", "-q", remote, branch)
    git(root, "reset", "-q", "--hard", "FETCH_HEAD")
    git(root, "clean", "-fdq")


def newest_anchor(root):
    ticks = root / "ticks"
    meta = json.loads((ticks / "HEAD.json").read_text())
    if meta.get("stream_id") != STREAM:
        raise Refused(f"ticks/HEAD.json names {meta.get('stream_id')!r}, not {STREAM}")
    head = json.loads((ticks / f"{meta['count'] - 1}.json").read_text())
    if head.get("frame_hash") != meta.get("head_frame") or head.get("seq") != meta["count"] - 1:
        raise Refused("ticks/HEAD.json does not name the newest anchor")
    return head


def mint(root, head, label, moment):
    stamp = fmt(moment)
    payload = {"tick": head["seq"] + 1, "beat_utc": stamp, "minted_by": label}
    frame = R.build_frame("tick.anchor", STREAM, head["seq"] + 1, stamp, payload, prev=head["payload_hash"])
    ok, step, why = R.verify_frame(frame, head=head, stream_id_of_record=STREAM)
    if not ok:
        raise Refused(f"refusing an invalid tick: step {step}: {why}")
    chainio.append_frame(root / "ticks", frame, STREAM)
    return frame


def run_tool(root, *args, timeout=STEP_TIMEOUT):
    return subprocess.run([sys.executable, str(root / "tools" / args[0]), *args[1:]],
                          cwd=str(root), capture_output=True, text=True, timeout=timeout)


def record_world(root, log):
    """The world dimension is optional per source and per tick: a failure is recorded, never fatal."""
    try:
        done = run_tool(root, "world.py", timeout=WORLD_TIMEOUT)
    except subprocess.TimeoutExpired:
        log("world: timed out; the tick stands and the last good world is kept")
        return "failed"
    for line in (done.stdout + done.stderr).strip().splitlines()[-3:]:
        log("world: " + line)
    return "ok" if done.returncode == 0 else "failed"


def project(root, world_state):
    """The same projection the fallback makes, so the orientation workflow finds nothing to change."""
    for args in (("verify_thread.py",), ("orient.py", "--world-refresh", world_state), ("orient.py", "--check")):
        done = run_tool(root, *args)
        if done.returncode != 0:
            raise Refused(f"{' '.join(args)} refused: {(done.stdout + done.stderr).strip()[-600:]}")


def beat(root=ROOT, every=EVERY, label="primary-beat", remote="origin", branch="main", push=True,
         world=None, now=utc_now, log=print, attempts=ATTEMPTS, pause=3.0):
    """Mint at most one tick. Returns the pushed (or, with push=False, committed) tick frame, or None
    when no tick is due. Raises Refused when it will not publish."""
    root = pathlib.Path(root)
    world = world or (lambda where: record_world(where, log))
    for attempt in range(1, attempts + 1):
        sync(root, remote, branch)
        head = newest_anchor(root)
        moment = now()
        age = (moment - parse(head["utc"])).total_seconds()
        if age < every - SLACK:
            log(f"not due: tick {head['seq']} is {int(age)}s old (a beat every {every}s)")
            return None
        frame = mint(root, head, label, moment)
        state = world(root)
        project(root, state)
        git(root, "add", "ticks", "world", "orient.json")
        message = f"tick {frame['seq']}: global anchor {frame['frame_hash'][:12]}" + (" + world" if state == "ok" else "")
        git(root, "commit", "-q", "-m", message)
        if not push:
            log(f"minted tick {frame['seq']} ({frame['frame_hash'][:16]}…), not pushed")
            return frame
        pushed = git(root, "push", "-q", remote, f"HEAD:{branch}", check=False)
        if pushed.returncode == 0:
            log(f"tick {frame['seq']} minted and pushed after {int(age)}s: {frame['frame_hash'][:16]}…"
                + ("" if state == "ok" else " (world refresh failed; last good world kept)"))
            return frame
        # Refused, never forced: main moved under us. Start again from what is published now.
        log(f"push refused on attempt {attempt}: {(pushed.stderr or pushed.stdout).strip()[-200:]}")
        time.sleep(pause * attempt)
    raise Refused(f"main kept moving: no tick published after {attempts} attempts")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--every", type=int, default=EVERY, help="seconds between ticks (default 600)")
    ap.add_argument("--label", default="primary-beat", help="written into each tick as minted_by")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--no-push", action="store_true", help="mint and commit locally, publish nothing")
    args = ap.parse_args(argv)
    if not 60 <= args.every <= 86400:
        ap.error("--every must be between 60 and 86400 seconds")
    try:
        frame = beat(ROOT, args.every, args.label, args.remote, args.branch, push=not args.no_push)
    except (Refused, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as ex:
        print(f"primary beat refused: {ex}", file=sys.stderr)
        return 1
    return 0 if frame is not None else NOT_DUE


if __name__ == "__main__":
    sys.exit(main())
