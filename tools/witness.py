#!/usr/bin/env python3
"""A WITNESS dimension — a second, independent machine re-observes the world.

One machine's reading of a public API is a claim; two unrelated machines recording the
same fact at the same tick corroborate each other. A witness runs on its own hardware,
re-fetches a core subset of the world sources, and appends its observations to its own
stream (witness-<host>/), each frame referencing the tick anchor it observed under.
Contributions arrive as branch pushes -> a CI gate re-verifies every chain and merges
only what proves itself. Anyone can run one: python3 tools/witness.py --host <name>
"""
import json, sys, pathlib, argparse, datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import rapp as R
import world as W
import chainio

ROOT = pathlib.Path(__file__).resolve().parent.parent

def utc():
    n = datetime.datetime.now(datetime.timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"

def observe():
    """Independent re-observation of core sources (same fetchers, this machine's vantage)."""
    obs, failed = {}, []
    def src(name, fn):
        try:
            obs[name] = fn()
        except Exception:
            failed.append(name)
    src("btc_block_height", lambda: {"height": int(W.get(
        "https://mempool.space/api/blocks/tip/height"))})
    src("btc_usd", lambda: {"spot": str(W.get(
        "https://api.coinbase.com/v2/prices/BTC-USD/spot")["data"]["amount"])})
    src("fx_usd", lambda: {k: f"{W.get_rates()[k]:.4f}" for k in ("EUR", "GBP", "JPY", "CNY")})
    src("earthquakes_past_hour", lambda: W.quake_facts(W.get(
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson")))
    return obs, failed

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="witness alias, e.g. battlestation")
    a = ap.parse_args()
    d = ROOT / f"witness-{a.host}"
    stream = f"witness:@kody-w/dogg-{a.host}"
    tick_head = json.loads((ROOT / "ticks" / "HEAD.json").read_text())
    d.mkdir(exist_ok=True)
    chain = W.load_chain(d)
    head = chain[-1] if chain else None
    obs, failed = observe()
    payload = {"witness": a.host, "tick": tick_head["count"] - 1,
               "tick_frame": tick_head["head_frame"], "observed_utc": utc(),
               "observations": obs, "sources_failed": failed}
    if head is None:
        payload["about"] = ("Independent re-observation of core world sources from a "
                            "second machine. Matching observations at the same tick "
                            "corroborate each other; every frame verifies on its own.")
    f = R.build_frame("witness.observation", stream, (head["seq"] + 1) if head else 0,
                      utc(), payload, prev=(head["payload_hash"] if head else None))
    ok, step, why = R.verify_frame(f, head=head, stream_id_of_record=stream)
    if not ok:
        raise ValueError(f"refusing invalid witness frame: {step}: {why}")
    chainio.append_frame(d, f, stream)
    print(f"witness {a.host}: frame {f['seq']} @ tick {payload['tick']} — "
          f"{', '.join(obs) or 'nothing'}" + (f" (failed: {', '.join(failed)})" if failed else ""))

if __name__ == "__main__":
    main()
