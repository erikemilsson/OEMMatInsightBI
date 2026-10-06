#!/usr/bin/env python3
"""End-to-end tests for fingerprint.py via subprocess.

Tests the CLI surface — happy path + key error modes. Covers the FB-039
class of bug (field-name drift between script and schema) by exercising
the dashboard-rollup path against a realistic task JSON. compute_drift()
(--drift, FB-128) is also tested directly, with the module loaded by path.
"""
import importlib.util
import json
import os
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
              "historical", "unmatched", "no_provenance", "unreadable", "unreconciled_sections"}


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
        for key in ("checked", "historical", "unmatched", "no_provenance", "unreconciled_sections"):
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


if __name__ == "__main__":
    unittest.main()
