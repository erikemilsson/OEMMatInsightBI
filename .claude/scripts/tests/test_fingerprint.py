#!/usr/bin/env python3
"""End-to-end tests for fingerprint.py via subprocess.

Tests the CLI surface — happy path + key error modes. Covers the FB-039
class of bug (field-name drift between script and schema) by exercising
the dashboard-rollup path against a realistic task JSON.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "fingerprint.py"


class FingerprintCLITests(unittest.TestCase):
    def test_help_flag_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Deterministic hashes", result.stdout)

    def test_no_args_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_spec_hash_deterministic(self):
        """--spec <file> emits sha256:... hash; same content → same hash."""
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("# Test Spec\n\nSome content.\n")
            path = f.name
        try:
            r1 = subprocess.run([sys.executable, str(SCRIPT), "--spec", path],
                                capture_output=True, text=True, timeout=10)
            r2 = subprocess.run([sys.executable, str(SCRIPT), "--spec", path],
                                capture_output=True, text=True, timeout=10)
            self.assertEqual(r1.returncode, 0)
            self.assertTrue(r1.stdout.startswith("sha256:"))
            self.assertEqual(r1.stdout.strip(), r2.stdout.strip())
        finally:
            os.unlink(path)

    def test_sections_emits_per_section_hashes(self):
        """--sections <file> emits a JSON object with one hash per ## section."""
        content = (
            "Preamble\n\n"
            "## Section A\n\nContent A\n\n"
            "## Section B\n\nContent B\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            result = subprocess.run([sys.executable, str(SCRIPT), "--sections", path],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            sections = json.loads(result.stdout)
            self.assertEqual(len(sections), 2)
            self.assertIn("## Section A", sections)
            self.assertIn("## Section B", sections)
            for v in sections.values():
                self.assertTrue(v.startswith("sha256:"))
        finally:
            os.unlink(path)

    def test_dashboard_rollup_reads_id_field(self):
        """--dashboard-rollup reads `id` (not `task_id`) per task-schema.md.

        Regression test for FB-039: prior versions used `data['task_id']`
        which raised KeyError on conformant task JSON files. Catching that
        would surface here — if rollup hashes the empty string for every
        task, two distinct fixtures would collide on output.
        """
        with tempfile.TemporaryDirectory() as task_dir:
            for tid, status in [("1", "Pending"), ("2", "Finished")]:
                with open(os.path.join(task_dir, f"task-{tid}.json"), "w") as f:
                    json.dump({"id": tid, "status": status}, f)
            r1 = subprocess.run([sys.executable, str(SCRIPT), "--dashboard-rollup", task_dir],
                                capture_output=True, text=True, timeout=10)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            self.assertTrue(r1.stdout.startswith("sha256:"))

            # Change one status; hash must change. (If the script silently skipped
            # tasks due to a KeyError, both runs would emit the same empty-string hash.)
            with open(os.path.join(task_dir, "task-2.json"), "w") as f:
                json.dump({"id": "2", "status": "In Progress"}, f)
            r2 = subprocess.run([sys.executable, str(SCRIPT), "--dashboard-rollup", task_dir],
                                capture_output=True, text=True, timeout=10)
            self.assertEqual(r2.returncode, 0)
            self.assertNotEqual(r1.stdout.strip(), r2.stdout.strip())


if __name__ == "__main__":
    unittest.main()
