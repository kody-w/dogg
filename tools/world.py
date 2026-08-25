#!/usr/bin/env python3
"""The WORLD dimension — globally useful DOGG data, one frame per tick.

Public "right now" APIs only ever serve the present: ask a price API what BTC cost two
hours ago and it shrugs. This dimension fixes that. At (almost) every global tick it
records what a handful of keyless public APIs said AT that instant, as a frame chained
to the tick anchor — so "what did the world look like at tick N" becomes an addressable,
verifiable object forever. Agents that were offline can catch up from here; any stream
can attach its own dimension frames referencing the same tick anchors to add context.

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
    # rapp/1 canonical hashing (JCS subset) forbids floats: numeric facts ride as strings
    src("btc_usd", lambda: {"spot": str(get(
        "https://api.coinbase.com/v2/prices/BTC-USD/spot")["data"]["amount"])})
    src("fx_usd", lambda: {k: f"{get_rates()[k]:.4f}" for k in ("EUR", "GBP", "JPY", "CNY")})
    src("earthquakes_past_hour", lambda: quake_facts(get(
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson")))
    src("iss", lambda: (lambda d: {"lat": f"{float(d['latitude']):.3f}",
                                   "lon": f"{float(d['longitude']):.3f}"})(
        get("https://api.wheretheiss.at/v1/satellites/25544")))
    src("hn_top", lambda: hn_facts())
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

def load_chain(d):
    if not (d / "HEAD.json").exists():
        return []
    count = json.loads((d / "HEAD.json").read_text())["count"]
    return [json.loads((d / f"{i}.json").read_text()) for i in range(count)]

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
    (WORLD / f"{f['seq']}.json").write_text(json.dumps(f, indent=2, ensure_ascii=False) + "\n")
    (WORLD / "HEAD.json").write_text(json.dumps({"count": f["seq"] + 1, "stream_id": STREAM,
        "head_frame": f["frame_hash"], "updated": utc()}, indent=2) + "\n")
    got = ", ".join(world) or "nothing"
    print(f"world frame {f['seq']} @ tick {tick_n}: {got}"
          + (f" (failed: {', '.join(failed)})" if failed else ""))
    return f

if __name__ == "__main__":
    main()
