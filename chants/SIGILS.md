# Sigils — the drawable form of a SEED program

A SEED chant (dogg/0, kind 4) carries a *program*, not data: a dimension id followed
by ops, each a 3-bit code plus 4-bit field operands or a 14-bit log-quantized
threshold, read until the last full op fits (see PROTOCOL.md, "The spellbook"). A
**sigil** is that same program drawn: one rune per op, its operands written beside the
rune. Two forms, both built from the identical decode — `tools/sigil.py` never
re-encodes the bits, it only re-skins `dogg.py`'s own `seed_compile` / `seed_make`.

- **SVG** — a self-contained, themed graphic: one row per op, the rune large and gold,
  the operand(s) beside it, the op name small underneath as a caption. No external
  fonts required; runes render as plain Unicode text against the system fallback
  stack.
- **Text** — a single line, human-writable and human-readable:

  ```
  ◆btc_usd ÷btc_usd/eth_usd ▲btc_usd>70100
  ```

## The rune table

Append-only, exactly like the wordlist, the op table and every field table it draws
from (PROTOCOL.md: "the codebook is append-only"). A rune, once assigned to an op, is
never reassigned or removed — new ops (should the SEED grammar ever grow past its
eight) get a new rune appended here, never a reuse of an existing glyph.

| op | rune | operand syntax | example |
|---|---|---|---|
| `select` | ◆ | `◆field` | `◆btc_usd` |
| `delta` | Δ | `Δfield` | `Δeth_usd` |
| `ratio` | ÷ | `÷a/b` | `÷btc_usd/eth_usd` |
| `above` | ▲ | `▲field>threshold` | `▲btc_usd>70100` |
| `below` | ▼ | `▼field<threshold` | `▼btc_fee_sat_vb<5` |
| `sum` | Σ | `Σa+b` | `Σbtc_usd+eth_usd` |
| `change_pct` | % | `%field` | `%crypto_mcap_usd` |
| `max_of` | ⋁ | `⋁a,b` | `⋁btc_usd,eth_usd` |

A text sigil is several of these tokens separated by a single space, one token per op,
in program order — the same order the SEED chant's ops appear in.

Field names are the dimension's own field-table names (`chants/MISSIONS.json`,
`_fields_for(dimension)` in `dogg.py`) — the same names `dogg.py seed` takes on the
command line. Thresholds are printed as the log-quantized value's canonical decode
(`dogg._sig(dogg._logd(code))`, formatted bare when it lands on a whole number) — the
same ~0.3%-precision number `dogg.py wear`/`recite` would show you.

## The round-trip guarantee

`text -> words -> text` is exact: parsing a text sigil back into a SEED program and
re-minting it with `dogg.seed_make` reproduces the identical chant words whenever the
text sigil was itself produced by `sigil.py`'s own decoder (`words_to_text` /
`program_to_text`) — the canonical-number formatting on both sides of the trip is the
same function, so it is a fixed point. A hand-written text sigil round-trips exactly
whenever its threshold numbers already are that canonical decode (the common case: any
number that came from reading a chant back). `chants/VECTORS.json`-style golden vectors
are not needed here — the guarantee is proven directly against three programs in
`tests/test_sigil.py`, which is the conformance gate for this lane.

What a sigil does **not** do: mint new SEED semantics. It never touches
`chants/CODEBOOK.lock`, the wordlist, or the op table — it is purely a second,
human-drawable skin over bits `dogg.py` already owns.

## CLI

```
python3 tools/sigil.py render W1 … Wn > out.svg     self-contained SVG of a SEED chant
python3 tools/sigil.py text   W1 … Wn                the one-line text sigil
python3 tools/sigil.py parse  "<text sigil>" <stream-id>
                                                      text sigil -> SEED chant words
```

`render` and `text` also accept a `dogg:` chant URI in place of words (same
`as_words()` convention every `dogg.py` verb uses). `parse` needs the target
dimension's stream id explicitly — a text sigil carries field *names*, and names
resolve to 4-bit indices only against one dimension's field table.
