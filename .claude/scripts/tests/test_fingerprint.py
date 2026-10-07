#!/usr/bin/env python3
"""End-to-end tests for fingerprint.py via subprocess.

Tests the CLI surface — happy path + key error modes. Covers the FB-039
class of bug (field-name drift between script and schema) by exercising
the dashboard-rollup path against a realistic task JSON. compute_drift()
(--drift, FB-128) is also tested directly, with the module loaded by path, and so
are --provenance and --baseline (FB-135), against throwaway git repositories.
"""
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "fingerprint.py"
_spec = importlib.util.spec_from_file_location("fingerprint", SCRIPT)
fp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fp)


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

    # --- DEC-021: --index + --depth 3 (section index + finer ### fingerprinting) ---

    def _write(self, content):
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        f.write(content)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_index_emits_sections_with_line_ranges(self):
        path = self._write(
            "Preamble\n\n## Section A\n\nContent A\n\n## Section B\n\nContent B\n"
        )
        r = subprocess.run([sys.executable, str(SCRIPT), "--index", path],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        idx = json.loads(r.stdout)
        self.assertTrue(idx["spec_fingerprint"].startswith("sha256:"))
        self.assertEqual(idx["section_count"], 2)
        a, b = idx["sections"]
        self.assertEqual(a["heading"], "## Section A")
        self.assertEqual((a["line_start"], a["line_end"]), (3, 6))
        self.assertEqual(b["heading"], "## Section B")
        self.assertEqual((b["line_start"], b["line_end"]), (7, 9))
        self.assertEqual(a["synopsis"], "Content A")
        self.assertTrue(a["fingerprint"].startswith("sha256:"))

    def test_index_fingerprint_matches_sections(self):
        """Per-section index fingerprints equal the --sections (depth 2) values — the
        index and the drift map stay consistent."""
        path = self._write("## Section A\n\nContent A\n\n## Section B\n\nContent B\n")
        ri = subprocess.run([sys.executable, str(SCRIPT), "--index", path],
                            capture_output=True, text=True, timeout=10)
        rs = subprocess.run([sys.executable, str(SCRIPT), "--sections", path],
                            capture_output=True, text=True, timeout=10)
        idx = json.loads(ri.stdout)
        secs = json.loads(rs.stdout)
        for entry in idx["sections"]:
            self.assertEqual(entry["fingerprint"], secs[entry["heading"]])

    def test_index_synopsis_skips_subheadings(self):
        path = self._write("## A\n\n### Sub\n\nProse line\n")
        r = subprocess.run([sys.executable, str(SCRIPT), "--index", path],
                           capture_output=True, text=True, timeout=10)
        idx = json.loads(r.stdout)
        self.assertEqual(idx["sections"][0]["synopsis"], "Prose line")

    def test_sections_depth3_is_additive(self):
        """--depth 3 is a strict superset of --depth 2: identical ## keys AND values,
        plus the ### subsection hashes. (No churn to existing ## fingerprints.)"""
        path = self._write("## A\n\nintro\n\n### A1\n\nx\n\n### A2\n\ny\n")
        r2 = subprocess.run([sys.executable, str(SCRIPT), "--sections", path],
                            capture_output=True, text=True, timeout=10)
        r3 = subprocess.run([sys.executable, str(SCRIPT), "--sections", path, "--depth", "3"],
                            capture_output=True, text=True, timeout=10)
        d2 = json.loads(r2.stdout)
        d3 = json.loads(r3.stdout)
        self.assertEqual(set(d2), {"## A"})
        self.assertEqual(d3["## A"], d2["## A"])  # ## hash UNCHANGED by depth
        self.assertIn("### A1", d3)
        self.assertIn("### A2", d3)
        self.assertNotIn("### A1", d2)

    def test_depth_rejects_invalid_value(self):
        path = self._write("## A\n\nx\n")
        r = subprocess.run([sys.executable, str(SCRIPT), "--sections", path, "--depth", "4"],
                           capture_output=True, text=True, timeout=10)
        self.assertNotEqual(r.returncode, 0)


# --- FB-128: --drift / compute_drift() (plan § Build contract: rule order 1-6) ---

# v1 -> v2: `### Sessions` (inside `## Auth`) and the `## Billing ` body change;
# `## Docs` doesn't. The spec's Billing heading carries a trailing space.
SPEC_V1 = ("# Fixture\n\nPreamble.\n\n"
           "## Auth\n\nLogin rules.\n\n### Tokens\n\nJWT, 1h.\n\n### Sessions\n\n30 min idle.\n\n"
           "## Billing \n\nInvoices monthly.\n\n"
           "## Docs\n\nReadme.\n")
SPEC_V2 = SPEC_V1.replace("30 min idle.", "15 min idle.").replace("monthly", "weekly")
DRIFT_KEYS = {"spec", "spec_fingerprint", "checked", "drifted", "missing", "unmigrated",
              "historical", "unmatched", "no_provenance", "unmapped", "unreadable",
              "unreconciled_sections"}


class DriftTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "tasks").mkdir()
        self.old = self.hashes(SPEC_V1)  # what decomposition recorded
        self.spec(SPEC_V2)

    def hashes(self, text):
        """`## ` + `### ` hashes of a spec text (stripped heading keys), as recorded at
        decomposition with --sections --depth 3."""
        path = self.root / "snapshot.md"
        path.write_text(text, encoding="utf-8")
        try:
            return {k.strip(): v for k, v in fp.hash_sections(path, depth=3).items()}
        finally:
            path.unlink()

    def spec(self, text, name="spec_v1.md"):
        (self.root / name).write_text(text, encoding="utf-8")

    def task(self, id, status="Pending", section=None, fingerprint=None, **kw):
        t = {"id": str(id), "title": f"Task {id}", "status": status, "owner": "claude"}
        if section is not None:
            t.update(spec_section=section, section_fingerprint=fingerprint)
        t.update(kw)
        (self.root / "tasks" / f"task-{id}.json").write_text(json.dumps(t), encoding="utf-8")

    def deferrals(self, data):
        (self.root / "drift-deferrals.json").write_text(json.dumps(data), encoding="utf-8")

    def drift(self):
        return fp.compute_drift(self.root)

    def ids(self, section_entry):
        return [t["id"] for t in section_entry["tasks"]]

    def test_keys_always_present(self):
        d = self.drift()
        self.assertEqual(set(d), DRIFT_KEYS)
        self.assertEqual(d["spec"], "spec_v1")
        self.assertEqual(d["spec_fingerprint"], fp.hash_file(self.root / "spec_v1.md"))

    def test_rule1_absorbed_and_broken_down_skipped(self):
        stale = self.old["## Auth"]
        self.task(1, "Absorbed", "## Auth", stale, absorbed_into="5")
        self.task(2, "Broken Down", "## Auth", stale, subtasks=["2_1"])
        self.task(3, "Absorbed", "## Old name", stale)
        self.task(4, "Broken Down", spec_version="spec_v0")
        d = self.drift()
        self.assertEqual((d["checked"], d["historical"], d["no_provenance"], d["unmatched"]), (0, 0, 0, 0))
        self.assertEqual((d["drifted"], d["missing"], d["unmigrated"]), ([], [], []))
        # positive control: the same stale provenance on a Pending task is flagged
        self.task(5, "Pending", "## Auth", stale)
        self.assertEqual(self.ids(self.drift()["drifted"][0]), ["5"])

    def test_rule1_out_of_spec_skipped(self):
        # A6: an out-of-spec task has no section to drift from
        stale = self.old["## Auth"]
        self.task(1, "Pending", "## Auth", stale, out_of_spec=True)
        self.task(2, "Finished", "## Old name", stale, out_of_spec=True)
        self.task(3, "Pending", "## Old name", stale, out_of_spec=True)
        self.task(4, "Pending", spec_version="spec_v0", out_of_spec=True)
        self.task(5, "Pending", out_of_spec=True)
        d = self.drift()
        self.assertEqual((d["checked"], d["historical"], d["no_provenance"], d["unmatched"]), (0, 0, 0, 0))
        self.assertEqual((d["drifted"], d["missing"], d["unmigrated"]), ([], [], []))
        # positive control: out_of_spec false is checked as usual
        self.task(6, "Pending", "## Auth", stale, out_of_spec=False)
        self.assertEqual(self.ids(self.drift()["drifted"][0]), ["6"])

    def test_rule2_spec_version_number_and_v_forms_name_current_spec(self):
        # A2: "3" and "v3" name spec_v3 (OEMMatInsightBI writes "1"); "2" is older
        (self.root / "spec_v1.md").unlink()
        self.spec(SPEC_V2, "spec_v3.md")
        stale = self.old["## Auth"]
        self.task(1, "Pending", "## Auth", stale, spec_version="3")
        self.task(2, "Pending", "## Auth", stale, spec_version=" v3 ")
        self.task(3, "Pending", "## Auth", stale, spec_version="spec_v3")
        self.task(4, "Finished", "## Auth", stale, spec_version="2")
        self.task(5, "Pending", "## Auth", stale, spec_version="2")
        d = self.drift()
        self.assertEqual(d["spec"], "spec_v3")
        self.assertEqual(self.ids(d["drifted"][0]), ["1", "2", "3"])
        self.assertEqual((d["historical"], d["unmigrated"]), (1, ["5"]))

    def test_rule2_older_spec_version(self):
        stale = self.old["## Auth"]
        self.task(1, "Finished", "## Auth", stale, spec_version="spec_v0")  # historical
        self.task(2, "Pending", "## Auth", stale, spec_version="spec_v0")   # unmigrated
        self.task(3, "Pending", "## Auth", stale)                            # no spec_version = current
        self.task(4, "Pending", "## Auth", stale, spec_version="spec_v1")
        d = self.drift()
        self.assertEqual((d["historical"], d["unmigrated"], d["checked"]), (1, ["2"], 2))
        self.assertEqual(self.ids(d["drifted"][0]), ["3", "4"])

    def test_rule3_no_provenance_never_flagged(self):
        self.task(1, "Pending")
        self.task(2, "Pending", "## Auth", "")
        self.task(3, "Finished", "   ", self.old["## Auth"])
        self.task(4, "Pending", section_fingerprint=self.old["## Auth"])
        d = self.drift()
        self.assertEqual(d["no_provenance"], 4)
        self.assertEqual((d["checked"], d["drifted"], d["missing"]), (0, [], []))

    def test_rule3_spec_unmapped_counted_apart(self):
        # FB-135: only a no-provenance task with spec_unmapped exactly true is `unmapped`
        self.task(1, "Pending", spec_unmapped=True)
        self.task(2, "Finished", "## Auth", "", spec_unmapped=True)
        self.task(3, "Pending", spec_unmapped="true")
        self.task(4, "Pending", spec_unmapped=False)
        self.task(5, "Pending")
        # provenance wins: checked (and drifted) like any task, counted in neither
        self.task(6, "Pending", "## Auth", self.old["## Auth"], spec_unmapped=True)
        d = self.drift()
        self.assertEqual((d["unmapped"], d["no_provenance"], d["checked"]), (2, 3, 1))
        self.assertEqual(self.ids(d["drifted"][0]), ["6"])
        self.assertLess(list(d).index("no_provenance"), list(d).index("unmapped"))
        self.assertEqual(list(d).index("unmapped"), list(d).index("no_provenance") + 1)

    def test_rule4_heading_match_strips_and_accepts_bare_heading(self):
        stale = self.old["## Billing"]  # the spec line is "## Billing " (trailing space)
        self.task(1, "Pending", "## Billing", stale)
        self.task(2, "Pending", "Billing", stale)          # bare heading: "## " prefixed
        self.task(3, "Pending", "  ## Billing  ", stale)
        d = self.drift()
        self.assertEqual(d["checked"], 3)
        self.assertEqual([(s["section"], self.ids(s)) for s in d["drifted"]],
                         [("## Billing", ["1", "2", "3"])])

    def test_rule4_unmatched_finished_counted_open_listed_missing(self):
        stale = self.old["## Auth"]
        self.task(1, "Finished", "## Old name", stale)
        self.task(2, "Finished", "§ 52.1 (x) + § 52.6 (y)", stale)  # free-form
        self.task(3, "Pending", "## Old name", stale)
        self.task(4, "Blocked", " ## Old name ", stale)
        self.task(5, "Pending", "### Nope", stale)  # names no current ### heading
        d = self.drift()
        self.assertEqual((d["unmatched"], d["checked"], d["unreconciled_sections"]), (2, 0, 2))
        self.assertEqual(d["missing"], [
            {"section": "## Old name", "tasks": [
                {"id": "3", "title": "Task 3", "status": "Pending", "owner": "claude"},
                {"id": "4", "title": "Task 4", "status": "Blocked", "owner": "claude"}]},
            {"section": "### Nope", "tasks": [
                {"id": "5", "title": "Task 5", "status": "Pending", "owner": "claude"}]}])

    def test_rule4_unique_subsection_heading_in_sync_or_drifted(self):
        # A1: spec_section names a `### ` heading and carries that subsection's hash
        now = self.hashes(SPEC_V2)
        self.task(1, "Pending", "### Tokens", self.old["### Tokens"])        # unchanged
        self.task(2, "Pending", " ### Sessions ", self.old["### Sessions"])  # changed
        self.task(3, "Finished", "### Sessions", self.old["### Sessions"],
                  spec_subsection="### Sessions", subsection_fingerprint=now["### Sessions"])
        d = self.drift()
        self.assertEqual((d["checked"], d["unmatched"], d["missing"]), (3, 0, []))
        self.assertEqual([(s["section"], s["fingerprint"]) for s in d["drifted"]],
                         [("### Sessions", now["### Sessions"])])
        # subsection_unchanged stays false for a task matched by its ### heading
        self.assertEqual([(t["id"], t["subsection_unchanged"]) for t in d["drifted"][0]["tasks"]],
                         [("2", False), ("3", False)])

    def test_rule4_repeated_subsection_heading_takes_no_match_branch(self):
        text = "## A\n\n### Notes\n\nA.\n\n## B\n\n### Notes\n\nB.\n"
        self.spec(text)
        notes = self.hashes(text)["### Notes"]
        self.task(1, "Finished", "### Notes", notes)
        self.task(2, "Pending", "### Notes", notes)
        d = self.drift()
        self.assertEqual((d["checked"], d["unmatched"], d["drifted"]), (0, 1, []))
        self.assertEqual([(m["section"], self.ids(m)) for m in d["missing"]], [("### Notes", ["2"])])

    def test_rule4_section_heading_matches_before_subsection_heading(self):
        text = "## Setup\n\nSection.\n\n## Other\n\n### Setup\n\nSubsection.\n"
        self.spec(text)
        h = self.hashes(text)
        self.task(1, "Pending", "Setup", h["### Setup"])      # resolves to ## Setup first
        self.task(2, "Pending", "### Setup", h["### Setup"])  # names the subsection: in sync
        d = self.drift()
        self.assertEqual(d["checked"], 2)
        self.assertEqual([(s["section"], self.ids(s)) for s in d["drifted"]], [("## Setup", ["1"])])

    def test_rules5_6_in_sync_vs_drifted(self):
        now = self.hashes(SPEC_V2)
        self.task(1, "Finished", "## Docs", self.old["## Docs"])  # section unchanged
        self.task(2, "Finished", "## Auth", now["## Auth"])       # already refreshed
        self.task(3, "Finished", "## Auth", self.old["## Auth"], owner="human")
        d = self.drift()
        self.assertEqual(d["checked"], 3)
        self.assertEqual(d["drifted"], [{
            "section": "## Auth", "fingerprint": now["## Auth"], "deferred": False,
            "tasks": [{"id": "3", "title": "Task 3", "status": "Finished", "owner": "human",
                       "deferred": False, "subsection_unchanged": False}]}])
        self.assertEqual(d["unreconciled_sections"], 1)

    def test_rule6_subsection_unchanged(self):
        stale = self.old["## Auth"]  # ### Sessions changed, ### Tokens didn't
        self.task(1, "Finished", "## Auth", stale, spec_subsection="### Tokens",
                  subsection_fingerprint=self.old["### Tokens"])
        self.task(2, "Finished", "## Auth", stale, spec_subsection="### Sessions",
                  subsection_fingerprint=self.old["### Sessions"])
        self.task(3, "Finished", "## Auth", stale)
        self.task(4, "Finished", "## Auth", stale, spec_subsection="### Nope",
                  subsection_fingerprint=self.old["### Tokens"])
        self.task(5, "Finished", "## Auth", stale, spec_subsection="### Tokens")
        tasks = self.drift()["drifted"][0]["tasks"]
        self.assertEqual({t["id"]: t["subsection_unchanged"] for t in tasks},
                         {"1": True, "2": False, "3": False, "4": False, "5": False})

    def test_rule6_subsection_resolves_inside_own_section(self):
        # `### Acceptance Criteria` sits under both sections; the flat --depth 3 map
        # keeps B's hash. Only A's intro changes, so A's own criteria are unchanged.
        v1 = ("## A\n\nIntro.\n\n### Acceptance Criteria\n\nA passes.\n\n"
              "## B\n\nIntro.\n\n### Acceptance Criteria\n\nB passes.\n")
        old = self.hashes(v1)
        a_criteria = fp._section_fingerprint(["### Acceptance Criteria\n\nA passes.\n"])
        self.assertNotEqual(a_criteria, old["### Acceptance Criteria"])
        self.task(1, "Finished", "## A", old["## A"], spec_subsection="### Acceptance Criteria",
                  subsection_fingerprint=a_criteria)
        self.task(2, "Finished", "## A", old["## A"], spec_subsection="### Acceptance Criteria",
                  subsection_fingerprint=old["### Acceptance Criteria"])  # B's, from the flat map
        self.spec(v1.replace("Intro.\n\n### Acceptance Criteria\n\nA", "New.\n\n### Acceptance Criteria\n\nA"))
        tasks = self.drift()["drifted"][0]["tasks"]
        self.assertEqual({t["id"]: t["subsection_unchanged"] for t in tasks}, {"1": True, "2": False})

    def two_drifted_auth_tasks(self):
        self.task(1, "Finished", "## Auth", self.old["## Auth"])
        self.task(2, "Pending", "## Auth", self.old["## Auth"])

    def test_deferral_dict_form(self):
        self.two_drifted_auth_tasks()
        self.deferrals({"deferrals": [{"section": "## Auth", "deferred_date": "2026-10-01",
                                       "affected_tasks": []}]})
        d = self.drift()
        self.assertTrue(d["drifted"][0]["deferred"])
        self.assertEqual([t["deferred"] for t in d["drifted"][0]["tasks"]], [True, True])
        self.assertEqual(d["unreconciled_sections"], 0)

    def test_deferral_list_form_with_bare_section(self):
        self.two_drifted_auth_tasks()
        self.deferrals([{"section": " Auth "}])
        d = self.drift()
        self.assertTrue(d["drifted"][0]["deferred"])
        self.assertEqual(d["unreconciled_sections"], 0)

    def test_deferral_affected_tasks_subset(self):
        self.two_drifted_auth_tasks()
        self.deferrals({"deferrals": [{"section": "## Auth", "affected_tasks": ["1"]}]})
        d = self.drift()
        self.assertEqual({t["id"]: t["deferred"] for t in d["drifted"][0]["tasks"]},
                         {"1": True, "2": False})
        self.assertFalse(d["drifted"][0]["deferred"])
        self.assertEqual(d["unreconciled_sections"], 1)

    def test_malformed_or_non_object_deferrals_ignored(self):
        self.two_drifted_auth_tasks()
        for data in ({"deferrals": [42, "## Auth", {"section": 5}, {"affected_tasks": ["1"]}]},
                     {"deferrals": "## Auth"}, "## Auth", 7, None):
            with self.subTest(data=data):
                self.deferrals(data)
                d = self.drift()
                self.assertFalse(d["drifted"][0]["deferred"])
                self.assertEqual(d["unreconciled_sections"], 1)
        (self.root / "drift-deferrals.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.drift()["unreconciled_sections"], 1)

    def test_missing_sections_never_deferred(self):
        self.task(1, "Pending", "## Old name", self.old["## Auth"])
        self.deferrals({"deferrals": [{"section": "## Old name"}]})
        d = self.drift()
        self.assertNotIn("deferred", d["missing"][0])
        self.assertEqual(d["unreconciled_sections"], 1)

    def test_unreadable_and_non_object_task_files(self):
        tasks = self.root / "tasks"
        (tasks / "task-10.json").write_text("{not json", encoding="utf-8")
        (tasks / "task-9.json").write_text("[1, 2]", encoding="utf-8")
        self.task(1, "Pending", "## Auth", self.old["## Auth"])
        d = self.drift()
        self.assertEqual(d["unreadable"], ["task-9.json", "task-10.json"])
        self.assertEqual(d["checked"], 1)

    def test_archive_is_not_a_candidate(self):
        archive = self.root / "tasks" / "archive"
        archive.mkdir()
        (archive / "task-50.json").write_text(json.dumps(
            {"id": "50", "status": "Pending", "spec_section": "## Auth",
             "section_fingerprint": self.old["## Auth"]}), encoding="utf-8")
        d = self.drift()
        self.assertEqual((d["checked"], d["drifted"]), (0, []))

    def test_no_spec_returns_empty_shape(self):
        (self.root / "spec_v1.md").unlink()
        self.task(1, "Pending", "## Auth", self.old["## Auth"])
        (self.root / "tasks" / "task-2.json").write_text("{bad", encoding="utf-8")
        d = self.drift()
        self.assertEqual(set(d), DRIFT_KEYS)
        self.assertEqual((d["spec"], d["spec_fingerprint"]), (None, None))
        for key in ("drifted", "missing", "unmigrated", "unreadable"):
            self.assertEqual(d[key], [], key)
        for key in ("checked", "historical", "unmatched", "no_provenance", "unmapped",
                    "unreconciled_sections"):
            self.assertEqual(d[key], 0, key)

    def test_highest_spec_version_wins(self):
        for n in (2, 9, 10):
            self.spec(SPEC_V2, f"spec_v{n}.md")
        d = self.drift()
        self.assertEqual(d["spec"], "spec_v10")
        self.assertEqual(d["spec_fingerprint"], fp.hash_file(self.root / "spec_v10.md"))

    def test_output_order_is_natural_and_deterministic(self):
        names = ("Zeta", "Alpha", "10 Ten", "9 Nine")
        text = "".join(f"## {h}\n\nv2 {h}\n\n" for h in names)
        old = self.hashes(text.replace("v2", "v1"))
        self.spec(text)
        for i, h in enumerate(names):
            self.task(f"S{i}", "Pending", f"## {h}", old[f"## {h}"])
        for tid in ("10", "T10", "2", "T9", "1_1"):
            self.task(tid, "Pending", "## Alpha", old["## Alpha"])
        d = self.drift()
        self.assertEqual([s["section"] for s in d["drifted"]],
                         ["## 9 Nine", "## 10 Ten", "## Alpha", "## Zeta"])
        self.assertEqual(self.ids(d["drifted"][2]), ["1_1", "2", "10", "S1", "T9", "T10"])
        self.assertEqual(json.dumps(d), json.dumps(self.drift()))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=10)

    def test_cli_exit_codes(self):
        self.task(1, "Pending", "## Auth", self.old["## Auth"])
        ok = self.run_cli("--drift", str(self.root))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout), self.drift())
        with tempfile.TemporaryDirectory() as empty:  # no spec, no tasks: still success
            r = self.run_cli("--drift", empty)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIsNone(json.loads(r.stdout)["spec"])
        self.assertEqual(self.run_cli("--drift", str(self.root / "nope")).returncode, 2)
        self.assertEqual(self.run_cli("--drift").returncode, 2)  # usage error


# --- FB-135: --provenance, --baseline, --baseline --write ---

# A -> B: `## Auth` body and `### Sessions` change, `### Tokens` and `## Docs` don't.
# B -> C: `## Docs` changes and `## Late` is added.
SPEC_A = ("# Fixture\n\n## Auth\n\nLogin rules.\n\n### Tokens\n\nJWT, 1h.\n\n"
          "### Sessions\n\n30 min idle.\n\n## Docs\n\nReadme.\n")
SPEC_B = SPEC_A.replace("Login rules.", "Login rules, v2.").replace("30 min", "15 min")
SPEC_C = SPEC_B.replace("Readme.", "Readme and guide.") + "\n## Late\n\nAdded last.\n"
PROPOSAL_KEYS = ["id", "file", "status", "title", "recorded_section", "action", "spec_section",
                 "section_fingerprint", "reference_date", "reference_field", "commit",
                 "commit_date", "changed_since", "same_day_edit", "reason"]


def section_hashes(text):
    """Stripped heading -> hash for the `## ` and `### ` sections of a spec text."""
    lines = text.splitlines(keepends=True)
    hashes = {k.strip(): v for k, v in fp._hash_section_lines(lines, depth=3).items()}
    return hashes


@unittest.skipUnless(shutil.which("git"), "git not available")
class BaselineTests(unittest.TestCase):
    """A git repository whose spec is committed at chosen dates; the project's
    `.claude` directory is `self.root` (nested two levels down when `nested`)."""
    nested = False

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve()
        self.root = self.repo / "apps" / "site" / ".claude" if self.nested else self.repo / ".claude"
        (self.root / "tasks").mkdir(parents=True)
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")

    def git(self, *args, date=None):
        env = dict(os.environ)
        if date:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
        r = subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
             "-c", "commit.gpgsign=false", *args],
            capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def commit(self, text, day, name="spec_v1.md", hour=12):
        """Write the spec (str, or bytes as is) and commit it on `day`; returns the sha."""
        path = self.root / name
        path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", f"spec {day}",
                 date=f"{day}T{hour:02d}:00:00+0000")
        return self.git("rev-parse", "HEAD")

    def commit_all(self, day, hour=12):
        """Commit whatever is in the work tree (task files included) on `day`."""
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"work {day}", date=f"{day}T{hour:02d}:00:00+0000")
        return self.git("rev-parse", "HEAD")

    def task(self, id, status="Finished", section="## Auth", **kw):
        t = {"id": str(id), "title": f"Task {id}", "status": status, "owner": "claude"}
        if section is not None:
            t["spec_section"] = section
        t.update(kw)
        path = self.root / "tasks" / f"task-{id}.json"
        path.write_text(json.dumps(t, indent=2) + "\n", encoding="utf-8")
        return path

    def baseline(self):
        return fp.compute_baseline(self.root)

    def one(self, id="1"):
        return next(t for t in self.baseline()["tasks"] if t["id"] == str(id))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=30)

    def three_commits(self):
        self.a = self.commit(SPEC_A, "2026-03-01")
        self.b = self.commit(SPEC_B, "2026-03-10")
        self.c = self.commit(SPEC_C, "2026-03-20")

    # -- shape, selection of tasks

    def test_shape_counts_and_which_tasks_get_a_proposal(self):
        self.three_commits()
        self.task(10, completion_date="2026-03-05")
        self.task(2, "Pending", created_date="2026-03-05")
        self.task("2_1", "Pending", "## Nope", created_date="2026-03-05")
        self.task(3, "Finished", "## Nope")
        # never proposed: unmapped, out of spec, skipped statuses, another spec version,
        # and a task that already has provenance
        self.task(4, "Pending", None, spec_unmapped=True)
        self.task(5, "Pending", out_of_spec=True)
        self.task(6, "Absorbed", absorbed_into="2")
        self.task(7, "Broken Down", subtasks=["7_1"])
        self.task(8, "Pending", spec_version="spec_v0")
        self.task(9, "Pending", section_fingerprint="sha256:x")
        (self.root / "tasks" / "task-11.json").write_text("{bad", encoding="utf-8")
        b = self.baseline()
        self.assertEqual(list(b), ["spec", "history", "tasks", "counts"])
        self.assertEqual((b["spec"], b["history"]), ("spec_v1", "git"))
        self.assertEqual([t["id"] for t in b["tasks"]], ["2", "2_1", "3", "10"])
        self.assertEqual(b["counts"], {"stamp_history": 2, "confirm_current": 0,
                                       "needs_section": 1, "report_only": 1})
        for t in b["tasks"]:
            self.assertEqual(list(t), PROPOSAL_KEYS)
        self.assertEqual(fp.compute_drift(self.root)["no_provenance"], 4)  # the same tasks
        ok = self.run_cli("--baseline", str(self.root))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout), b)

    def test_no_spec_and_bad_directory(self):
        self.task(1)
        b = self.baseline()
        self.assertEqual((b["spec"], b["history"], b["tasks"]), (None, "none", []))
        self.assertEqual(set(b["counts"]), set(fp.BASELINE_ACTIONS))
        self.assertEqual(self.run_cli("--baseline", str(self.root / "nope")).returncode, 2)

    # -- rule 1

    def test_rule1_unresolvable_or_blank_section(self):
        self.three_commits()
        self.task(1, "Finished", "§ 5.1 (x)", completion_date="2026-03-05")
        self.task(2, "On Hold", "## Old name", created_date="2026-03-05")
        self.task(3, "Finished", None)
        self.task(4, "Pending", "   ")
        self.task(5, "Pending", "### Nope")
        got = {t["id"]: t for t in self.baseline()["tasks"]}
        self.assertEqual({i: t["action"] for i, t in got.items()},
                         {"1": "report_only", "2": "needs_section", "3": "report_only",
                          "4": "needs_section", "5": "needs_section"})
        self.assertEqual({i: t["reason"] for i, t in got.items()},
                         {"1": fp.REASON_UNRESOLVED, "2": fp.REASON_UNRESOLVED,
                          "3": fp.REASON_NO_SECTION, "4": fp.REASON_NO_SECTION,
                          "5": fp.REASON_UNRESOLVED})
        for t in got.values():
            self.assertEqual((t["spec_section"], t["section_fingerprint"], t["commit"],
                              t["commit_date"], t["changed_since"], t["same_day_edit"]),
                             (None, None, None, None, False, False))
        self.assertEqual((got["1"]["recorded_section"], got["3"]["recorded_section"]),
                         ("§ 5.1 (x)", None))

    # -- rule 3: stamp_history

    def test_stamp_history_takes_the_newest_commit_on_or_before_the_date(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")            # at A; Auth changed in B
        self.task(2, completion_date="2026-03-15")            # at B; Auth unchanged since
        self.task(3, section="## Docs", completion_date="2026-03-05")  # at A; changed in C
        self.task(4, section="## Docs", completion_date="2026-04-01")  # at C
        got = {t["id"]: t for t in self.baseline()["tasks"]}
        a, b, c = section_hashes(SPEC_A), section_hashes(SPEC_B), section_hashes(SPEC_C)
        self.assertEqual(
            {i: (t["action"], t["section_fingerprint"], t["commit"], t["commit_date"],
                 t["changed_since"], t["same_day_edit"], t["reason"]) for i, t in got.items()},
            {"1": ("stamp_history", a["## Auth"], self.a, "2026-03-01", True, False, ""),
             "2": ("stamp_history", b["## Auth"], self.b, "2026-03-10", False, False, ""),
             "3": ("stamp_history", a["## Docs"], self.a, "2026-03-01", True, False, ""),
             "4": ("stamp_history", c["## Docs"], self.c, "2026-03-20", False, False, "")})
        self.assertEqual(got["1"]["reference_date"], "2026-03-05")

    def test_bare_heading_is_normalised_to_the_real_heading(self):
        self.three_commits()
        self.task(1, section="Auth", completion_date="2026-03-05")
        self.task(2, section="  ## Docs ", completion_date="2026-03-05")
        got = {t["id"]: t for t in self.baseline()["tasks"]}
        self.assertEqual((got["1"]["recorded_section"], got["1"]["spec_section"]), ("Auth", "## Auth"))
        self.assertEqual((got["2"]["recorded_section"], got["2"]["spec_section"]), ("  ## Docs ", "## Docs"))
        self.assertEqual(got["1"]["section_fingerprint"], section_hashes(SPEC_A)["## Auth"])

    def test_subsection_heading_is_stamped_with_the_subsection_hash(self):
        self.three_commits()
        self.task(1, section="### Sessions", completion_date="2026-03-05")
        self.task(2, section="### Tokens", completion_date="2026-03-05")
        got = {t["id"]: t for t in self.baseline()["tasks"]}
        a = section_hashes(SPEC_A)
        self.assertEqual((got["1"]["spec_section"], got["1"]["section_fingerprint"],
                          got["1"]["changed_since"]), ("### Sessions", a["### Sessions"], True))
        self.assertEqual((got["2"]["section_fingerprint"], got["2"]["changed_since"]),
                         (a["### Tokens"], False))

    def test_current_hash_is_the_working_file_even_with_uncommitted_edits(self):
        self.three_commits()
        (self.root / "spec_v1.md").write_text(SPEC_C.replace("Login rules, v2.", "Uncommitted."),
                                              encoding="utf-8")
        self.task(1, completion_date="2026-04-01")
        t = self.one()
        self.assertEqual((t["action"], t["commit"], t["changed_since"]), ("stamp_history", self.c, True))
        self.assertEqual(t["section_fingerprint"], section_hashes(SPEC_C)["## Auth"])

    def test_crlf_spec_hashes_the_same_at_a_commit_as_in_the_working_file(self):
        crlf = SPEC_A.replace("\n", "\r\n").encode("utf-8")
        self.commit(crlf, "2026-03-01")
        self.assertEqual((self.root / "spec_v1.md").read_bytes(), crlf)
        self.task(1, completion_date="2026-03-05")
        self.task(2, section="### Tokens", completion_date="2026-03-05")
        for t in self.baseline()["tasks"]:
            self.assertEqual((t["action"], t["changed_since"]), ("stamp_history", False), t["id"])
        self.assertEqual(self.one()["section_fingerprint"], section_hashes(SPEC_A)["## Auth"])

    def test_each_commit_is_read_once(self):
        self.three_commits()
        for i in range(1, 9):
            self.task(i, section=("## Auth", "## Docs")[i % 2], completion_date="2026-03-10")
        calls = []
        real = fp._git

        def counting(cwd, *args):
            calls.append(args[0])
            return real(cwd, *args)
        fp._git = counting
        self.addCleanup(setattr, fp, "_git", real)
        self.assertEqual(self.baseline()["counts"]["stamp_history"], 8)
        # 8 tasks, 2 sections, both commits of the comparison (B, and A before it); the
        # spec's log, plus one log per task that hit a same-day difference (the 4 Auth
        # tasks: their files are untracked, so the second log is never run)
        self.assertEqual((calls.count("show"), calls.count("log")), (2, 1 + 4))

    # -- reference date

    def test_reference_date_per_status_and_fallbacks(self):
        self.three_commits()
        dates = dict(completion_date="2026-03-02", updated_date="2026-03-12", created_date="2026-03-22")
        self.task(1, "Finished", **dates)
        self.task(2, "Finished", task_verification={"result": "pass", "timestamp": "2026-03-12T10:00:00Z"},
                  updated_date="2026-03-14", created_date="2026-03-02")
        self.task(3, "Finished", completion_date="  ", task_verification={"timestamp": None},
                  updated_date="2026-03-12", created_date="2026-03-22")
        self.task(4, "Finished", updated_date="2026-03-12")  # updated_date is never used
        self.task(12, "Finished", task_verification="pass", created_date="2026-03-22")
        for i, status in enumerate(("Pending", "In Progress", "Awaiting Verification", "Blocked",
                                    "On Hold"), start=5):
            self.task(i, status, **dates)
        self.task(10, "Pending", completion_date="2026-03-02", updated_date="2026-03-12")
        self.task(11, "Finished", completion_date="2026-03-12T09:30:00Z")
        got = {t["id"]: (t["reference_date"], t["reference_field"]) for t in self.baseline()["tasks"]}
        self.assertEqual(got, {
            "1": ("2026-03-02", "completion_date"),
            "2": ("2026-03-12", "task_verification.timestamp"),
            "3": ("2026-03-22", "created_date"), "4": (None, None),
            "12": ("2026-03-22", "created_date"),
            "5": ("2026-03-22", "created_date"), "6": ("2026-03-22", "created_date"),
            "7": ("2026-03-22", "created_date"), "8": ("2026-03-22", "created_date"),
            "9": ("2026-03-22", "created_date"), "10": (None, None),
            "11": ("2026-03-12", "completion_date")})

    def test_unparseable_date_is_no_reference_date(self):
        self.three_commits()
        for i, value in enumerate(("26 Aug 2026", "2026-13-01", "2026-02-30", "20260305",
                                   "2026-3-5", 20260305, "2026-W10-1"), start=1):
            # no fallback to a later field once a field is set
            self.task(i, completion_date=value, created_date="2026-03-12")
        for t in self.baseline()["tasks"]:
            self.assertEqual((t["action"], t["reason"], t["reference_date"], t["reference_field"]),
                             ("confirm_current", fp.REASON_NO_DATE, None, None), t["id"])
        # positive control: the same task with a real date is stamped from history
        self.task(1, completion_date="2026-03-05")
        self.assertEqual(self.one()["action"], "stamp_history")

    # -- rule 2: confirm_current, every reason

    def assert_confirm(self, t, reason, text, heading="## Auth"):
        self.assertEqual((t["action"], t["reason"], t["spec_section"], t["section_fingerprint"],
                          t["commit"], t["commit_date"], t["changed_since"], t["same_day_edit"]),
                         ("confirm_current", reason, heading, section_hashes(text)[heading],
                          None, None, False, False))

    def test_confirm_current_spec_untracked(self):
        self.git("commit", "-q", "--allow-empty", "-m", "root", date="2026-03-01T12:00:00+0000")
        (self.root / "spec_v1.md").write_text(SPEC_B, encoding="utf-8")
        self.task(1, completion_date="2026-03-05")
        self.assertEqual(self.baseline()["history"], "none")
        self.assert_confirm(self.one(), fp.REASON_NO_HISTORY, SPEC_B)

    def test_confirm_current_directory_not_in_a_git_work_tree(self):
        with tempfile.TemporaryDirectory() as plain:
            inside = subprocess.run(["git", "-C", plain, "rev-parse", "--is-inside-work-tree"],
                                    capture_output=True, text=True)
            if inside.returncode == 0:
                self.skipTest("the temp directory is inside a git work tree")
            root = Path(plain)
            (root / "tasks").mkdir()
            (root / "spec_v1.md").write_text(SPEC_B, encoding="utf-8")
            (root / "tasks" / "task-1.json").write_text(json.dumps(
                {"id": "1", "status": "Finished", "spec_section": "Auth",
                 "completion_date": "2026-03-05"}), encoding="utf-8")
            b = fp.compute_baseline(root)
            self.assertEqual((b["history"], b["counts"]["confirm_current"]), ("none", 1))
            self.assert_confirm(b["tasks"][0], fp.REASON_NO_HISTORY, SPEC_B)

    def test_confirm_current_no_reference_date(self):
        self.three_commits()
        self.task(1, "Pending")
        self.assert_confirm(self.one(), fp.REASON_NO_DATE, SPEC_C)

    def test_confirm_current_no_commit_on_or_before_the_date(self):
        self.three_commits()
        self.task(1, completion_date="2026-02-28", spec_version="spec_v1")
        self.assert_confirm(self.one(), fp.REASON_NO_COMMIT, SPEC_C)
        # positive control: the first commit's day
        self.task(1, completion_date="2026-03-01", spec_version="spec_v1")
        self.assertEqual((self.one()["action"], self.one()["commit"]), ("stamp_history", self.a))

    def test_confirm_current_task_without_spec_version_may_predate_the_spec_file(self):
        # spec_v1 is rewritten into spec_v2.md, first committed on 03-10
        self.commit(SPEC_A, "2026-03-01")
        self.git("mv", str(self.root / "spec_v1.md"), str(self.root / "spec_v2.md"))
        first = self.commit(SPEC_B, "2026-03-10", name="spec_v2.md")
        self.commit(SPEC_C, "2026-03-20", name="spec_v2.md")
        self.task(1, completion_date="2026-03-05")                        # before the file's history
        self.task(2, completion_date="2026-03-10")                        # on its first commit's day
        self.task(3, completion_date="2026-03-10", spec_version="  ")
        self.task(4, completion_date="2026-03-11")                        # younger than the file
        self.task(5, completion_date="2026-03-10", spec_version="spec_v2")  # says which spec
        self.task(6, completion_date="2026-03-05", spec_version="v2")
        got = {t["id"]: t for t in self.baseline()["tasks"]}
        for i in "123":
            self.assert_confirm(got[i], fp.REASON_MAY_PREDATE, SPEC_C)
        for i in "45":
            self.assertEqual((got[i]["action"], got[i]["commit"]), ("stamp_history", first), i)
        self.assert_confirm(got["6"], fp.REASON_NO_COMMIT, SPEC_C)

    def test_confirm_current_section_not_in_the_spec_at_the_commit(self):
        self.three_commits()
        self.task(1, section="## Late", completion_date="2026-03-15")  # added in C
        self.assert_confirm(self.one(), fp.REASON_NOT_AT_COMMIT, SPEC_C, "## Late")

    def test_confirm_current_subsection_not_unique_at_the_commit(self):
        twice = SPEC_A + "\n## Other\n\n### Tokens\n\nOther tokens.\n"
        self.commit(twice, "2026-03-01")
        self.commit(SPEC_A, "2026-03-10")
        self.task(1, section="### Tokens", completion_date="2026-03-05")
        self.assert_confirm(self.one(), fp.REASON_NOT_AT_COMMIT, SPEC_A, "### Tokens")
        self.task(1, section="### Tokens", completion_date="2026-03-12")  # positive control
        self.assertEqual(self.one()["action"], "stamp_history")

    def test_confirm_current_spec_not_utf8_at_the_commit(self):
        self.commit(b"## Auth\n\n\xff\xfe broken\n", "2026-03-01")
        self.commit(SPEC_B, "2026-03-10")
        self.task(1, completion_date="2026-03-05")
        self.assert_confirm(self.one(), fp.REASON_UNREADABLE, SPEC_B)

    def test_confirm_current_spec_deleted_at_the_commit(self):
        self.commit(SPEC_A, "2026-03-01")
        self.git("rm", "-q", str(self.root / "spec_v1.md"))
        self.git("commit", "-q", "-m", "drop", date="2026-03-05T12:00:00+0000")
        self.commit(SPEC_B, "2026-03-10")
        self.task(1, completion_date="2026-03-06")
        self.assert_confirm(self.one(), fp.REASON_NOT_AT_COMMIT, SPEC_B)

    # -- the same-day rule

    def test_same_day_section_edited_that_day_takes_the_earlier_commit(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-10")  # B, committed that day, changed ## Auth
        t = self.one()
        self.assertEqual((t["action"], t["commit"], t["commit_date"], t["same_day_edit"], t["reason"]),
                         ("stamp_history", self.a, "2026-03-01", True, ""))
        self.assertEqual(t["section_fingerprint"], section_hashes(SPEC_A)["## Auth"])
        self.assertTrue(t["changed_since"])

    def test_same_day_section_not_edited_that_day_keeps_that_days_commit(self):
        self.three_commits()
        self.task(1, section="## Docs", completion_date="2026-03-10")   # B left ## Docs alone
        self.task(2, section="### Tokens", completion_date="2026-03-10")
        for t in self.baseline()["tasks"]:
            self.assertEqual((t["action"], t["commit"], t["same_day_edit"]),
                             ("stamp_history", self.b, False), t["id"])

    def test_same_day_several_commits_compare_with_the_day_before(self):
        a = self.commit(SPEC_A, "2026-03-01")
        self.commit(SPEC_B, "2026-03-10", hour=9)
        back = self.commit(SPEC_A, "2026-03-10", hour=15)  # edited twice, back to A's text
        self.task(1, completion_date="2026-03-10")
        t = self.one()
        self.assertEqual((t["commit"], t["same_day_edit"]), (back, False))
        self.assertNotEqual(a, back)

    def test_same_day_spec_first_committed_on_the_reference_date(self):
        only = self.commit(SPEC_A, "2026-03-10")
        self.commit(SPEC_B, "2026-03-20")
        self.task(1, completion_date="2026-03-10", spec_version="spec_v1")
        t = self.one()
        self.assertEqual((t["action"], t["commit"], t["same_day_edit"], t["changed_since"]),
                         ("stamp_history", only, False, True))

    def test_same_day_history_starting_that_day_compares_with_its_oldest_commit(self):
        first = self.commit(SPEC_A, "2026-03-10", hour=9)
        self.commit(SPEC_B, "2026-03-10", hour=15)
        self.task(1, completion_date="2026-03-10", spec_version="spec_v1")
        self.task(2, section="## Docs", completion_date="2026-03-10", spec_version="spec_v1")
        got = {t["id"]: t for t in self.baseline()["tasks"]}
        self.assertEqual((got["1"]["commit"], got["1"]["same_day_edit"]), (first, True))
        self.assertFalse(got["2"]["same_day_edit"])

    def test_same_day_section_added_that_day_keeps_that_days_commit(self):
        self.three_commits()
        self.task(1, section="## Late", completion_date="2026-03-20")  # C added it
        t = self.one()
        self.assertEqual((t["action"], t["commit"], t["same_day_edit"]), ("stamp_history", self.c, False))

    # -- same-day exceptions from git evidence: (a) own edit, (b) filed after, (c) neither

    SPEC_B2 = SPEC_B.replace("Login rules, v2.", "Login rules, v3.")

    def same_day(self, id="1"):
        t = self.one(id)
        self.assertEqual((t["action"], t["same_day_edit"]), ("stamp_history", True), id)
        return t["commit"], t["reason"], t["section_fingerprint"], t["changed_since"]

    def test_same_day_own_spec_edit_takes_the_commit_that_touches_the_task_file(self):
        a = self.commit(SPEC_A, "2026-03-01")
        spec = [".claude/spec_v1.md", "src/app.py"]
        self.task(1, completion_date="2026-03-10", files_affected=spec)
        self.task(2, completion_date="2026-03-10", files_affected=["src/app.py"])  # not its edit
        self.task(3, completion_date="2026-03-10", files_affected=spec)  # not in the spec commit
        self.commit_all("2026-03-05")
        self.task(1, completion_date="2026-03-10", files_affected=spec, notes="done")
        self.task(2, completion_date="2026-03-10", files_affected=["src/app.py"], notes="done")
        b = self.commit(SPEC_B, "2026-03-10")  # the spec edit, with tasks 1 and 2
        now = section_hashes(SPEC_B)["## Auth"]
        self.assertEqual(self.same_day("1"), (b, "own spec edit", now, False))
        self.assertEqual(self.one("1")["commit_date"], "2026-03-10")
        before = section_hashes(SPEC_A)["## Auth"]
        self.assertEqual(self.same_day("2"), (a, "", before, True))
        self.assertEqual(self.same_day("3"), (a, "", before, True))

    def test_same_day_own_spec_edit_takes_the_oldest_commit_touching_the_task_file(self):
        """A later same-day spec commit that also touches the task file may be someone
        else's edit plus housekeeping, so the oldest one is the task's own: a wrong
        pick then reads as drift, never as in sync."""
        self.commit(SPEC_A, "2026-03-01")
        kw = dict(completion_date="2026-03-10", files_affected=["spec_v1.md"])
        self.task(1, **kw)
        self.commit_all("2026-03-05")
        self.task(1, notes="own edit", **kw)
        first = SPEC_B.replace("v2", "v1.5")
        own = self.commit(first, "2026-03-10", hour=8)
        self.task(1, notes="touched again", **kw)
        self.commit(SPEC_B, "2026-03-10", hour=9)         # another edit that touches the file
        self.commit(self.SPEC_B2, "2026-03-10", hour=15)  # a later edit, without the task
        # the later same-day edits show as a change since the task
        self.assertEqual(self.same_day(), (own, "own spec edit", section_hashes(first)["## Auth"], True))

    def test_same_day_task_first_committed_as_finished_is_not_filed_after(self):
        """A task done before the edit whose file enters git later (a bulk commit, a
        rename) is no evidence that it was written after the edit: earlier commit."""
        a = self.commit(SPEC_A, "2026-03-01")
        self.commit(SPEC_B, "2026-03-10", hour=18)
        self.task(1, completion_date="2026-03-10")          # Finished, committed days later
        self.task(2, "Pending", created_date="2026-03-10")  # control: open at first commit
        self.commit_all("2026-03-20")
        self.assertEqual(self.same_day("1"), (a, "", section_hashes(SPEC_A)["## Auth"], True))
        self.assertEqual(self.same_day("2")[1], "task filed after the edit")

    def test_same_day_task_filed_after_the_edit_takes_that_days_commit(self):
        a = self.commit(SPEC_A, "2026-03-01")
        self.task(2, "Pending", created_date="2026-03-10")
        self.commit_all("2026-03-05")                       # task 2 is in git before the edit
        edit = self.commit(SPEC_B, "2026-03-10", hour=9)
        self.task(1, "Pending", created_date="2026-03-10")
        self.commit_all("2026-03-10", hour=11)              # task 1 enters git after it
        self.task(3, "Pending", created_date="2026-03-10")
        last = self.commit(self.SPEC_B2, "2026-03-10", hour=15)  # task 3 enters git in this one
        self.task(4, "Pending", created_date="2026-03-10")
        self.commit_all("2026-03-12")                       # days later: after every edit of the day
        b, b2 = section_hashes(SPEC_B)["## Auth"], section_hashes(self.SPEC_B2)["## Auth"]
        self.assertEqual(self.same_day("1"), (edit, "task filed after the edit", b, True))
        self.assertEqual(self.same_day("2"), (a, "", section_hashes(SPEC_A)["## Auth"], True))
        self.assertEqual(self.same_day("3"), (last, "task filed after the edit", b2, False))
        self.assertEqual(self.same_day("4"), (last, "task filed after the edit", b2, False))

    def test_same_day_untracked_or_ignored_task_file_takes_the_earlier_commit(self):
        (self.root / ".gitignore").write_text("tasks/\n", encoding="utf-8")
        a = self.commit(SPEC_A, "2026-03-01")
        self.commit(SPEC_B, "2026-03-10")
        self.task(1, completion_date="2026-03-10", files_affected=[".claude/spec_v1.md"])
        self.assertEqual(self.git("ls-files", "--", str(self.root / "tasks")), "")
        self.assertEqual(self.same_day(), (a, "", section_hashes(SPEC_A)["## Auth"], True))

    # -- which history is read

    def test_side_branch_spec_edit_is_dated_by_its_merge(self):
        self.commit(SPEC_A, "2026-03-01")
        main = self.git("symbolic-ref", "--short", "HEAD")
        self.git("checkout", "-q", "-b", "feat")
        self.commit(SPEC_B, "2026-03-05")                                 # edits ## Auth
        self.git("checkout", "-q", main)
        on_main = self.commit(SPEC_A.replace("Readme.", "Readme and guide."), "2026-03-04")
        self.git("merge", "-q", "--no-ff", "feat", "-m", "merge", date="2026-03-20T12:00:00+0000")
        merge = self.git("rev-parse", "HEAD")
        self.assertIn("Login rules, v2.", (self.root / "spec_v1.md").read_text(encoding="utf-8"))
        self.task(1, completion_date="2026-03-10")   # main still had A's ## Auth that day
        self.task(2, completion_date="2026-03-21")
        got = {t["id"]: t for t in self.baseline()["tasks"]}
        self.assertEqual((got["1"]["commit"], got["1"]["section_fingerprint"], got["1"]["changed_since"]),
                         (on_main, section_hashes(SPEC_A)["## Auth"], True))
        self.assertEqual((got["2"]["commit"], got["2"]["commit_date"], got["2"]["changed_since"]),
                         (merge, "2026-03-20", False))

    def test_commits_are_dated_by_committer_date(self):
        a = self.commit(SPEC_A, "2026-03-01")
        (self.root / "spec_v1.md").write_text(SPEC_B, encoding="utf-8")
        self.git("add", "-A")
        env = dict(os.environ, GIT_AUTHOR_DATE="2026-03-02T12:00:00+0000",
                   GIT_COMMITTER_DATE="2026-03-12T12:00:00+0000")
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "-c", "commit.gpgsign=false", "commit", "-q", "-m", "rebased"],
                       check=True, env=env, capture_output=True)
        b = self.git("rev-parse", "HEAD")
        self.task(1, completion_date="2026-03-05")   # after the author date, before the committer date
        self.task(2, completion_date="2026-03-15")
        got = {t["id"]: (t["commit"], t["commit_date"]) for t in self.baseline()["tasks"]}
        self.assertEqual(got, {"1": (a, "2026-03-01"), "2": (b, "2026-03-12")})

    def test_archived_task_is_neither_proposed_nor_writable(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")
        archive = self.root / "tasks" / "archive"
        archive.mkdir()
        old = archive / "task-50.json"
        old.write_bytes((self.root / "tasks" / "task-1.json").read_bytes().replace(b'"1"', b'"50"'))
        before = old.read_bytes()
        self.assertEqual([t["id"] for t in self.baseline()["tasks"]], ["1"])
        r = self.write("50")
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("not a baseline proposal: 50", r.stderr)
        self.assertEqual(self.write("1").returncode, 0)
        self.assertEqual(old.read_bytes(), before)

    def test_write_goes_to_the_file_that_holds_the_id_whatever_its_name(self):
        self.three_commits()
        path = self.task("007", completion_date="2026-03-05")
        task = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(dict(task, id="7"), indent=2) + "\n", encoding="utf-8")
        t = self.one("7")
        self.assertEqual(t["file"], "task-007.json")
        r = self.write("7")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["written"][0]["file"], "task-007.json")
        self.assertEqual([p.name for p in (self.root / "tasks").iterdir()], ["task-007.json"])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["section_fingerprint"],
                         section_hashes(SPEC_A)["## Auth"])

    # -- --provenance

    def test_provenance_fields(self):
        self.three_commits()
        now = section_hashes(SPEC_C)
        spec = self.root / "spec_v1.md"
        for value, heading in (("## Auth", "## Auth"), ("Auth", "## Auth"), (" ## Docs ", "## Docs"),
                               ("### Sessions", "### Sessions")):
            r = self.run_cli("--provenance", str(self.root), "--section", value)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout), {
                "spec_version": "spec_v1", "spec_fingerprint": fp.hash_file(spec),
                "spec_section": heading, "section_fingerprint": now[heading]})
            self.assertEqual(list(json.loads(r.stdout)),
                             ["spec_version", "spec_fingerprint", "spec_section", "section_fingerprint"])

    def test_provenance_exit_codes(self):
        self.three_commits()
        for value in ("§ 5.1 free-form", "Sessions", "### Nope", ""):
            r = self.run_cli("--provenance", str(self.root), "--section", value)
            self.assertEqual((r.returncode, r.stdout), (1, ""), value)
            self.assertEqual(r.stderr.strip(), f"error: no current spec heading matches '{value}'")
        self.assertEqual(self.run_cli("--provenance", str(self.root)).returncode, 2)  # no --section
        self.assertEqual(self.run_cli("--provenance", str(self.root / "nope"), "--section", "Auth").returncode, 2)
        self.assertEqual(self.run_cli("--drift", str(self.root), "--section", "Auth").returncode, 2)
        (self.root / "spec_v1.md").unlink()
        r = self.run_cli("--provenance", str(self.root), "--section", "Auth")
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("no spec_v*.md", r.stderr)

    # -- --baseline --write

    def write(self, ids, *flags):
        return self.run_cli("--baseline", str(self.root), "--write", "--ids", ids, *flags)

    def snapshot(self):
        return {p.name: p.read_bytes() for p in sorted((self.root / "tasks").iterdir())}

    def test_write_stamps_only_the_pinned_keys(self):
        self.three_commits()
        before = {"id": "1", "title": "T", "status": "Finished", "owner": "claude",
                  "spec_version": "1", "spec_fingerprint": "sha256:old", "spec_section": "Auth",
                  "completion_date": "2026-03-05", "updated_date": "2026-03-06",
                  "notes": "Done earlier.", "task_verification": {"result": "pass"},
                  "verification_attempts": 1}
        path = self.root / "tasks" / "task-1.json"
        path.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
        a = section_hashes(SPEC_A)["## Auth"]
        r = self.write("1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"written": [
            {"id": "1", "file": "task-1.json", "action": "stamp_history", "spec_section": "## Auth",
             "section_fingerprint": a, "changed_since": True}], "unchanged": []})
        after = json.loads(path.read_text(encoding="utf-8"))
        note = (f"[BASELINE] section_fingerprint stamped from the spec at {self.a[:7]} "
                "(2026-03-01); the task records no hash of its own.")
        self.assertEqual(after, dict(before, spec_section="## Auth", section_fingerprint=a,
                                     notes=note + " Done earlier."))
        # existing keys keep their order; the new key sits right after spec_section
        keys = list(before)
        keys.insert(keys.index("spec_section") + 1, "section_fingerprint")
        self.assertEqual(list(after), keys)
        self.assertEqual([p.name for p in (self.root / "tasks").iterdir()], ["task-1.json"])  # no temp left
        # the next drift check sees the task, and reports it (changed_since)
        d = fp.compute_drift(self.root)
        self.assertEqual((d["no_provenance"], d["checked"]), (0, 1))
        self.assertEqual([t["id"] for t in d["drifted"][0]["tasks"]], ["1"])

    def test_write_spec_version_only_when_missing_or_blank(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")
        self.task(2, completion_date="2026-03-05", spec_version="  ")
        self.task(3, completion_date="2026-03-05", spec_version="v1")
        self.assertEqual(self.write("1,2,3").returncode, 0)
        tasks = {i: json.loads((self.root / "tasks" / f"task-{i}.json").read_text()) for i in (1, 2, 3)}
        self.assertEqual([tasks[i]["spec_version"] for i in (1, 2, 3)], ["spec_v1", "spec_v1", "v1"])
        keys = list(tasks[1])  # a new spec_version goes right before spec_section
        self.assertEqual(keys[keys.index("spec_section") - 1], "spec_version")
        for t in tasks.values():
            self.assertNotIn("spec_fingerprint", t)
            self.assertNotIn("updated_date", t)

    def test_write_notes_are_prepended_newest_first(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")                       # no notes key
        self.task(2, completion_date="2026-03-05", notes="")
        self.task(3, completion_date="2026-03-05", notes=None)
        self.task(4, completion_date="2026-03-05", notes="[VERIFICATION FAIL #1] x")
        self.task(5, completion_date="2026-03-05", notes=["first", "second"])
        self.task(6, completion_date="2026-03-05", notes=[])
        self.assertEqual(self.write("1,2,3,4,5,6").returncode, 0)
        note = (f"[BASELINE] section_fingerprint stamped from the spec at {self.a[:7]} "
                "(2026-03-01); the task records no hash of its own.")
        notes = {i: json.loads((self.root / "tasks" / f"task-{i}.json").read_text())["notes"]
                 for i in range(1, 7)}
        self.assertEqual(notes, {1: note, 2: note, 3: note, 4: note + " [VERIFICATION FAIL #1] x",
                                 5: [note, "first", "second"], 6: [note]})
        last = list(json.loads((self.root / "tasks" / "task-1.json").read_text()))[-1]
        self.assertEqual(last, "notes")

    def test_write_keeps_indent_trailing_newline_and_non_ascii(self):
        self.three_commits()
        task = {"id": "1", "title": "Tête-à-tête — ✓", "status": "Finished", "owner": "claude",
                "spec_section": "## Auth", "completion_date": "2026-03-15",
                "dependencies": [], "nested": {"list": [1, {"k": "v"}], "empty": {}}}
        layouts = {"2-space": (2, "\n"), "4-space": (4, ""), "tab": ("\t", "\n"),
                   "1-space": (1, "\n\n"), "one line": (None, "")}
        for name, (indent, tail) in layouts.items():
            for ensure_ascii in (False, True):
                with self.subTest(layout=name, ensure_ascii=ensure_ascii):
                    path = self.root / "tasks" / "task-1.json"
                    path.write_text(json.dumps(task, indent=indent, ensure_ascii=ensure_ascii) + tail,
                                    encoding="utf-8")
                    self.assertEqual(self.write("1").returncode, 0)
                    after = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(path.read_text(encoding="utf-8"),
                                     json.dumps(after, indent=indent, ensure_ascii=ensure_ascii) + tail)
                    self.assertEqual(after["section_fingerprint"], section_hashes(SPEC_B)["## Auth"])
                    self.assertEqual(after["title"], task["title"])

    def test_write_keeps_crlf_line_endings_and_file_mode(self):
        self.three_commits()
        path = self.task(1, completion_date="2026-03-15")
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        os.chmod(path, 0o640)
        self.assertEqual(self.write("1").returncode, 0)
        raw = path.read_bytes()
        self.assertIn(b"\r\n", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertTrue(raw.endswith(b"}\r\n"))
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o640)

    def test_write_confirm_current_needs_the_flag_and_notes_today(self):
        (self.root / "spec_v1.md").write_text(SPEC_B, encoding="utf-8")  # untracked: no history
        path = self.task(1, section="Auth", completion_date="2026-03-05")
        before = self.snapshot()
        r = self.write("1")
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("confirm_current needs --confirm-current: 1", r.stderr)
        self.assertEqual(self.snapshot(), before)
        r = self.write("1", "--confirm-current")
        self.assertEqual(r.returncode, 0, r.stderr)
        now = section_hashes(SPEC_B)["## Auth"]
        self.assertEqual(json.loads(r.stdout)["written"], [
            {"id": "1", "file": "task-1.json", "action": "confirm_current",
             "spec_section": "## Auth", "section_fingerprint": now, "changed_since": False}])
        after = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((after["spec_section"], after["section_fingerprint"]), ("## Auth", now))
        self.assertEqual(after["notes"], "[BASELINE] section_fingerprint set to the current section "
                         f"text on {datetime.date.today().isoformat()}, confirmed by the user as "
                         "what the task was built against.")
        again = self.write("1")  # nothing left to write, so no flag needed
        self.assertEqual(json.loads(again.stdout), {"written": [], "unchanged": ["1"]})

    def test_write_confirm_current_note_says_what_the_user_asserted(self):
        self.three_commits()
        self.task(1, "Pending")                                               # no usable date
        self.task(2, completion_date="2026-03-01")                            # may predate
        self.task(3, completion_date="2026-02-28", spec_version="spec_v1")    # no commit that early
        self.task(4, section="## Late", completion_date="2026-03-15")         # section not there yet
        got = {t["id"]: t["reason"] for t in self.baseline()["tasks"]}
        self.assertEqual(got, {"1": fp.REASON_NO_DATE, "2": fp.REASON_MAY_PREDATE,
                               "3": fp.REASON_NO_COMMIT, "4": fp.REASON_NOT_AT_COMMIT})
        r = self.write("1,2,3,4", "--confirm-current")
        self.assertEqual(r.returncode, 0, r.stderr)
        start = ("[BASELINE] section_fingerprint set to the current section text on "
                 f"{datetime.date.today().isoformat()}, ")
        notes = {i: json.loads((self.root / "tasks" / f"task-{i}.json").read_text())["notes"]
                 for i in range(1, 5)}
        accepted = start + "accepted by the user as the task's baseline."
        self.assertEqual(notes, {
            1: start + "confirmed by the user as what the task was built against.",
            2: accepted, 3: accepted, 4: accepted})
        # task 2 now has a spec_version, so a fresh proposal would be A's hash from
        # history; the rerun still reports it unchanged
        self.assertEqual(json.loads((self.root / "tasks" / "task-2.json").read_text())["spec_version"],
                         "spec_v1")
        again = self.write("1,2,3,4")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(json.loads(again.stdout), {"written": [], "unchanged": ["1", "2", "3", "4"]})

    def test_write_refuses_a_file_it_cannot_encode_before_any_write(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")
        # a lone surrogate escape parses, but the non-ASCII layout can't be written back
        (self.root / "tasks" / "task-2.json").write_text(
            '{\n  "id": "2",\n  "title": "é \\ud83d x",\n  "status": "Finished",\n'
            '  "spec_section": "Auth",\n  "completion_date": "2026-03-05"\n}\n', encoding="utf-8")
        self.assertEqual(self.baseline()["counts"]["stamp_history"], 2)
        before = self.snapshot()
        r = self.write("1,2")
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("nothing written; task file can't be rewritten", r.stderr)
        self.assertTrue(r.stderr.strip().endswith(": 2"), r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_write_refuses_duplicate_keys_before_any_write(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")
        for n, body in enumerate(('"notes": "first",\n  "notes": "second"',
                                  '"nested": {"k": 1, "k": 2}'), start=2):
            (self.root / "tasks" / f"task-{n}.json").write_text(
                '{\n  "id": "%d",\n  "status": "Finished",\n  "spec_section": "Auth",\n'
                '  "completion_date": "2026-03-05",\n  %s\n}\n' % (n, body), encoding="utf-8")
        before = self.snapshot()
        for bad, key in (("2", "notes"), ("3", "k")):
            r = self.write(f"1,{bad}")
            self.assertEqual((r.returncode, r.stdout), (2, ""))
            self.assertIn(f"nothing written; task file can't be rewritten (duplicate key '{key}'): {bad}",
                          r.stderr)
            self.assertEqual(self.snapshot(), before)

    def test_write_refuses_a_symlink_or_hard_linked_task_file_before_any_write(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")
        outside = self.repo / "outside.json"
        outside.write_text(json.dumps({"id": "2", "status": "Finished", "spec_section": "Auth",
                                       "completion_date": "2026-03-05"}, indent=2), encoding="utf-8")
        os.symlink(outside, self.root / "tasks" / "task-2.json")
        linked = self.task(3, completion_date="2026-03-05")
        os.link(linked, self.repo / "second-name.json")
        self.assertEqual(self.baseline()["counts"]["stamp_history"], 3)
        before, outside_before = self.snapshot(), outside.read_bytes()
        for bad, why in (("2", "not a regular file"), ("3", "more than one hard link")):
            r = self.write(f"1,{bad}")
            self.assertEqual((r.returncode, r.stdout), (2, ""))
            self.assertIn(f"nothing written; task file can't be rewritten ({why}): {bad}", r.stderr)
            self.assertEqual(self.snapshot(), before)
        self.assertTrue((self.root / "tasks" / "task-2.json").is_symlink())
        self.assertEqual(outside.read_bytes(), outside_before)
        self.assertEqual((self.repo / "second-name.json").read_bytes(), before["task-3.json"])

    def test_write_io_error_names_the_ids_already_written(self):
        self.three_commits()
        for i in (1, 2, 3):
            self.task(i, completion_date="2026-03-05")
        before = self.snapshot()
        real, calls = fp._replace_file, []

        def failing(path, data):
            calls.append(path.name)
            if len(calls) == 2:
                raise OSError(28, "No space left on device")
            real(path, data)
        fp._replace_file = failing
        self.addCleanup(setattr, fp, "_replace_file", real)
        with self.assertRaises(fp.BaselineError) as caught:
            fp.write_baseline(self.root, ["1", "2", "3"])
        self.assertEqual(str(caught.exception), "write failed at task 2 ([Errno 28] No space left on "
                         "device); already written: 1; a rerun finishes")
        after = self.snapshot()
        self.assertNotEqual(after["task-1.json"], before["task-1.json"])
        self.assertEqual((after["task-2.json"], after["task-3.json"]),
                         (before["task-2.json"], before["task-3.json"]))
        fp._replace_file = real
        rerun = fp.write_baseline(self.root, ["1", "2", "3"])  # a rerun finishes
        self.assertEqual(([w["id"] for w in rerun["written"]], rerun["unchanged"]), (["2", "3"], ["1"]))

    def test_write_refuses_before_any_write(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")                          # valid: stamp_history
        self.task(2, "Pending", "## Nope", created_date="2026-03-05")       # needs_section
        self.task(3, "Finished", "## Nope")                                  # report_only
        self.task(4, "Pending")                                              # confirm_current
        self.task(5, "Pending", None, spec_unmapped=True)                    # unmapped: no proposal
        self.task(6, "Pending", section_fingerprint="sha256:other")          # has provenance
        self.task(7, completion_date="2026-03-05", notes={"a": 1})           # notes can't be prepended
        self.task(8, "Pending", out_of_spec=True)
        before = self.snapshot()
        cases = {"2": "needs_section (no section to stamp): 2",
                 "3": "report_only (no section to stamp): 3",
                 "4": "confirm_current needs --confirm-current: 4",
                 "5": "not a baseline proposal: 5", "6": "not a baseline proposal: 6",
                 "7": "notes is dict", "8": "not a baseline proposal: 8",
                 "99": "not a baseline proposal: 99"}
        for bad, message in cases.items():
            with self.subTest(id=bad):
                r = self.write(f"1,{bad}")
                self.assertEqual((r.returncode, r.stdout), (2, ""))
                self.assertIn(message, r.stderr)
                self.assertIn("nothing written", r.stderr)
                self.assertEqual(self.snapshot(), before)
        r = self.write("1,2,3,99")
        self.assertIn("2", r.stderr)
        self.assertIn("not a baseline proposal: 99", r.stderr)
        self.assertEqual(self.snapshot(), before)
        # positive control: the same call with only the valid id writes
        r = self.write("1")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = self.snapshot()
        self.assertNotEqual(after["task-1.json"], before["task-1.json"])
        self.assertEqual({k: v for k, v in after.items() if k != "task-1.json"},
                         {k: v for k, v in before.items() if k != "task-1.json"})

    def test_write_refuses_an_id_shared_by_two_task_files(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")
        (self.root / "tasks" / "task-1b.json").write_bytes((self.root / "tasks" / "task-1.json").read_bytes())
        before = self.snapshot()
        r = self.write("1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("more than one task file: 1", r.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_write_is_idempotent(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")
        self.task(2, section="Docs", completion_date="2026-03-15")
        first = self.write("1, 2,1")  # spaces and a repeated id are fine
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual([w["id"] for w in json.loads(first.stdout)["written"]], ["1", "2"])
        after = self.snapshot()
        second = self.write("2,1")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout), {"written": [], "unchanged": ["2", "1"]})
        self.assertEqual(self.snapshot(), after)
        # a task whose fingerprint was since refreshed is no longer what the baseline proposes
        path = self.root / "tasks" / "task-1.json"
        task = json.loads(path.read_text())
        task["section_fingerprint"] = section_hashes(SPEC_C)["## Auth"]
        path.write_text(json.dumps(task), encoding="utf-8")
        r = self.write("1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a baseline proposal: 1", r.stderr)

    def test_write_usage_errors(self):
        self.three_commits()
        self.task(1, completion_date="2026-03-05")
        before = self.snapshot()
        base = ["--baseline", str(self.root)]
        for args in (base + ["--write"], base + ["--write", "--ids", " , "], base + ["--ids", "1"],
                     base + ["--confirm-current"], ["--drift", str(self.root), "--write", "--ids", "1"],
                     ["--provenance", str(self.root), "--section", "Auth", "--ids", "1"]):
            r = self.run_cli(*args)
            self.assertEqual((r.returncode, r.stdout), (2, ""), args)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git("status", "--porcelain", "--", str(self.root / "spec_v1.md")), "")


class NestedProjectBaselineTests(BaselineTests):
    """The same behaviour for a project that sits two directories below the root of
    the repository that tracks it (the spec's repo-relative path is not `.claude/…`)."""
    nested = True

    def test_spec_path_resolves_inside_the_larger_repository(self):
        # a decoy spec at the repository root's own .claude must not be read
        decoy = self.repo / ".claude"
        decoy.mkdir()
        (decoy / "spec_v1.md").write_text(SPEC_C, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "decoy", date="2026-02-01T12:00:00+0000")
        self.three_commits()
        self.task(1, completion_date="2026-03-05")
        t = self.one()
        self.assertEqual((t["action"], t["commit"]), ("stamp_history", self.a))
        self.assertEqual(t["section_fingerprint"], section_hashes(SPEC_A)["## Auth"])


if __name__ == "__main__":
    unittest.main()
