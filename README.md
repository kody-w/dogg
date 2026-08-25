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
immutable anchor per tick, ~10-min beat) · `notary/` public digest timestamps
([notarize yours](../../issues/new?template=notarize.yml)) · `registry/` the network's
dimension map ([register yours](../../issues/new?template=register.yml)) · `pulse/`
nightly sealed commitments of a private estate. All CI-verified as rapp/1 chains.

**Technical walkthrough:** [the blog post](https://kody-w.github.io/dogg/post.html).

Every push re-verifies the whole chain in CI with the reference implementation
(`tools/verify_thread.py`). A red oracle means the chain is broken — fix the frames,
never bypass the oracle.
