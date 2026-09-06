#!/usr/bin/env node
// Closed dogg-rapp1-bridge/1 verifier/recovery host, not a universal RAPP Consumer.
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const PROFILE = "dogg-rapp1-bridge/1";
const TRUST = "unsigned-local";
const REFERENCE = {
  repository: "https://github.com/kody-w/rapp-1",
  commit: "8a83b3fa8bebe16411fc4a130c6447ace15b43ac",
  rapp_py_sha256: "d11ad216fb4cee7a2326d870c934876ecf67fb5af5df876f1866913a55ae3c38",
};
const SOURCE_REPOSITORY = "https://github.com/kody-w/dogg";
const NATIVE_STREAM = "tick:@kody-w/global";
const MAX_SOURCE = 1024 * 1024;
const MAX_DOCUMENT = 16 * 1024;
const SELF = fileURLToPath(import.meta.url);
const VENDOR = path.join(path.dirname(SELF), "rapp1_bridge_vendor", "rapp.py");
const HEX64 = /^[0-9a-f]{64}$/;
const FRAME_KEYS = [
  "spec", "kind", "stream_id", "seq", "utc", "payload", "payload_hash",
  "frame_hash", "prev", "prev_wave", "sig",
];
const SOURCE_KEYS = [
  "repository", "revision", "path", "sha256", "size", "blob",
  "native_stream_id", "native_seq", "native_frame_hash", "native_utc",
];

function requireThat(condition, reason) {
  if (!condition) throw new Error(reason);
}

function sha256(raw) {
  return createHash("sha256").update(raw).digest("hex");
}

function directory(location) {
  const absolute = path.resolve(location);
  let part = absolute;
  for (;;) {
    requireThat(fs.lstatSync(part).isDirectory(), `not a real directory (symlinks forbidden): ${part}`);
    const parent = path.dirname(part);
    if (part === parent) break;
    part = parent;
  }
  return absolute;
}

function readFile(location, limit) {
  directory(path.dirname(location));
  requireThat(fs.lstatSync(location).isFile(), `not a regular file: ${location}`);
  const flags = fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0) | (fs.constants.O_NONBLOCK || 0);
  const fd = fs.openSync(location, flags);
  try {
    const info = fs.fstatSync(fd);
    requireThat(info.isFile() && info.size > 0 && info.size <= limit, `file size/type limit: ${location}`);
    const buffer = Buffer.alloc(limit + 1);
    let size = 0;
    while (size < buffer.length) {
      const count = fs.readSync(fd, buffer, size, buffer.length - size, null);
      if (count === 0) break;
      size += count;
    }
    requireThat(size > 0 && size <= limit, `file size limit: ${location}`);
    return buffer.subarray(0, size);
  } finally {
    fs.closeSync(fd);
  }
}

function entries(location, expected) {
  directory(location);
  const names = [];
  const handle = fs.opendirSync(location);
  try {
    for (;;) {
      const entry = handle.readSync();
      if (entry === null) break;
      names.push(entry.name);
      requireThat(names.length <= expected.length, "unexpected artifact entries");
    }
  } finally {
    handle.closeSync();
  }
  requireThat(names.sort().join("\0") === [...expected].sort().join("\0"),
    "missing or unexpected artifact entries");
}

function depthLimit(raw, maximum) {
  let depth = 0, quoted = false, escaped = false;
  for (const byte of raw) {
    if (quoted) {
      if (escaped) escaped = false;
      else if (byte === 92) escaped = true;
      else if (byte === 34) quoted = false;
    } else if (byte === 34) quoted = true;
    else if (byte === 91 || byte === 123) {
      depth += 1;
      requireThat(depth <= maximum, `JSON nesting exceeds ${maximum}`);
    } else if (byte === 93 || byte === 125) {
      depth -= 1;
      requireThat(depth >= 0, "unbalanced JSON");
    }
  }
}

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function canonical(value, depth = 1) {
  requireThat(depth <= 8, "profile JSON nesting exceeds 8");
  if (value === null || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") {
    requireThat(Number.isSafeInteger(value) && value >= 0, "profile number must be uint53");
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    requireThat(value.length <= 512 && /^[\x20-\x7e]*$/.test(value),
      "profile strings must be printable ASCII, at most 512 characters");
    return JSON.stringify(value);
  }
  requireThat(object(value), "profile only permits objects, ASCII strings, uint53, bool and null");
  return "{" + Object.keys(value).sort().map(
    (key) => canonical(key, depth + 1) + ":" + canonical(value[key], depth + 1),
  ).join(",") + "}";
}

function document(raw) {
  requireThat(raw.length > 0 && raw.length <= MAX_DOCUMENT, "profile document exceeds 16 KiB or is empty");
  depthLimit(raw, 8);
  const text = new TextDecoder("utf-8", { fatal: true }).decode(raw);
  const value = JSON.parse(text);
  // Parsing is provisional. Trust no fields until exact canonical octets match:
  // duplicate keys, -0, seq:0.0 / 0e0 and lossy numbers cannot survive this gate.
  requireThat(raw.equals(Buffer.from(canonical(value), "utf8")), "profile JSON bytes are not canonical");
  return value;
}

function exactKeys(value, keys, label) {
  requireThat(object(value) && Object.keys(value).sort().join("\0") === [...keys].sort().join("\0"),
    `${label} key set`);
}

function equal(a, b) {
  return canonical(a) === canonical(b);
}

function validUtc(value) {
  return typeof value === "string" &&
    /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$/.test(value) &&
    value.slice(0, 4) !== "0000" &&
    Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
}

function validRappid(value) {
  if (typeof value !== "string") return false;
  const match = /^rappid:@([a-z0-9]+(?:-[a-z0-9]+)*)\/([a-z0-9]+(?:-[a-z0-9]+)*):([0-9a-f]{64})$/.exec(value);
  return match !== null && match[1].length <= 39 && match[2].length <= 100;
}

function validateSource(source) {
  exactKeys(source, SOURCE_KEYS, "source");
  requireThat(source.repository === SOURCE_REPOSITORY, "source repository mismatch");
  requireThat(typeof source.revision === "string" && /^[0-9a-f]{40}$/.test(source.revision),
    "source revision must be a full lowercase Git commit");
  requireThat(Number.isSafeInteger(source.native_seq) && source.native_seq >= 0, "native_seq must be uint53");
  requireThat(source.path === `ticks/${source.native_seq}.json`, "unsafe or unsupported source path");
  requireThat(source.native_stream_id === NATIVE_STREAM, "native stream mismatch");
  requireThat(validUtc(source.native_utc), "invalid source UTC");
  for (const key of ["sha256", "native_frame_hash"]) {
    requireThat(typeof source[key] === "string" && HEX64.test(source[key]), `invalid source ${key}`);
  }
  requireThat(Number.isSafeInteger(source.size) && source.size > 0 && source.size <= MAX_SOURCE, "source size limit");
  requireThat(source.blob === `blobs/${source.sha256}.bin`, "unsafe source blob path");
}

function H(domain, value) {
  return sha256(Buffer.from(domain + "\n" + canonical(value), "utf8"));
}

function verifyArtifact(location) {
  requireThat(sha256(readFile(VENDOR, 256 * 1024)) === REFERENCE.rapp_py_sha256, "reference source pin mismatch");
  const root = directory(location);
  entries(root, ["manifest.json", "frames", "blobs"]);
  const manifestRaw = readFile(path.join(root, "manifest.json"), MAX_DOCUMENT);
  const manifest = document(manifestRaw);
  exactKeys(manifest, ["profile", "trust", "reference", "rappid", "stream_id", "frame", "source"], "manifest");
  requireThat(manifest.profile === PROFILE && manifest.trust === TRUST, "unsupported profile/trust");
  requireThat(equal(manifest.reference, REFERENCE), "manifest reference pin mismatch");
  requireThat(validRappid(manifest.rappid), "invalid bridge RAPPID");
  requireThat(manifest.stream_id === manifest.rappid + ":dogg-bridge", "bridge stream mismatch");
  validateSource(manifest.source);
  exactKeys(manifest.frame, ["path", "sha256", "frame_hash"], "frame descriptor");
  requireThat(manifest.frame.path === "frames/0.json", "unsafe frame path");
  entries(path.join(root, "frames"), ["0.json"]);
  entries(path.join(root, "blobs"), [manifest.source.sha256 + ".bin"]);
  const frameRaw = readFile(path.join(root, "frames", "0.json"), MAX_DOCUMENT);
  const frame = document(frameRaw);
  exactKeys(frame, FRAME_KEYS, "frame");
  requireThat(frame.spec === "rapp/1" && frame.kind === "memory.save", "unsupported bridge frame");
  requireThat(frame.stream_id === manifest.stream_id, "frame stream mismatch");
  requireThat(frame.seq === 0 && frame.prev === null && frame.prev_wave === null && frame.sig === null,
    "snapshot must be unsigned local seq=0 with null predecessors");
  requireThat(validUtc(frame.utc), "invalid frame UTC");
  const payload = { profile: PROFILE, reference: REFERENCE, source: manifest.source, trust: TRUST };
  requireThat(equal(frame.payload, payload), "bridge payload/manifest mismatch");
  requireThat(typeof frame.payload_hash === "string" && HEX64.test(frame.payload_hash) &&
    frame.payload_hash === H("rapp/1:particle", frame.payload), "payload hash mismatch");
  const preimage = Object.fromEntries(Object.entries(frame).filter(
    ([key]) => key !== "frame_hash" && key !== "sig",
  ));
  requireThat(typeof frame.frame_hash === "string" && HEX64.test(frame.frame_hash) &&
    frame.frame_hash === H("rapp/1:wave", preimage), "frame hash mismatch");
  requireThat(manifest.frame.sha256 === sha256(frameRaw) && manifest.frame.frame_hash === frame.frame_hash,
    "frame descriptor hash mismatch");
  const blob = readFile(path.join(root, manifest.source.blob), MAX_SOURCE);
  requireThat(blob.length === manifest.source.size && sha256(blob) === manifest.source.sha256,
    "source blob size/hash mismatch");
  return { manifest, frame, blob, manifestHash: sha256(manifestRaw) };
}

function writeNew(location, raw) {
  const fd = fs.openSync(location, fs.constants.O_WRONLY | fs.constants.O_CREAT |
    fs.constants.O_EXCL | (fs.constants.O_NOFOLLOW || 0), 0o600);
  try {
    fs.writeFileSync(fd, raw);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
}

function summary(verified, status) {
  return {
    status, profile: PROFILE, trust: TRUST, frames_verified: 1,
    scope: "closed-bridge-integrity-and-byte-recovery; no authenticated Consumer claim",
    stream_id: verified.manifest.stream_id, frame_hash: verified.frame.frame_hash,
    source_sha256: verified.manifest.source.sha256, source_bytes: verified.blob.length,
    manifest_sha256: verified.manifestHash, reference: REFERENCE,
    reference_source_checked_not_executed: VENDOR,
    node_verifier_sha256: sha256(readFile(SELF, 256 * 1024)),
  };
}

function main() {
  const [command, artifact, destination, ...rest] = process.argv.slice(2);
  requireThat((command === "verify" && artifact && !destination) ||
    (command === "recover" && artifact && destination && rest.length === 0),
  "usage: node tools/rapp1_recover.mjs verify ARTIFACT | recover ARTIFACT NEW_DIRECTORY");
  const verified = verifyArtifact(artifact);
  if (command === "verify") {
    console.log(JSON.stringify(summary(verified, "verified")));
    return;
  }
  const out = path.resolve(destination);
  directory(path.dirname(out));
  // Never use a source-provided path as an extraction path; all names are fixed.
  fs.mkdirSync(out, { mode: 0o700 });
  writeNew(path.join(out, "source.json"), verified.blob);
  const receipt = {
    profile: PROFILE, trust: TRUST, recovered_path: "source.json",
    stream_id: verified.manifest.stream_id, frame_hash: verified.frame.frame_hash,
    source_sha256: verified.manifest.source.sha256, source_bytes: verified.blob.length,
    manifest_sha256: verified.manifestHash, reference: REFERENCE,
  };
  writeNew(path.join(out, "receipt.json"), Buffer.from(canonical(receipt), "utf8"));
  console.log(JSON.stringify({ ...summary(verified, "recovered"), recovered_path: path.join(out, "source.json") }));
}

try {
  main();
} catch (error) {
  console.error(`bridge refused: ${error.message}`);
  process.exitCode = 1;
}
