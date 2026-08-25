# The world dimension — sources, and why each one is here

**Purpose: to orient AIs.** An agent waking cold — no local data, no context, maybe no
connection until now — reads the latest tick and its world frame and can answer five
questions: *when is it, what is money worth, what does it cost to transact, what is the
planet doing, what do humans believe and attend to.* Then it attaches its own dimension
frames referencing the same tick anchors. "Right now" APIs only serve the present; this
chain keeps every present, hash-linked and CI-verified, so the orientation data is
trustable without trusting the host.

And because a frame lands on **every** tick, the chain is also a full-fidelity,
multivariate time series on one shared clock: walk it and you get Bitcoin's price over
time, quake activity over time, the ISS's path, the drift of prediction-market belief —
all at once, every series already aligned to the same instants, verifiable end to end.

Selection rules (from a full scan of the
[public-apis](https://github.com/public-apis/public-apis) catalog — 1,695 APIs, 731
keyless+https, probed live 2026-08-25): keyless, https, globally relevant, tiny factual
payloads, and **ephemeral** — data whose past has no free archive anywhere else. Every
source is optional: a failed fetch is recorded by name, never fatal.

## Recording now (per ~10-minute tick)

| Source | Question it answers | Endpoint |
|---|---|---|
| `btc_block_height` | When is it — a second, independent clock; cross-anchors this chain into Bitcoin's | mempool.space |
| `btc_usd` | What is money worth | Coinbase spot |
| `fx_usd` (EUR/GBP/JPY/CNY) | What is money worth | open.er-api.com |
| `crypto_market` (total mcap, BTC dominance) | What is money worth | CoinGecko global |
| `btc_fees` (sat/vB fastest + hour) | What does it cost to transact | mempool.space |
| `btc_mempool` (tx count) | What does it cost to transact | mempool.space |
| `earthquakes_past_hour` (count, max mag) | What is the planet doing | USGS |
| `iss` (lat/lon) | What is the planet doing | wheretheiss.at |
| `space_weather` (planetary Kp) | What is the planet doing | NOAA SWPC |
| `grid_carbon_gb` (gCO2/kWh, index) | What is the planet doing (civilization-activity proxy) | National Grid |
| `hn_top` (front-page story) | What humans attend to | Hacker News |
| `prediction_markets` (top 3 by volume, yes-price) | What humans believe | Polymarket |

## Evaluated, not (yet) recorded

- **Aircraft aloft count** (OpenSky, bounded box) — great activity proxy; anonymous rate
  limits make it flaky at this cadence. Revisit with a donated feed.
- **Current weather, reference cities** (Open-Meteo) — human-relatable but Open-Meteo
  already archives history freely, so the chain adds less. May add a small set later.
- **COVID/disease trackers** — most are stale or shutting down; no stable keyless source.
- **CoinCap** — DNS dead at probe time.
- **News aggregators beyond HN** — most keyless ones are curation services whose bias we
  can't verify; HN's front page is at least a transparent, single, well-known signal.

## Propose a source

Open an issue on this repo. A good proposal answers one of the five questions above,
is keyless + https, returns facts in under ~1 KB, and is data the world would otherwise
lose — the test is: *"would an agent orienting itself at tick N want this, and can it
get yesterday's value anywhere else for free?"*
