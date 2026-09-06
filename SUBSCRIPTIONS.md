# Read public DOGGs, with or without an AI

DOGGs are **public change journals for people and AIs**. The
[front door](https://kody-w.github.io/dogg/) offers a curated starting point:
read an observation, see its date/source, follow a feed, or take a read-only profile
to your AI. No login, API key, private estate state, or executable payload is needed.

The website code and its publication are separate: a branch or pull request is not
a deployed website. The deployment checklist below is part of shipping this feature.

## For people

1. Open **Read & follow**. World snapshot and Project journal are the fresh-browser
   defaults; use search or **Only show following** to narrow the list.
2. **Follow** stores the public feed ID in this browser only. **Check once** reads
   without following. Neither action posts a subscription, endorses a publisher,
   adopts a registry entry, grants authority, or executes source content.
3. Look at the record date, check date and source link. **Fresh** means within the
   curator's stated **age limit**, not necessarily within the expected update
   interval or proven true. Both intervals appear on each scheduled feed.
   For example, World snapshot expects updates every ten minutes but allows a
   sixty-minute age limit; that grace does not prove the schedule ran.
   **Stale** means the age limit was exceeded.
   **Partial** means some upstream readings failed. Event-driven journals promise
   no periodic update. **Not checked yet** is unmeasured, never a successful check.
4. If a refresh fails, the card keeps its last-good observation under **Refresh
   failed**, with the failed attempt time. It does not replace that observation
   with an empty success or quietly hide the source.
5. **Use with my AI** copies/downloads a profile on your device. Clipboard denial
   selects the text for manual copying. The profile is not sent anywhere until you
   choose to share it.

If localStorage is denied or full, following works for the tab only and says so.
Malformed saved choices do not silently enable a new set of feeds. Private state,
credentials, and profiles are never uploaded by this reader. Public hosts can
still see ordinary read requests; fetches omit credentials and referrers.

Original thread payloads are available under **Read the original project journal**.
They remain unchanged historical quotes. Obsolete claims about “signed-by-math”,
full RAPP/1 conformance or “one global chain” are not current product claims.

## One maintained starter roster

[`subscriptions.json`](subscriptions.json) is the **only authoritative curated
starter list**. [`subscriptions.schema.json`](subscriptions.schema.json) describes
its versioned application configuration; it is not a new DOGG/RAPP wire protocol.
`site/data.mjs::validateRoster` enforces the additional cross-field/URL constraints.

The initial bounded roster has seven actual public sources across two publishers:
local network journals plus selected registered markets, planet and attention
feeds. Their public HEAD endpoints were checked during implementation. Availability
is observed again at read time, not guaranteed by being listed. All initial entries
are native `dogg/0` sources; none pretends to be a continuously published RAPP/1
bridge feed. The opt-in [bridge](BRIDGE.md) is a separate snapshot workflow.

Each entry includes a stable `id`, human `title`/`purpose`, publisher, repository,
path, source kind, expected stream label, exact public HTTPS HEAD/record/source
URLs, default choice, audiences, topics, refresh interval and freshness targets.
IDs do not encode trust scores. Increment roster `version` when curating it; retain
stable IDs for the same source. Saved profiles keep their explicit IDs rather than
silently inheriting changed defaults.

The registry and orientation view are **discovery inputs**, not automatic admission.
At the initial implementation base (`7fce94a`) the registry contained **21
records: one genesis and 20 dimension announcements**. A genesis is not a
dimension announcement. Current counts are derived from the current registry,
not frozen to that example. Duplicate announcements, if present, resolve to the newest one.
The website never crawls all registry URLs or silently follows unknown endpoints.

### Full known directory is larger than the starter set

**Browse the full known directory** accounts for every current registered
dimension and any additional core journals (such as ticks, thread and notary),
not just seven starter feeds or two default follows. Its size grows with the
source metadata rather than a hard-coded directory count.
`orient.json.dimensions` preserves the full deduplicated registration metadata;
the UI joins it with the canonical starter roster by stream label. This is a
derived directory view, not a second subscription authority.

Directory browsing reads metadata already loaded with orientation. It makes **no
per-source remote record requests**. Unknown availability, invalid repository/path
metadata, failures and retained old registry views stay explicit instead of
disappearing or becoming a successful check. Record/check times remain unmeasured
unless this tab actually checked a source.

Current starter feeds can be followed from either view, using the same browser-only
choices. Other registrations are metadata-only discovery links, not silently
admitted to the bounded following profile; inspect them or propose normal reviewed
curation. Following still transfers no trust. Search covers the entire known
directory; more than 50 matches are visibly paginated rather than silently omitted.

To add another publisher: propose a normal reviewed public contribution updating
this roster, with a public purpose, stable source ID, rights-safe contents, existing
HEAD/record examples and honest cadence. Run the tests, inspect its actual producer/
reader boundary, and verify the source can be read without credentials. This is
curation, not automatic trust transfer. Others can also fork a profile or their own
roster; that does not change this starter list.

## API and CLI

Public endpoints, once this feature is published:

* Canonical roster: `https://kody-w.github.io/dogg/subscriptions.json`
* Schema: `https://kody-w.github.io/dogg/subscriptions.schema.json`
* Current derived view: `https://raw.githubusercontent.com/kody-w/dogg/main/orient.json`
* Per-source endpoints: exactly the `head_url`, `records_url` and `source_url` in the roster.

The UI fetches the roster from its own Pages deployment, then reads public Raw
endpoints directly. It does not depend on hundreds of unauthenticated GitHub REST
requests, a token, a private runtime, or a catalog service being deployed.

From a public checkout, with Node 22+ and Python 3.12+:

```sh
# Configuration only, explicitly not a zero-frame verification success:
node tools/follow.mjs --list

# Full known directory metadata from this checkout; no remote record polling:
node tools/follow.mjs --directory

# A bounded live observation:
node tools/follow.mjs --feed dogg.world

# Use a profile downloaded from the page; it stays local:
node tools/follow.mjs --profile my-following.json

# Check the derived view against this checkout, without writing:
python3 tools/orient.py --check

# Independently verify all existing native chains:
python3 tools/verify_thread.py
```

The CLI prints `dogg-observations/1`, an **application status projection**, not a
second roster. It includes the canonical roster URL/version and observations keyed
by stable feed ID, `state`, `checked_utc`, `record_utc`, `seq`, `frame_hash`,
`stream_id`, source kind/URL and explicit `coverage`. Error entries stay in the
output with `state: "error"` and zero checked frames; the command exits nonzero if
any requested read fails. Stale/event-driven statuses are not erased by a successful
hash check. An empty profile is refused as “no sources observed.”

`--directory` instead prints a `dogg-directory-view/1` application view of the
checked-out orientation plus canonical starter roster. It reports registered/core/
starter counts and all entries, with availability initially unmeasured. Its
`generated_utc` describes the metadata snapshot, not individual feed freshness.

A profile is `{schema: "dogg-following/1", roster, roster_version, feed_ids, mode:
"read-only"}`. This is portable application configuration, not native stream data.
No profile causes source code to be executed.

### Small catalog ingestion interface

The public [organism catalog code](https://github.com/kody-w/rapp-organism) can:

1. Fetch the canonical roster and key starter UI/status records by `feeds[].id`.
   Consume, do not copy or maintain another authoritative starter list. This
   curated subset is **not the full known directory**.
2. Read `orient.json` for `tick`, `world`, `status`, `sources`, `dimensions`,
   `generated_utc` and `input_fingerprint`. `sources` contains measured local
   head counts/hashes, **not another subscription list**. Account for every
   `dimensions[]` entry, including unknown/unreachable entries, and join the
   additional core journals from the roster by stream label. `knownDirectory` in
   `site/data.mjs` and `--directory` demonstrate that complete metadata union.
3. Use `tools/follow.mjs` output or the same bounded reader contract for per-feed
   status/history. Preserve error entries and last-good observations. Always
   expose observation time and actual coverage; do not treat metadata publication
   time as source freshness or produce observer-self/timestamp-only commits.
4. For history, use the source HEAD's epoch/tail layout and a stated bound.
   The UI's optional history view reads at most six records, not an entire estate.

The [public catalog](https://kody-w.github.io/rapp-organism/) is available for
inventory and provenance questions, with a small
[machine index](https://kody-w.github.io/rapp-organism/index.json) and a separate
[poll receipt](https://kody-w.github.io/rapp-organism/freshness.json). Its static
SQLite, JSON and CSV downloads are query projections, not a hosted SQL API.
It links to DOGG's canonical starter roster; it does not replace that authority
or ingest personal following choices. The exact full raw organism carrier is
**withheld after disclosure/rights review**. Only safe metadata/query projection
is offered; there is no enabled full-carrier download or encrypted-private upload
workaround.

## Exactly what the limited checker proves

`site/data.mjs` and `tools/public_data.py` support native DOGG's unsigned,
non-swarm **safe-integer JSON profile**, not full frozen RAPP/1:

* Full JSON input is parsed with duplicate-member rejection. Decimal/exponent
  number tokens, `-0`, unsafe integers, non-finite values, bad UTF-8, unpaired
  surrogates, trailing input and excessive depth/size refuse.
* Native hashing follows existing `tools/rapp.py`: Unicode **code-point** key
  sorting and exact safe integer serialization. That differs from frozen RAPP/1
  UTF-16 JCS and is labeled native rather than silently “fixing” stored hashes.
* The reader binds the expected stream label, sequence, fixed UTC, key set,
  payload/frame hashes and the HEAD's latest frame hash. It checks the immediate
  predecessor's hashes and the link into the latest record, or one valid genesis.
* HEAD drives epoch/tail lookup; no directory-listing or flat-only assumption.
  Fetched epochs must be complete, parseable, declared-length and correctly ordered,
  with native envelope shape checks for every contained record.
  Only the requested records' hashes are verified; parsing a container does not
  imply every historical hash was checked.
* Each complete fetched **HTTP entity body** receives a raw-byte SHA-256 (after
  ordinary HTTP transfer decoding). That is not a Git object ID, signature, owner
  proof, registered genesis, or truth proof.
* A same-sequence changed head or rollback relative to the tab's last observation
  fails and preserves last-good state. Skipped intervening history is disclosed.
  There is no persistent authenticated anti-rollback ledger.

Limits: one HEAD plus at most two record containers per normal observation; at
most six records for an explicitly opened history view; HEAD ≤ 16 KiB, each JSON
record ≤ 256 KiB, epoch ≤ 4 MiB, total source transfer ≤ 8 MiB, epoch size ≤ 512,
JSON depth ≤ 32, at most 20,000 values and strings ≤ 64 KiB. Native sequences are
uint53; payload integers may also be signed, within the exact safe range. Frame
kind labels are limited to 129 characters. The derived reader caps each local
chain read at 8 MiB and registry history at 4,096 records.
Oversized/unsupported sources fail visibly instead of prefix-verifying a fragment.

Requests require a complete HTTP 200 response, reject redirects, use 8-second
per-request and 25-second per-source budgets, and read full bodies under those caps.
The UI runs two feed readers plus at most one orientation read; the CLI runs at
most three feed readers. The page checks followed feeds at their roster cadence
(minimum five minutes), only while visible. History loading and regular refresh
are serialized. No ever-growing scan is needed to paint a badge.

## Why orientation and the old page were stale

The old homepage displayed only the six historical `frames/` entries. It had no
subscription view and did not use current network orientation. Updating a tick
could not turn that page into a network reader.

Separately, `orient.json` at the implementation base described tick **810** from
August 31 while the checked-out spine was at **854**. `tools/orient.py` claimed it
ran each beat, but the supported fallback workflow invoked the tick/world producers,
verified native chains, and committed only `ticks`/`world`. It never invoked or
committed the derived projection. That wiring, not the native frame grammar, is fixed.

`tools/orient.py` now reads bounded native inputs without running any producer or
external API. It emits the latest tick/world, deduplicated registry dimensions,
chants, source heads, explicit world/registry state and an input fingerprint.
`--check` fails on a missing/stale projection and never writes. Unchanged semantic
inputs preserve **the exact existing file and `generated_utc`**.

`status.world.state: "current"` means **tick-aligned**, not wall-clock fresh.
Clients compare the source `utc` with their own clock. Older world data shows
`stale` and `ticks_behind`; per-API failures show `partial`/`sources_failed`.
`last_refresh: "failed"` remains explicit until a successful refresh or a new
world observation. Missing/invalid world or registry data retains a last-good
projection, if present and its semantic fingerprint still matches, with an error.
That fingerprint detects accidental cache corruption, not malicious unsigned
replacement or owner identity. It does not publish raw private diagnostics.
A broken/missing tick remains a hard failure, preserving the old derived file.

### Automatic derived refresh

* `fallback-beat.yml` still uses the unchanged native producer/identity. It
  regenerates orientation **even when no new tick is needed**. World fetch
  failure is explicitly recorded; it does not discard an otherwise valid tick.
  The native integrity oracle remains mandatory. Only real changes are committed.
* `orientation.yml` regenerates only derived data after supported `main` pushes
  touching ticks/world/registry/chants or its reader code. It invokes no live
  producer. Both workflows serialize through `dogg-public-updates` and check out
  current `main` when their queued job starts.
* A separate primary writer outside this repository must call
  `python3 tools/orient.py` after committing its valid native inputs, or allow the
  push/scheduled fallback path to repair the projection. Its private runtime is
  not modified by this feature.

Manual read-only projection repair in a public checkout:

```sh
python3 tools/orient.py
python3 tools/orient.py --check
```

This changes only `orient.json`; it never invokes `world.py` or `fallback_beat.py`.

## Deployment: code readiness is not live readiness

The observed production source is legacy GitHub Pages from **`main` / repository
root**. An open PR, a clean mergeability result, or local screenshots do not update
that site. Authorized publication/deployment remains a maintainer action.

1. Update the implementation branch from current public `main` without rewriting
   any native history. Regenerate `orient.json` from those exact merged inputs.
2. Run the checks below, then publish through the normal reviewed merge path.
   Do not bypass branch protections or dispatch live producers merely to test UI.
3. Confirm Pages is still using the intended branch/root. Wait for the actual
   Pages build/deployment and verify its commit, not just the PR checks.
4. Fetch the public homepage, `site/app.mjs`, `site/data.mjs`, stylesheet, roster
   and schema. Confirm the “Public change journals” and read/follow/AI paths appear
   at the real URL. Exercise a fresh isolated browser without a GitHub token.
5. Check Raw `ticks/HEAD.json` and Raw `orient.json` agree with the intended
   source snapshot. Future data reads go directly to Raw; they do not depend on
   a Pages rebuild for every tick. Confirm the next supported derived workflow
   includes orientation and does not commit just to change an observer timestamp.

**GitHub Pages caveat:** [GitHub documents that commits pushed using an Actions
`GITHUB_TOKEN` do not trigger a branch-based Pages build](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#troubleshooting-publishing-from-a-branch).
An authorized publisher must ensure the UI/roster deployment really occurred.
If fully automatic Pages rebuilding is desired, configure a normal approved Pages
deployment workflow/source rather than relying on token-pushed data commits to
trigger it. This feature does not change Pages settings, issue tokens, dispatch
deployments, or claim that deployment has happened.

## Validation

```sh
python3 tools/verify_thread.py
python3 tests/test_rapp1_bridge.py
python3 tests/test_orientation.py
python3 tools/orient.py --check
node --test tests/test_public_site.mjs
```

For real DOM checks with an **already installed** Chrome and Node's built-in
WebSocket (no package install, no sandbox disabling, no normal-profile reuse):

```sh
CHROME_BIN="/path/to/existing/chrome" \
DOGG_BROWSER_EVIDENCE=browser-evidence \
node tests/test_site_browser.mjs
```

The runner serves the actual page, supplies deterministic public-source HTTP
fixtures, uses a new isolated profile, exercises following/persistence/storage
denial, full directory accounting without remote polling, failures/staleness/no-ops,
profile copy/download, history, all audience
paths, keyboard access and light/dark desktop/mobile layouts. It records and stops
only its owned browser descendants. These are **local fixture browser checks**,
not a claim about the user's browser/session or the actual deployed public URL.
The page is not a self-contained offline application: offline source requests
fail visibly, and private selections remain local.
