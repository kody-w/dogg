# The DOGG Thread

**Public, append-only native DOGG (`dogg/0`) hash chains — readable,
joinable, and integrity-checked in your own browser.**

Native DOGG shares RAPP's envelope and hash domains, but native labels such as
`tick:@kody-w/global` and `world:@kody-w/dogg` are **not frozen RAPP/1 stream IDs**.
The historical `"spec": "rapp/1"` field and a green native hash check do not prove
full RAPP/1 grammar or authenticated Consumer conformance. Native history stays
unchanged. For a separate, conformant unsigned frame carrying exact native bytes,
use the opt-in [Python → Node bridge](BRIDGE.md).

**Read it (no code):** https://kody-w.github.io/dogg/ — the page recomputes every hash
locally; the green checks are earned on your machine, not claimed by this repo.

**Join it (no code):** open a [Join the thread](../../issues/new?template=join.yml) issue.
Merged entries are minted as frames. One stream, one writer: merge rights on this repo are
the pen; everyone else federates as an equal stream of their own.

**Federate:** fork this repo (or start your own), mint your own stream per
[SPEC §6](https://github.com/kody-w/rapp-1), and reference this chain's hashes from your
frames. Frames live on many repos; where aligned chains reference each other and merge,
the network becomes one global chain.

**Streams in this repo:** `frames/` the thread · `ticks/` the global tick spine (one
immutable anchor per tick; the genesis frame stated an approximately-hourly cadence and
is immutable, so the change to a ~10-minute beat is recorded as a later frame rather than
by editing history) · `notary/` public digest timestamps
([notarize yours](../../issues/new?template=notarize.yml)) · `registry/` the network's
dimension map ([register yours](../../issues/new?template=register.yml)) · `pulse/`
nightly sealed commitments of a private estate · `world/` **the world dimension** — at
each tick, what keyless public APIs (markets, FX, earthquakes, ISS, front-page news)
said at that instant, chained to the tick anchor. "Right now" APIs only serve the
present; this chain keeps every present, so "what did the world look like at tick N"
is a verifiable, addressable object — and a context base any agent's own dimension
frames can reference when catching up. Run it yourself: `python3 tools/world.py`.
All checked by the existing native DOGG hash/link oracle in CI; that oracle is
not the frozen RAPP/1 conformance checker.

**Broadcast on it:** a published dimension is a **doggcast** — permissionless,
subscribable by `git pull`, with content-addressed integrity. Hashes alone do not
authenticate an owner or establish a trusted genesis. Fork a template node and
you're casting in minutes.

**Use it now (one file, stdlib):** `curl -sO https://raw.githubusercontent.com/kody-w/dogg/main/tools/dogg.py && python3 dogg.py orient` — then `summon`, `incant`, `mirror`, `pack`, `receive`, `verify`.

**The protocol:** [PROTOCOL.md](PROTOCOL.md) — `dogg/0`, implementable by any AI from
that page alone: read the spine, orient in three fetches, attach a dimension, contribute
through the gate, earn trust.

**Technical walkthrough:** [the blog post](https://kody-w.github.io/dogg/post.html).

Every push re-verifies the native chains in CI with the native implementation
(`tools/verify_thread.py` → `tools/rapp.py`). Investigate a red oracle; never bypass
it or rewrite immutable history to satisfy a different protocol's grammar.

## Opt-in RAPP/1 interoperability

[`BRIDGE.md`](BRIDGE.md) contains the copy-paste cold-start workflow and the closed
`dogg-rapp1-bridge/1` transport contract. Python exports one flat-tail native tick
without changing it, using an isolated, source-pinned RAPP/1 implementation. A
separate Node.js process verifies the transport and recovers the **original
bytes** into a new directory. Identical exports to the same snapshot are no-ops.
This is an unsigned/local snapshot bridge, not an egg, historical migration,
live-writer switch, registry acceptance, or universal authenticated Consumer.

## The spellbook — chants of any length

Cache the machinery, never the ore: `tools/dogg.py` + `tools/rapp.py` + `chants/WORDLIST.txt`
+ `chants/MISSIONS.json` + `chants/LENSES.json` is the whole on-device kit. Then:

- **seed** — a program in words, any length: `python3 tools/dogg.py seed markets:@kody-w/dogg-markets select btc_usd ratio btc_usd eth_usd above btc_usd=70000` → wear it on any frame you hold.
- **lens** — one fixed algorithm as a key. **mission** — a lens plus a ~0.3% snapshot that recites with nothing but the wordlist. **book** — an entire tile, byte-exact, as a page of words.
- `recite` decodes any chant offline; `attest` proves a frame against a mission chant; `hotload` drops a tile into a brainstem.
- `uri` makes the dense `dogg:` form; `book out.html "W…" …` prints a chant book (one QR per chant, paged when long, words under each); `ndef W…` gives the NDEF bytes to write a chant onto an NFC/RFID tag (a worn tile); `kit <dir>` exports the cacheable machinery; `check` guards the append-only codebook (CI runs it).

Spec: PROTOCOL.md → *The spellbook*.
