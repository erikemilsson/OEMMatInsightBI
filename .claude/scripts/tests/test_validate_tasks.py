#!/usr/bin/env python3
"""End-to-end tests for validate-tasks.py via subprocess.

Covers happy path + key error modes. Catches the FB-039 class of bug
(field-name drift) by verifying that a fully-conformant task JSON
passes schema validation.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "validate-tasks.py"


def _conformant_task(task_id="1", status="Pending"):
    """Return a task dict that satisfies all REQUIRED_FIELDS in validate-tasks.py."""
    return {
        "id": task_id,
        "title": "Test task",
        "description": "Test description",
        "status": status,
        "difficulty": 3,
        "owner": "claude",
        "dependencies": [],
        "files_affected": [],
    }


class ValidateTasksCLITests(unittest.TestCase):
    def test_help_flag_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Validate task JSON", result.stdout)

    def test_conformant_task_passes(self):
        """Task with all REQUIRED_FIELDS → exit 0, 'Schema: OK'.

        Regression test for FB-039: prior versions had `task_id` in
        REQUIRED_FIELDS instead of `id`, so every conformant task
        emitted a false-positive 'missing required field: task_id'
        error. This test would have caught that.
        """
        with tempfile.TemporaryDirectory() as task_dir:
            with open(os.path.join(task_dir, "task-1.json"), "w") as f:
                json.dump(_conformant_task(), f)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), task_dir],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Schema: OK", result.stdout)

    def test_missing_required_field_reports_error(self):
        """Task missing a required field → exit 1, names the missing field."""
        with tempfile.TemporaryDirectory() as task_dir:
            task = _conformant_task()
            del task["status"]
            with open(os.path.join(task_dir, "task-1.json"), "w") as f:
                json.dump(task, f)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), task_dir],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing required field: status", result.stdout)

    def test_invalid_status_reports_error(self):
        with tempfile.TemporaryDirectory() as task_dir:
            task = _conformant_task(status="MadeUpStatus")
            with open(os.path.join(task_dir, "task-1.json"), "w") as f:
                json.dump(task, f)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), task_dir],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("invalid status", result.stdout)

    def test_verification_debt_finished_without_pass(self):
        """Finished task without task_verification.result == 'pass' → debt entry."""
        with tempfile.TemporaryDirectory() as task_dir:
            task = _conformant_task(status="Finished")
            # No task_verification field → debt
            with open(os.path.join(task_dir, "task-1.json"), "w") as f:
                json.dump(task, f)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), task_dir],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("Verification debt:", result.stdout)
            self.assertIn("task_verification is missing", result.stdout)

    def test_json_flag_emits_parseable_summary(self):
        """--json flag emits a parseable JSON summary."""
        with tempfile.TemporaryDirectory() as task_dir:
            with open(os.path.join(task_dir, "task-1.json"), "w") as f:
                json.dump(_conformant_task(), f)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), task_dir, "--json"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["task_count"], 1)
            self.assertEqual(summary["validation_errors"], {})
            self.assertEqual(summary["verification_debt"], [])

    def test_empty_dir_passes(self):
        """Empty task directory → exit 0, 'Validated 0 task files.'"""
        with tempfile.TemporaryDirectory() as task_dir:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), task_dir],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("Validated 0 task files", result.stdout)


if __name__ == "__main__":
    unittest.main()
