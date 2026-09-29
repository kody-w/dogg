#!/usr/bin/env python3
"""The contribution gate (tools/pr_gate.py), run for real in a throwaway git repo.

A witness branch merges only if every tick reference it adds names a real spine frame:
frames inside a contributed epochs/<k>.jsonl bundle are checked like flat ones, and a
tick must be an integer index into the spine, never a path to some other chain's file.
"""
import json, pathlib, shutil, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import rapp as R

GIT = ["git", "-c", "user.name=gate-test", "-c", "user.email=gate-test@localhost",
       "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
       "-c", "init.defaultBranch=main"]


def write_chain(d, stream, kind, payloads, epoch_size=2, sealed=0):
    """A valid chain in the chainio layout: `sealed` epoch bundles, then a flat tail."""
    frames, head = [], None
    for seq, payload in enumerate(payloads):
        head = R.build_frame(kind, stream, seq, f"2026-09-26T00:00:{seq:02d}.000Z", payload,
                             prev=head["payload_hash"] if head else None)
        frames.append(head)
    d.mkdir(parents=True)
    for k in range(sealed):
        (d / "epochs").mkdir(exist_ok=True)
        (d / "epochs" / f"{k}.jsonl").write_text("".join(
            json.dumps(f) + "\n" for f in frames[k * epoch_size:(k + 1) * epoch_size]))
    for f in frames[sealed * epoch_size:]:
        (d / f"{f['seq']}.json").write_text(json.dumps(f, indent=2) + "\n")
    (d / "HEAD.json").write_text(json.dumps({
        "count": len(frames), "stream_id": stream, "head_frame": head["frame_hash"],
        "epoch_size": epoch_size, "sealed_epochs": sealed}, indent=2) + "\n")
    return frames


class ContributionGate(unittest.TestCase):
    def setUp(self):
        self.repo = pathlib.Path(tempfile.mkdtemp(prefix="dogg-gate-"))
        self.addCleanup(shutil.rmtree, self.repo, True)
        (self.repo / "tools").mkdir()
        for name in ("pr_gate.py", "verify_thread.py", "rapp.py", "chainio.py"):
            shutil.copy(ROOT / "tools" / name, self.repo / "tools" / name)
        # a six-tick spine: ticks 0-3 sealed in two bundles, ticks 4-5 flat
        self.ticks = write_chain(self.repo / "ticks", "tick:@test/spine", "tick.anchor",
                                 [{"tick": n} for n in range(6)], sealed=2)
        # another verified chain in the repo whose flat frames are not tick anchors
        self.decoy = write_chain(self.repo / "decoy", "decoy:@test/other", "decoy.note",
                                 [{"note": n} for n in range(2)])
        # a file outside every chain, which no contribution may touch
        (self.repo / "PROTOCOL.md").write_text("# the law of this test repo\n\nno moving it.\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(GIT + ["-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout

    def spine(self, n):
        return n, self.ticks[n]["frame_hash"]

    def contribute(self, refs, sealed=0, moves=()):
        """Commit a witness-alpha/ chain whose frames claim the given (tick, tick_frame)
        pairs, plus any (src, dst) `git mv` moves, on top of the base, then run the gate
        against the base as CI does."""
        self.git("reset", "-q", "--hard", self.base)
        self.git("clean", "-qfd")
        write_chain(self.repo / "witness-alpha", "witness:@test/alpha", "witness.observation",
                    [{"witness": "alpha", "tick": t, "tick_frame": h} for t, h in refs],
                    sealed=sealed)
        for src, dst in moves:
            self.git("mv", src, dst)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "witness")
        return subprocess.run([sys.executable, str(self.repo / "tools" / "pr_gate.py"),
                               self.base], capture_output=True, text=True)

    def test_real_references_pass_in_bundles_and_flat_files(self):
        # frames 0-1 ride in witness-alpha/epochs/0.jsonl, as chainio.compact seals them
        r = self.contribute([self.spine(0), self.spine(1), self.spine(3), self.spine(5)],
                            sealed=1)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GATE PASS: witness-alpha", r.stdout)
        self.assertIn("4 tick reference(s) confirmed", r.stdout)

    def test_forged_reference_in_flat_frame_fails(self):
        r = self.contribute([self.spine(1), (4, self.ticks[5]["frame_hash"])])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("GATE FAIL: witness-alpha/1.json claims tick 4", r.stdout)

    def test_forged_reference_in_sealed_bundle_fails(self):
        # frames 0-1 ride in witness-alpha/epochs/0.jsonl; frame 0's claim is forged
        r = self.contribute([(0, "0" * 64), self.spine(2), self.spine(4), self.spine(5)],
                            sealed=1)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("GATE FAIL: witness-alpha/epochs/0.jsonl claims tick 0", r.stdout)

    def test_tick_must_index_the_spine(self):
        for tick, claimed in (("../decoy/1", self.decoy[1]["frame_hash"]),
                              ("5", self.ticks[5]["frame_hash"]),
                              (True, self.ticks[1]["frame_hash"]),
                              (-1, self.ticks[5]["frame_hash"]),
                              (6, self.ticks[5]["frame_hash"])):
            with self.subTest(tick=tick):
                r = self.contribute([(tick, claimed)])
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("GATE FAIL: witness-alpha/0.json claims tick", r.stdout)

    def test_moving_a_path_into_the_witness_dir_fails(self):
        # git names a rename by its new path alone; the path it vacates must be gated too.
        # Moving a chain's HEAD.json away would also drop that chain from verify_thread.
        for src, dst in (("PROTOCOL.md", "witness-alpha/PROTOCOL.md"),
                         ("decoy/HEAD.json", "witness-alpha/decoy-HEAD.json")):
            with self.subTest(src=src):
                r = self.contribute([self.spine(5)], moves=[(src, dst)])
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(f"GATE FAIL: '{src}' is outside a witness-*/ dimension", r.stdout)


if __name__ == "__main__":
    unittest.main()
