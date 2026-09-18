# Native DOGG/0 → RAPP/1: signed forward projection

`dogg-rapp1-bridge/2` is a subordinate operational profile over the frozen
RAPP/1 wire. It continuously projects one existing native DOGG/0 chain into a
keyed RAPP/1 memory stream using the already-registered `memory.save` kind. It
does not define DOGG/1, add an envelope or endpoint, rewrite/relabel native
records, or replace the immutable one-record `dogg-rapp1-bridge/1` snapshot in
[BRIDGE.md](BRIDGE.md).

The bridge is local and forward-only. Before minting anything it reads the
complete selected native chain from the selected immutable Git commit tree,
applies the `tools/chainio.py` storage contract, and verifies every record with
the native `tools/rapp.py` oracle. `HEAD.json`, flat records, and sealed epoch
blobs must all be ordinary `100644` Git blobs; mutable worktree paths are never
source authority. Bridge/2 bounds a native record at 1 MiB and declared
`epoch_size` at `1..288`. A sealed epoch Git blob may therefore exceed the
generic 1 MiB blob ceiling, but may not exceed
`epoch_size * (1 MiB + 1)` bytes: at most 1 MiB of record octets plus one LF per
declared record. It is streamed in declared line order with a bounded read;
every line must be nonempty valid UTF-8/JSON, no record may exceed 1 MiB, and
the epoch must contain exactly `epoch_size` LF-terminated records. Flat native
records retain the tighter 1 MiB whole-blob bound.

For a tick-referencing dimension the bridge separately verifies the complete
`ticks/` chain at the **same immutable Git commit** and requires every resolved
anchor to have the exact tick stream, `tick.anchor` kind, and
`payload.tick == seq`. It never joins a dimension head to a newer independent
spine head. Native record octets are copied opaquely, not parsed and re-dumped
as archival truth.

## Exact frame profile

Every output record is an ordinary RAPP/1 frame with exactly the frozen eleven
keys. It has:

- `spec: "rapp/1"`, `kind: "memory.save"`;
- `stream_id: "<keyed-estate-owner-rappid>:dogg-bridge"`;
- a contiguous sequence beginning at zero, normal RAPP particle/wave links,
  `prev_wave: null`, and a detached unencoded ES256 JWS in `sig`;
- bridge projection time in `utc` (native time remains provenance); and
- a payload with exactly `profile`, `native_source`, `tick_frame`, and
  `tick_source`.

The signed profile never accepts a null `sig`, even though generic RAPP/1 allows
unsigned memory frames. Every accepted frame must carry the exact registered
estate-owner `kid`; its protected `alg` must match that owner's registered SPKI
(`ES256` for P-256 or `EdDSA` for Ed25519), and the detached signature must
verify. Owner initialization in this implementation mints P-256/ES256.

`profile` is exactly `dogg-rapp1-bridge/2`. `native_source` has exactly:

| Member | Meaning |
|---|---|
| `repository` | `https://github.com/kody-w/dogg` |
| `commit` | Full immutable SHA-1 Git commit containing the source |
| `chain_path` | Native chain directory |
| `storage_path` / `storage_line` | Flat file and `null`, or sealed JSONL bundle and one-based line |
| `raw_sha256` / `raw_bytes` | Ordinary SHA-256 and byte count of the exact native record octets |
| `native_stream_id` | Original DOGG/0 stream label, unchanged |
| `native_genesis_frame_hash` | Verified original chain genesis |
| `native_seq` / `native_frame_hash` / `native_utc` | Exact verified native frame provenance |

For a flat record the raw object is the complete file, including its existing
formatting and terminator. For a sealed epoch it is the exact JSONL record
octets excluding the bundle's LF record terminator. `tick_frame` is either
`null` or the exact string in the native payload. When non-null, `tick_source`
has the same exact tuple shape and describes the independently verified native
tick record at the same commit; otherwise `tick_source` is `null`.

RAPP sequence `N` projects native sequence `N`. Cold start therefore projects
native genesis through the verified head; later runs append only the missing
suffix. The signed frame contains no receiver, copy, or delivery status.

## Registry profile and root of trust

The estate registry is canonical JCS with exactly these top-level members:

```json
{"canonical_source":{"path":"<safe relative path>","ref":"refs/remotes/origin/main","repository":"https://github.com/kody-w/dogg"},"entries":[],"profile":"dogg-rapp1-bridge-registry/1","registry_seq":0,"schema":"rapp/1-registry","sig":"<detached owner JWS>"}
```

This explicitly closes the RAPP/1 §13 profile gaps: the entries member is
exactly `entries`, and `canonical_source` is exactly the three-member object
above. The configured source ref is exactly `refs/remotes/origin/main`, and
`remote.origin.url` must be the exact repository URL above. A CLI ref is only
accepted when byte-equal to that configured ref; a local main or feature ref is
not an alternative. A consumer obtains the registry bytes from `path` at an
immutable protected-main Git checkpoint, verifies that both the checkpoint and
selected native commit are on that canonical history, and supplies the
estate-owner RAPPID independently through `--trust-anchor` or
`DOGG_RAPP1_BRIDGE_TRUST_ANCHOR`.

The initial registry contains exact §13.3 entries for:

1. `estate_owner`;
2. that owner's public SPKI;
3. canonical `rapp/1` at normative SPEC SHA-256
   `348e7d5baa94aaf2ce4c5354f3cb261f389298a04af65e271a686d3b62f7c384`;
4. this subordinate `dogg-rapp1-bridge/2` document by its exact raw SHA-256;
5. `memory.save` → `memory`; and
6. the bridge stream's creation genesis.

The whole registry is owner-signed. `registry_seq` starts at zero and must be
contiguous: a lower sequence is rollback, the same sequence with different
bytes is a fork, and a jump is a gap. A successor snapshot must preserve the
old entries as an exact prefix. Bridge/2 intentionally does not implement
re-genesis; a changed registered or native genesis refuses.

The canonical RAPP reference is copied byte-for-byte under
`tools/rapp1_bridge_v2_vendor/` from
[`kody-w/rapp-1@dda32d741c7218f41443a5bd17eebfe0eae82cb7`](https://github.com/kody-w/rapp-1/tree/dda32d741c7218f41443a5bd17eebfe0eae82cb7).
`PROVENANCE.json` pins exact paths, sizes, and raw SHA-256 values. Bridge/2
imports that canonicalizer and registry checker; it does not retype JCS.

## Owner initialization

Requirements are Git, Python 3.12+, and OpenSSL with P-256. No network call is
made. The private PEM, controller state, registry candidate, and outputs must
be outside the repository. The key's immediate directory must be owner-held
mode `0700`. Key generation captures OpenSSL's bytes without giving OpenSSL an
output path, then creates the PEM once with `O_EXCL|O_NOFOLLOW` mode `0600`,
fsyncs it and its directory, and reads it back. Every later use requires a
single-link regular file owned by the current uid at exact mode `0600` and uses
the validated open descriptor. Key generation occurs **only** through the
explicit local command below; `init`, CI, and scheduled append never generate
a key.

```sh
SOURCE_REVISION=$(GIT_NO_REPLACE_OBJECTS=1 git --no-replace-objects rev-parse HEAD)

python3 tools/rapp1_bridge_v2.py generate-key \
  --source-root . --out "$HOME/.dogg-private/dogg-rapp1-bridge.pem"

python3 tools/rapp1_bridge_v2.py init \
  --source-root . --source-revision "$SOURCE_REVISION" \
  --main-ref refs/remotes/origin/main --chain world \
  --owner kody-w --slug dogg-rapp1-bridge \
  --canonical-registry-path rapp1-bridge-v2/registry.json \
  --state "$HOME/.dogg-private/bridge-v2-state" \
  --registry-out "$HOME/.dogg-private/registry-0.json" \
  --signing-key "$HOME/.dogg-private/dogg-rapp1-bridge.pem"
```

Initialization mints one candidate genesis once and writes it create-only. It
does not claim authority yet. The owner must separately:

1. publish the **exact** registry candidate bytes at its declared path on
   protected `main`;
2. retain that immutable Git commit as the registry/main checkpoint; and
3. distribute the printed public `trust_anchor` RAPPID out of band.

Do not publish the controller state or private PEM. Public SPKI bytes in the
registry are key-discovery data, not private key material. A next registry
candidate can be made create-only with `advance-registry`; publishing it is
again a separate owner action.

## Scheduled-workflow-ready append

No workflow is enabled by this PR: enabling one before the owner configures an
external persistent controller/output and secret PEM path would make protected
main noisily red. The ready command is:

```sh
test -n "${DOGG_RAPP1_BRIDGE_SIGNING_KEY:-}"
test -n "${DOGG_RAPP1_BRIDGE_TRUST_ANCHOR:-}"
test -n "${DOGG_RAPP1_BRIDGE_REGISTRY_CHECKPOINT:-}"

python3 tools/rapp1_bridge_v2.py append \
  --source-root . \
  --source-revision "$(GIT_NO_REPLACE_OBJECTS=1 git --no-replace-objects rev-parse HEAD)" \
  --main-ref refs/remotes/origin/main \
  --registry-checkpoint "$DOGG_RAPP1_BRIDGE_REGISTRY_CHECKPOINT" \
  --state "$DOGG_RAPP1_BRIDGE_STATE" \
  --out "$DOGG_RAPP1_BRIDGE_OUTPUT"
```

Absent signing configuration is a hard refusal. One exclusive controller lock
starts with recovery, then covers append validation, candidate creation, every
delivery, and controller head commit. A retained controller chain must reach
the accepted RAPP sequence. Every accepted frame—not only its head—and every
referenced tick are re-verified against their exact historical commit, chain
storage path/line, Git blob bytes, native oracle result, and canonical-main
ancestry before another frame can be minted. Each head is re-read both before
and after its pending file is made, so a waiting stale process cannot overwrite
a newer high-water mark or replace a same-sequence frame hash.

State and all outputs must be pairwise disjoint filesystem identities. Existing
ancestor identities, symlink/mount-like aliases, and filesystem-supported case
or Unicode aliases of nonexistent descendants are considered overlap; equality
and ancestor/descendant overlap refuse before the lock or any output write. The
source root must be the exact filesystem identity returned by a hardened
`git --no-replace-objects rev-parse --show-toplevel`; repository subdirectories
are never accepted as roots. That canonical top-level is used for every
repository-containment decision. The
append command confirms the PEM-derived public key equals the out-of-band
anchor, verifies the signed registry at the main checkpoint, verifies native
Git bytes and the entire source chain, then writes one candidate frame once.
Every bridge Git process also sets `GIT_NO_REPLACE_OBJECTS=1` and uses
`--no-replace-objects`. Replacement refs, grafts, shallow repositories, and
Git ancestry-override environment are refused before provenance is accepted.
Interrupted/retried delivery reuses those exact candidate bytes.

Every `frames/N.json`, content-addressed native blob, and retained registry is
create-only. It is first written and fsynced through a unique temporary inode,
then linked into place without replacement and followed by a parent-directory
fsync. Exact existing bytes are idempotent; differing bytes refuse. Recognized
unpublished temporaries may be removed at locked startup only when no accepted
or pending head references their destination. Local `HEAD.json` files hold the
highest verified RAPP `(seq, frame_hash)`, native
`(seq, frame_hash, genesis)`, source commit, and registry checkpoint. They are
unsigned delivery/controller state and are never folded into a frame.
All head sequence fields use the RAPP/1 uint53 bound
(`0..9007199254740991`), but recovery additionally bounds them against the
controller's retained contiguous frame and registry object counts before
resolving any references. An output head ahead of those controller objects is
refused without expanding a numeric sequence range.
Files and containing directories are fsynced in dependency order: registry and
opaque blobs precede frames, and all three precede the atomically replaced
delivery/controller head. A durable `.HEAD.json.pending` is validated against
the current accepted head and every durable dependency under the controller
lock. A complete next head is committed; a candidate with no published
dependency is removed before rebuilding; partial or conflicting evidence
refuses without being discarded. A lagging output may recover across multiple
already-accepted controller registry sequences only after every intermediate
registry object verifies as a contiguous append-only prefix and is byte-equal
to controller state.

An interrupted first output-directory setup may create missing `frames/`,
`blobs/`, or `registries/` directories on retry only while neither `HEAD.json`
nor `.HEAD.json.pending` exists. Unexpected root/object entries, files in place
of directories, and symlinks refuse. Once an output has an accepted or pending
head, missing layout is evidence loss and is never recreated. Verification
compares every accepted output frame, blob, registry, and head byte-for-byte
with controller state, and independently requires output frame zero's hash to
equal the signed registry genesis.

The gate refuses registry rollback/fork/gap; RAPP rollback/fork/gap; native
rollback/fork/gap or changed genesis; non-fast-forward Git; commit/path/raw
byte mismatch; bad tick references; null or invalid signatures, any bridge kind
other than exact `memory.save`, genesis
bindings, or anchors; unexpected files; and create-only collisions.

## Integrity is not authenticity

Native DOGG hashes and Git object IDs establish byte integrity and history
linkage, not writer identity. Bridge signatures authenticate the projection
key, not the truth of native observations or original DOGG authorship.
Authenticity requires **both** the signed registry/main checkpoint and the
estate-owner RAPPID obtained out of band. A self-signed replacement registry,
a valid chain from an untrusted head, or a mutable-main URL without the
checkpoint is insufficient. Registry freshness remains an operator policy;
verification against an old accepted checkpoint must not be described as
current or clean.
