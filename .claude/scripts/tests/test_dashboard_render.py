"""Tests for dashboard-render.py — DATA LAYER.

DEC-024 hard-retired the Markdown renderers; this file covers the data-layer
functions the HTML renderer reuses (loaders, phase model, phase status, graph
topology, week activity, canonical task_hash) directly — independent of any
render target. HTML-output tests live in test_dashboard_render_html.py.
"""

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "dashboard-render.py"
spec = importlib.util.spec_from_file_location("dashboard_render", SCRIPT)
dr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dr)


def write_tasks(dirpath, tasks):
    for t in tasks:
        (dirpath / f"task-{t['id']}.json").write_text(json.dumps(t), encoding="utf-8")


def task(id, status="Pending", phase="1", **kw):
    base = {"id": str(id), "title": f"Task {id}", "status": status,
            "difficulty": 3, "owner": "claude", "dependencies": [], "phase": str(phase)}
    base.update(kw)
    return base


def decision_md(num, title, status, selected=None):
    body = f"---\nid: DEC-{num:03d}\ntitle: {title}\nstatus: {status}\ncreated: 2026-01-01\n---\n\n## Select an Option\n"
    if selected:
        body += f"- [x] **{selected}**\n- [ ] Other option\n"
    else:
        body += "- [ ] Option A\n- [ ] Option B\n"
    return body


# ---------------------------------------------------------------- task_hash

class TestTaskHash(unittest.TestCase):
    def test_canonical_convention(self):
        tasks = [task(2, "Pending"), task(1, "Finished")]
        rows = sorted(f"{t['id']}:{t['status']}:{t['difficulty']}:{t['owner']}" for t in tasks)
        import hashlib
        expected = "sha256:" + hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
        self.assertEqual(dr.canonical_task_hash(tasks), expected)

    def test_excludes_archive(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            write_tasks(p, [task(1, "Pending")])
            (p / "archive").mkdir()
            write_tasks(p / "archive", [task(2, "Finished")])
            self.assertEqual(dr.canonical_task_hash(dr.load_tasks(p)),
                             dr.canonical_task_hash([task(1, "Pending")]))

    def test_order_independent(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            tasks = [task(i) for i in (3, 1, 10, 2)]
            write_tasks(Path(a), tasks)
            write_tasks(Path(b), list(reversed(tasks)))
            self.assertEqual(dr.canonical_task_hash(dr.load_tasks(Path(a))),
                             dr.canonical_task_hash(dr.load_tasks(Path(b))))


class TestNumericKey(unittest.TestCase):
    def test_numeric_aware_order(self):
        ids = ["10", "2", "2_1", "A", "1"]
        self.assertEqual(sorted(ids, key=dr.numeric_key), ["1", "2", "2_1", "10", "A"])


# ------------------------------------------------------------- phase model

class TestPhaseModel(unittest.TestCase):
    def test_counts_exclude_absorbed_include_on_hold(self):
        phases = dr.build_phases([
            task(1, "Finished", "1"), task(2, "On Hold", "1"),
            task(3, "Absorbed", "1", absorbed_into="1")], [])
        done, total, arch_other = dr.phase_counts(phases["1"])
        self.assertEqual((done, total), (1, 2))  # On Hold in total, Absorbed excluded

    def test_archived_finished_count(self):
        phases = dr.build_phases(
            [task(50, "Finished", "1", phase_name="Core")],
            [task(i, "Finished", "1", phase_name="Core") for i in range(1, 34)])
        done, total, _ = dr.phase_counts(phases["1"])
        self.assertEqual((done, total), (34, 34))

    def test_archived_non_finished_surfaced(self):
        phases = dr.build_phases([task(2, "Finished", "1")],
                                 [task(1, "Finished", "1"), task(9, "On Hold", "1")])
        done, total, arch_other = dr.phase_counts(phases["1"])
        self.assertEqual(arch_other, 1)

    def test_phase_name_vote_prefers_majority(self):
        phases = dr.build_phases(
            [task(60, "Pending", "4", phase_name="New Name")],
            [task(i, "Finished", "4", phase_name="Canonical Name") for i in (1, 2, 3)])
        self.assertEqual(phases["4"]["name"], "Canonical Name")

    def test_unphased_bucket(self):
        phases = dr.build_phases([task(1, "Finished", phase=None)], [])
        self.assertIn("?", phases)


# -------------------------------------------------------- phase status map

class TestPhaseStatus(unittest.TestCase):
    def setUp(self):
        dr._GLOBAL_FINISHED = set()

    def test_complete_active_partial_blocked(self):
        active = [
            task(1, "Pending", "1"),
            task(2, "Finished", "1"),
            task(3, "Pending", "2", dependencies=["2"]),
            task(4, "Pending", "3", decision_dependencies=["DEC-001"])]
        decisions = [{"id": "DEC-001", "title": "Q", "status": "proposed",
                      "selected": None, "file": "x.md"}]
        dr._GLOBAL_FINISHED = {"2"}
        phases = dr.build_phases(active, [])
        smap = dr._phase_status_map(phases, decisions)
        self.assertTrue(smap["2"].startswith("Partially Actionable"))  # dep on finished 2
        self.assertEqual(smap["3"], "Blocked (DEC-001)")

    def test_completed_phase_is_complete(self):
        phases = dr.build_phases([task(1, "Finished", "1", task_verification={"result": "pass"})], [])
        smap = dr._phase_status_map(phases, [])
        self.assertEqual(smap["1"], "Complete")

    def test_blocked_partial_gate_label(self):
        # Only 1 of 3 open tasks in phase 2 is decision-gated (prior phase
        # incomplete): a whole-phase "Blocked (DEC-001)" reads as "nothing here
        # can start" — the label must carry the split (v5.2.0, tinder 06-27).
        active = [
            task(1, "Pending", "1"),
            task(2, "Pending", "2", decision_dependencies=["DEC-001"]),
            task(3, "Pending", "2"),
            task(4, "Pending", "2")]
        decisions = [{"id": "DEC-001", "title": "Q", "status": "proposed",
                      "selected": None, "file": "x.md"}]
        phases = dr.build_phases(active, [])
        smap = dr._phase_status_map(phases, decisions)
        self.assertEqual(
            smap["2"],
            "Blocked (DEC-001 gates 1 of 3; rest awaiting prior phase)")


# --------------------------------------------------- graph topology (shared)

class TestGraph(unittest.TestCase):
    def test_sequential_chain(self):
        active = [task(1, "Pending"), task(2, "Pending", dependencies=["1"]),
                  task(3, "Pending", dependencies=["2"])]
        nodes, edges = dr.build_graph(active, [])
        path = dr.longest_path(nodes, edges)
        self.assertEqual(path, ["T1", "T2", "T3"])

    def test_decision_node_included(self):
        active = [task(1, "Pending", decision_dependencies=["DEC-001"])]
        decisions = [{"id": "DEC-001", "title": "Q", "status": "proposed", "selected": None, "file": "x.md"}]
        nodes, edges = dr.build_graph(active, decisions)
        self.assertIn("D DEC-001".replace(" ", ""), nodes)  # node key 'DDEC-001'
        self.assertIn("DDEC-001", nodes)
        self.assertIn("T1", edges.get("DDEC-001", []))

    def test_cycle_returns_none(self):
        active = [task(1, "Pending", dependencies=["2"]), task(2, "Pending", dependencies=["1"])]
        nodes, edges = dr.build_graph(active, [])
        self.assertIsNone(dr.longest_path(nodes, edges))

    def test_on_hold_excluded(self):
        active = [task(1, "On Hold"), task(2, "Pending", dependencies=["1"])]
        nodes, _ = dr.build_graph(active, [])
        self.assertNotIn("T1", nodes)

    def test_finished_excluded(self):
        active = [task(1, "Finished"), task(2, "Pending", dependencies=["1"])]
        nodes, edges = dr.build_graph(active, [])
        self.assertNotIn("T1", nodes)
        self.assertEqual(edges, {})  # dep on finished task creates no edge


# ----------------------------------------------------------- week activity

class TestWeekActivity(unittest.TestCase):
    def test_completed_and_started_within_7_days(self):
        now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
        active = [
            task(1, "Finished", completion_date="2026-06-10"),
            task(2, "In Progress", updated_date="2026-06-09"),
            task(3, "Finished", completion_date="2026-01-01")]  # too old
        completed, started, _created = dr.week_activity(active, now)
        self.assertEqual([t["id"] for _, t in completed], ["1"])
        self.assertEqual([t["id"] for _, t in started], ["2"])


# ----------------------------------------------------------------- loaders

class TestLoaders(unittest.TestCase):
    def test_load_tasks_skips_unparseable(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            write_tasks(p, [task(1)])
            (p / "task-bad.json").write_text("{not json", encoding="utf-8")
            self.assertEqual([t["id"] for t in dr.load_tasks(p)], ["1"])

    def test_load_decisions_extracts_selected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "decision-001-x.md").write_text(decision_md(1, "Pick", "approved", "Hardwood"), encoding="utf-8")
            decs = dr.load_decisions(p)
            self.assertEqual(decs[0]["selected"], "Hardwood")
            self.assertEqual(decs[0]["status"], "approved")

    def test_load_spec_title_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "spec_v3.md").write_text("---\ntitle: My Project\nstatus: active\n---\n\nBody.\n", encoding="utf-8")
            s = dr.load_spec(p)
            self.assertEqual(s["version"], "spec_v3")
            self.assertEqual(s["title"], "My Project")
            self.assertTrue(s["fingerprint"].startswith("sha256:"))

    def test_load_archived_index_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / "archive"
            archive.mkdir()
            (archive / "archive-index.json").write_text(json.dumps(
                {"tasks": [{"id": str(i), "status": "Finished", "phase": "1"} for i in (1, 2, 3)]}),
                encoding="utf-8")
            self.assertEqual(len(dr.load_archived(Path(d))), 3)


# --------------------------------------------------------------------- CLI

class TestCli(unittest.TestCase):
    def test_requires_mode_flag(self):
        self.assertEqual(dr.main([]), 2)

    def test_html_missing_dir(self):
        self.assertEqual(dr.main(["--html", "--claude-dir", "/nonexistent-xyz"]), 2)

    def test_task_hash_missing_dir(self):
        self.assertEqual(dr.main(["--task-hash", "--tasks-dir", "/nonexistent-xyz"]), 2)


if __name__ == "__main__":
    unittest.main()
