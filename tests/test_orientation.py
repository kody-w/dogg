#!/usr/bin/env python3
"""Deterministic derived-view contracts; fixtures stay outside immutable native chains."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import orient
import public_data as D
import rapp

WORK = Path(os.environ.get("DOGG_SITE_TEST_WORK", ROOT / ".site-test-work")).absolute()


def write_chain(root, name, stream, items, sealed=0, epoch=2):
    directory = root / name
    directory.mkdir(exist_ok=True)
    frames = []
    for seq, (kind, payload) in enumerate(items):
        frame = rapp.build_frame(kind, stream, seq, f"2026-09-06T13:00:{seq:02d}.000Z",
                                 payload, frames[-1]["payload_hash"] if frames else None)
        frames.append(frame)
    if sealed:
        (directory / "epochs").mkdir(exist_ok=True)
        for index in range(sealed):
            (directory / "epochs" / f"{index}.jsonl").write_text("\n".join(
                json.dumps(frame) for frame in frames[index * epoch:(index + 1) * epoch]) + "\n")
    for frame in frames[sealed * epoch:]:
        (directory / f"{frame['seq']}.json").write_text(json.dumps(frame, indent=2) + "\n")
    (directory / "HEAD.json").write_text(json.dumps({
        "count": len(frames), "stream_id": stream, "head_frame": frames[-1]["frame_hash"],
        "updated": frames[-1]["utc"], "epoch_size": epoch, "sealed_epochs": sealed,
    }))
    return frames


class Orientation(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(exist_ok=True)
        self.root = WORK / (self._testMethodName + "-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.ticks = write_chain(self.root, "ticks", "tick:@kody-w/global",
                                 [("tick.anchor", {"tick": seq}) for seq in range(3)], sealed=1)
        write_chain(self.root, "world", "world:@kody-w/dogg", [
            ("world.snapshot", {"tick": seq, "tick_frame": self.ticks[seq]["frame_hash"],
                                "world": {"value": seq}, "sources_failed": []})
            for seq in range(3)], sealed=1)
        self.registry()

    def registry(self):
        return write_chain(self.root, "registry", "registry:@kody-w/global", [
            ("registry.genesis", {"note": "a registry, not a dimension"}),
            ("registry.dimension", {"dimension": "world:@kody-w/dogg", "repo": "kody-w/dogg", "path": "world/", "outlook": "old"}),
            ("registry.dimension", {"dimension": "world:@kody-w/dogg", "repo": "kody-w/dogg", "path": "world/", "outlook": "new"}),
        ])

    def tearDown(self):
        shutil.rmtree(self.root)

    def generate(self, **kwargs):
        return orient.regenerate(self.root, clock=lambda: "2026-09-06T13:10:00.000Z", **kwargs)

    def test_derived_inputs_update_once_and_check_noop_never_changes_timestamp(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            self.generate(check=True)
        self.assertFalse((self.root / "orient.json").exists())
        state, value = self.generate()
        self.assertEqual(state, "updated")
        self.assertEqual(value["tick"]["seq"], 2)
        self.assertEqual(value["world"]["tick"], 2)
        self.assertEqual(value["status"]["registry"], {"state": "current", "records": 3, "dimensions": 1})
        self.assertEqual(value["dimensions"][0]["outlook"], "new")
        before = (self.root / "orient.json").read_bytes()
        state, again = orient.regenerate(self.root, clock=lambda: self.fail("no-op called the clock"))
        self.assertEqual(state, "unchanged")
        self.assertEqual(again, value)
        self.generate(check=True)
        self.assertEqual((self.root / "orient.json").read_bytes(), before)

    def test_new_tick_marks_old_world_stale_without_rewriting_source(self):
        self.generate()
        world = (self.root / "world/2.json").read_bytes()
        write_chain(self.root, "ticks", "tick:@kody-w/global", [("tick.anchor", {"tick": seq}) for seq in range(4)], sealed=1)
        state, value = self.generate(world_refresh="failed")
        self.assertEqual(state, "updated")
        self.assertEqual(value["world"]["tick"], 2)
        self.assertEqual(value["status"]["world"]["state"], "stale")
        self.assertEqual(value["status"]["world"]["ticks_behind"], 1)
        self.assertEqual(value["status"]["world"]["last_refresh"], "failed")
        self.assertEqual((self.root / "world/2.json").read_bytes(), world)
        self.assertEqual(self.generate()[0], "unchanged")

    def test_missing_world_and_registry_retain_last_good_with_explicit_errors(self):
        _, old = self.generate()
        shutil.rmtree(self.root / "world")
        shutil.rmtree(self.root / "registry")
        _, current = self.generate(world_refresh="failed")
        self.assertEqual(current["world"], old["world"])
        self.assertEqual(current["dimensions"], old["dimensions"])
        self.assertEqual(current["status"]["world"]["state"], "error")
        self.assertTrue(current["status"]["world"]["retained_last_good"])
        self.assertEqual(current["status"]["registry"]["state"], "error")
        self.assertNotIn(str(self.root), json.dumps(current))
        self.assertEqual(self.generate()[0], "unchanged")

    def test_empty_or_corrupt_sources_never_report_success(self):
        _, old = self.generate()
        (self.root / "world/HEAD.json").write_text('{"count":0}')
        _, value = self.generate()
        self.assertEqual(value["status"]["world"]["state"], "error")
        self.assertEqual(value["world"], old["world"])
        before = (self.root / "orient.json").read_bytes()
        (self.root / "ticks/HEAD.json").write_text('{"count":0}')
        with self.assertRaises(ValueError):
            self.generate()
        self.assertEqual((self.root / "orient.json").read_bytes(), before)

    def test_corrupt_derived_cache_is_not_promoted_as_last_good(self):
        self.generate()
        output = self.root / "orient.json"
        value = json.loads(output.read_bytes())
        value["status"] = None
        output.write_text(json.dumps(value))
        self.assertEqual(self.generate()[0], "updated")
        value = json.loads(output.read_bytes())
        value["world"]["data"] = {"unverified": "changed cached data"}
        output.write_text(json.dumps(value))
        shutil.rmtree(self.root / "world")
        _, rebuilt = self.generate()
        self.assertIsNone(rebuilt["world"])
        self.assertFalse(rebuilt["status"]["world"]["retained_last_good"])

    def test_partial_world_is_explicit_and_tick_reference_cannot_be_forged(self):
        write_chain(self.root, "world", "world:@kody-w/dogg", [
            ("world.snapshot", {"tick": 2, "tick_frame": self.ticks[2]["frame_hash"],
                                "world": {}, "sources_failed": ["unavailable-api"]})])
        _, value = self.generate(world_refresh="ok")
        self.assertEqual(value["status"]["world"]["state"], "partial")
        write_chain(self.root, "world", "world:@kody-w/dogg", [
            ("world.snapshot", {"tick": 2, "tick_frame": "0" * 64, "world": {}, "sources_failed": []})])
        self.assertEqual(self.generate()[1]["status"]["world"]["state"], "error")

    def browser_accepts(self, value):
        result = subprocess.run(
            ["node", "--input-type=module", "-e",
             "import {validateOrientation} from './site/data.mjs';"
             "let raw='';for await (const chunk of process.stdin) raw+=chunk;"
             "validateOrientation(JSON.parse(raw));"],
            cwd=ROOT, input=json.dumps(value), text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_stale_world_bad_reference_retains_last_good_and_valid_directory(self):
        _, previous = self.generate()
        for reference in (None, "", "bad", 42):
            with self.subTest(reference=reference):
                write_chain(self.root, "world", "world:@kody-w/dogg", [
                    ("world.snapshot", {"tick": 1, "tick_frame": reference,
                                        "world": {}, "sources_failed": []})])
                _, value = self.generate()
                self.assertEqual(value["status"]["world"]["state"], "error")
                self.assertTrue(value["status"]["world"]["retained_last_good"])
                self.assertEqual(value["world"], previous["world"])
                self.assertEqual(value["dimensions"], previous["dimensions"])
                self.browser_accepts(value)
        write_chain(self.root, "world", "world:@kody-w/dogg", [
            ("world.snapshot", {"tick": 1, "world": {}, "sources_failed": []})])
        _, missing = self.generate()
        self.assertEqual(missing["world"], previous["world"])
        self.assertEqual(missing["status"]["world"]["state"], "error")
        self.browser_accepts(missing)

    def test_stale_world_without_prior_data_is_explicit_error_not_broken_projection(self):
        write_chain(self.root, "world", "world:@kody-w/dogg", [
            ("world.snapshot", {"tick": 1, "tick_frame": None, "world": {}, "sources_failed": []})])
        _, value = self.generate()
        self.assertEqual(value["status"]["world"]["state"], "error")
        self.assertIsNone(value["world"])
        self.assertFalse(value["status"]["world"]["retained_last_good"])
        self.browser_accepts(value)
        write_chain(self.root, "world", "world:@kody-w/dogg", [
            ("world.snapshot", {"tick": 1, "tick_frame": self.ticks[1]["frame_hash"],
                                "world": {}, "sources_failed": []})])
        _, valid = self.generate()
        self.assertEqual(valid["status"]["world"]["state"], "stale")
        self.assertFalse(valid["status"]["world"]["retained_last_good"])
        self.browser_accepts(valid)

    def test_native_epoch_tail_is_full_read_and_reordering_truncation_refuses(self):
        self.assertEqual([frame["seq"] for frame in D.Chain(self.root / "ticks").tail()], [1, 2])
        bundle = self.root / "ticks/epochs/0.jsonl"
        raw = bundle.read_text()
        for changed in ("\n".join(reversed(raw.splitlines())) + "\n", raw.splitlines()[0] + "\n",
                        raw + "{}\n", raw.replace('"seq": 0', '"seq": 0.0')):
            bundle.write_text(changed)
            with self.assertRaises(ValueError):
                D.Chain(self.root / "ticks").tail()

    def test_bounded_native_json_rejects_duplicates_numeric_loss_and_invalid_unicode(self):
        for raw in (b'{"a":1,"a":2}', b'{"seq":0.0}', b'{"seq":0e0}', b'{"seq":-0}',
                    b'{"seq":9007199254740993}', b'{"x":NaN}', b'{}{}', b'{"x":"\\ud800"}',
                    b'{"x":', b"\xff{}", b"[" * 33 + b"0" + b"]" * 33,
                    b" " * (D.MAX_FRAME + 1)):
            with self.subTest(raw=raw[:32]), self.assertRaises((ValueError, UnicodeError)):
                D.strict_json(raw)

    def test_history_cap_and_native_hash_mismatch_refuse(self):
        chain = D.Chain(self.root / "registry")
        with self.assertRaisesRegex(ValueError, "history limit"):
            chain.all(maximum=2)
        value = json.loads((self.root / "ticks/2.json").read_bytes())
        value["payload"]["tick"] = 4
        (self.root / "ticks/2.json").write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            D.Chain(self.root / "ticks").tail()

    def test_source_symlink_and_cumulative_byte_budget_refuse(self):
        folder = self.root / "alias"
        folder.symlink_to(self.root / "ticks", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "directory symlinks"):
            D.Chain(folder)
        chain = D.Chain(self.root / "ticks")
        chain.total_bytes = 8 * 1024 * 1024
        with self.assertRaisesRegex(ValueError, "total byte budget"):
            chain.tail()

    def test_workflows_refresh_even_without_new_tick_and_keep_world_failure_visible(self):
        fallback = (ROOT / ".github/workflows/fallback-beat.yml").read_text()
        self.assertIn("WORLD_REFRESH=failed", fallback)
        self.assertIn('python3 tools/orient.py --world-refresh "$WORLD_REFRESH"', fallback)
        self.assertIn("git add ticks world orient.json", fallback)
        self.assertNotIn("tools/world.py || true", fallback)
        self.assertNotIn("/tmp/", fallback)
        self.assertIn("git diff --cached --quiet", fallback)
        workflow = (ROOT / ".github/workflows/orientation.yml").read_text()
        self.assertIn("branches: [main]", workflow)
        self.assertNotIn("tools/world.py", workflow)
        self.assertNotIn("tools/fallback_beat.py", workflow)


if __name__ == "__main__":
    created_work = not WORK.exists()
    try:
        unittest.main(verbosity=2)
    finally:
        if created_work and WORK.exists() and not any(WORK.iterdir()):
            WORK.rmdir()
