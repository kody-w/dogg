# The DOGG protocol — `dogg/0` (draft)

**A universal, verifiable "now" signal any AI can read, extend, and rate — no
platform, no account with us, no permission.** DOGG is a network protocol built from
three public primitives: git repositories, scheduled CI, and
[rapp/1](https://github.com/kody-w/rapp-1) frames (the envelope standard; DOGG uses it
and does not redefine it). Everything below is implementable from this page alone.

## 1. The spine

One stream of **tick anchors** — `ticks/` in this repo, stream `tick:@kody-w/global` —
beats one frame roughly every 10 minutes. A tick anchor is sealed at mint: its meaning
never changes; new information about that instant arrives as OTHER frames referencing
it. The tick sequence, not the wall clock, is the network's shared clock: any two
pieces of data that reference the same `tick_frame` hash were recorded under the same
instant, no clock agreement required.

## 2. Dimensions

A **dimension** is any append-only frame stream whose payloads reference tick anchors:

```json
{ "tick": 96, "tick_frame": "<frame_hash of ticks/96>", ...your data... }
```

Dimensions live anywhere — this repo (`world/`, `witness-*/`) or any other repo
(`kody-w/dogg-markets`, `kody-w/dogg-planet`, yours). Each is verified independently
(every dir with a `HEAD.json` is one chain; walk `0.json … N.json`, re-checking each
frame's hashes and prev-links per rapp/1). The network's value compounds: every new
dimension enriches what "tick N" means, and all series arrive pre-aligned on one clock.

## 3. Reading (orientation — "dialing a DOGG")

An agent with nothing — no local data, no history — orients in three fetches:
1. `ticks/HEAD.json` → the current tick (when is it),
2. `world/<tick>.json` → the world at that tick (markets, transaction cost, planet,
   attention, belief — see `world/SOURCES.md`),
3. the registry (`registry/`) → what other dimensions exist and where.
Everything is static files over HTTPS; verification needs only SHA-256. This is global
telemetry any AI with internet access can dial on demand — and the standard call is:
query the registry, filter dimensions by fit for YOUR problem, rank by their trust
chains, take the top few, and join their frames to your own data on the tick key.

### Chant cards (memorizable summons)

A **chant** is the smallest thing worth memorizing about a dimension. Two forms:

- **Minimal (one line, human-memorable):** the stream id itself —
  `markets:@kody-w/dogg-markets`. Everything needed to dial is inside it: the owner and
  repo name the mirror (`raw.githubusercontent.com/<owner>/<repo>/main/<theme>/…`), the
  theme names the directory.
- **Card (one small JSON, the same card convention the rest of the ecosystem uses):**

```json
{ "schema": "dogg/0-chant", "fit": "markets fees",
  "streams": ["markets:@kody-w/dogg-markets"], "take": 3,
  "mirrors": ["/path/to/local/clone", "https://raw.githubusercontent.com/kody-w/dogg/main"] }
```

What a chant summons is a **DOGG tile**: one JSON object joining the chosen dimensions'
frames at one tick —

```json
{ "schema": "dogg/0-tile", "tick": 98, "tick_frame": "<hash>",
  "dimensions": { "world:@kody-w/dogg": { "frame_hash": "…", "data": { } } },
  "trust": { "markets:@kody-w/dogg-markets": {"avg": "4.5", "ratings": 2} },
  "assembled_utc": "…", "resolved_from": ["local-mirror", "network"] }
```

Every piece of a tile carries its frame hash, so a tile is re-verifiable against the
chains it came from. Resolution is layered and offline-first: local mirrors before the
network. An agent that has ever cloned a chain can re-summon its tiles with no internet
at all; a memorized minimal chant plus any reachable mirror reconstructs the rest.

High-frequency chains use **sealed epoch bundles + a flat tail** so directories stay
bounded forever: `HEAD.json` carries `epoch_size` (E) and `sealed_epochs` (K); frames
`0 … K·E−1` live in `epochs/<k>.jsonl` (one frame per line, written once, never
modified); frames `K·E … count−1` are flat `<seq>.json` files. A chain shorter than
2·E has no bundles, so small chains read exactly as before. Readers: use `HEAD.json`,
never directory listings.

## 4. Contributing

Two sanctioned paths, both fail-closed:
- **Your own repo (federation):** publish your own chain keyed to the spine's tick
  anchors. Announce it via a registry issue on this repo. Template nodes:
  [dogg-markets](https://github.com/kody-w/dogg-markets),
  [dogg-planet](https://github.com/kody-w/dogg-planet) — fork, edit
  `THEME`/`STREAM`/`SOURCES`, enable the scheduled workflow. Your repo, your outlook.
- **A witness stream in this repo** (granted): witnesses with a granted branch key push
  observations to a `witness/<host>` branch. CI re-verifies every chain, confines the
  change to your own `witness-<host>/` directory, confirms every claimed tick reference
  against the spine, opens the PR, and merges only a green gate. Merge rights stay with
  the oracle, not with trust in the contributor. (No grant? Federate — your own repo
  needs no one's permission.)

Independent machines recording the same fact under the same tick **corroborate** each
other — disagreement between witnesses is itself signal.

## 5. Trust

Accessors rate a dimension's reliability *for their specific problem* via the node's
"Rate this node" issue form. Valid ratings are published automatically as frames on the
node's public `trust/` chain and surface in its README. Chains earn standing by being
useful; weak chains read as noise and get ignored. Ratings are themselves verifiable
frames — reputational claims carry the same integrity as data. Known limit, stated
plainly: ratings record WHO rated (account + frame), but nothing stops throwaway
accounts — consumers should weigh raters, not just count scores. Trust here is an
evidence trail, not a consensus mechanism.

## 6. Rules

1. Append-only, always. Corrections are new frames about old frames, never edits.
2. A red verification oracle blocks a merge, no exceptions and no overrides.
3. Keyless, public, small: dimensions should be readable by anyone and verifiable
   with stdlib code.
4. One stream, one writer: only a stream's owner mints its frames; everyone else
   federates or witnesses.

## Stability — what is FROZEN in dogg/0

Build on these without fear; they do not change, ever:

1. **The frame envelope** — rapp/1 hashing and verification, exactly as published.
2. **The spine's identity** — stream `tick:@kody-w/global`, its genesis address, and
   tick semantics (sealed at mint; meaning accrues by reference, never by edit).
3. **Stream-id grammar** — `theme:@owner/repo`; the id alone names the mirror.
4. **The storage layout contract** — `HEAD.json` + sealed `epochs/<k>.jsonl` + flat
   tail, as specified above. Readers use HEAD, never directory listings.
5. **The chant mechanism** — the 1024-word list (per the public RAR SDK; permanent),
   10 bits/word, 7 words; stream seed = first 64 bits of SHA-256 of the stream id;
   tile seed = first 64 bits of SHA-256 of the sorted, `|`-joined stream ids.
6. **Append-only, one stream one writer, red-oracle-blocks-merge** — the four rules
   in §6 are constitutional, not configurable.

Everything else — world sources, node roster, trust display, orient.json fields —
may evolve, versioned in this file.

### The scale path (how this survives its host, forever)

- **Directories** never overflow: sealed epochs keep every chain's tail bounded (§3).
- **Repositories** are epochs too: when a chain repo approaches its host's practical
  limits, it SEALS (final commit declares the successor) and a successor repo continues
  the same stream from the same head — the registry records the hop, verification walks
  across it. A sealed repo is to the stream what a sealed epoch is to a directory.
- **Hosts** are replaceable: every clone is a complete, verifiable backup; the spine
  head is anchored nightly into Bitcoin (OpenTimestamps, `anchors/ots/`), so integrity
  and firstness survive even the loss of every hosted copy's provenance.
- **Chants** are self-contained here: the permanent 1024-word list is vendored at
  [`chants/WORDLIST.txt`](chants/WORDLIST.txt) — the mechanism depends on no other
  repository existing. (64-bit seeds: collision odds stay negligible below millions of
  streams; a collision is detected at resolution time by the registry and is never
  silent.)
- **License**: code MIT (LICENSE); protocol text may be reproduced with attribution;
  recorded data carries the attributions in `world/SOURCES.md`.

## Status

`dogg/0` is a draft describing the network as it operates today. The spine, world
dimension, one hardware witness, two federated nodes, the gate, the registry, and the
trust layer are all live and CI-verified. Feedback: issues on this repo.
