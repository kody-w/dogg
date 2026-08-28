#!/usr/bin/env python3
"""sigil — the drawable form of a SEED program.

A SEED chant (dogg/0, kind 4) carries a bit-grammar program: one op per step,
operands as 4-bit field indices, thresholds as 14-bit log-quantized codes. A sigil is
that same program made visible: one rune per op, operand field names beside the rune,
thresholds as plain numbers — rendered as a self-contained SVG, or as a one-line text
form that round-trips back into the exact SEED chant words.

  python3 sigil.py render W1 … Wn > out.svg     self-contained SVG of a SEED chant
  python3 sigil.py text   W1 … Wn                the one-line text sigil for a SEED chant
  python3 sigil.py parse  "<text sigil>" <stream-id>
                                                  text sigil -> the SEED chant words

Rune table and the round-trip guarantee: chants/SIGILS.md. This reuses dogg.py's own
codec (seed_compile / seed_make / chant_unpack / wordlist) — a sigil is a second SKIN
on the same bits, never a second encoding of them. Protocol: ../PROTOCOL.md
("The spellbook" — SEED grammar).
"""
import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import dogg  # noqa: E402  (path must be set up first)

# op name -> rune. The SEED grammar's eight ops are append-only (dogg/0: "the codebook
# is append-only" — see PROTOCOL.md); this table mirrors that law — a rune, once
# assigned, is never reassigned or removed. New ops (if the grammar ever grows) get a
# new rune appended here, never a reuse of an existing one.
RUNES = {
    "select": "◆",       # ◆
    "delta": "Δ",        # Δ
    "ratio": "÷",        # ÷
    "above": "▲",        # ▲
    "below": "▼",        # ▼
    "sum": "Σ",          # Σ
    "change_pct": "%",
    "max_of": "⋁",       # ⋁
}
OP_OF_RUNE = {r: op for op, r in RUNES.items()}
ALL_RUNES = "".join(RUNES.values())


def _fmt_num(x):
    """Canonical display of a log-quantized threshold: whole numbers print bare
    ("70100", not "70100.0"), so text->words->text reproduces the same characters."""
    try:
        xf = float(x)
        if xf.is_integer():
            return str(int(xf))
    except (TypeError, ValueError):
        pass
    return str(x)


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


# ── words -> program -----------------------------------------------------------------
def decode_seed(words):
    """SEED chant words -> (dimension, program, field table).

    `program` is dogg.seed_compile's own shape: a list of (op_name, [operand_indices]).
    Raises ValueError if the chant is not a SEED chant — a sigil exists only for
    programs; recite() is the right tool for MISSION/LENS/BOOK chants."""
    kind, body = dogg.chant_unpack(words)
    if kind != dogg.KIND_SEED:
        raise ValueError("not a SEED chant — a sigil is the drawable form of a program")
    dim_id, prog = dogg.seed_compile(body)
    dimension = dogg._resolve_dim(dim_id)
    table = dogg._fields_for(dimension) if dimension else []
    return dimension, prog, table


def _rows(prog, table):
    """program -> [(rune, op, operand_text)], the shared shape text and SVG both draw from."""
    def name(i):
        return table[i]["name"] if i < len(table) else f"field_{i}"

    rows = []
    for op, args in prog:
        r = RUNES[op]
        if op in ("select", "delta", "change_pct"):
            rows.append((r, op, name(args[0])))
        elif op == "ratio":
            rows.append((r, op, f"{name(args[0])}/{name(args[1])}"))
        elif op == "sum":
            rows.append((r, op, f"{name(args[0])}+{name(args[1])}"))
        elif op == "max_of":
            rows.append((r, op, f"{name(args[0])},{name(args[1])}"))
        elif op in ("above", "below"):
            thr = _fmt_num(dogg._sig(dogg._logd(args[1])))
            sym = ">" if op == "above" else "<"
            rows.append((r, op, f"{name(args[0])}{sym}{thr}"))
        else:
            raise ValueError(f"no rune for op {op!r}")  # unreachable: RUNES covers every op
    return rows


def program_to_text(prog, table):
    """program -> the one-line text sigil, e.g. '◆btc_usd ÷btc_usd/eth_usd ▲btc_usd>70100'."""
    return " ".join(f"{r}{operand}" for r, _op, operand in _rows(prog, table))


def words_to_text(words):
    """SEED chant words -> the one-line text sigil."""
    _dimension, prog, table = decode_seed(words)
    return program_to_text(prog, table)


# ── text -> program -> words -----------------------------------------------------------
# One token per op: <rune><operand>. Operand grammar mirrors program_to_text exactly,
# so every string that function can produce, this parses back losslessly.
_TOKEN_RE = re.compile(r"^(?P<rune>[" + re.escape(ALL_RUNES) + r"])(?P<rest>.+)$")


def text_to_program(text):
    """The one-line text sigil -> a program in dogg.seed_make's own input shape:
    (op_name, *args) with field NAMES and numeric thresholds — ready to hand straight
    to dogg.seed_make(dimension, program)."""
    prog = []
    for tok in text.split():
        m = _TOKEN_RE.match(tok)
        if not m:
            raise ValueError(f"not a sigil token: {tok!r}")
        rune, rest = m.group("rune"), m.group("rest")
        op = OP_OF_RUNE[rune]
        if op in ("select", "delta", "change_pct"):
            if not rest:
                raise ValueError(f"{op} sigil needs a field name: {tok!r}")
            prog.append((op, rest))
        elif op == "ratio":
            if "/" not in rest:
                raise ValueError(f"ratio sigil needs 'a/b': {tok!r}")
            a, b = rest.split("/", 1)
            prog.append((op, a, b))
        elif op == "sum":
            if "+" not in rest:
                raise ValueError(f"sum sigil needs 'a+b': {tok!r}")
            a, b = rest.split("+", 1)
            prog.append((op, a, b))
        elif op == "max_of":
            if "," not in rest:
                raise ValueError(f"max_of sigil needs 'a,b': {tok!r}")
            a, b = rest.split(",", 1)
            prog.append((op, a, b))
        else:  # above / below
            sym = ">" if op == "above" else "<"
            if sym not in rest:
                raise ValueError(f"{op} sigil needs {sym!r}: {tok!r}")
            f, v = rest.split(sym, 1)
            prog.append((op, f, float(v)))
    return prog


def text_to_words(text, dimension):
    """The one-line text sigil -> the SEED chant words, cut for `dimension`."""
    return dogg.seed_make(dimension, text_to_program(text))


# ── SVG: one rune per op, operand field names beside it -----------------------------
def render_svg(words, title=None):
    """SEED chant words -> a self-contained SVG. One row per op: the rune, then its
    operand field name(s)/threshold as plain text. No external fonts required — runes
    render as Unicode text against the system fallback stack."""
    dimension, prog, table = decode_seed(words)
    rows = _rows(prog, table)
    if not rows:
        rows = [("", "(empty program)", "")]

    pad, row_h, rune_w = 18, 40, 46
    title_txt = title or dimension or "sigil"
    text_w = max((len(op) + len(operand) for _, op, operand in rows), default=10)
    width = max(320, pad * 2 + rune_w + text_w * 11)
    height = pad * 2 + 28 + row_h * len(rows)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f'aria-label="SEED sigil: {_esc(title_txt)}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b0f14"/>',
        f'<text x="{pad}" y="{pad + 14}" font-family="ui-monospace, Menlo, Consolas, '
        f'monospace" font-size="12" fill="#7a8699">{_esc(title_txt)}</text>',
    ]
    y = pad + 28 + row_h * 0.68
    for rune, op, operand in rows:
        out.append(
            f'<text x="{pad}" y="{y:.1f}" font-family="ui-monospace, Menlo, Consolas, '
            f'monospace, \'Noto Sans Symbols\', sans-serif" font-size="26" '
            f'fill="#e8b64a">{_esc(rune)}</text>'
        )
        out.append(
            f'<text x="{pad + rune_w}" y="{y:.1f}" font-family="ui-monospace, Menlo, '
            f'Consolas, monospace" font-size="16" fill="#e6edf3">{_esc(operand)}'
            f'<tspan fill="#4c5666" font-size="11" dx="6">{_esc(op)}</tspan></text>'
        )
        y += row_h
    out.append("</svg>")
    return "\n".join(out)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]
    if cmd == "render":
        print(render_svg(dogg.as_words(rest)))
    elif cmd == "text":
        print(words_to_text(dogg.as_words(rest)))
    elif cmd == "parse":
        if len(rest) != 2:
            raise SystemExit('usage: sigil.py parse "<text sigil>" <stream-id>')
        print(text_to_words(rest[0], rest[1]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
