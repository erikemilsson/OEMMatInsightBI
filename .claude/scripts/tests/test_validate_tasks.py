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

    def test_decisions_pending_array_of_objects_passes(self):
        """FB-129: the optional decisions_pending field (also when empty) is accepted."""
        for value in ([{"title": "Cache layer", "selected": "LRU"}], []):
            with tempfile.TemporaryDirectory() as task_dir:
                task = _conformant_task()
                task["decisions_pending"] = value
                with open(os.path.join(task_dir, "task-1.json"), "w") as f:
                    json.dump(task, f)
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), task_dir],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Schema: OK", result.stdout)

    def test_decisions_pending_wrong_shape_reports_error(self):
        for value in ("DEC-001", {"title": "x"}, ["DEC-001"], [{"title": "x"}, 3]):
            with tempfile.TemporaryDirectory() as task_dir:
                task = _conformant_task()
                task["decisions_pending"] = value
                with open(os.path.join(task_dir, "task-1.json"), "w") as f:
                    json.dump(task, f)
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), task_dir],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 1, repr(value))
                self.assertIn("decisions_pending must be an array of objects", result.stdout)

    # --- FB-135: spec_unmapped + provenance_warnings ---

    def _run(self, tasks, *flags):
        """Run the script on a directory holding `tasks` ({file stem: task dict})."""
        with tempfile.TemporaryDirectory() as task_dir:
            for stem, task in tasks.items():
                with open(os.path.join(task_dir, f"{stem}.json"), "w") as f:
                    json.dump(task, f)
            return subprocess.run([sys.executable, str(SCRIPT), task_dir, *flags],
                                  capture_output=True, text=True, timeout=10)

    def test_spec_unmapped_must_be_boolean(self):
        for value in ("true", 1, None, []):
            task = dict(_conformant_task(), spec_unmapped=value)
            result = self._run({"task-1": task})
            self.assertEqual(result.returncode, 1, repr(value))
            self.assertIn("spec_unmapped must be boolean", result.stdout)
        for value in (True, False):  # positive control
            result = self._run({"task-1": dict(_conformant_task(), spec_unmapped=value)})
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_provenance_warnings_each_reason(self):
        full = dict(spec_section="## Auth", section_fingerprint="sha256:abc")
        tasks = {
            "task-1": dict(_conformant_task("1")),
            "task-2": dict(_conformant_task("2"), spec_section="## Auth"),
            "task-3": dict(_conformant_task("3"), section_fingerprint="sha256:abc"),
            "task-4": dict(_conformant_task("4"), spec_section="  ", section_fingerprint=""),
            "task-5": dict(_conformant_task("5"), spec_unmapped=True, **full),
            # no warning: provenance, unmapped, out of spec, Absorbed, Broken Down
            "task-6": dict(_conformant_task("6"), **full),
            "task-7": dict(_conformant_task("7"), spec_unmapped=True),
            "task-8": dict(_conformant_task("8"), spec_unmapped=True, spec_section="## Auth"),
            "task-9": dict(_conformant_task("9"), out_of_spec=True),
            "task-10": dict(_conformant_task("10", "Absorbed"), absorbed_into="6"),
            "task-11": dict(_conformant_task("11", "Broken Down"), subtasks=["11_1"]),
            # spec_unmapped false is not a marker
            "task-12": dict(_conformant_task("12"), spec_unmapped=False),
        }
        result = self._run(tasks, "--json")
        self.assertEqual(result.returncode, 0, result.stdout)  # warnings never fail the run
        summary = json.loads(result.stdout)
        self.assertEqual(list(summary), ["task_count", "validation_errors", "verification_debt",
                                         "provenance_warnings"])
        self.assertEqual(sorted(summary["provenance_warnings"], key=lambda w: int(w["task_id"])), [
            {"file": "task-1.json", "task_id": "1", "reason": "no spec_section, no section_fingerprint"},
            {"file": "task-2.json", "task_id": "2", "reason": "no section_fingerprint"},
            {"file": "task-3.json", "task_id": "3", "reason": "no spec_section"},
            {"file": "task-4.json", "task_id": "4", "reason": "no spec_section, no section_fingerprint"},
            {"file": "task-5.json", "task_id": "5",
             "reason": "spec_unmapped set on a task with section provenance"},
            {"file": "task-12.json", "task_id": "12", "reason": "no spec_section, no section_fingerprint"},
        ])
        text = self._run(tasks)
        self.assertEqual(text.returncode, 0, text.stdout)
        self.assertIn("Provenance: 5 task(s) without section provenance "
                      "(see /health-check Part 1 check 11); 1 task(s) with spec_unmapped "
                      "set despite section provenance\n", text.stdout)

    def test_provenance_text_line(self):
        full = dict(_conformant_task(), spec_section="## Auth", section_fingerprint="sha256:abc")
        ok = self._run({"task-1": full})
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(ok.stdout.splitlines()[-1], "Provenance: OK")
        missing = self._run({"task-1": _conformant_task("1"), "task-2": _conformant_task("2")})
        self.assertEqual(missing.returncode, 0, missing.stdout)
        self.assertEqual(missing.stdout.splitlines()[-1], "Provenance: 2 task(s) without section "
                         "provenance (see /health-check Part 1 check 11)")
        both = self._run({"task-1": dict(full, spec_unmapped=True)})
        self.assertEqual(both.returncode, 0, both.stdout)
        self.assertEqual(both.stdout.splitlines()[-1],
                         "Provenance: 1 task(s) with spec_unmapped set despite section provenance")
        self.assertEqual(self._run({}).stdout.splitlines()[-1], "Provenance: OK")

    def test_provenance_warnings_leave_a_failing_exit_code_failing(self):
        task = _conformant_task(status="Finished")  # verification debt, and no provenance
        result = self._run({"task-1": task}, "--json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(json.loads(result.stdout)["provenance_warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
