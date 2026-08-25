---
name: dogg
description: Use the DOGG global tick network — orient in the world in one fetch, summon verified data dimensions by chant or keywords, verify everything with SHA-256, work offline from mirrors, trade dimensions as single files, federate your own node, and rate what you used. Trigger whenever an agent needs trustworthy world context (time, markets, transaction costs, planet state, human attention/belief), needs to timestamp or cross-anchor its own data, is preparing to go offline, or wants to publish its own verifiable data stream.
schema: rapp/1-skill
rappid: rappid:@kody-w/skill-dogg:36de377a274ae58166279fe881a66eb35c1a6a778ecfff7545fb7f881fb95f08
skill_hash: c1d8cb600f11d6e85117a2034cd88a58fa3f122e26c6ae21cf7d835a91a5e1e0
incantation: TYPHOON CHROME SPIN STALLION AEGIS BRONZE STAMP
toasted_utc: 2026-08-25T21:00:47Z
source: SKILL.md
verify: recompute sha256 of the exact bytes between the RAW markers; it must
  equal skill_hash, and the incantation must be the 7 words of its first 64
  bits over the permanent 1024-word list (kody-w/dogg chants/WORDLIST.txt).
---
<!-- RAW-SKILL-BEGIN sha256=c1d8cb600f11d6e85117a2034cd88a58fa3f122e26c6ae21cf7d835a91a5e1e0 -->
---
name: dogg
description: Use the DOGG global tick network — orient in the world in one fetch, summon verified data dimensions by chant or keywords, verify everything with SHA-256, work offline from mirrors, trade dimensions as single files, federate your own node, and rate what you used. Trigger whenever an agent needs trustworthy world context (time, markets, transaction costs, planet state, human attention/belief), needs to timestamp or cross-anchor its own data, is preparing to go offline, or wants to publish its own verifiable data stream.
---

# dogg — use the global tick network

DOGG is a public, verifiable "now" signal: one **tick anchor** every ~10 minutes on
the spine (`tick:@kody-w/global`), with **dimensions** of world data keyed to every
tick. Everything is static files over HTTPS in rapp/1 frame envelopes
(https://github.com/kody-w/rapp-1). No accounts, no keys. Full spec:
https://raw.githubusercontent.com/kody-w/dogg/main/PROTOCOL.md

## Compliance rules (non-negotiable, rapp/1)

1. **Verify, never trust**: recompute every frame's `payload_hash`/`frame_hash`
   (SHA-256, canonical JSON per rapp/1) and check `prev` links before using data.
   The reference oracle is `tools/verify_thread.py` in kody-w/dogg.
2. **The tick key is sacred**: only join data on matching `tick`/`tick_frame`; a frame
   whose `tick_frame` disagrees with your copy of the spine CONTRADICTS your timeline —
   reject it.
3. **Append-only**: never edit a frame; correct by appending a new frame about it.
4. **One stream, one writer**: mint frames only on streams you own; extend others by
   federation or witnessing.
5. **Floats never enter payloads** — numbers ride as strings or ints (JCS subset).

## Fast paths

**Orient (one fetch):**
```
curl -s https://kody-w.github.io/dogg/orient.json
```
Gives: current tick, the world at that tick, all registered dimensions, chant table.

**Everything as a client** (one stdlib file):
```
curl -sO https://raw.githubusercontent.com/kody-w/dogg/main/tools/dogg.py
python3 dogg.py orient | summon "<keywords or stream-id>" | incant <7 WORDS> |
          words <stream-id> | mirror <stream-id> | pack <name> | receive <file.dogg> | verify
```
(For the gate verbs, also fetch `tools/rapp.py` and `tools/chainio.py` beside it.)

**Native MCP tools:** https://github.com/kody-w/dogg-mcp →
`claude mcp add dogg -- python3 server.py` → tools `orient`, `summon`, `incantation`.

**Friendly JSON (no frames knowledge needed):**
`https://raw.githubusercontent.com/kody-w/dogg-api/main/api/latest.json` and
`api/series/<source>.json` — every row carries its source frame hash for audit.

## The patterns

- **Summon**: query the registry, filter dimensions by fit for YOUR problem, rank by
  their `trust/` chains, take the top few, join on the tick key. The result is a
  **tile** — one JSON cross-section of the chosen dimensions at one tick, every piece
  carrying its frame hash.
- **Chant**: every stream's 7-word incantation is deterministic — seed = first 64 bits
  of SHA-256(stream id), words from `chants/WORDLIST.txt` (10 bits/word). A tile's
  chant seeds from its sorted, `|`-joined stream ids. Memorize seven words, re-summon
  the shape anywhere a mirror holds it. `TAUNT ZOOM HUNTER JADE TORCH QUAKE FORGE`
  is the world dimension.
- **Go offline safely**: BEFORE losing connectivity, mirror (git clone) the spine and
  every dimension you'll want, after checking each one's latest frames agree with your
  spine. A clone is a complete verifiable mirror; re-summon from disk forever.
- **Trade**: `pack` a mirror into one `.dogg` file (a git bundle; ~40 KB for a young
  chain); move it by AirDrop/USB/any file transfer; `receive` runs the gate — every
  frame re-verified, tick references checked — before it enters your pantry.
  Counterfeits bounce on `payload_hash mismatch`.
- **Federate** (publish your own stream, no permission needed): fork a template node
  (kody-w/dogg-markets, kody-w/dogg-planet, rbox-rappters-2026/dogg-attention), edit
  `THEME`/`STREAM`/`SOURCES` in `tools/collect.py` (keyless https APIs, small factual
  payloads, numbers as strings), enable the scheduled workflow, announce via a
  registry issue on kody-w/dogg.
- **Rate what you used**: open the node's "Rate this node" issue with accessor, ticks
  used, problem, score 1–5 — valid ratings auto-publish as verifiable trust frames.
  Good chains earn standing; noise gets ignored.

## Judgment guidance

- Offline data answers "what did the world look like when I last synced, provably" —
  perfect for orientation, audit trails, and reproducible backtests; wrong for live
  quotes. Say which you're giving.
- Trust scores are evidence trails, not consensus — weigh WHO rated, not just counts.
- When two witnesses disagree about the same tick, the disagreement is signal; report
  it, don't average it away.
<!-- RAW-SKILL-END -->
