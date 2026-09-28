#!/usr/bin/env python3
"""Chant codec conformance — stdlib only. Golden vectors in chants/VECTORS.json pin the codebook:
if these words change for this fixture, every chant ever spoken has changed meaning."""
import json, pathlib, random, sys, unittest, zlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import dogg
import subprocess, tempfile

DIM = "markets:@kody-w/dogg-markets"
FRAME = json.loads((ROOT / "tests" / "fixture_markets_frame.json").read_text())
VECTORS = ROOT / "chants" / "VECTORS.json"


def w(s): return s.split()


class GateExitStatus(unittest.TestCase):
    """verify/receive report the gate's verdict in their exit status, so a script cannot take FAIL for OK."""
    STREAM = "demo:@kody-w/gate-exit"

    def dogg(self, *args, cwd):
        return subprocess.run([sys.executable, str(ROOT / "tools" / "dogg.py"), *args],
                              cwd=str(cwd), capture_output=True, text=True)

    def chain(self, repo, forged=False):
        repo.mkdir(parents=True)
        head = None
        for seq in range(2):
            frame = dogg.R.build_frame("demo.frame", self.STREAM, seq, f"2026-01-01T00:00:0{seq}.000Z",
                                       {"n": seq}, prev=head["payload_hash"] if head else None)
            dogg.chainio.append_frame(repo / "demo", frame, self.STREAM)
            head = frame
        if forged:
            path = repo / "demo" / "1.json"
            frame = json.loads(path.read_text()); frame["payload"]["n"] = 99
            path.write_text(json.dumps(frame))

    def bundle(self, base, name, forged):
        repo = base / name
        self.chain(repo, forged)
        git = ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
               "-c", "commit.gpgsign=false"]
        for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "chain"],
                     ["bundle", "create", str(base / f"{name}.dogg"), "--all"]):
            subprocess.run(git + step, check=True, capture_output=True)

    def test_verify_exits_1_on_a_forged_chain_and_0_on_an_honest_one(self):
        with tempfile.TemporaryDirectory() as t:
            honest, forged = pathlib.Path(t) / "honest", pathlib.Path(t) / "forged"
            self.chain(honest)
            self.chain(forged, forged=True)
            ok = self.dogg("verify", str(honest), cwd=t)
            self.assertEqual((ok.returncode, ok.stdout.strip()), (0, "OK — every chain verifies"), ok.stderr)
            bad = self.dogg("verify", str(forged), cwd=t)
            self.assertEqual((bad.returncode, bad.stdout.strip()), (1, "FAIL: frame 1: step 2"), bad.stderr)

    def test_receive_exits_1_when_it_bounces_a_forged_bundle(self):
        with tempfile.TemporaryDirectory() as t:
            base = pathlib.Path(t)
            self.bundle(base, "honest", forged=False)
            self.bundle(base, "forged", forged=True)
            ok = self.dogg("receive", "honest.dogg", cwd=base)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            self.assertTrue((base / "pantry" / "honest" / "demo" / "HEAD.json").exists())
            bad = self.dogg("receive", "forged.dogg", cwd=base)
            self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
            self.assertIn("forged: REJECTED (frame 1: step 2)", bad.stdout)
            self.assertFalse((base / "pantry" / "forged").exists())


class Codec(unittest.TestCase):
    def test_mission_roundtrip_and_precision(self):
        words = w(dogg.mission_encode(DIM, FRAME, ["btc_usd", "eur_per_usd", "btc_fee_sat_vb"]))
        tile = dogg.recite(words)
        truth = {"btc_usd": 79669.125, "eur_per_usd": 0.8583, "btc_fee_sat_vb": 3}
        for k, v in truth.items():
            got = tile["fields"][k]["value"]
            self.assertLess(abs(got - v) / v, 0.005, f"{k}: {got} vs {v}")
        self.assertEqual(dogg.mission_attest(words, FRAME)[0], "MATCH")

    def test_mission_attest_verdicts(self):
        words = w(dogg.mission_encode(DIM, FRAME))
        other = dict(FRAME, seq=FRAME["seq"] - 1)
        self.assertEqual(dogg.mission_attest(words, other)[0], "DIFFERENT-TICK")
        forged = json.loads(json.dumps(FRAME)); forged["payload"]["markets"]["btc_usd"]["spot"] = "99999"
        self.assertEqual(dogg.mission_attest(words, forged)[0], "FORGED")

    def test_checksum_refuses_one_wrong_word(self):
        words = w(dogg.mission_encode(DIM, FRAME))
        words[3] = "TAUNT" if words[3] != "TAUNT" else "FORGE"
        with self.assertRaises(ValueError): dogg.recite(words)

    def test_length_declaration_enforced(self):
        words = w(dogg.mission_encode(DIM, FRAME))
        with self.assertRaises(ValueError): dogg.recite(words[:-1])
        with self.assertRaises(ValueError): dogg.recite(words + ["FORGE"])

    def test_negative_mission_value_refused_loudly(self):
        f = json.loads(json.dumps(FRAME)); f["payload"]["markets"]["btc_usd"]["spot"] = "-1"
        with self.assertRaises(ValueError): dogg.mission_encode(DIM, f, ["btc_usd"])

    def test_lens_exact_and_dimension_bound(self):
        key = w(dogg.lens_make("select", DIM, ["btc_usd", "eth_usd"]))
        tile = dogg.wear(key, FRAME)
        self.assertEqual(tile["fields"]["btc_usd"]["value"], "79669.125")
        foreign = dict(FRAME, stream_id="world:@kody-w/dogg")
        with self.assertRaises(ValueError): dogg.wear(key, foreign)

    def test_seed_program_and_every_bitstring_parses(self):
        prog = [("select", "btc_usd"), ("ratio", "btc_usd", "eth_usd"), ("above", "btc_usd", 70000)]
        words = w(dogg.seed_make(DIM, prog))
        out = dogg.wear(words, FRAME)["results"]
        self.assertAlmostEqual(out["btc_usd"], 79669.125)
        self.assertTrue(out[[k for k in out if k.startswith("above")][0]])
        rng = random.Random(1)
        for _ in range(50):
            b = dogg.Bits().put(12, dogg._dim_id(DIM))
            for _ in range(rng.randint(3, 90)): b.put(1, rng.randint(0, 1))
            dogg.recite(w(dogg.chant_pack(dogg.KIND_SEED, b)))  # must never raise

    def test_book_exact_and_capped(self):
        words = w(dogg.inscribe(FRAME))
        self.assertEqual(dogg.recite(words)["tile"], FRAME)
        bomb = zlib.compress(b"0" * (dogg.BOOK_MAX_BYTES + 10), 9)
        b = dogg.Bits().put(16, len(bomb))
        for byte in bomb: b.put(8, byte)
        with self.assertRaises(ValueError): dogg.recite(w(dogg.chant_pack(dogg.KIND_BOOK, b)))

    def test_uri_and_pages_roundtrip(self):
        words = w(dogg.inscribe(FRAME))
        uri = dogg.to_uri(words)
        self.assertEqual(dogg.from_uri(uri), words)
        pages = dogg.uri_pages(uri)
        self.assertGreater(len(pages), 1)
        self.assertEqual(dogg.as_words(list(reversed(pages))), words)  # any page order

    def test_ndef_record_is_well_formed_and_round_trips(self):
        words = w(dogg.mission_encode(DIM, FRAME))
        msg = dogg.ndef_uri(dogg.to_uri(words))
        self.assertEqual(msg[0] & 0xD7, 0xD1)          # MB, ME, SR, TNF=well-known
        self.assertEqual(msg[1], 1); self.assertEqual(msg[3:4], b"U"); self.assertEqual(msg[4], 0)
        uri = msg[5:5 + msg[2] - 1].decode()
        self.assertEqual(dogg.from_uri(uri), words)
        self.assertTrue(any(fits for _, _, fits in dogg.ndef_pages(words)))

    def test_codebook_gate(self):
        self.assertEqual(dogg.codebook_check(), [], "codebook drift or dimension-id collision")

    def test_golden_vectors_pin_the_codebook(self):
        vec = json.loads(VECTORS.read_text())
        self.assertEqual(dogg.mission_encode(DIM, FRAME), vec["mission_default"])
        self.assertEqual(dogg.lens_make("select", DIM, ["btc_usd"]), vec["lens_select_btc"])
        self.assertEqual(dogg.seed_make(DIM, [("select", "btc_usd"), ("above", "btc_usd", 70000)]), vec["seed_btc_above_70000"])
        self.assertEqual(dogg.to_uri(w(vec["mission_default"])), vec["mission_default_uri"])


if __name__ == "__main__":
    if "--regen" in sys.argv:
        VECTORS.write_text(json.dumps({
            "schema": "dogg/0-chant-vectors", "fixture": "tests/fixture_markets_frame.json", "dimension": DIM,
            "note": "golden vectors — a second implementation must reproduce these words exactly; changing them means the codebook changed",
            "mission_default": dogg.mission_encode(DIM, FRAME),
            "mission_default_uri": dogg.to_uri(w(dogg.mission_encode(DIM, FRAME))),
            "lens_select_btc": dogg.lens_make("select", DIM, ["btc_usd"]),
            "seed_btc_above_70000": dogg.seed_make(DIM, [("select", "btc_usd"), ("above", "btc_usd", 70000)]),
        }, indent=1) + "\n"); print("vectors regenerated"); sys.exit(0)
    unittest.main(verbosity=1)
