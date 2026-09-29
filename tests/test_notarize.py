#!/usr/bin/env python3
"""The public notary appends verified, tick-keyed digest frames, idempotently, from untrusted issue text."""
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import chainio  # noqa: E402
import notarize  # noqa: E402
import rapp as R  # noqa: E402

DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class Notary(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix=".notary-test-")
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        (self.root / "ticks").mkdir()
        shutil.copy(ROOT / "ticks" / "HEAD.json", self.root / "ticks" / "HEAD.json")
        shutil.copytree(ROOT / "notary", self.root / "notary")
        self.tick = json.loads((ROOT / "ticks" / "HEAD.json").read_text())

    def chain(self):
        frames = chainio.load_chain(self.root / "notary")
        head = None
        for frame in frames:
            ok, step, why = R.verify_frame(frame, head=head, stream_id_of_record=notarize.STREAM)
            self.assertTrue(ok, f"frame {frame['seq']}: step {step}: {why}")
            head = frame
        return frames

    def test_a_digest_becomes_a_verified_frame_keyed_to_the_spine(self):
        before = len(self.chain())
        frame, added = notarize.notarize(DIGEST.upper(), "a test label", root=self.root, issue=7)
        self.assertTrue(added)
        frames = self.chain()
        self.assertEqual(len(frames), before + 1)
        self.assertEqual(frames[-1]["frame_hash"], frame["frame_hash"])
        self.assertEqual(frame["kind"], "notary.digest")
        self.assertEqual(frame["payload"], {"digest": DIGEST, "label": "a test label", "issue": 7,
                                            "tick": self.tick["count"] - 1, "tick_frame": self.tick["head_frame"]})
        head = json.loads((self.root / "notary" / "HEAD.json").read_text())
        self.assertEqual((head["count"], head["head_frame"]), (before + 1, frame["frame_hash"]))

    def test_a_digest_is_notarized_once(self):
        first, _ = notarize.notarize(DIGEST, "first", root=self.root)
        again, added = notarize.notarize(DIGEST, "second", root=self.root)
        self.assertFalse(added)
        self.assertEqual(again["frame_hash"], first["frame_hash"])

    def test_only_a_digest_and_a_printable_label_are_taken_from_the_issue(self):
        body = ("### sha256 digest\n\n" + DIGEST + "\n\n### Label\n\nKestrel tick 131 \u2014 alive\x07; rm -rf /\n\n"
                "### Anything else\n\n$(curl evil)\n")
        digest, label = notarize.from_issue_body(body)
        self.assertEqual(digest, DIGEST)
        frame, _ = notarize.notarize(digest, label, root=self.root)
        self.assertEqual(frame["payload"]["label"], "Kestrel tick 131  alive; rm -rf /")
        self.assertNotIn("curl", json.dumps(frame))
        for bad in ("", "not-hex", DIGEST[:-1], DIGEST + "0"):
            with self.assertRaises(ValueError):
                notarize.notarize(bad, "label", root=self.root)
        with self.assertRaises(ValueError):
            notarize.notarize("a" * 64, "\x00\x01", root=self.root)


if __name__ == "__main__":
    unittest.main()
