#!/usr/bin/env python3
"""Offline Python/Node bridge contracts; synthetic sources are NOT native-chain proofs."""
import copy
import importlib._bootstrap_external
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import rapp1_bridge as B

R = B.load_reference()
NODE = ROOT / "tools" / "rapp1_recover.mjs"
WORK = Path(os.environ.get("DOGG_BRIDGE_TEST_WORK", ROOT / ".bridge-test-work")).absolute()
REVISION = "1" * 40


class Bridge(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(exist_ok=True)
        self.case = WORK / (self._testMethodName + "-" + uuid.uuid4().hex)
        self.case.mkdir()
        self.source = self.case / "native"
        (self.source / "ticks").mkdir(parents=True)
        self.record = self.source / "ticks" / "7.json"
        self.out = self.case / "snapshot"
        self.frame = {
            "spec": "rapp/1", "kind": "tick.anchor", "stream_id": B.NATIVE_STREAM,
            "seq": 7, "utc": "2026-09-06T12:00:00.000Z",
            "payload": {"tick": 7, "note": "original"}, "payload_hash": "a" * 64,
            "frame_hash": "b" * 64, "prev": "c" * 64, "prev_wave": None, "sig": None,
        }
        self.raw = (json.dumps(self.frame, indent=2) + "\n").encode()
        self.record.write_bytes(self.raw)

    def tearDown(self):
        shutil.rmtree(self.case)

    def export(self, **overrides):
        args = {"source_root": self.source, "record": "ticks/7.json", "revision": REVISION,
                "owner": "local", "slug": "dogg-tick", "out": self.out}
        args.update(overrides)
        return B.export_snapshot(**args)

    def node(self, command="verify", artifact=None, destination=None, script=NODE):
        args = ["node", str(script), command, str(artifact or self.out)]
        if destination is not None:
            args.append(str(destination))
        return subprocess.run(args, cwd=self.case, capture_output=True, text=True, timeout=20)

    def manifest(self):
        return json.loads((self.out / "manifest.json").read_bytes())

    def frame_value(self):
        return json.loads((self.out / "frames" / "0.json").read_bytes())

    def put_manifest(self, value):
        (self.out / "manifest.json").write_bytes(R.canonical(value).encode())

    def put_frame(self, value, rehash=False):
        if rehash:
            value["payload_hash"] = R.H("rapp/1:particle", value["payload"])
            value["frame_hash"] = R.H("rapp/1:wave", {
                key: item for key, item in value.items() if key not in {"frame_hash", "sig"}
            })
        raw = R.canonical(value).encode()
        (self.out / "frames" / "0.json").write_bytes(raw)
        manifest = self.manifest()
        manifest["frame"]["sha256"] = B.sha256(raw)
        manifest["frame"]["frame_hash"] = value["frame_hash"]
        self.put_manifest(manifest)

    def reject_both(self):
        with self.assertRaises((ValueError, OSError, UnicodeError, TypeError)):
            B.verify_artifact(self.out)
        destination = self.case / "must-not-exist"
        result = self.node("recover", destination=destination)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("bridge refused:", result.stderr)
        self.assertFalse(destination.exists(), "invalid transport created a recovery destination")

    def files(self):
        return {p.relative_to(self.out).as_posix(): p.read_bytes()
                for p in self.out.rglob("*") if p.is_file()}

    def test_python_export_node_recovery_exact_raw_numbers_and_unicode(self):
        self.frame["payload"].update({"literal": "NUMBER", "unicode": "snowman ☃",
                                     "inert": "print('source is data, not instructions')"})
        raw = json.dumps(self.frame, ensure_ascii=False, indent=3).replace(
            '"NUMBER"', '[9007199254740993,0.100000000000000005,-0,1E+2,1e-308]',
        ).replace("\n", "\r\n").encode() + b"\r\n"
        self.record.write_bytes(raw)
        self.assertNotEqual(raw, json.dumps(json.loads(raw)).encode())
        exported = self.export()
        self.assertEqual(exported["frames_verified"], 1)
        self.assertEqual(exported["reference_executed_sha256"], B.REFERENCE["rapp_py_sha256"])
        manifest, frame, blob, _ = B.verify_artifact(self.out)
        self.assertEqual(blob, raw)
        self.assertEqual(frame["kind"], "memory.save")
        self.assertEqual(R.stream_form(frame["stream_id"]), "memory-stream")
        self.assertNotEqual(frame["stream_id"], B.NATIVE_STREAM)
        self.assertIsNone(frame["prev"])
        self.assertIsNone(frame["sig"])
        self.assertTrue(R.verify_frame(frame, stream_id_of_record=manifest["stream_id"])[0])
        # Transfer only the closed artifact; remove the source tree before Node starts.
        transferred = self.case / "node-input"
        shutil.copytree(self.out, transferred)
        shutil.rmtree(self.source)
        destination = self.case / "recovered"
        result = self.node("recover", artifact=transferred, destination=destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["frames_verified"], 1)
        self.assertEqual(report["source_sha256"], B.sha256(raw))
        self.assertEqual(report["node_verifier_sha256"], B.sha256(NODE.read_bytes()))
        self.assertEqual((destination / "source.json").read_bytes(), raw)
        self.assertEqual(set(p.name for p in destination.iterdir()), {"source.json", "receipt.json"})

    def test_repeat_is_noop_without_remint_or_rewrite(self):
        first = self.export()
        before = self.files()
        with mock.patch("uuid.uuid4", side_effect=AssertionError("repeat minted identity")):
            second = self.export()
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(first["frame_hash"], second["frame_hash"])
        self.assertEqual(first["stream_id"], second["stream_id"])
        self.assertEqual(before, self.files())

    def test_changed_input_cannot_append_overwrite_or_reparent(self):
        self.export()
        before = self.files()
        self.record.write_bytes(self.raw.replace(b"original", b"modified"))
        with self.assertRaisesRegex(ValueError, "immutable snapshot"):
            self.export()
        self.assertEqual(before, self.files())
        self.record.write_bytes(self.raw)
        for overrides in ({"revision": "2" * 40}, {"owner": "other"}, {"slug": "other"}):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, "immutable snapshot"):
                self.export(**overrides)

    def test_semantically_equal_source_bytes_are_not_silently_normalized(self):
        self.export()
        self.record.write_bytes(json.dumps(json.loads(self.raw), separators=(",", ":")).encode())
        self.assertNotEqual(self.record.read_bytes(), self.raw)
        with self.assertRaisesRegex(ValueError, "immutable snapshot"):
            self.export()
        self.assertEqual(B.verify_artifact(self.out)[2], self.raw)

    def test_reencoded_raw_number_blob_is_not_the_archival_source(self):
        raw = self.raw.replace(b'"note": "original"', b'"number": 9007199254740993.0')
        self.record.write_bytes(raw)
        self.export()
        normalized = json.dumps(json.loads(raw)).encode()
        self.assertIn(b"9007199254740992.0", normalized)
        self.assertNotEqual(raw, normalized)
        blob = self.out / self.manifest()["source"]["blob"]
        blob.write_bytes(normalized)
        self.reject_both()

    def test_explicit_new_target_is_new_local_snapshot_not_native_history(self):
        first = self.export()
        second = self.export(out=self.case / "explicit-second-snapshot")
        self.assertEqual(second["status"], "created-new-local-snapshot")
        self.assertNotEqual(first["stream_id"], second["stream_id"])
        self.assertEqual(first["source_sha256"], second["source_sha256"])
        self.assertEqual(self.record.read_bytes(), self.raw)

    def test_corrupt_and_missing_blob_refuse(self):
        self.export()
        blob = self.out / self.manifest()["source"]["blob"]
        original = blob.read_bytes()
        blob.write_bytes(original.replace(b"original", b"modified"))
        self.reject_both()
        blob.unlink()
        self.reject_both()

    def test_bad_hashes_refuse_in_both_hosts(self):
        self.export()
        original_frame, original_manifest = self.frame_value(), self.manifest()
        for field in ("payload_hash", "frame_hash"):
            with self.subTest(field=field):
                value = copy.deepcopy(original_frame)
                value[field] = "0" * 64
                self.put_frame(value)
                self.reject_both()
        self.put_frame(original_frame)
        for field in ("sha256", "frame_hash"):
            with self.subTest(descriptor=field):
                value = copy.deepcopy(original_manifest)
                value["frame"][field] = "0" * 64
                self.put_manifest(value)
                self.reject_both()

    def test_manifest_reference_pin_and_commit_refuse(self):
        self.export()
        original = self.manifest()
        for key, bad in (("rapp_py_sha256", "0" * 64), ("commit", "0" * 40),
                         ("repository", "https://example.invalid")):
            with self.subTest(key=key):
                changed = copy.deepcopy(original)
                changed["reference"][key] = bad
                self.put_manifest(changed)
                self.reject_both()

    def test_payload_is_bound_to_manifest_provenance(self):
        self.export()
        value = self.frame_value()
        value["payload"]["source"]["revision"] = "2" * 40
        self.put_frame(value, rehash=True)
        self.reject_both()

    def test_payload_boolean_cannot_equal_manifest_integer_across_hosts(self):
        for number, boolean in ((0, False), (1, True)):
            with self.subTest(number=number, boolean=boolean):
                native = copy.deepcopy(self.frame)
                native["seq"] = number
                native["prev"] = None if number == 0 else "c" * 64
                native["payload"]["tick"] = number
                record = f"ticks/{number}.json"
                (self.source / record).write_bytes((json.dumps(native, indent=2) + "\n").encode())
                self.out = self.case / f"snapshot-{number}"
                self.export(record=record)
                B.verify_artifact(self.out)
                self.assertEqual(self.node().returncode, 0)
                changed = self.frame_value()
                changed["payload"]["source"]["native_seq"] = boolean
                self.put_frame(changed, rehash=True)
                self.reject_both()

    def test_unsafe_transport_paths_refuse_before_extraction(self):
        self.export()
        original = self.manifest()
        for key, bad in (("path", "../outside.json"), ("path", "/outside.json"),
                         ("path", "ticks\\7.json"), ("blob", "../outside.json"),
                         ("blob", "/outside.json"), ("blob", "blobs/../outside.json")):
            with self.subTest(key=key, bad=bad):
                value = copy.deepcopy(original)
                value["source"][key] = bad
                self.put_manifest(value)
                self.reject_both()
        value = copy.deepcopy(original)
        value["frame"]["path"] = "../outside.json"
        self.put_manifest(value)
        self.reject_both()

    def test_wire_duplicates_seq_spellings_and_malformed_json_refuse(self):
        self.export()
        location = self.out / "frames" / "0.json"
        raw = location.read_bytes()
        cases = [
            raw.replace(b'"seq":0', b'"seq":0,"seq":0'),
            raw.replace(b'"seq":0', b'"seq":0.0'),
            raw.replace(b'"seq":0', b'"seq":0e0'),
            raw.replace(b'"seq":0', b'"seq":-0'),
            raw.replace(b'"seq":0', b'"seq":true'),
            raw.replace(b'"seq":0', b'"seq":9007199254740993'),
            raw.replace(b'"seq":0', b'"seq":NaN'),
            raw.replace(b'"seq":0', b'"seq":0.000000000000000001'),
            raw + b"\n", raw[:-1], b"\xff" + raw,
            b"\xef\xbb\xbf" + raw,
        ]
        for index, changed in enumerate(cases):
            with self.subTest(case=index):
                location.write_bytes(changed)
                self.reject_both()

    def test_manifest_duplicate_and_noncanonical_members_refuse(self):
        self.export()
        location = self.out / "manifest.json"
        raw = location.read_bytes()
        for changed in (b'{"profile":"dogg-rapp1-bridge/1",' + raw[1:],
                        b" " + raw, raw.replace(b'"profile"', b'"\\u0070rofile"'),
                        b'{"extra":' + b'{"a":' * 20 + b"0" + b"}" * 20 + b"}"):
            with self.subTest(changed=changed[:30]):
                location.write_bytes(changed)
                self.reject_both()

    def test_closed_frame_rules_reject_recomputed_invalid_frames(self):
        self.export()
        original = self.frame_value()
        cases = [
            {"seq": 1}, {"prev": "0" * 64}, {"prev_wave": "0" * 64},
            {"sig": "not-a-signature"}, {"kind": "body.pulse"},
            {"stream_id": B.NATIVE_STREAM}, {"stream_id": "net:bridge"},
            {"utc": "2026-02-30T12:00:00.000Z"}, {"utc": "0000-01-01T00:00:00.000Z"},
            {"extra": None}, {"payload": {}},
        ]
        for change in cases:
            with self.subTest(change=change):
                frame = copy.deepcopy(original)
                frame.update(change)
                self.put_frame(frame, rehash=True)
                self.reject_both()

    def test_profile_identity_types_and_limits_refuse(self):
        self.export()
        original = self.manifest()
        cases = [
            ("rappid", "rappid:@OWNER/dogg:" + "0" * 64),
            ("rappid", "rappid:@" + "a" * 40 + "/dogg:" + "0" * 64),
            ("rappid", "rappid:@local/" + "a" * 101 + ":" + "0" * 64),
            ("rappid", original["rappid"] + "\n"), ("trust", "authenticated"),
            ("source", None), ("frame", {}), ("reference", {}),
        ]
        for key, bad in cases:
            with self.subTest(key=key, bad=bad):
                value = copy.deepcopy(original)
                value[key] = bad
                self.put_manifest(value)
                self.reject_both()
        for key, bad in (("native_seq", True), ("size", 0), ("size", B.MAX_SOURCE + 1),
                         ("native_seq", B.MAX_UINT + 1), ("revision", "main")):
            with self.subTest(source_key=key):
                value = copy.deepcopy(original)
                value["source"][key] = bad
                self.put_manifest(value)
                self.reject_both()

    def test_document_source_blob_and_entry_count_limits(self):
        self.export()
        manifest_raw = (self.out / "manifest.json").read_bytes()
        (self.out / "manifest.json").write_bytes(b" " * (B.MAX_DOCUMENT + 1))
        self.reject_both()
        (self.out / "manifest.json").write_bytes(manifest_raw)
        blob = self.out / self.manifest()["source"]["blob"]
        blob.write_bytes(b"x" * (B.MAX_SOURCE + 1))
        self.reject_both()
        blob.write_bytes(self.raw)
        (self.out / "unexpected").write_bytes(b"not part of this transport")
        self.reject_both()
        (self.out / "unexpected").unlink()
        (self.out / "frames" / "1.json").write_bytes(b"{}")
        self.reject_both()

    def test_export_refuses_unsafe_record_missing_source_and_unsupported_epoch(self):
        for record in ("../ticks/7.json", "/ticks/7.json", "ticks\\7.json",
                       "ticks/07.json", "ticks/../7.json", "ticks/epochs/0.jsonl",
                       "ticks/9007199254740992.json"):
            with self.subTest(record=record), self.assertRaises((ValueError, OSError)):
                self.export(record=record)
            self.assertFalse(self.out.exists())
        self.record.unlink()
        with self.assertRaises(FileNotFoundError):
            self.export()
        self.assertFalse(self.out.exists())

    def test_native_duplicate_malformed_number_depth_and_size_limits(self):
        cases = [
            b"{}", b"", self.raw[:-1] + b"x", b"\xff" + self.raw,
            self.raw.replace(b'"seq": 7', b'"seq": 7, "seq": 7'),
            self.raw.replace(b'"note": "original"', b'"a": 1, "a": 2'),
            self.raw.replace(b'"seq": 7', b'"seq": 7.0'),
            self.raw.replace(b'"seq": 7', b'"seq": 7e0'),
            self.raw.replace(b'"seq": 7', b'"seq": -0'),
            self.raw.replace(b'"seq": 7', b'"seq": 9007199254740993'),
            self.raw.replace(b'"seq": 7', b'"seq": true'),
            self.raw.replace(b'"note": "original"', b'"note": NaN'),
            self.raw.replace(b'"note": "original"', b'"note": 1e309'),
            self.raw.replace(b'"note": "original"', b'"note": ' + b"1" * 129),
            self.raw.replace(b'"note": "original"', b'"note": "' + b"x" * 65537 + b'"'),
            self.raw.replace(b'"note": "original"', b'"note": "\\ud800"'),
            self.raw.replace(b'"note": "original"', b'"note":' + b"[" * 33 + b"0" + b"]" * 33),
            self.raw.replace(b'"note": "original"', b'"note":[' + b"0," * 32768 + b"0]"),
            b" " * (B.MAX_SOURCE + 1),
        ]
        for index, raw in enumerate(cases):
            with self.subTest(case=index), self.assertRaises((ValueError, UnicodeError)):
                self.record.write_bytes(raw)
                self.export()
            self.assertFalse(self.out.exists())

    def test_native_adapter_rejects_foreign_labels_fields_and_seq(self):
        cases = [
            {"stream_id": "world:@kody-w/dogg"}, {"kind": "world.snapshot"},
            {"seq": 8}, {"payload": {"tick": 8}}, {"frame_hash": "bad"},
            {"prev": False}, {"utc": "2026-02-30T12:00:00.000Z"}, {"sig": 123},
        ]
        for change in cases:
            value = copy.deepcopy(self.frame)
            value.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.record.write_bytes(json.dumps(value).encode())
                self.export()
            self.assertFalse(self.out.exists())

    def test_existing_recovery_destinations_never_overwritten(self):
        self.export()
        existing = self.case / "existing"
        existing.mkdir()
        sentinel = existing / "source.json"
        sentinel.write_bytes(b"keep me")
        result = self.node("recover", destination=existing)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b"keep me")
        result = self.node("recover", destination=sentinel)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b"keep me")
        with self.assertRaises((ValueError, OSError)):
            self.export(out=existing)
        self.assertEqual(sentinel.read_bytes(), b"keep me")

    def test_interrupted_export_is_not_a_valid_snapshot_or_repeat(self):
        write = B.write_new
        calls = 0

        def fail_before_manifest(location, raw):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("simulated interrupted write")
            write(location, raw)

        with mock.patch.object(B, "write_new", side_effect=fail_before_manifest):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.export()
        self.assertFalse((self.out / "manifest.json").exists())
        self.reject_both()
        with self.assertRaises((ValueError, OSError)):
            self.export()

    def test_symlink_source_artifact_and_destination_paths_refuse(self):
        real = self.case / "real-source"
        self.record.rename(real)
        self.record.symlink_to(real)
        with self.assertRaises(ValueError):
            self.export()
        self.record.unlink()
        real.rename(self.record)
        self.export()
        blob = self.out / self.manifest()["source"]["blob"]
        blob.unlink()
        blob.symlink_to(self.record)
        self.reject_both()
        blob.unlink()
        blob.write_bytes(self.raw)
        linked = self.case / "linked-root"
        linked.symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError):
            B.verify_artifact(linked)
        self.assertNotEqual(self.node(artifact=linked).returncode, 0)
        result = self.node("recover", destination=linked / "new")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.out / "new").exists())
        result = self.node("recover", destination=linked)
        self.assertNotEqual(result.returncode, 0)

    def test_fifo_source_is_rejected_without_blocking(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO unavailable on this platform")
        self.record.unlink()
        os.mkfifo(self.record)
        with self.assertRaises(ValueError):
            self.export()

    def test_pinned_bytes_ignore_shadow_imports_and_stale_pyc(self):
        copied = self.case / "vendor" / "rapp.py"
        copied.parent.mkdir()
        copied.write_bytes(B.VENDOR.read_bytes())
        evil = compile("raise AssertionError('cached or shadow core executed')", str(copied), "exec")
        info = copied.stat()
        pyc = Path(importlib.util.cache_from_source(str(copied)))
        pyc.parent.mkdir()
        pyc.write_bytes(importlib._bootstrap_external._code_to_timestamp_pyc(
            evil, int(info.st_mtime), info.st_size,
        ))
        with mock.patch.object(B, "VENDOR", copied), mock.patch.dict(
            sys.modules, {"rapp": types.ModuleType("shadow_rapp")},
        ):
            reference = B.load_reference()
            self.assertEqual(reference.__file__, str(copied))
            self.assertEqual(reference.SPEC, "rapp/1")
            self.assertIsNone(reference.stream_form(B.NATIVE_STREAM))
        copied.write_bytes(copied.read_bytes() + b"\nraise AssertionError('must not execute')\n")
        with mock.patch.object(B, "VENDOR", copied), self.assertRaisesRegex(ValueError, "source pin mismatch"):
            B.load_reference()

    def test_node_checks_its_own_vendored_source_pin(self):
        self.export()
        script = self.case / "node-host" / "rapp1_recover.mjs"
        vendor = script.parent / "rapp1_bridge_vendor" / "rapp.py"
        vendor.parent.mkdir(parents=True)
        shutil.copyfile(NODE, script)
        shutil.copyfile(B.VENDOR, vendor)
        self.assertEqual(self.node(script=script).returncode, 0)
        vendor.write_bytes(vendor.read_bytes() + b"\n# corruption\n")
        result = self.node(script=script)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reference source pin mismatch", result.stderr)

    def test_vendored_provenance_and_mit_license_match_exact_bytes(self):
        source = json.loads((B.VENDOR.parent / "SOURCE.json").read_bytes())
        self.assertEqual(source["commit"], B.REFERENCE["commit"])
        self.assertEqual(source["sha256"], B.sha256(B.VENDOR.read_bytes()))
        license_bytes = (B.VENDOR.parent / "LICENSE").read_bytes()
        self.assertEqual(source["license_sha256"], B.sha256(license_bytes))
        self.assertIn(b"MIT License", license_bytes)


if __name__ == "__main__":
    created_work = not WORK.exists()
    try:
        unittest.main(verbosity=2)
    finally:
        if created_work and WORK.exists() and not any(WORK.iterdir()):
            WORK.rmdir()
