#!/usr/bin/env python3
"""Mission registration preserves append-only field indices without duplicate additions."""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import register  # noqa: E402

DIM = "weather:@example/weather"
OTHER = "weather:@example/other"
FIELDS = [
    {"name": "temperature", "path": "weather.temperature", "unit": "C"},
    {"name": "humidity", "path": "weather.humidity", "unit": "%"},
    {"name": "pressure", "path": "weather.pressure", "unit": "hPa"},
]


class MissionRegistration(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix=".register-test-", dir=ROOT)
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        self.path = root / "chants" / "MISSIONS.json"
        self.path.parent.mkdir()
        self.other = {"fields": [FIELDS[0]], "default": ["temperature"]}
        self.document = {"schema": "dogg/0-missions", "missions": {OTHER: self.other}}
        self.path.write_text(json.dumps(self.document) + "\n")
        root_patch = patch.object(register, "ROOT", root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def assert_saved(self, mission):
        expected = {**self.document, "missions": {OTHER: self.other, DIM: mission}}
        self.assertEqual(json.loads(self.path.read_text()), expected)

    def test_new_names_are_added_once_in_first_seen_order(self):
        changed = {**FIELDS[0], "path": "different.temperature", "unit": "F"}
        result = register.fold_mission(
            DIM, [FIELDS[0], changed, FIELDS[1], FIELDS[0], FIELDS[2]])
        self.assertEqual(result, {"fields": FIELDS})
        self.assert_saved(result)

    def test_extension_preserves_existing_fields_and_repeated_import_is_noop(self):
        register.fold_mission(DIM, [FIELDS[0]], default=["temperature"])
        changed = {**FIELDS[0], "path": "different.temperature", "unit": "F"}
        incoming = [FIELDS[2], changed, FIELDS[1]]
        result = register.fold_mission(DIM, incoming)
        self.assertEqual(result, {
            "fields": [FIELDS[0], FIELDS[2], FIELDS[1]], "default": ["temperature"]})
        self.assert_saved(result)
        before = self.path.read_bytes()
        self.assertEqual(register.fold_mission(DIM, incoming), result)
        self.assertEqual(self.path.read_bytes(), before)

    def test_duplicates_do_not_consume_the_twelve_field_capacity(self):
        fields = [{"name": f"field_{i}", "path": f"values.field_{i}"} for i in range(13)]
        incoming = [field for field in fields for _ in range(2)]
        result = register.fold_mission(DIM, incoming)
        self.assertEqual(result, {
            "fields": [{**field, "unit": ""} for field in fields[:12]]})
        self.assert_saved(result)
        self.assertEqual(register.fold_mission(DIM, [FIELDS[0]]), result)
        self.assert_saved(result)

    def test_existing_duplicate_indices_are_never_removed(self):
        existing = [FIELDS[0], FIELDS[0], FIELDS[1]]
        self.document["missions"][DIM] = {"fields": existing}
        self.path.write_text(json.dumps(self.document) + "\n")
        result = register.fold_mission(DIM, [FIELDS[0], FIELDS[2], FIELDS[2]])
        self.assertEqual(result, {"fields": existing + [FIELDS[2]]})
        self.assert_saved(result)


if __name__ == "__main__":
    unittest.main()
