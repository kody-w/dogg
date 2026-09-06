# Native DOGG → RAPP/1: one-tick snapshot bridge

This opt-in bridge exports **one existing flat-tail `ticks/N.json` file**, unchanged,
into a new local RAPP/1 memory stream. A separate Node.js process validates the closed
transport and recovers the original bytes. It performs no network calls, runs no
recovered code, and does not change native history, native tools, scheduled writers,
registries, or any live service.

It is an **immutable snapshot**, not an incremental history migration. Native
`tick:@kody-w/global` remains provenance. The bridge mints a genuine keyless RAPPID
once with UUID4 through the pinned reference and emits exactly one `memory.save`
frame on `<rappid>:dogg-bridge`: `seq: 0`, `prev: null`, `prev_wave: null`, `sig: null`.
The frame's UTC is export time; native UTC is separate provenance. This does **not**
re-parent the native tick or pretend it was originally written to RAPP/1.

## Cold-start workflow

Requirements: Git, Python 3.12+ and Node.js 22+; no pip/npm packages, credentials,
private files, or sibling checkout. Start at the root of the **public bridge
branch/PR checkout containing this file** (not an older `main` without the bridge).
The working tree and output parents must be quiescent, local directories that you
control. Use a fresh output name if `bridge-demo` already exists.

Copy/paste in a POSIX shell:

```sh
set -eu
python3 tools/verify_thread.py
python3 tests/test_rapp1_bridge.py

mkdir bridge-demo
SOURCE_REVISION=$(git rev-parse HEAD)
RECORD=$(python3 -c 'import json; print("ticks/%d.json" % (json.load(open("ticks/HEAD.json"))["count"] - 1))')

# Confirm this exact working-tree source belongs to the stated commit.
git show "$SOURCE_REVISION:$RECORD" > bridge-demo/git-source.json
cmp "$RECORD" bridge-demo/git-source.json

python3 tools/rapp1_bridge.py export \
  --source-root . --record "$RECORD" --source-revision "$SOURCE_REVISION" \
  --owner local --slug dogg-tick --out bridge-demo/transfer
python3 tools/rapp1_bridge.py verify bridge-demo/transfer

# This directory is the complete transport; it can be copied to another machine.
cp -R bridge-demo/transfer bridge-demo/node-input
node tools/rapp1_recover.mjs verify bridge-demo/node-input
node tools/rapp1_recover.mjs recover bridge-demo/node-input bridge-demo/recovered
cmp "$RECORD" bridge-demo/recovered/source.json
printf 'PASS: Python source bytes equal Node recovered bytes\n'

# Same inputs AND same target: unchanged, same identity and frame, no new history.
python3 tools/rapp1_bridge.py export \
  --source-root . --record "$RECORD" --source-revision "$SOURCE_REVISION" \
  --owner local --slug dogg-tick --out bridge-demo/transfer
```

Both verification hosts must print `"frames_verified": 1`, the same frame hash,
manifest SHA-256, source SHA-256 and source byte count. Python reports the exact
reference source path/hash it executed. Node reports its own verifier source hash
and explicitly labels the Python reference as **checked, not executed**. `cmp`
confirms byte equality, not just equality of parsed JSON. Tests also remove the
original source before Node recovery and preserve precision-sensitive number
tokens, Unicode and CRLF formatting.

To receive on another host, copy `transfer/` and this public checkout's
`tools/rapp1_recover.mjs` plus `tools/rapp1_bridge_vendor/rapp.py` in the same
relative layout. No source DOGG checkout is needed by the receiver. Run the two
Node commands against the transferred directory. This proves two runtimes/processes;
it does not claim two independent owners, signatures, or independent networks.

## Immutable repeat and recovery rules

* A new output directory is an explicit new local snapshot and identity, even if
  another snapshot elsewhere observed the same source. It is **not another native
  tick or a continuation of an older bridge stream**.
* Repeating identical bytes, source revision/path and owner/slug against the same
  valid snapshot reports `unchanged`; no remint, rewrite, append or timestamp
  change occurs. Changed inputs at that target fail. There is no global duplicate
  ledger and no incremental mode.
* Recovery always requires a **new destination**. Existing directories, files
  and symlinks are refused; `source.json` is a fixed filename, never an extraction
  path supplied by a payload. `receipt.json` is a local integrity receipt, not an
  owner signature.
* Each artifact contains exactly the files below. Unknown entries, symlinks,
  non-regular files, missing/corrupt blobs, mismatched pins and hashes fail closed.
  The exporter writes its manifest last; a missing/partial manifest is not a
  valid transfer. An interrupted recovery without its final receipt is incomplete.
  Failed output directories are left for inspection, not silently reused/deleted.
* Parent directories must already exist and contain no symlink components.
  Internal source/transport paths cannot contain traversal. This is not a
  hostile-concurrent-filesystem sandbox: keep source, transport and destination
  parent directories under your control during an operation. All verified blob
  bytes are held in memory before Node creates its destination.

## Closed transport profile: `dogg-rapp1-bridge/1`

This directory profile is **not a RAPP egg or a new egg dialect**. It packages a
conformant unsigned frame and its opaque archival source; it is not a runnable
organism. No ZIP or other archive framework is used.

```text
transfer/
  manifest.json
  frames/0.json
  blobs/<source-sha256>.bin
```

Metadata JSON is the exact UTF-8 canonical serialization: no BOM, trailing
newline, whitespace variations, duplicate members, alternate numeric spelling or
extra members. The closed profile permits only objects, printable ASCII strings,
uint53 integers, booleans and null (no arrays/floats). Keys are sorted ascending;
this ASCII/integer subset has identical JCS bytes in Python and JavaScript.
Node's `JSON.parse` result remains provisional until exact canonical bytes match,
so duplicate members or `seq: 0.0`, `0e0`, `-0` cannot be normalized into acceptance.
This stricter transport subset does not restrict or redefine general RAPP/1.

`manifest.json` has exactly:

| Member | Meaning |
|---|---|
| `profile` | Exactly `dogg-rapp1-bridge/1` |
| `trust` | Exactly `unsigned-local` |
| `reference` | Exact repository, commit and `rapp_py_sha256` pin below |
| `rappid` | A newly minted keyless RAPPID; owner/slug labels are not account authentication |
| `stream_id` | Exactly `<rappid>:dogg-bridge` |
| `frame` | Exactly `{path: "frames/0.json", sha256, frame_hash}` |
| `source` | Exactly the descriptor below |

`source` contains exactly `repository` (`https://github.com/kody-w/dogg`),
`revision` (40 lowercase hex characters), `path` (`ticks/<native_seq>.json`),
`sha256`, `size`, `blob` (`blobs/<sha256>.bin`), `native_stream_id`
(`tick:@kody-w/global`), `native_seq`, `native_frame_hash`, and `native_utc`.
Source/descriptor/file hashes are ordinary SHA-256 of exact octets. The original
source file is read once and is **never re-dumped as the archival payload**.

The frame has the frozen eleven RAPP/1 keys. Its payload is exactly
`{profile, reference, source, trust}`, equal to the corresponding manifest values.
`payload_hash` is `SHA256("rapp/1:particle\n" || JCS(payload))`; `frame_hash` is
`SHA256("rapp/1:wave\n" || JCS(frame without frame_hash and sig))`.
Both hosts verify the snapshot's identity/stream binding, key sets, UTC,
genesis/null-link rules, byte hashes and exact payload/manifest agreement.
The Python host additionally uses the pinned canonical reference's frame checker.

### Bounds and unsupported inputs

| Input | Bound |
|---|---|
| Native file/blob | 1 byte–1 MiB, one regular file only |
| Native JSON | At most 32 nesting levels and 32,768 values |
| Native strings/member names | At most 64 KiB / 256 UTF-8 bytes |
| Native number tokens | At most 128 characters; explicit exponent magnitude ≤ 308 |
| Native sequence | Integer token, 0–2^53−1; must agree with path and payload tick |
| Manifest / frame | At most 16 KiB each; at most 8 JSON nesting levels |
| Metadata strings / numbers | Printable ASCII, ≤ 512 characters / uint53 only |
| Transport | Exactly one manifest, one frame, one blob, two subdirectories |

The exporter checks a native tick's shape and extracts bounded provenance. Native
payload numbers need not be losslessly representable as RAPP/1 numbers, because
they remain **opaque bytes**, not RAPP/1 payload numbers. Duplicate native JSON
members, invalid UTF-8, surrogate code points, non-finite literals and excessive
sizes/depth/tokens refuse rather than producing partial success.

Sealed epoch lines/bundles, arbitrary source paths, other dimensions, history
rewrites, native write-back, signing, registry updates, and incremental append
are deliberately unsupported. To export an older tick stored only in an epoch,
this version refuses: it will not parse/reformat a line and call that the original
flat file. Select a current flat-tail record in a static checkout instead.

## Source pin and trust boundary

The isolated dependency is copied byte-for-byte from
[kody-w/rapp-1 PR 38](https://github.com/kody-w/rapp-1/pull/38), commit
[`8a83b3fa8bebe16411fc4a130c6447ace15b43ac`](https://github.com/kody-w/rapp-1/tree/8a83b3fa8bebe16411fc4a130c6447ace15b43ac).
It is a reviewed implementation candidate, **not canonical-main ratification**.
The accepted normative frozen rev-15 SPEC/anchor is unchanged.

* `rapp.py` SHA-256: `d11ad216fb4cee7a2326d870c934876ecf67fb5af5df876f1866913a55ae3c38`
* MIT `LICENSE` SHA-256: `3b1952c1f983b4fc60337137cc6c863e9ea617ce551397c80e5b2d74eb1c476b`
* Preserved source/license/provenance: [`tools/rapp1_bridge_vendor/`](tools/rapp1_bridge_vendor/)

Python checks the pinned source before compiling **those very bytes**, without
import-name lookup, development checkouts or `.pyc` caches. Node independently
checks its local reference source pin and implements only this closed transport
profile with built-in `fs`/`crypto`. Neither host downloads a floating dependency.
The existing native `tools/rapp.py` is deliberately untouched.

**Integrity is not authenticity.** A native `frame_hash` in the descriptor is a
copied native claim. `--source-revision` is exporter-supplied provenance, not a
Git/owner verification performed by the bridge; the workflow's `git show`/`cmp`
step supplies that additional local check. The recovery hosts hash the opaque
blob but do not certify its native semantics or truth. Run the separate native
oracle for native chain integrity. No owner trust, registry lookup, registered
genesis, signature verification, anti-rollback ledger or universal authenticated
RAPP Consumer acceptance is claimed. A party can replace/re-hash an entire unsigned
snapshot; compare its manifest/frame/source hashes with an independently trusted
channel if authenticity matters.

## Why the native/bridge distinction matters

At public DOGG commit `ce1fa2af1454b96217760529e246c244393b8d17`,
the last committed change was `fallback tick 854`, writing `ticks/854.json`,
`world/758.json` and their head pointers. The actual producer path is
`.github/workflows/fallback-beat.yml` → `tools/fallback_beat.py` →
native `tools/rapp.py` → `tools/chainio.py`; it explicitly emits the native
`tick:@kody-w/global` label. `tools/world.py` uses `world:@kody-w/dogg`.
The scheduled workflow and recent fallback commits demonstrate the active
boundary; a stored old label alone does not establish current writer behavior.

`tools/verify_thread.py` loads the sealed-epoch-plus-flat-tail layout and checks
native hashes/links. At that commit it passed **1,652 frames across seven chains**.
The pinned RAPP/1 checker instead refuses native tick IDs at the stream grammar
gate. Both observations are expected; neither authorizes changing native data.
The bridge lives beside those paths and is never imported by them.

## Tests and CI

```sh
python3 tests/test_rapp1_bridge.py
python3 tools/verify_thread.py
```

The stdlib `unittest` runner invokes real Node subprocesses and covers exact-byte
recovery, source removal, raw-number loss, immutable repeats, corrupt/missing blobs,
wrong hashes/pins, masked imports/stale bytecode, duplicate/malformed JSON, forbidden
sequence tokens, bounds, invalid links/identities, path traversal, symlinks, FIFO
refusal and overwrite protection. `.github/workflows/verify.yml` runs the native
oracle and bridge contracts separately on every push/PR. No test is allowed to
rewrite a stored native record.
