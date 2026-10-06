#!/usr/bin/env python3
"""End-to-end tests for persist-session-export.py via subprocess.

Covers the happy paths plus the failure modes FB-109 mechanizes against:
the never-dot-prefixed destination invariant, slug derivation from
source_project, timestamp parsing from the working filename, the Step 0f
`-recovered` suffix, and the no-op behavior when the inbox is unconfigured.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "persist-session-export.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=10)


def make_export(path: Path, source_project="styler", export_quality="full"):
    path.write_text(json.dumps({
        "export_version": 1,
        "source_project": source_project,
        "template_version": "5.5.0",
        "session_date": "2026-08-12",
        "automated_markers": [],
        "session_metrics": {"tasks_completed": 2, "verification_pass_rate": 1.0,
                            "recovery_events": 0},
        "claude_assessment": {"friction": []},
        "export_quality": export_quality,
    }), encoding="utf-8")
    return path


class PersistSessionExportCLITests(unittest.TestCase):
    def test_help_flag_exits_zero(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0)
        self.assertIn("FB-109", r.stdout)
        self.assertIn("session-export", r.stdout)

    def test_inbox_unconfigured_is_noop_exit_zero(self):
        """Empty template_inbox_path → copied:false, exit 0 (pause never fails)."""
        with tempfile.TemporaryDirectory() as d:
            vj = Path(d) / "version.json"
            vj.write_text(json.dumps({"template_version": "5.5.0",
                                      "template_inbox_path": ""}), encoding="utf-8")
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src)
            r = run("--source", str(src), "--version-json", str(vj))
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertFalse(out["copied"])
            self.assertEqual(out["reason"], "inbox not configured")

    def test_inbox_not_a_directory_is_noop_with_warning(self):
        """Configured but missing inbox dir → no-op + stderr warning, exit 0."""
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "no-such-dir"
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src)
            r = run("--source", str(src), "--inbox", str(inbox))
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertFalse(out["copied"])
            self.assertEqual(out["reason"], "inbox not a directory")
            self.assertIn("not a directory", r.stderr)

    def test_happy_path_copies_with_canonical_name(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src, source_project="styler")
            r = run("--source", str(src), "--inbox", str(inbox))
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertTrue(out["copied"])
            self.assertEqual(out["destination_basename"],
                             "styler-session-export-2026-08-12-1402.json")
            dest = Path(out["destination"])
            self.assertTrue(dest.is_file())
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8"))["source_project"],
                             "styler")

    def test_destination_is_never_dot_prefixed(self):
        """The invariant FB-109 exists to enforce: inbox files are NOT dot-prefixed."""
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src)
            r = run("--source", str(src), "--inbox", str(inbox))
            out = json.loads(r.stdout)
            self.assertFalse(out["destination_basename"].startswith("."))

    def test_slug_derived_kebab_from_source_project(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src, source_project="OEMMatInsightBI")
            r = run("--source", str(src), "--inbox", str(inbox))
            out = json.loads(r.stdout)
            self.assertEqual(out["destination_basename"],
                             "oemmatinsightbi-session-export-2026-08-12-1402.json")

    def test_slug_kebab_handles_spaces_and_punctuation(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src, source_project="My Cool Project (v2)!")
            r = run("--source", str(src), "--inbox", str(inbox))
            out = json.loads(r.stdout)
            self.assertEqual(out["destination_basename"],
                             "my-cool-project-v2-session-export-2026-08-12-1402.json")

    def test_project_slug_override_wins_and_is_kebab_cleaned(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src, source_project="styler")
            r = run("--source", str(src), "--inbox", str(inbox),
                    "--project-slug", "Flirty_Gym")
            out = json.loads(r.stdout)
            self.assertEqual(out["destination_basename"],
                             "flirty-gym-session-export-2026-08-12-1402.json")

    def test_timestamp_parsed_from_source_filename(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-03-07-0915.json"
            make_export(src)
            r = run("--source", str(src), "--inbox", str(inbox))
            out = json.loads(r.stdout)
            self.assertEqual(out["destination_basename"],
                             "styler-session-export-2026-03-07-0915.json")

    def test_timestamp_override_wins(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src)
            r = run("--source", str(src), "--inbox", str(inbox),
                    "--timestamp", "2026-01-02-0304")
            out = json.loads(r.stdout)
            self.assertEqual(out["destination_basename"],
                             "styler-session-export-2026-01-02-0304.json")

    def test_step_0f_recovered_suffix_lands_in_name(self):
        """The Step 0f recovery export carries a -recovered suffix (FB-089).

        Pass the suffix WITHOUT a leading hyphen (the CLI-ergonomic contract);
        the script prepends exactly one.
        """
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402-recovered.json"
            make_export(src, export_quality="recovered")
            r = run("--source", str(src), "--inbox", str(inbox),
                    "--suffix", "recovered")
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertEqual(out["destination_basename"],
                             "styler-session-export-2026-08-12-1402-recovered.json")

    def test_suffix_with_leading_hyen_is_idempotent(self):
        """`--suffix=-recovered` also works (stripped then re-added)."""
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402-recovered.json"
            make_export(src, export_quality="recovered")
            r = run("--source", str(src), "--inbox", str(inbox),
                    "--suffix=-recovered")
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertEqual(out["destination_basename"],
                             "styler-session-export-2026-08-12-1402-recovered.json")

    def test_empty_source_project_falls_back_to_project_slug(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src, source_project="")
            r = run("--source", str(src), "--inbox", str(inbox))
            out = json.loads(r.stdout)
            self.assertEqual(out["destination_basename"],
                             "project-session-export-2026-08-12-1402.json")

    def test_inbox_resolved_from_version_json(self):
        """With no --inbox, the script reads template_inbox_path from version.json."""
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            vj = Path(d) / "version.json"
            vj.write_text(json.dumps({"template_version": "5.5.0",
                                      "template_inbox_path": str(inbox)}), encoding="utf-8")
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src)
            r = run("--source", str(src), "--version-json", str(vj))
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertTrue(out["copied"])
            self.assertTrue(Path(out["destination"]).is_file())

    def test_overwrite_existing_destination_warns_but_succeeds(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src, source_project="styler")
            run("--source", str(src), "--inbox", str(inbox))
            r = run("--source", str(src), "--inbox", str(inbox))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("overwriting", r.stderr)
            out = json.loads(r.stdout)
            self.assertTrue(out["copied"])

    def test_source_not_found_is_runtime_error(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            r = run("--source", str(Path(d) / "missing.json"), "--inbox", str(inbox))
            self.assertEqual(r.returncode, 2)
            self.assertIn("not found", r.stderr)

    def test_source_invalid_json_is_runtime_error(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            src.write_text("not json", encoding="utf-8")
            r = run("--source", str(src), "--inbox", str(inbox))
            self.assertEqual(r.returncode, 2)
            self.assertIn("not valid JSON", r.stderr)

    def test_timestamp_unparseable_and_not_given_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / "export-with-no-timestamp.json"
            make_export(src)
            r = run("--source", str(src), "--inbox", str(inbox))
            self.assertEqual(r.returncode, 2)
            self.assertIn("timestamp", r.stderr)

    def test_bad_timestamp_format_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d) / "inbox"
            inbox.mkdir()
            src = Path(d) / ".session-export-2026-08-12-1402.json"
            make_export(src)
            r = run("--source", str(src), "--inbox", str(inbox),
                    "--timestamp", "2026-8-12-14")
            self.assertEqual(r.returncode, 2)
            self.assertIn("YYYY-MM-DD-HHMM", r.stderr)


if __name__ == "__main__":
    unittest.main()