# Chants — scan, speak, or memorize

A chant summons a DOGG tile ([PROTOCOL.md §3](../PROTOCOL.md)). Three equivalent forms
per dimension: the stream id (memorize it), the seven-word incantation (speak it —
seed = first 64 bits of SHA-256 of the stream id, words from the permanent 1024-word
list in [kody-w/RAR](https://github.com/kody-w/RAR)'s public SDK), or the QR (scan it
— it contains the full chant card, so a phone camera is a summoning circle).

| Dimension | Incantation | Card | QR |
|---|---|---|---|
| `world:@kody-w/dogg` | **TAUNT ZOOM HUNTER JADE TORCH QUAKE FORGE** | [card](world.chant.json) | [qr](world.qr.png) |
| `witness:@kody-w/dogg-battlestation` | **RUSK BARB SCEPTER SERPENT VECTOR MUSK BIND** | [card](witness-battlestation.chant.json) | [qr](witness-battlestation.qr.png) |
| `markets:@kody-w/dogg-markets` | **ALTAR WYRM EVOKE DRENCH DANCE ROYAL MOLD** | [card](markets.chant.json) | [qr](markets.qr.png) |
| `planet:@kody-w/dogg-planet` | **ROYAL PYLON SANCTIFY GROOM LYRE MOLD CARVE** | [card](planet.chant.json) | [qr](planet.qr.png) |
| `attention:@rbox-rappters-2026/dogg-attention` | **DASH BAIT CROAK JAUNT CONDUIT SHAMAN ETCH** | [card](attention.chant.json) | [qr](attention.qr.png) |
