#!/usr/bin/env python3
"""Sigil conformance — stdlib only. Proves text<->words round trips for three SEED
programs and that a rendered SVG carries every rune. sigil.py never re-encodes SEED
bits; it re-skins dogg.py's own seed_compile/seed_make, so this gate rides on top of
tests/test_chants.py, not instead of it."""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import dogg  # noqa: E402
import sigil  # noqa: E402

DIM = "markets:@kody-w/dogg-markets"

# Three programs spanning all eight ops between them (select/ratio/above use only 3 in
# program 1; delta/below/change_pct in program 2; sum/max_of in program 3) — every op
# in the SEED grammar is exercised across the three.
PROGRAMS = [
    [("select", "btc_usd"), ("ratio", "btc_usd", "eth_usd"), ("above", "btc_usd", 70100)],
    [("delta", "eth_usd"), ("below", "btc_fee_sat_vb", 5), ("change_pct", "crypto_mcap_usd")],
    [("sum", "btc_usd", "eth_usd"), ("max_of", "btc_usd", "eth_usd")],
]

ALL_OPS = {"select", "delta", "ratio", "above", "below", "sum", "change_pct", "max_of"}


class Sigils(unittest.TestCase):
    def test_programs_cover_every_op(self):
        # a guard on the fixture itself: if this ever drifts, the "every rune" claim
        # below would silently stop meaning what it says.
        used = {op for prog in PROGRAMS for op, *_ in prog}
        self.assertEqual(used, ALL_OPS)

    def test_text_words_text_roundtrip(self):
        for prog in PROGRAMS:
            words1 = dogg.seed_make(DIM, prog).split()
            text1 = sigil.words_to_text(words1)

            # every op's rune appears, and it decodes back to a SEED chant
            for op, *_ in prog:
                self.assertIn(sigil.RUNES[op], text1)
            kind, _ = dogg.chant_unpack(words1)
            self.assertEqual(kind, dogg.KIND_SEED)

            words2 = sigil.text_to_words(text1, DIM).split()
            text2 = sigil.words_to_text(words2)
            self.assertEqual(text1, text2, "text -> words -> text must be a fixed point")

            # and the re-minted words are themselves a valid, re-decodable SEED chant
            # for the same dimension (round trip proven on meaning, not byte identity —
            # SEED chants pad to a word boundary, so trailing zero-bits can decode as an
            # extra no-op-equivalent op; that padding is dogg/0's own "every bitstring
            # is a valid program" property, not a sigil defect).
            dimension2, prog2, table2 = sigil.decode_seed(words2)
            self.assertEqual(dimension2, DIM)
            self.assertEqual(sigil.program_to_text(prog2, table2), text1)

    def test_text_to_program_matches_hand_shape(self):
        text = "◆btc_usd ÷btc_usd/eth_usd ▲btc_usd>70100"
        prog = sigil.text_to_program(text)
        self.assertEqual(prog, [
            ("select", "btc_usd"),
            ("ratio", "btc_usd", "eth_usd"),
            ("above", "btc_usd", 70100.0),
        ])
        # and it mints the same words dogg.py's own seed_make would for that program
        self.assertEqual(
            sigil.text_to_words(text, DIM),
            dogg.seed_make(DIM, [("select", "btc_usd"), ("ratio", "btc_usd", "eth_usd"),
                                  ("above", "btc_usd", 70100)]),
        )

    def test_bad_token_refuses(self):
        with self.assertRaises(ValueError):
            sigil.text_to_program("notarune_field")
        with self.assertRaises(ValueError):
            sigil.text_to_program("÷btc_usd")  # ratio needs a/b

    def test_render_svg_contains_every_rune(self):
        prog = [op_args for prog in PROGRAMS for op_args in prog]
        words = dogg.seed_make(DIM, prog).split()
        svg = sigil.render_svg(words)
        self.assertTrue(svg.strip().startswith("<svg"))
        self.assertTrue(svg.strip().endswith("</svg>"))
        for rune in sigil.RUNES.values():
            self.assertIn(rune, svg, f"missing rune {rune!r} in rendered SVG")
        # well-formed enough to parse as XML (a real renderer will be far stricter)
        import xml.etree.ElementTree as ET
        ET.fromstring(svg)

    def test_render_svg_is_self_contained(self):
        words = dogg.seed_make(DIM, PROGRAMS[0]).split()
        svg = sigil.render_svg(words)
        self.assertNotIn("http://", svg.replace("http://www.w3.org/2000/svg", ""))
        self.assertNotIn("@font-face", svg)

    def test_non_seed_chant_refused(self):
        # a LENS chant (kind 2) is enough to prove the guard: a sigil exists only for
        # SEED programs (kind 4).
        lens_words = dogg.lens_make("select", DIM, ["btc_usd"]).split()
        with self.assertRaises(ValueError):
            sigil.decode_seed(lens_words)
        with self.assertRaises(ValueError):
            sigil.words_to_text(lens_words)


if __name__ == "__main__":
    unittest.main()
