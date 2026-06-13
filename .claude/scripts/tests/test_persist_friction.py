#!/usr/bin/env python3
"""End-to-end tests for persist-friction.py via subprocess.

Covers the happy path plus the failure modes that motivated FB-098:
collision-safe FR-NNN assignment (register ids + textual references),
audit-eligible vs template-only routing, and the missing-source_anchor skip.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "persist-friction.py"
NOW = "2026-06-12T00:00:00Z"


def run(markers, *extra_args, register=None, scan=None):
    args = [sys.executable, str(SCRIPT), "--now", NOW]
    if register is not None:
        args += ["--friction-register", str(register)]
    for s in (scan or []):
        args += ["--scan", str(s)]
    args += list(extra_args)
    payload = markers if isinstance(markers, str) else json.dumps(markers)
    return subprocess.run(args, input=payload, capture_output=True, text=True, timeout=10)


class PersistFrictionCLITests(unittest.TestCase):
    def test_help_flag_exits_zero(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0)
        self.assertIn("collision-safe", r.stdout)

    def test_empty_input_emits_empty_streams(self):
        r = run("")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["markers"], [])
        self.assertEqual(out["register"], [])
        self.assertEqual(out["assigned_ids"], [])

    def test_non_array_input_is_usage_error(self):
        r = run('{"type": "vocab_drift"}')  # object, not array
        self.assertEqual(r.returncode, 2)
        self.assertIn("must be a JSON array", r.stderr)

    def test_invalid_json_is_usage_error(self):
        r = run("not json at all")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not valid JSON", r.stderr)

    def test_audit_eligible_marker_projects_to_register(self):
        """First audit-eligible marker with a source_anchor → FR-001 when register absent."""
        markers = [{
            "type": "path_drift",
            "details": "spec says foundation/coloring/; on-disk is foundation/user/coloring/",
            "source_anchor": "spec_v3.md § 22.2",
            "timestamp": "2026-06-12T11:00:00Z",
            "task_id": "task-42",
            "agent": "verify-agent",
        }]
        with tempfile.TemporaryDirectory() as d:
            reg = Path(d) / "friction.jsonl"  # does not exist yet
            r = run(markers, register=reg)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(len(out["markers"]), 1)
        self.assertEqual(len(out["register"]), 1)
        entry = out["register"][0]
        self.assertEqual(entry["id"], "FR-001")
        self.assertEqual(entry["kind"], "path_drift")
        self.assertEqual(entry["status"], "open")
        self.assertEqual(entry["captured"], "2026-06-12T11:00:00Z")  # marker timestamp wins
        self.assertEqual(entry["source_anchor"], "spec_v3.md § 22.2")
        self.assertEqual(entry["captured_in"], {"agent": "verify-agent", "task": "task-42", "command": "/work"})
        self.assertEqual(out["assigned_ids"], [{"marker_index": 0, "task": "task-42", "id": "FR-001"}])

    def test_template_only_kind_is_not_projected(self):
        """workflow_deviation is NOT audit-eligible → markers only, no register entry."""
        markers = [{"type": "workflow_deviation", "details": "skipped a step", "task_id": "task-9"}]
        r = run(markers)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(len(out["markers"]), 1)
        self.assertEqual(out["register"], [])
        self.assertEqual(out["assigned_ids"], [])

    def test_audit_eligible_missing_anchor_skips_register_with_warning(self):
        markers = [{"type": "terminology_mismatch", "details": "Reference surface vs MyStyle gallery"}]
        r = run(markers)
        self.assertEqual(r.returncode, 0, r.stderr)  # still success
        out = json.loads(r.stdout)
        self.assertEqual(len(out["markers"]), 1)        # dual-write still happens
        self.assertEqual(out["register"], [])           # but no projection
        self.assertIn("source_anchor", r.stderr)        # warned
        self.assertTrue(out["warnings"])

    def test_now_fallback_when_marker_has_no_timestamp(self):
        markers = [{"type": "vocab_drift", "details": "x", "source_anchor": "spec_v1.md § 1"}]
        r = run(markers)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["register"][0]["captured"], NOW)

    def test_collision_safe_against_register_and_textual_refs(self):
        """Next id is one past max(register ids, textual FR-<n> in --scan), not naive register+1.

        Register tops out at FR-005, but a task note already references FR-007.
        Naive max-over-register would assign FR-006 (collision with the dangling
        FR-007 reference). Correct behavior: FR-008.
        """
        with tempfile.TemporaryDirectory() as d:
            reg = Path(d) / "friction.jsonl"
            reg.write_text(
                json.dumps({"id": "FR-003", "kind": "vocab_drift", "status": "open"}) + "\n" +
                json.dumps({"id": "FR-005", "kind": "path_drift", "status": "resolved"}) + "\n",
                encoding="utf-8",
            )
            note = Path(d) / "task-700.json"
            note.write_text('{"notes": "follow-up tracked as FR-007 pending audit"}', encoding="utf-8")
            markers = [{
                "type": "design_contradiction",
                "details": "vision rules out picker chrome but spec prescribes it",
                "source_anchor": "spec_v3.md § 41.4",
            }]
            r = run(markers, register=reg, scan=[note])
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["register"][0]["id"], "FR-008")
        self.assertEqual(out["next_fr_after"], 9)

    def test_multiple_audit_markers_get_sequential_ids(self):
        markers = [
            {"type": "vocab_drift", "details": "a", "source_anchor": "spec.md § 1"},
            {"type": "path_drift", "details": "b", "source_anchor": "spec.md § 2"},
            {"type": "workflow_deviation", "details": "not eligible"},
            {"type": "spec_implementation_gap", "details": "c", "source_anchor": "spec.md § 3"},
        ]
        with tempfile.TemporaryDirectory() as d:
            reg = Path(d) / "friction.jsonl"
            r = run(markers, register=reg)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(len(out["markers"]), 4)                 # all dual-written
        ids = [e["id"] for e in out["register"]]
        self.assertEqual(ids, ["FR-001", "FR-002", "FR-003"])    # the 3 eligible, in order
        self.assertEqual([a["id"] for a in out["assigned_ids"]], ["FR-001", "FR-002", "FR-003"])

    def test_default_task_id_stamped_when_missing(self):
        markers = [{"type": "vocab_drift", "details": "x", "source_anchor": "spec.md § 1"}]
        r = run(markers, "--task-id", "task-555")
        out = json.loads(r.stdout)
        self.assertEqual(out["markers"][0]["task_id"], "task-555")
        self.assertEqual(out["register"][0]["captured_in"]["task"], "task-555")


if __name__ == "__main__":
    unittest.main()
