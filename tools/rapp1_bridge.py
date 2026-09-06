#!/usr/bin/env python3
"""Opt-in, immutable native tick -> unsigned RAPP/1 snapshot. See BRIDGE.md."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

PROFILE = "dogg-rapp1-bridge/1"
TRUST = "unsigned-local"
REFERENCE = {
    "repository": "https://github.com/kody-w/rapp-1",
    "commit": "8a83b3fa8bebe16411fc4a130c6447ace15b43ac",
    "rapp_py_sha256": "d11ad216fb4cee7a2326d870c934876ecf67fb5af5df876f1866913a55ae3c38",
}
VENDOR = Path(__file__).absolute().parent / "rapp1_bridge_vendor" / "rapp.py"
SOURCE_REPOSITORY = "https://github.com/kody-w/dogg"
NATIVE_STREAM = "tick:@kody-w/global"
MAX_SOURCE = 1024 * 1024
MAX_DOCUMENT = 16 * 1024
MAX_UINT = 2**53 - 1
HEX64 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
RECORD = re.compile(r"ticks/(0|[1-9][0-9]{0,15})\.json")
SOURCE_KEYS = {
    "repository", "revision", "path", "sha256", "size", "blob",
    "native_stream_id", "native_seq", "native_frame_hash", "native_utc",
}
MANIFEST_KEYS = {
    "profile", "trust", "reference", "rappid", "stream_id", "frame", "source",
}
NATIVE_KEYS = {
    "spec", "kind", "stream_id", "seq", "utc", "payload", "payload_hash",
    "frame_hash", "prev", "prev_wave", "sig",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def directory(path):
    """Reject symlinks at every existing directory component."""
    path = Path(os.path.abspath(path))
    for component in reversed((path, *path.parents)):
        require(stat.S_ISDIR(component.lstat().st_mode),
                f"not a real directory (symlinks forbidden): {component}")
    return path


def read_file(path, limit):
    path = Path(path)
    directory(path.parent)
    require(stat.S_ISREG(path.lstat().st_mode), f"not a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        require(stat.S_ISREG(info.st_mode), f"not a regular file: {path}")
        require(0 < info.st_size <= limit, f"file size outside 1..{limit}: {path}")
        raw = handle.read(limit + 1)
        require(0 < len(raw) <= limit, f"file size outside 1..{limit}: {path}")
    return raw


def load_reference():
    # Compile precisely the checked bytes, never an import name or cached .pyc.
    raw = read_file(VENDOR, 256 * 1024)
    require(sha256(raw) == REFERENCE["rapp_py_sha256"], "reference source pin mismatch")
    module = types.ModuleType("_dogg_pinned_rapp1")
    module.__file__ = str(VENDOR)
    exec(compile(raw, str(VENDOR), "exec"), module.__dict__)
    return module


def depth_limit(raw, maximum):
    depth = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            require(depth <= maximum, f"JSON nesting exceeds {maximum}")
        elif byte in (93, 125):
            depth -= 1
            require(depth >= 0, "unbalanced JSON")


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON member")
        result[key] = value
    return result


def no_constant(_):
    raise ValueError("non-finite JSON number")


class NumberToken(str):
    """Native numeric lexemes are inspected without binary64 conversion."""


def number_token(token):
    require(len(token) <= 128, "native number token exceeds 128 characters")
    exponent = token.lower().partition("e")[2]
    require(not exponent or abs(int(exponent)) <= 308, "native number exponent exceeds 308")
    return NumberToken(token)


def read_native(raw, record, reference):
    match = RECORD.fullmatch(record)
    require(match is not None and int(match[1]) <= MAX_UINT, "only flat ticks/N.json supported")
    require(0 < len(raw) <= MAX_SOURCE, "native source exceeds 1 MiB or is empty")
    depth_limit(raw, 32)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                       parse_int=number_token, parse_float=number_token,
                       parse_constant=no_constant)
    nodes = 0

    def bounded(item):
        nonlocal nodes
        nodes += 1
        require(nodes <= 32768, "native JSON exceeds 32768 values")
        if isinstance(item, str):
            require(len(item.encode("utf-8")) <= 65536, "native string exceeds 64 KiB")
        elif isinstance(item, list):
            for child in item:
                bounded(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                require(len(key.encode("utf-8")) <= 256, "native member name exceeds 256 bytes")
                bounded(child)

    bounded(value)
    require(isinstance(value, dict) and set(value) == NATIVE_KEYS, "native tick frame key set")
    require(value["spec"] == "rapp/1" and value["kind"] == "tick.anchor"
            and value["stream_id"] == NATIVE_STREAM, "not a supported native DOGG tick")
    token = value["seq"]
    require(type(token) is NumberToken and re.fullmatch(r"0|[1-9][0-9]*", token) is not None,
            "native seq must be an unsigned integer token")
    seq = int(token)
    require(seq <= MAX_UINT and seq == int(match[1]), "native seq/path mismatch or overflow")
    require(reference.utc_valid(value["utc"]), "invalid native UTC")
    require(isinstance(value["payload"], dict), "native payload must be an object")
    require(type(value["payload"].get("tick")) is NumberToken
            and value["payload"]["tick"] == token, "native payload tick/seq mismatch")
    for key in ("frame_hash", "payload_hash"):
        require(type(value[key]) is str and HEX64.fullmatch(value[key]) is not None,
                f"invalid native {key}")
    for key in ("prev", "prev_wave"):
        require(value[key] is None or type(value[key]) is str
                and HEX64.fullmatch(value[key]) is not None, f"invalid native {key}")
    require(value["sig"] is None or type(value["sig"]) is str, "invalid native sig")
    return {"native_stream_id": NATIVE_STREAM, "native_seq": seq,
            "native_frame_hash": value["frame_hash"], "native_utc": value["utc"]}


def profile_value(value, depth=1):
    require(depth <= 8, "profile JSON nesting exceeds 8")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        require(0 <= value <= MAX_UINT, "profile number must be uint53")
    elif type(value) is str:
        require(len(value) <= 512 and all(32 <= ord(c) <= 126 for c in value),
                "profile strings must be printable ASCII, at most 512 characters")
    elif type(value) is dict:
        for key, child in value.items():
            profile_value(key, depth + 1)
            profile_value(child, depth + 1)
    else:
        raise ValueError("profile only permits objects, ASCII strings, uint53, bool and null")


def canonical(value, reference):
    profile_value(value)
    raw = reference.canonical(value).encode("utf-8")
    require(len(raw) <= MAX_DOCUMENT, "profile document exceeds 16 KiB")
    return raw


def read_document(raw, reference):
    require(0 < len(raw) <= MAX_DOCUMENT, "profile document exceeds 16 KiB or is empty")
    depth_limit(raw, 8)
    value = reference._strict_json(raw)
    require(raw == canonical(value, reference), "profile JSON bytes are not canonical")
    return value


def exact_keys(value, keys, label):
    require(type(value) is dict and set(value) == keys, f"{label} key set")


def validate_source(source, reference):
    exact_keys(source, SOURCE_KEYS, "source")
    require(source["repository"] == SOURCE_REPOSITORY, "source repository mismatch")
    require(type(source["revision"]) is str and REVISION.fullmatch(source["revision"]),
            "source revision must be a full lowercase Git commit")
    seq = source["native_seq"]
    require(type(seq) is int and 0 <= seq <= MAX_UINT, "native_seq must be uint53")
    require(source["path"] == f"ticks/{seq}.json", "unsafe or unsupported source path")
    require(source["native_stream_id"] == NATIVE_STREAM, "native stream mismatch")
    require(reference.utc_valid(source["native_utc"]), "invalid source UTC")
    for key in ("sha256", "native_frame_hash"):
        require(type(source[key]) is str and HEX64.fullmatch(source[key]), f"invalid source {key}")
    require(type(source["size"]) is int and 1 <= source["size"] <= MAX_SOURCE, "source size limit")
    require(source["blob"] == f"blobs/{source['sha256']}.bin", "unsafe source blob path")


def payload_for(source):
    return {"profile": PROFILE, "reference": REFERENCE, "source": source, "trust": TRUST}


def entries(path, expected):
    directory(path)
    names = set()
    with os.scandir(path) as scan:
        for entry in scan:
            names.add(entry.name)
            require(len(names) <= len(expected), "unexpected artifact entries")
    require(names == expected, "missing or unexpected artifact entries")


def verify_artifact(path, reference=None):
    reference = reference or load_reference()
    path = directory(path)
    entries(path, {"manifest.json", "frames", "blobs"})
    manifest_raw = read_file(path / "manifest.json", MAX_DOCUMENT)
    manifest = read_document(manifest_raw, reference)
    exact_keys(manifest, MANIFEST_KEYS, "manifest")
    require(manifest["profile"] == PROFILE and manifest["trust"] == TRUST, "unsupported profile/trust")
    require(manifest["reference"] == REFERENCE, "manifest reference pin mismatch")
    require(reference.rappid_valid(manifest["rappid"]), "invalid bridge RAPPID")
    require(manifest["stream_id"] == manifest["rappid"] + ":dogg-bridge", "bridge stream mismatch")
    source = manifest["source"]
    validate_source(source, reference)
    descriptor = manifest["frame"]
    exact_keys(descriptor, {"path", "sha256", "frame_hash"}, "frame descriptor")
    require(descriptor["path"] == "frames/0.json", "unsafe frame path")
    entries(path / "frames", {"0.json"})
    entries(path / "blobs", {source["sha256"] + ".bin"})
    frame_raw = read_file(path / "frames" / "0.json", MAX_DOCUMENT)
    frame = read_document(frame_raw, reference)
    ok, step, why = reference.verify_frame(frame, stream_id_of_record=manifest["stream_id"])
    require(ok, f"RAPP/1 frame step {step}: {why}")
    require(frame["kind"] == "memory.save" and frame["seq"] == 0 and frame["prev"] is None
            and frame["prev_wave"] is None and frame["sig"] is None, "unsupported bridge frame")
    require(reference.canonical(frame["payload"]) == reference.canonical(payload_for(source)),
            "bridge payload/manifest mismatch")
    require(descriptor["sha256"] == sha256(frame_raw)
            and descriptor["frame_hash"] == frame["frame_hash"], "frame descriptor hash mismatch")
    blob = read_file(path / source["blob"], MAX_SOURCE)
    require(len(blob) == source["size"] and sha256(blob) == source["sha256"],
            "source blob size/hash mismatch")
    return manifest, frame, blob, sha256(manifest_raw)


def write_new(path, raw):
    with open(path, "xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def report(manifest, frame, manifest_hash, status):
    return {
        "status": status, "profile": PROFILE, "trust": TRUST, "frames_verified": 1,
        "stream_id": manifest["stream_id"], "frame_hash": frame["frame_hash"],
        "source_sha256": manifest["source"]["sha256"], "source_bytes": manifest["source"]["size"],
        "manifest_sha256": manifest_hash, "reference": REFERENCE,
        "reference_executed_from": str(VENDOR), "reference_executed_sha256": REFERENCE["rapp_py_sha256"],
    }


def export_snapshot(source_root, record, revision, owner, slug, out):
    reference = load_reference()
    require(type(record) is str and RECORD.fullmatch(record), "only flat ticks/N.json supported")
    require(REVISION.fullmatch(revision), "source revision must be a full lowercase Git commit")
    # Validate labels before touching output, without minting an identity on repeats.
    require(reference.rappid_valid(f"rappid:@{owner}/{slug}:" + "0" * 64), "invalid owner/slug")
    root = directory(source_root)
    raw = read_file(root / record, MAX_SOURCE)
    native = read_native(raw, record, reference)
    digest = sha256(raw)
    source = {
        "repository": SOURCE_REPOSITORY, "revision": revision, "path": record,
        "sha256": digest, "size": len(raw), "blob": f"blobs/{digest}.bin", **native,
    }
    validate_source(source, reference)
    out = Path(os.path.abspath(out))
    directory(out.parent)
    if os.path.lexists(out):
        manifest, frame, blob, manifest_hash = verify_artifact(out, reference)
        require(manifest["source"] == source and blob == raw
                and manifest["rappid"].startswith(f"rappid:@{owner}/{slug}:"),
                "existing immutable snapshot has different input; it cannot be appended or overwritten")
        return report(manifest, frame, manifest_hash, "unchanged")
    rappid = reference.mint_rappid(owner, slug)
    stream = rappid + ":dogg-bridge"
    frame = reference.build_frame("memory.save", stream, 0, now(), payload_for(source), prev=None)
    ok, step, why = reference.verify_frame(frame, stream_id_of_record=stream)
    require(ok, f"RAPP/1 frame step {step}: {why}")
    frame_raw = canonical(frame, reference)
    manifest = {
        "profile": PROFILE, "trust": TRUST, "reference": REFERENCE, "rappid": rappid,
        "stream_id": stream, "source": source,
        "frame": {"path": "frames/0.json", "sha256": sha256(frame_raw), "frame_hash": frame["frame_hash"]},
    }
    manifest_raw = canonical(manifest, reference)
    out.mkdir(mode=0o700)
    (out / "frames").mkdir(mode=0o700)
    (out / "blobs").mkdir(mode=0o700)
    write_new(out / source["blob"], raw)
    write_new(out / "frames" / "0.json", frame_raw)
    # Manifest is the completion marker; an interrupted write is never a valid snapshot.
    write_new(out / "manifest.json", manifest_raw)
    manifest, frame, _, manifest_hash = verify_artifact(out, reference)
    return report(manifest, frame, manifest_hash, "created-new-local-snapshot")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="create one immutable snapshot; identical repeats are no-ops")
    export.add_argument("--source-root", default=".")
    export.add_argument("--record", required=True, help="flat native ticks/N.json only; no epoch bundles")
    export.add_argument("--source-revision", required=True, help="full Git commit, exporter-supplied provenance")
    export.add_argument("--owner", required=True, help="local RAPPID label, not proof of account ownership")
    export.add_argument("--slug", default="dogg-tick")
    export.add_argument("--out", required=True, help="new snapshot directory, or the identical existing snapshot")
    verify = commands.add_parser("verify", help="pinned Python RAPP/1 + closed profile integrity verification")
    verify.add_argument("artifact")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            result = export_snapshot(args.source_root, args.record, args.source_revision,
                                     args.owner, args.slug, args.out)
        else:
            manifest, frame, _, digest = verify_artifact(args.artifact)
            result = report(manifest, frame, digest, "verified")
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        print(f"bridge refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
