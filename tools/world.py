#!/usr/bin/env python3
"""The WORLD dimension — one frame per tick. Its purpose: TO ORIENT AIs.

An agent waking cold — no local data, no context — reads the latest tick and its world
frame and knows: when it is, what money is worth, what it costs to transact, what the
planet is doing, what humans believe and attend to. Then it attaches its own dimension
frames referencing the same tick anchors. Public "right now" APIs only serve the
present; this chain keeps every present — hash-linked and CI-verified, so orientation
data is trustable without trusting the host. Source selection: world/SOURCES.md.

Design rules:
  * keyless, https public APIs only (github.com/public-apis/public-apis is the menu)
  * every source is OPTIONAL: a failed fetch is recorded by name, never fatal
  * tiny payloads — a snapshot is facts, not dumps
  * the chain is the value: same envelope, same verification as every DOGG stream
Run it yourself: python3 tools/world.py   (from a checkout; appends one frame)
"""
import json, sys, pathlib, datetime, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import rapp as R
import chainio

ROOT = pathlib.Path(__file__).resolve().parent.parent
TICKS, WORLD = ROOT / "ticks", ROOT / "world"
STREAM = "world:@kody-w/dogg"
TIMEOUT = 6

def utc():
    n = datetime.datetime.now(datetime.timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dogg-world-dimension"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())

def snapshot():
    """Each source: (name, fn) -> small dict of facts. Add sources by adding a line."""
    world, failed = {}, []
    def src(name, fn):
        try:
            world[name] = fn()
        except Exception:
            failed.append(name)
    # rapp/1 canonical hashing (JCS subset) forbids floats: numeric facts ride as strings.
    # Sources are chosen as ORIENTATION primitives: an agent holding nothing but this
    # chain should be able to answer — when is it, what is money worth, what is the
    # planet doing, what do humans believe and attend to, what does it cost to transact.

    # WHEN IS IT — a second, independent clock: Bitcoin's block height at this tick
    # cross-anchors this chain into another system's notion of time.
    src("btc_block_height", lambda: {"height": int(get(
        "https://mempool.space/api/blocks/tip/height"))})
    # WHAT IS MONEY WORTH
    src("btc_usd", lambda: {"spot": str(get(
        "https://api.coinbase.com/v2/prices/BTC-USD/spot")["data"]["amount"])})
    src("fx_usd", lambda: {k: f"{get_rates()[k]:.4f}" for k in ("EUR", "GBP", "JPY", "CNY")})
    src("crypto_market", lambda: (lambda d: {
        "total_mcap_usd": str(int(d["total_market_cap"]["usd"])),
        "btc_dominance_pct": f"{d['market_cap_percentage']['btc']:.1f}"})(
        get("https://api.coingecko.com/api/v3/global")["data"]))
    # WHAT IT COSTS TO TRANSACT — settlement-layer congestion right now
    src("btc_fees", lambda: (lambda d: {"fastest_sat_vb": int(d["fastestFee"]),
                                        "hour_sat_vb": int(d["hourFee"])})(
        get("https://mempool.space/api/v1/fees/recommended")))
    src("btc_mempool", lambda: {"tx_count": int(get(
        "https://mempool.space/api/mempool")["count"])})
    # WHAT IS THE PLANET DOING
    src("earthquakes_past_hour", lambda: quake_facts(get(
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson")))
    src("iss", lambda: (lambda d: {"lat": f"{float(d['latitude']):.3f}",
                                   "lon": f"{float(d['longitude']):.3f}"})(
        get("https://api.wheretheiss.at/v1/satellites/25544")))
    src("space_weather", lambda: kp_facts(get(
        "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json")))
    src("grid_carbon_gb", lambda: (lambda d: {"gco2_kwh": int(d["actual"] or d["forecast"]),
                                              "index": d["index"]})(
        get("https://api.carbonintensity.org.uk/intensity")["data"][0]["intensity"]))
    # WHAT HUMANS BELIEVE AND ATTEND TO
    src("hn_top", lambda: hn_facts())
    src("prediction_markets", lambda: poly_facts(get(
        "https://gamma-api.polymarket.com/markets"
        "?order=volume24hr&ascending=false&limit=3&active=true&closed=false")))
    return world, failed

_rates_cache = None
def get_rates():
    global _rates_cache
    if _rates_cache is None:
        _rates_cache = get("https://open.er-api.com/v6/latest/USD")["rates"]
    return _rates_cache

def quake_facts(geo):
    mags = [f["properties"]["mag"] for f in geo["features"]
            if f["properties"]["mag"] is not None]
    return {"count": len(geo["features"]),
            "max_mag": f"{max(mags):.1f}" if mags else None}

def hn_facts():
    top = get("https://hacker-news.firebaseio.com/v0/topstories.json")[0]
    item = get(f"https://hacker-news.firebaseio.com/v0/item/{top}.json")
    return {"id": top, "title": item.get("title", "")[:120]}

def kp_facts(rows):
    # SWPC serves either dict rows ({"time_tag","Kp",...}) or a header row + array rows
    last = rows[-1]
    if isinstance(last, dict):
        return {"kp": str(last["Kp"]), "at": str(last["time_tag"])}
    return {"kp": str(last[1]), "at": str(last[0])}

def poly_facts(markets):
    out = []
    for m in markets[:3]:
        prices = m.get("outcomePrices")
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except Exception:
                prices = []
        out.append({"question": str(m.get("question", ""))[:110],
                    "yes_price": str(prices[0]) if prices else None})
    return {"top_by_volume": out}

def load_chain(d):
    return chainio.load_chain(d)

def main():
    tick_head = json.loads((TICKS / "HEAD.json").read_text())
    tick_n, tick_hash = tick_head["count"] - 1, tick_head["head_frame"]
    WORLD.mkdir(exist_ok=True)
    chain = load_chain(WORLD)
    head = chain[-1] if chain else None
    if head is not None and head["payload"].get("tick") == tick_n:
        print(f"world: tick {tick_n} already recorded — nothing to do")
        return None
    world, failed = snapshot()
    payload = {"tick": tick_n, "tick_frame": tick_hash, "fetched_utc": utc(),
               "world": world, "sources_failed": failed}
    if head is None:
        payload["about"] = ("The world dimension: at each global tick, what a handful of "
                            "keyless public APIs said at that instant. The APIs only serve "
                            "the present; this chain keeps every present. Attach your own "
                            "dimension frames referencing the same tick anchors.")
    f = R.build_frame("world.snapshot", STREAM, (head["seq"] + 1) if head else 0, utc(),
                      payload, prev=(head["payload_hash"] if head else None))
    ok, step, why = R.verify_frame(f, head=head, stream_id_of_record=STREAM)
    if not ok:
        raise ValueError(f"refusing invalid world frame: {step}: {why}")
    chainio.append_frame(WORLD, f, STREAM)
    got = ", ".join(world) or "nothing"
    print(f"world frame {f['seq']} @ tick {tick_n}: {got}"
          + (f" (failed: {', '.join(failed)})" if failed else ""))
    return f

if __name__ == "__main__":
    main()
