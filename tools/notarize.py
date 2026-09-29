#!/usr/bin/env python3
"""notarize.py — append a sha256 digest to the public notary stream (notary:@kody-w/global).

A notary frame records a digest, a short public label and the spine tick it was notarized at. The frame names
that tick by hash, so it cannot predate the tick. Each notary frame is then stamped with OpenTimestamps on its own
(anchors/ots/notary-<seq>.txt holds that frame's hash) and the nightly anchor upgrades the proof to a Bitcoin
attestation, after which that digest provably existed by the attesting block. A rapp/1 frame commits to its
predecessor's payload and nothing earlier, so a proof covers its own frame and, through `prev`, the one before it:
never assume a later frame's proof covers an older digest.
Only digests, never content: anyone reveals content later and verifies it by hashing.

  python3 tools/notarize.py <digest> "<label>"            # a maintainer, by hand
  python3 tools/notarize.py --issue-body-env BODY --issue N  # from the notarize issue form's body
"""
import datetime
import json
import os
import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import rapp as R
import chainio

STREAM = "notary:@kody-w/global"
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def utc():
    n = datetime.datetime.now(datetime.timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


def clean_label(label):
    """A short public label: printable ASCII only, at most 120 characters."""
    return re.sub(r"[^\x20-\x7e]", "", str(label or "")).strip()[:120]


def from_issue_body(body):
    """The digest and label from the notarize issue form, and nothing else from the untrusted issue text."""
    sections, current = {}, None
    for line in str(body or "").splitlines():
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip().lower()
            sections[current] = []
        elif current is not None and line.strip():
            sections[current].append(line.strip())
    digest = next(iter(sections.get("sha256 digest") or []), "")
    label = next(iter(sections.get("label") or []), "")
    return digest, label


def spine_head(root=ROOT):
    meta = json.loads((root / "ticks" / "HEAD.json").read_text())
    return int(meta["count"]) - 1, meta["head_frame"]


def notarize(digest, label, root=ROOT, issue=None):
    """Append one notary frame; a digest already on the stream returns its frame instead (idempotent)."""
    digest = str(digest or "").strip().lower()
    if not DIGEST.fullmatch(digest):
        raise ValueError("a digest is 64 hexadecimal characters: run shasum -a 256 <file>")
    label = clean_label(label)
    if not label:
        raise ValueError("a notarization needs a short public label")
    chain = root / "notary"
    frames = chainio.load_chain(chain)
    for frame in frames:
        if frame["payload"].get("digest") == digest:
            return frame, False
    head = frames[-1]
    tick, tick_frame = spine_head(root)
    payload = {"digest": digest, "label": label, "tick": tick, "tick_frame": tick_frame}
    if issue:
        payload["issue"] = int(issue)
    frame = R.build_frame("notary.digest", STREAM, head["seq"] + 1, max(utc(), head["utc"]), payload,
                          prev=head["payload_hash"])
    ok, step, why = R.verify_frame(frame, head=head, stream_id_of_record=STREAM)
    if not ok:
        raise ValueError(f"refusing an invalid notary frame: step {step}: {why}")
    chainio.append_frame(chain, frame, STREAM)
    return frame, True


def main(argv):
    args = list(argv)
    issue = None
    if "--issue" in args:
        issue = args[args.index("--issue") + 1]
    if "--issue-body-env" in args:
        digest, label = from_issue_body(os.environ.get(args[args.index("--issue-body-env") + 1], ""))
    else:
        digest, label = args[0], args[1]
    try:
        frame, added = notarize(digest, label, issue=issue)
    except ValueError as exc:
        print(json.dumps({"ok": False, "why": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "added": added, "seq": frame["seq"], "frame_hash": frame["frame_hash"],
                      "digest": frame["payload"]["digest"], "label": frame["payload"]["label"],
                      "tick": frame["payload"]["tick"], "tick_frame": frame["payload"]["tick_frame"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
