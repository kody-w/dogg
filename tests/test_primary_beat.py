#!/usr/bin/env python3
"""The primary beat against a real spine, a real oracle and a real git remote.

Each test copies this checkout into a throwaway repository, publishes it to a local bare remote,
and runs tools/primary_beat.py from a marked clone of that remote. The clock and the world
observation are the only stand-ins: the clock so that "ten minutes old" is exact, and the world so
that no test depends on twelve public APIs. Everything else is real: the tick is minted with
tools/rapp.py, stored with tools/chainio.py, and held to tools/verify_thread.py and tools/orient.py
before a push the remote can refuse.

    python3 tests/test_primary_beat.py
"""
import datetime
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import rapp as R  # noqa: E402
import chainio  # noqa: E402
import primary_beat as B  # noqa: E402

LABEL = "primary-beat (test)"
WORLD_STREAM = "world:@kody-w/dogg"


def sh(*args, cwd):
    done = subprocess.run(list(args), cwd=str(cwd), capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError(f"{' '.join(args)}: {done.stderr or done.stdout}")
    return done.stdout.strip()


def identity(where):
    sh("git", "config", "user.name", "test", cwd=where)
    sh("git", "config", "user.email", "test@example.invalid", cwd=where)


def quiet_maintenance(where, bare=False):
    prefix = ("git", "--git-dir", str(where)) if bare else ("git",)
    for key, value in (("gc.auto", "0"), ("maintenance.auto", "false"), ("receive.autogc", "false")):
        sh(*prefix, "config", key, value, cwd=where)


def stamp(moment):
    return B.fmt(moment)


class PrimaryBeat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = pathlib.Path(tempfile.mkdtemp(prefix="primary-beat-"))
        seed = cls.base / "seed"
        shutil.copytree(ROOT, seed, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".bridge-test-work", "node_modules", "pantry"))
        sh("git", "init", "-q", "-b", "main", cwd=seed)
        identity(seed)
        quiet_maintenance(seed)
        sh("git", "add", "-A", cwd=seed)
        sh("git", "commit", "-q", "-m", "seed", cwd=seed)
        # thousands of loose objects would invite a background gc that races the clones below
        sh("git", "repack", "-adq", cwd=seed)
        cls.seed = seed
        head = B.newest_anchor(seed)
        cls.head_seq = head["seq"]
        cls.head_utc = B.parse(head["utc"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="beat-", dir=self.base))
        self.remote = self.tmp / "remote.git"
        sh("git", "clone", "-q", "--bare", "--no-hardlinks", str(self.seed), str(self.remote), cwd=self.tmp)
        quiet_maintenance(self.remote, bare=True)
        self.clone = self.clone_of("beat")
        sh("git", "config", "dogg.primaryBeat", "true", cwd=self.clone)
        self.logs = []

    def clone_of(self, name):
        where = self.tmp / name
        sh("git", "clone", "-q", "--no-hardlinks", str(self.remote), str(where), cwd=self.tmp)
        identity(where)
        quiet_maintenance(where)
        return where

    def remote_head(self):
        return sh("git", "--git-dir", str(self.remote), "rev-parse", "refs/heads/main", cwd=self.tmp)

    def published(self):
        """A fresh reader's view of the remote: the chain, and whether the oracle and the
        orientation workflow would both find nothing to do."""
        reader = self.tmp / f"reader-{len(list(self.tmp.iterdir()))}"
        sh("git", "clone", "-q", "--no-hardlinks", str(self.remote), str(reader), cwd=self.tmp)
        oracle = subprocess.run([sys.executable, "tools/verify_thread.py"], cwd=str(reader), capture_output=True, text=True)
        projection = subprocess.run([sys.executable, "tools/orient.py", "--check"], cwd=str(reader),
                                    capture_output=True, text=True)
        return reader, chainio.load_chain(reader / "ticks"), oracle.returncode == 0, projection.returncode == 0

    def at(self, minutes):
        return lambda: self.head_utc + datetime.timedelta(minutes=minutes)

    def fake_world(self, root, moment, state="ok"):
        """What tools/world.py writes, with fixed facts instead of twelve live APIs."""
        if state != "ok":
            return state
        ticks = json.loads((root / "ticks" / "HEAD.json").read_text())
        chain = chainio.load_chain(root / "world")
        head = chain[-1]
        payload = {"tick": ticks["count"] - 1, "tick_frame": ticks["head_frame"], "fetched_utc": stamp(moment),
                   "world": {"test": {"value": "1"}}, "sources_failed": []}
        frame = R.build_frame("world.snapshot", WORLD_STREAM, head["seq"] + 1, stamp(moment), payload,
                              prev=head["payload_hash"])
        chainio.append_frame(root / "world", frame, WORLD_STREAM)
        return "ok"

    def beat(self, minutes, world=None, **kw):
        moment = self.at(minutes)
        return B.beat(self.clone, label=LABEL, now=moment, log=self.logs.append, pause=0.01,
                      world=world or (lambda root: self.fake_world(root, moment())), **kw)

    def test_not_due_writes_nothing(self):
        before = self.remote_head()
        self.assertIsNone(self.beat(5))
        self.assertEqual(self.remote_head(), before)
        self.assertEqual(sh("git", "status", "--porcelain", cwd=self.clone), "")
        self.assertTrue(any(line.startswith("not due") for line in self.logs), self.logs)

    def test_a_due_beat_mints_one_verified_tick_and_leaves_nothing_for_the_projection(self):
        frame = self.beat(11)
        self.assertEqual(frame["seq"], self.head_seq + 1)
        self.assertEqual(frame["payload"], {"tick": frame["seq"], "beat_utc": frame["utc"], "minted_by": LABEL})
        reader, ticks, oracle_ok, projection_unchanged = self.published()
        self.assertEqual(ticks[-1]["frame_hash"], frame["frame_hash"])
        self.assertTrue(oracle_ok, "the pushed chain must verify under the spine's own oracle")
        self.assertTrue(projection_unchanged, "the orientation workflow would have to commit after this tick")
        orient = json.loads((reader / "orient.json").read_text())
        self.assertEqual(orient["tick"]["seq"], frame["seq"])
        self.assertEqual(orient["status"]["world"]["state"], "current")
        world = chainio.load_chain(reader / "world")[-1]["payload"]
        self.assertEqual((world["tick"], world["tick_frame"]), (frame["seq"], frame["frame_hash"]))
        message = sh("git", "--git-dir", str(self.remote), "log", "-1", "--format=%s", "main", cwd=self.tmp)
        self.assertEqual(message, f"tick {frame['seq']}: global anchor {frame['frame_hash'][:12]} + world")

    def test_a_tick_minted_by_someone_else_meanwhile_means_this_beat_stands_down(self):
        def competing(root):
            other = self.clone_of("fallback")
            head = B.newest_anchor(other)
            when = stamp(self.head_utc + datetime.timedelta(minutes=10))
            payload = {"tick": head["seq"] + 1, "beat_utc": when, "minted_by": "fallback-beat (test)"}
            f = R.build_frame("tick.anchor", B.STREAM, head["seq"] + 1, when, payload, prev=head["payload_hash"])
            chainio.append_frame(other / "ticks", f, B.STREAM)
            sh("git", "add", "ticks", cwd=other)
            sh("git", "commit", "-q", "-m", f"fallback tick {f['seq']}", cwd=other)
            sh("git", "push", "-q", "origin", "HEAD:main", cwd=other)
            return self.fake_world(root, self.at(11)())
        self.assertIsNone(self.beat(11, world=competing))
        _, ticks, oracle_ok, _ = self.published()
        self.assertEqual(len(ticks), self.head_seq + 2, "exactly one new tick, and it is the other writer's")
        self.assertEqual(ticks[-1]["payload"]["minted_by"], "fallback-beat (test)")
        self.assertTrue(oracle_ok)
        self.assertTrue(any(line.startswith("push refused") for line in self.logs), self.logs)

    def test_an_unrelated_commit_meanwhile_is_built_on_never_overwritten(self):
        calls = []

        def unrelated(root):
            calls.append(1)
            if len(calls) == 1:
                other = self.clone_of("witness")
                (other / "unrelated.txt").write_text("somebody else's commit\n")
                sh("git", "add", "unrelated.txt", cwd=other)
                sh("git", "commit", "-q", "-m", "unrelated", cwd=other)
                sh("git", "push", "-q", "origin", "HEAD:main", cwd=other)
            return self.fake_world(root, self.at(11)())
        frame = self.beat(11, world=unrelated)
        self.assertEqual(frame["seq"], self.head_seq + 1)
        reader, ticks, oracle_ok, projection_unchanged = self.published()
        self.assertTrue((reader / "unrelated.txt").exists(), "the other commit must survive: nothing is forced")
        self.assertEqual([t["seq"] for t in ticks[-2:]], [self.head_seq, self.head_seq + 1])
        self.assertTrue(oracle_ok and projection_unchanged)
        subjects = sh("git", "--git-dir", str(self.remote), "log", "-3", "--format=%s", "main", cwd=self.tmp).splitlines()
        self.assertEqual(subjects[1:], ["unrelated", "seed"])

    def test_a_failed_world_refresh_still_publishes_the_tick_and_says_so(self):
        frame = self.beat(11, world=lambda root: "failed")
        reader, ticks, oracle_ok, projection_unchanged = self.published()
        self.assertEqual(ticks[-1]["frame_hash"], frame["frame_hash"])
        self.assertTrue(oracle_ok and projection_unchanged)
        orient = json.loads((reader / "orient.json").read_text())
        self.assertEqual(orient["status"]["world"]["last_refresh"], "failed")
        message = sh("git", "--git-dir", str(self.remote), "log", "-1", "--format=%s", "main", cwd=self.tmp)
        self.assertFalse(message.endswith("+ world"), message)

    def test_a_red_oracle_publishes_nothing(self):
        other = self.clone_of("vandal")
        victim = other / "registry" / "5.json"
        frame = json.loads(victim.read_text())
        frame["payload"]["outlook"] = "edited without re-hashing"
        victim.write_text(json.dumps(frame, indent=2) + "\n")
        sh("git", "commit", "-q", "-am", "an edit the oracle refuses", cwd=other)
        sh("git", "push", "-q", "origin", "HEAD:main", cwd=other)
        before = self.remote_head()
        with self.assertRaises(B.Refused):
            self.beat(11)
        self.assertEqual(self.remote_head(), before)

    def test_an_unmarked_clone_is_never_touched(self):
        sh("git", "config", "--unset", "dogg.primaryBeat", cwd=self.clone)
        (self.clone / "work-in-progress.txt").write_text("somebody's uncommitted work\n")
        with self.assertRaisesRegex(B.Refused, "not marked as a beat clone"):
            self.beat(11)
        self.assertTrue((self.clone / "work-in-progress.txt").exists())

    def test_no_push_commits_locally_and_publishes_nothing(self):
        before = self.remote_head()
        frame = self.beat(11, push=False)
        self.assertEqual(frame["seq"], self.head_seq + 1)
        self.assertEqual(self.remote_head(), before)
        self.assertIn(f"tick {frame['seq']}:", sh("git", "log", "-1", "--format=%s", cwd=self.clone))


if __name__ == "__main__":
    unittest.main(verbosity=2)
