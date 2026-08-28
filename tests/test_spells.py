#!/usr/bin/env python3
"""Named spells conformance — stdlib only. chants/SPELLS.json is append-only: a name,
once minted, never changes meaning. These tests exercise the `spell` verb's helper
(dogg.spell_registry), the as_words() expansion that lets wear/recite/attest accept a
spell NAME, and the seeded markets/sky/water spells against the real codebook."""
import json, os, pathlib, shutil, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import dogg

FRAME = json.loads((ROOT / "tests" / "fixture_markets_frame.json").read_text())
SPELLS = json.loads((ROOT / "chants" / "SPELLS.json").read_text())["spells"]


def w(s): return s.split()


class NamedSpells(unittest.TestCase):
    # ── the seeded book itself ──────────────────────────────────────────────
    def test_seed_book_has_six_spells_across_three_dimensions(self):
        self.assertEqual(len(SPELLS), 6)
        dims = {entry["dimension"] for entry in SPELLS.values()}
        self.assertEqual(dims, {"markets:@kody-w/dogg-markets", "sky:@kody-w/dogg-sky", "water:@kody-w/dogg-water"})
        for name, entry in SPELLS.items():
            self.assertTrue(entry["meaning"], name)
            kind, body = dogg.chant_unpack(entry["words"])       # every seeded spell must still check
            self.assertIn(kind, (dogg.KIND_SEED, dogg.KIND_LENS), name)
            self.assertEqual(dogg._resolve_dim(body.get(12)), entry["dimension"], name)

    # ── expansion: wear/recite/attest accept a spell NAME ──────────────────
    def test_as_words_expands_a_known_spell_name(self):
        got = dogg.as_words(["sunrise-atlanta"])
        self.assertEqual(got, SPELLS["sunrise-atlanta"]["words"])

    def test_as_words_leaves_real_words_and_uris_alone(self):
        words = SPELLS["moon-watch"]["words"]
        self.assertEqual(dogg.as_words(words), words)                       # plain words pass through
        uri = dogg.to_uri(words)
        self.assertEqual(dogg.as_words([uri]), words)                       # a dogg: URI still resolves

    def test_recite_accepts_a_spell_name(self):
        tile = dogg.recite(dogg.as_words(["moon-watch"]))
        self.assertEqual(tile["schema"], "dogg/0-lens-key")
        self.assertEqual(tile["dimension"], "sky:@kody-w/dogg-sky")
        self.assertEqual(tile["lens"], "select")

    def test_wear_via_a_spell_name_on_the_markets_fixture(self):
        tile = dogg.wear(dogg.as_words(["btc-alarm-70k"]), FRAME)
        self.assertEqual(tile["schema"], "dogg/0-lens-tile")
        self.assertEqual(tile["dimension"], "markets:@kody-w/dogg-markets")
        self.assertEqual(tile["alarm"]["field"], "btc_usd")
        self.assertTrue(tile["alarm"]["fired"])                             # fixture spot is 79669.125 > 70000
        self.assertEqual(tile["alarm"]["value"], "79669.125")

    def test_wear_via_spell_name_matches_wear_via_raw_words(self):
        by_name = dogg.wear(dogg.as_words(["gauge-select"]), _water_frame())
        by_words = dogg.wear(SPELLS["gauge-select"]["words"], _water_frame())
        self.assertEqual(by_name, by_words)

    # ── refusals ─────────────────────────────────────────────────────────
    def test_refuses_unknown_spell_name(self):
        with self.assertRaises(ValueError):
            dogg.spell_registry(action="get", name="not-a-real-spell")

    def test_unknown_name_falls_through_as_words_and_still_refuses_downstream(self):
        # a single arg that matches no spell is passed through unchanged, then fails as a chant
        with self.assertRaises(ValueError):
            dogg.recite(dogg.as_words(["not-a-real-spell"]))

    def test_refuses_duplicate_name_on_add(self):
        existing = SPELLS["btc-alarm-70k"]
        with self.assertRaises(ValueError) as ctx:
            dogg.spell_registry(action="add", name="btc-alarm-70k", words=existing["words"], meaning="anything")
        self.assertIn("already exists", str(ctx.exception))

    def test_refuses_words_that_do_not_check_on_add(self):
        with self.assertRaises(ValueError):
            dogg.spell_registry(action="add", name="brand-new-name-xyz", words=["NOTAWORD", "ALSO", "NOT"], meaning="bad")

    def test_refuses_a_book_chant_as_a_spell(self):
        # spells cache SEED or LENS chants only, per the spec ("a full chant (SEED or LENS words)")
        book_words = w(dogg.inscribe({"a": 1}))
        with self.assertRaises(ValueError):
            dogg.spell_registry(action="add", name="brand-new-book-xyz", words=book_words, meaning="a book, refused")

    # ── minting a new spell end-to-end, isolated from the tracked file ─────
    def test_add_mints_a_retrievable_append_only_entry(self):
        with _isolated_spellbook():
            words = w(dogg.lens_make("select", "markets:@kody-w/dogg-markets", ["btc_usd"]))
            entry = dogg.spell_registry(action="add", name="test-only-spell", words=words, meaning="a throwaway test spell")
            self.assertEqual(entry["dimension"], "markets:@kody-w/dogg-markets")
            self.assertEqual(entry["words"], [x.upper() for x in words])
            # retrievable afterwards, and expands through as_words like any seeded spell
            self.assertEqual(dogg.spell_registry(action="get", name="test-only-spell"), entry)
            self.assertEqual(dogg.as_words(["test-only-spell"]), entry["words"])
            # append-only: minting the same name again refuses, even mid-session
            with self.assertRaises(ValueError):
                dogg.spell_registry(action="add", name="test-only-spell", words=words, meaning="again")
            # persisted to disk, not just held in memory
            on_disk = json.loads((dogg.ROOT / "chants" / "SPELLS.json").read_text())["spells"]
            self.assertIn("test-only-spell", on_disk)


def _water_frame():
    return {
        "spec": "rapp/1", "kind": "water.gauge", "stream_id": "water:@kody-w/dogg-water", "seq": 5,
        "payload": {"water": {"gauge": {"gauge_height_ft": "12.4", "flood_stage_ft": "20.0", "pct_of_flood_stage": "62.0"},
                               "procedure": {"version": 1}}},
    }


class _isolated_spellbook:
    """Redirect dogg.ROOT to a scratch dir that symlinks the real codebook (wordlist, missions,
    lenses, lock) but starts with no chants/SPELLS.json of its own — so `--add` writes land
    nowhere near the tracked file. Only the pieces spell_registry/wordlist/missions actually
    touch are linked; registry/ is not needed since markets/sky/water already have mission tables."""
    def __enter__(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        chants = self.tmp / "chants"; chants.mkdir()
        for name in ("WORDLIST.txt", "MISSIONS.json", "LENSES.json", "CODEBOOK.lock"):
            os.symlink(ROOT / "chants" / name, chants / name)
        self._real_root = dogg.ROOT
        dogg.ROOT = self.tmp
        return self.tmp

    def __exit__(self, *exc):
        dogg.ROOT = self._real_root
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


if __name__ == "__main__":
    unittest.main(verbosity=1)
