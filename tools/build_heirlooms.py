#!/usr/bin/env python3
"""build_heirlooms.py — the ten heirloom dimensions on one page.

For each registered heirloom node: mint its CURRENT mission chant from the live chain, decode
the tile it recites, render a QR of the tap URL, and say what it is still true for. Static
output (Article XXIV): the page is committed HTML, not a runtime API call.
"""
import json, sys, pathlib, urllib.request
TOOLS = pathlib.Path(__file__).resolve().parent; ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS)); import dogg

HEIRLOOMS = {
    "genesis": ("The root chant", "Fingerprints the chant kit itself — wordlist, ops, lock, client — plus the spine's genesis hash. Verify this first; every other chant is meaningless without the machinery it names."),
    "sky":     ("Astronomy as a seed", "Sunrise, sunset, day length and moon phase computed from pure equations. True for any date, any century, with no feed and no server — the algorithm is the heirloom."),
    "water":   ("Purification and the river", "A versioned procedure that never expires — boil, disinfect, filter, store — beside the live gauge height of your actual river and its flood stage."),
    "firstaid":("The kitchen-table chant", "A lay-rescuer decision tree: bleeding, CPR, choking, shock, burns, hypothermia. Procedures do not expire. Not medical advice."),
    "muster":  ("Where we meet", "The family rendezvous plan — points, roles, check-in windows, comms fallback. Template only here; a real plan lives in a private kit."),
    "land":    ("What we hold", "Deed hash, boundary corners, registry pointer. Proves the integrity of a record after the office that issued it is gone. Not title."),
    "seedvault":("What we plant", "Varieties, days to maturity, sow windows and frost dates — the growing year derived from the sky seed for your cell."),
    "radio":   ("How we call", "Emergency frequencies as public constants — weather radio, marine 16, aviation guard — beside the live count of active alerts."),
    "canon":   ("What our rules were", "Hashes and lengths of the constitution and specs that governed. A grandchild can prove in 2076 which text was law."),
    "lineage": ("Who we were", "Births, vows, deaths as frames. Template only here; a real lineage is private, and the heirloom is its head chant."),
}


def show(v):
    """Display a decoded magnitude honestly. A count lives on the integers, so a log-decoded
    4.01 is read back as 4 — decoding with a known prior, not inventing precision. Values that
    are not near an integer are shown exactly as they decoded."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if f and abs(f - round(f)) / max(abs(f), 1e-9) < 0.005:
        return int(round(f))
    return v


def qr_data_uri(text):
    try:
        import qrcode, io, base64
    except ImportError:
        return None
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=3)
    q.add_data(text); q.make(fit=True)
    buf = io.BytesIO(); q.make_image().save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def main():
    cards = []
    for slug, (title, why) in HEIRLOOMS.items():
        dim = f"{slug}:@kody-w/dogg-{slug}"
        try:
            words = dogg.mission_encode(dim, dogg.latest(next(d for d in dogg.registry() if d["dimension"] == dim))[0])
            tile = dogg.recite(words.split())
            uri = dogg.to_uri(words.split())
        except Exception as exc:
            cards.append(f'<article class="card"><h2>{title}</h2><p class="dim">{dim}</p><p class="err">unreachable this build: {type(exc).__name__}</p></article>')
            continue
        tap = f"{dogg.PAGES}/recite.html#{uri}"
        img = qr_data_uri(tap)
        fields = "".join(f'<div class="f"><span class="k">{k}</span><span class="v">{show(v["value"])} <em>{v.get("unit","")}</em></span></div>' for k, v in tile["fields"].items())
        qr = f'<img alt="tap or scan" src="{img}">' if img else ""
        cards.append(f'''<article class="card">
      <div class="qr">{qr}<a class="tap" href="{tap}">tap / scan</a></div>
      <div class="body">
        <h2>{title}</h2>
        <p class="dim"><a href="https://github.com/kody-w/dogg-{slug}">{dim}</a> · tick {tile["tick"]}</p>
        <p class="why">{why}</p>
        <div class="fields">{fields}</div>
        <p class="words">{words}</p>
      </div>
    </article>''')
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The heirloom chants</title>
<meta name="description" content="Ten dimensions worth passing down: each recites offline from words alone, and proves any frame it meets.">
<style>
:root{{color-scheme:dark}}
body{{font:16px/1.6 -apple-system,system-ui,sans-serif;margin:0;background:#0a0a12;color:#e8e8f0}}
main{{max-width:900px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:26px;margin:0 0 6px}}
.lede{{color:#9a9ab0;margin:0 0 6px;max-width:62ch}}
.rule{{color:#7de3ff;font-size:13px;margin:0 0 26px}}
.card{{display:flex;gap:18px;align-items:flex-start;background:#12122a;border:1px solid #26264a;border-radius:14px;padding:16px;margin:0 0 14px}}
.qr{{flex:0 0 auto;text-align:center}}
.qr img{{width:132px;height:132px;image-rendering:pixelated;background:#fff;padding:6px;border-radius:8px;display:block}}
.tap{{display:block;font-size:11px;color:#7de3ff;text-decoration:none;margin-top:6px}}
h2{{font-size:17px;margin:0 0 2px}}
.dim{{font:12px ui-monospace,Menlo,monospace;color:#8a8aa8;margin:0 0 8px}}
.dim a{{color:#8a8aa8}}
.why{{margin:0 0 10px;color:#c8c8dc;font-size:14px}}
.fields{{display:flex;flex-wrap:wrap;gap:8px 18px;margin-bottom:10px}}
.k{{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:#8a8aa8}}
.v{{font-size:17px;font-weight:700}}
.v em{{font-size:11px;font-weight:400;color:#8a8aa8;font-style:normal}}
.words{{font:600 12px/1.7 ui-monospace,Menlo,monospace;color:#ffd98a;word-break:break-word;margin:0}}
.err{{color:#ff8f8f}}
footer{{color:#8a8aa8;font-size:13px;margin-top:26px;border-top:1px solid #26264a;padding-top:16px}}
a{{color:#7de3ff}}
@media(max-width:640px){{.card{{flex-direction:column}}.qr img{{width:150px;height:150px}}}}
</style></head><body><main>
<h1>The heirloom chants</h1>
<p class="lede">Ten dimensions worth passing down. Each one recites offline from its words alone — no network, no account, no app — and proves any full frame it later meets.</p>
<p class="rule">Frames need a source. Tiles live in words. Programs live in seeds. Cache the machinery, never the ore.</p>
{"".join(cards)}
<footer>
<p>Every chant below is a snapshot of one tick; re-mint for the latest with <code>python3 tools/dogg.py mission &lt;dimension&gt;</code>. The words and the square carry the same bits — say them, scan them, write them on a tag, or print them.</p>
<p><a href="https://github.com/kody-w/dogg/blob/main/PROTOCOL.md">The protocol</a> · <a href="recite.html">recite any chant</a> · <a href="orient.json">orient.json</a></p>
</footer>
</main></body></html>'''
    (ROOT / "heirlooms.html").write_text(html)
    print(f"heirlooms.html: {len(cards)} cards")


if __name__ == "__main__":
    main()
