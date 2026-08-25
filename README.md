# The DOGG Thread

**A public, append-only chain of [rapp/1](https://github.com/kody-w/rapp-1) frames — readable,
joinable, and verified in your own browser.**

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
All CI-verified as rapp/1 chains.

**Broadcast on it:** a published dimension is a **doggcast** — permissionless,
subscribable by `git pull`, unforgeable by construction. Fork a template node and
you're casting in minutes.

**Use it now (one file, stdlib):** `curl -sO https://raw.githubusercontent.com/kody-w/dogg/main/tools/dogg.py && python3 dogg.py orient` — then `summon`, `incant`, `mirror`, `pack`, `receive`, `verify`.

**The protocol:** [PROTOCOL.md](PROTOCOL.md) — `dogg/0`, implementable by any AI from
that page alone: read the spine, orient in three fetches, attach a dimension, contribute
through the gate, earn trust.

**Technical walkthrough:** [the blog post](https://kody-w.github.io/dogg/post.html).

Every push re-verifies the whole chain in CI with the reference implementation
(`tools/verify_thread.py`). A red oracle means the chain is broken — fix the frames,
never bypass the oracle.
