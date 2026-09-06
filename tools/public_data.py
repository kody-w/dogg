"""Bounded read-only native DOGG snapshots for derived public views, not RAPP/1 conformance."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import stat

import rapp as native

MAX_FRAME = 256 * 1024
MAX_EPOCH = 4 * 1024 * 1024
MAX_UINT = 2**53 - 1
HEX = re.compile(r"[0-9a-f]{64}")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc_valid(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z", value):
        return False
    try:
        datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
        return True
    except ValueError:
        return False


def read_bytes(path, maximum=MAX_FRAME):
    path = Path(path).absolute()
    require(all(stat.S_ISDIR(parent.lstat().st_mode) for parent in path.parents),
            "source directory symlinks are unsupported")
    require(path.is_file() and not path.is_symlink(), "source must be a regular non-symlink file")
    require(path.stat().st_size <= maximum, "source exceeds byte limit")
    with path.open("rb") as handle:
        raw = handle.read(maximum + 1)
    require(0 < len(raw) <= maximum, "source is empty or exceeds byte limit")
    return raw


def strict_json(raw):
    require(len(raw) <= MAX_FRAME, "JSON exceeds byte limit")
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
            require(depth <= 32, "JSON nesting exceeds 32")
        elif byte in (93, 125):
            depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON member")
            result[key] = value
        return result

    def integer(token):
        require(len(token) <= 17 and token != "-0", "unsupported integer token")
        value = int(token)
        require(abs(value) <= MAX_UINT, "integer outside safe profile")
        return value

    def unsupported(_):
        raise ValueError("only exact safe integer tokens supported")

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                       parse_int=integer, parse_float=unsupported, parse_constant=unsupported)
    nodes = 0

    def bounded(item):
        nonlocal nodes
        nodes += 1
        require(nodes <= 20000, "JSON exceeds value limit")
        if isinstance(item, str):
            require(len(item.encode("utf-8")) <= 65536, "JSON string exceeds limit")
        elif isinstance(item, list):
            for child in item:
                bounded(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                bounded(key)
                bounded(child)
    bounded(value)
    return value


def head(value, stream=None):
    require(type(value) is dict, "HEAD must be an object")
    require(type(value.get("count")) is int and 1 <= value["count"] <= MAX_UINT, "empty or invalid HEAD count")
    require(type(value.get("stream_id")) is str and 1 <= len(value["stream_id"]) <= 256, "invalid HEAD stream")
    require(stream is None or value["stream_id"] == stream, "unexpected HEAD stream")
    require(type(value.get("head_frame")) is str and HEX.fullmatch(value["head_frame"]), "invalid HEAD hash")
    require(utc_valid(value.get("updated")), "invalid HEAD UTC")
    epoch, sealed = value.get("epoch_size", 288), value.get("sealed_epochs", 0)
    require(type(epoch) is int and 1 <= epoch <= 512, "unsupported epoch size")
    require(type(sealed) is int and 0 <= sealed <= MAX_UINT // epoch and sealed * epoch <= value["count"],
            "invalid sealed epoch count")
    return {**value, "epoch_size": epoch, "sealed_epochs": sealed}


def frame_shape(frame, seq, stream):
    require(type(frame) is dict and set(frame) == native.FRAME_KEYS, "invalid native frame key set")
    require(frame["spec"] == "rapp/1", "unexpected native envelope declaration")
    require(type(frame["seq"]) is int and frame["seq"] == seq, "native sequence/order mismatch")
    require(frame["stream_id"] == stream, "native stream mismatch")
    require(type(frame["kind"]) is str and len(frame["kind"]) <= 129 and re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*\.[a-z0-9]+(?:-[a-z0-9]+)*", frame["kind"]), "invalid kind")
    require(utc_valid(frame["utc"]) and type(frame["payload"]) is dict, "invalid native frame fields")
    for key in ("payload_hash", "frame_hash"):
        require(type(frame[key]) is str and HEX.fullmatch(frame[key]), "invalid frame hash")
    for key in ("prev", "prev_wave"):
        require(frame[key] is None or type(frame[key]) is str and HEX.fullmatch(frame[key]), "invalid predecessor")
    require(frame["prev_wave"] is None and frame["sig"] is None, "signed/swarm sources unsupported by this reader")
    require(seq != 0 or frame["prev"] is None, "invalid native genesis link")


def check_frame(frame, seq, stream):
    frame_shape(frame, seq, stream)
    require(frame["payload_hash"] == native.H("rapp/1:particle", frame["payload"]), "native payload hash mismatch")
    preimage = {key: value for key, value in frame.items() if key not in ("frame_hash", "sig")}
    require(frame["frame_hash"] == native.H("rapp/1:wave", preimage), "native frame hash mismatch")


class Chain:
    def __init__(self, directory, stream=None):
        self.directory = Path(directory)
        self.total_bytes = 0
        self.meta = head(strict_json(self.read(self.directory / "HEAD.json", 16384)), stream)
        self.epochs = {}

    def read(self, path, maximum=MAX_FRAME):
        raw = read_bytes(path, maximum)
        self.total_bytes += len(raw)
        require(self.total_bytes <= 8 * 1024 * 1024, "native read exceeds total byte budget")
        return raw

    def record(self, seq):
        require(type(seq) is int and 0 <= seq < self.meta["count"], "record outside HEAD")
        size = self.meta["epoch_size"]
        if seq < self.meta["sealed_epochs"] * size:
            index = seq // size
            if index not in self.epochs:
                raw = self.read(self.directory / "epochs" / f"{index}.jsonl", MAX_EPOCH)
                lines = raw.splitlines()
                require(len(lines) == size and all(lines), "epoch must contain exactly its declared records")
                values = [strict_json(line) for line in lines]
                for offset, value in enumerate(values):
                    frame_shape(value, index * size + offset, self.meta["stream_id"])
                self.epochs[index] = values
            return self.epochs[index][seq % size]
        return strict_json(self.read(self.directory / f"{seq}.json"))

    def tail(self, limit=2):
        require(1 <= limit <= 12, "tail coverage bound")
        start = max(0, self.meta["count"] - limit)
        records = [self.record(seq) for seq in range(start, self.meta["count"])]
        previous = None
        for seq, frame in enumerate(records, start):
            check_frame(frame, seq, self.meta["stream_id"])
            if previous is not None:
                require(frame["prev"] == previous["payload_hash"] and frame["utc"] >= previous["utc"], "native predecessor mismatch")
            previous = frame
        require(records[-1]["frame_hash"] == self.meta["head_frame"], "HEAD does not bind the latest record")
        return records

    def all(self, maximum=4096):
        require(self.meta["count"] <= maximum, "chain exceeds bounded history limit")
        frames, previous = [], None
        for seq in range(self.meta["count"]):
            frame = self.record(seq)
            check_frame(frame, seq, self.meta["stream_id"])
            require(previous is None or frame["prev"] == previous["payload_hash"]
                    and frame["utc"] >= previous["utc"], "native chain link mismatch")
            frames.append(frame)
            previous = frame
        require(frames[-1]["frame_hash"] == self.meta["head_frame"], "HEAD mismatch")
        return frames


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
