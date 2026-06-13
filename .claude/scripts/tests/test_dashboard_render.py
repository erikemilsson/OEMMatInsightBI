"""Tests for dashboard-render.py (Family C PoC).

The load-bearing test is byte-identical re-rendering (the PoC acceptance
gate from scripts-candidates.md § Family C). Rule tests pin the Section
Display Rules the script mirrors from dashboard-regeneration.md.
"""

import importlib.util
import json
import tempfile
import unittest
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


class TestDeterminism(unittest.TestCase):
    def test_byte_identical_rerender(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_tasks(d, [
                task(1, "Finished", "1", phase_name="Planning"),
                task(2, "Finished", "1", phase_name="Planning"),
                task(3, "In Progress", "2", phase_name="Build", dependencies=["1"]),
                task(4, "Pending", "2", phase_name="Build", owner="human",
                     decision_dependencies=["DEC-002"]),
                task("4_1", "Pending", "2", phase_name="Build"),
            ])
            first = dr.render_tasks_section(dr.load_tasks(d))
            second = dr.render_tasks_section(dr.load_tasks(d))
            self.assertEqual(first.encode(), second.encode())

    def test_order_independent_of_file_mtime(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            tasks = [task(i, phase="1") for i in (3, 1, 10, 2)]
            write_tasks(Path(a), tasks)
            write_tasks(Path(b), list(reversed(tasks)))
            self.assertEqual(dr.render_tasks_section(dr.load_tasks(Path(a))),
                             dr.render_tasks_section(dr.load_tasks(Path(b))))


class TestDisplayRules(unittest.TestCase):
    def render(self, tasks):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_tasks(d, tasks)
            return dr.render_tasks_section(dr.load_tasks(d))

    def test_completed_phase_collapses(self):
        out = self.render([task(1, "Finished"), task(2, "Finished"),
                           task(3, "Absorbed", absorbed_into="1")])
        self.assertIn("✅ 2 tasks finished", out)
        self.assertNotIn("| 1 |", out)  # no individual rows

    def test_finished_summarization_over_10(self):
        tasks = [task(i, "Finished", "1") for i in range(1, 12)]
        tasks.append(task(20, "Pending", "1"))
        out = self.render(tasks)
        self.assertIn("✅ 11 tasks finished", out)
        self.assertIn("| 20 |", out)
        self.assertNotIn("| 5 |", out)  # finished rows summarized away

    def test_blocked_phase_collapses(self):
        tasks = [task(i, "Blocked", "2", dependencies=["99"]) for i in range(1, 8)]
        out = self.render(tasks)
        self.assertIn("⏳ 7 tasks awaiting upstream", out)
        self.assertIn("blocked by task-99", out)

    def test_small_blocked_phase_stays_tabular(self):
        tasks = [task(i, "Blocked", "2") for i in range(1, 4)]  # 3 <= 5
        out = self.render(tasks)
        self.assertIn("| 1 |", out)

    def test_status_displays(self):
        out = self.render([
            task(1, "On Hold"),
            task(2, "Absorbed", absorbed_into="1"),
            task(3, "Finished", verification_history=[{}, {}, {}]),
            task(4, "Pending", conflict_note="9"),
            task(5, "Pending", out_of_spec=True),
            task(6, "Pending", cross_phase=True),
        ])
        self.assertIn("⏸️ On Hold", out)
        self.assertIn("Absorbed → Task 1", out)
        self.assertIn("Finished (2 retries)", out)
        self.assertIn("Pending (held: conflict with Task 9)", out)
        self.assertIn("⚠️ Task 5", out)
        self.assertIn("Task 6 (cross-phase)", out)

    def test_counts_exclude_absorbed_include_on_hold(self):
        out = self.render([
            task(1, "Finished"), task(2, "On Hold"),
            task(3, "Absorbed", absorbed_into="1"),
        ])
        self.assertIn("*Phase 1: 1/2 complete (50%)", out)
        self.assertIn("*1/2 tasks complete (50%)*", out)

    def test_deps_column_merges_decision_deps(self):
        out = self.render([task(1, dependencies=["9"], decision_dependencies=["DEC-002"])])
        self.assertIn("| 9, DEC-002 |", out)

    def test_phase_naming_and_subtask_sort(self):
        out = self.render([
            task("2_1", "Pending", "1", phase_name="Core"),
            task(2, "Pending", "1", phase_name="Core"),
            task(10, "Pending", "1", phase_name="Core"),
        ])
        self.assertIn("### Phase 1 — Core", out)
        rows = [l for l in out.splitlines() if l.startswith("| ")]
        ids = [r.split("|")[1].strip() for r in rows[1:]]
        self.assertEqual(ids, ["2", "2_1", "10"])

    def test_empty_dir(self):
        out = self.render([])
        self.assertIn("## 📋 Tasks", out)
        self.assertIn("*0/0 tasks complete (0%)*", out)


class TestCli(unittest.TestCase):
    def test_requires_mode_flag(self):
        self.assertEqual(dr.main([]), 2)

    def test_missing_dir(self):
        self.assertEqual(dr.main(["--tasks-section", "--tasks-dir", "/nonexistent-xyz"]), 2)

    def test_modes_are_exclusive(self):
        self.assertEqual(dr.main(["--tasks-section", "--render"]), 2)


# ---------------------------------------------------------------- full port


def decision_md(num, title, status, selected=None):
    body = f"---\nid: DEC-{num:03d}\ntitle: {title}\nstatus: {status}\ncreated: 2026-01-01\n---\n\n## Select an Option\n"
    if selected:
        body += f"- [x] **{selected}**\n- [ ] Other option\n"
    else:
        body += "- [ ] Option A\n- [ ] Option B\n"
    return body


class FullPortBase(unittest.TestCase):
    """Builds a full .claude fixture dir."""

    def make_env(self, active=(), archived=(), decisions=(), sidecar=None,
                 verification=None, spec="# Fixture Project\n\nBody.\n"):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        tasks = root / "tasks"
        tasks.mkdir()
        write_tasks(tasks, list(active))
        if archived:
            (tasks / "archive").mkdir()
            write_tasks(tasks / "archive", list(archived))
        dec_dir = root / "support" / "decisions"
        dec_dir.mkdir(parents=True)
        for i, d in enumerate(decisions, start=1):
            (dec_dir / f"decision-{i:03d}-x.md").write_text(d, encoding="utf-8")
        if sidecar is not None:
            (root / "dashboard-state.json").write_text(json.dumps(sidecar), encoding="utf-8")
        if verification is not None:
            (root / "verification-result.json").write_text(json.dumps(verification), encoding="utf-8")
        (root / "spec_v1.md").write_text(spec, encoding="utf-8")
        (root / "version.json").write_text(json.dumps({"template_version": "9.9.9"}), encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)
        return root

    def render(self, root):
        from datetime import datetime, timezone
        now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)
        return dr.render_full(root, now)


class TestArchiveAware(FullPortBase):
    def test_archived_finished_count_in_collapse(self):
        root = self.make_env(active=[task(50, "Finished", "1", phase_name="Core",
                                          task_verification={"result": "pass"})],
                             archived=[task(i, "Finished", "1", phase_name="Core") for i in range(1, 34)])
        out = self.render(root)
        self.assertIn("✅ 34 tasks finished", out)
        self.assertIn("| Phase 1 — Core | 34 | 34 | Complete |", out)

    def test_archived_non_finished_note(self):
        root = self.make_env(active=[task(2, "Finished", "1", task_verification={"result": "pass"})],
                             archived=[task(1, "Finished", "1"), task(9, "On Hold", "1")])
        out = self.render(root)
        self.assertIn("✅ 2 tasks finished (+1 archived non-finished)", out)

    def test_archive_index_fallback(self):
        root = self.make_env(active=[task(5, "Pending", "2", phase_name="Next")])
        archive = root / "tasks" / "archive"
        archive.mkdir()
        (archive / "archive-index.json").write_text(json.dumps(
            {"archived_count": 3, "tasks": [{"id": str(i), "status": "Finished", "phase": "1"} for i in (1, 2, 3)]}),
            encoding="utf-8")
        out = self.render(root)
        self.assertIn("✅ 3 tasks finished", out)

    def test_phase_name_vote_prefers_majority(self):
        root = self.make_env(active=[task(60, "Pending", "4", phase_name="New Name")],
                             archived=[task(i, "Finished", "4", phase_name="Canonical Name") for i in (1, 2, 3)])
        out = self.render(root)
        self.assertIn("### Phase 4 — Canonical Name", out)

    def test_unphased_bucket(self):
        out = dr.render_tasks_section([task(1, "Finished", phase=None)])
        self.assertIn("### Unphased", out)
        self.assertNotIn("Phase None", out)


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


class TestDecisionsSection(FullPortBase):
    def test_status_mapping_and_selected(self):
        root = self.make_env(
            active=[task(1, "Pending", "1")],
            decisions=[decision_md(1, "Pick a flooring", "approved", selected="Hardwood"),
                       decision_md(2, "Pick a vendor", "proposed")])
        out = self.render(root)
        self.assertIn("| DEC-001 | Pick a flooring | Decided | [Hardwood](support/decisions/decision-001-x.md) |", out)
        self.assertIn("| DEC-002 | Pick a vendor | Pending | [Pending](support/decisions/decision-002-x.md) |", out)


class TestProgress(FullPortBase):
    def test_status_summary_gate(self):
        small = self.make_env(active=[task(i, "Pending", "1") for i in range(1, 6)])
        self.assertNotIn("| Status | Count |", self.render(small))
        big = self.make_env(active=[task(i, "Pending", "1") for i in range(1, 26)])
        self.assertIn("| Status | Count |", self.render(big))

    def test_partially_actionable_and_blocked(self):
        root = self.make_env(active=[
            task(1, "Pending", "1"),
            task(2, "Finished", "1", task_verification={"result": "pass"}),
            task(3, "Pending", "2", dependencies=["2"]),
            task(4, "Pending", "3", decision_dependencies=["DEC-001"])],
            decisions=[decision_md(1, "Open question", "proposed")])
        out = self.render(root)
        self.assertIn("| Phase 2 | 0 | 1 | Partially Actionable (1 eligible: 3) |", out)
        self.assertIn("| Phase 3 | 0 | 1 | Blocked (DEC-001) |", out)

    def test_acceptance_criteria_and_fallback(self):
        full = self.make_env(active=[task(1, "Pending", "1")],
                             verification={"criteria": [
                                 {"criterion": "Logs in", "status": "pass", "notes": "ok"},
                                 {"criterion": "Expires", "status": "fail"}]})
        out = self.render(full)
        self.assertIn("- [x] Logs in — *ok*", out)
        self.assertIn("- [ ] Expires", out)
        self.assertIn("**1/2 criteria passed**", out)
        summary_only = self.make_env(active=[task(1, "Pending", "1")],
                                     verification={"criteria_passed": 4, "criteria_failed": 1})
        self.assertIn("**4/5 criteria passed**", self.render(summary_only))

    def test_timeline_overdue(self):
        root = self.make_env(active=[task(1, "Pending", "1", due_date="2026-01-01", owner="human"),
                                     task(2, "Pending", "1", due_date="2026-12-01")])
        out = self.render(root)
        self.assertIn("| ~~2026-01-01~~ | ⚠️ OVERDUE: Task 1 — Task 1 | Pending | ❗ Human task |", out)
        self.assertIn("| 2026-12-01 | Task 2 — Task 2 | Pending |  |", out)


class TestCriticalPath(unittest.TestCase):
    def cp(self, active, decisions=(), vr=None):
        return dr.render_critical_path(list(active), list(decisions), vr)

    def test_sequential_chain(self):
        out = self.cp([task(1, "Pending"), task(2, "Pending", dependencies=["1"]),
                       task(3, "Pending", dependencies=["2"])])
        self.assertIn("🤖 Task 1 → 🤖 Task 2 → 🤖 Task 3 → Done *(3 steps)*", out)

    def test_decision_node(self):
        out = self.cp([task(1, "Pending", decision_dependencies=["DEC-001"])],
                      [{"id": "DEC-001", "title": "Q", "status": "proposed", "selected": None, "file": "x.md"}])
        self.assertIn("❗ Resolve DEC-001 → 🤖 Task 1 → Done", out)

    def test_no_edges(self):
        self.assertIn("All tasks can start now", self.cp([task(1, "Pending"), task(2, "Pending")]))

    def test_all_complete_with_pass(self):
        out = self.cp([task(1, "Finished")], vr={"result": "pass"})
        self.assertIn("All tasks complete! ✓", out)

    def test_all_complete_without_result(self):
        self.assertIn("🤖 Phase verification → Done *(1 step)*", self.cp([task(1, "Finished")]))

    def test_truncation_over_5_steps(self):
        chain = [task(1, "Pending")]
        for i in range(2, 9):
            chain.append(task(i, "Pending", dependencies=[str(i - 1)]))
        out = self.cp(chain)
        self.assertIn("... ", out)
        self.assertIn("*(8 steps)*", out)

    def test_cycle_detected(self):
        out = self.cp([task(1, "Pending", dependencies=["2"]), task(2, "Pending", dependencies=["1"])])
        self.assertIn("dependency cycle detected", out)

    def test_on_hold_excluded(self):
        out = self.cp([task(1, "On Hold"), task(2, "Pending", dependencies=["1"])])
        self.assertNotIn("Task 1", out)


class TestMermaid(unittest.TestCase):
    def diagram(self, active, archived=(), decisions=()):
        phases = dr.build_phases(list(active), list(archived))
        return "\n".join(dr.render_mermaid(list(active), list(archived), list(decisions), phases, {}))

    def test_omitted_under_4_tasks(self):
        self.assertEqual(self.diagram([task(1, "Pending"), task(2, "Pending"), task(3, "Pending")]), "")

    def test_critical_path_only_over_15(self):
        chain = [task(1, "Pending")]
        for i in range(2, 6):
            chain.append(task(i, "Pending", dependencies=[str(i - 1)]))
        islands = [task(100 + i, "Pending") for i in range(14)]
        out = self.diagram(chain + islands)
        self.assertIn("Showing critical path only —", out)

    def test_lazy_phase_nodes(self):
        active = [task(10, "Pending", "2", dependencies=["1"]),
                  task(11, "Pending", "2"), task(12, "Pending", "2"), task(13, "Pending", "2")]
        archived = [task(1, "Finished", "1", phase_name="Linked"),
                    task(2, "Finished", "9", phase_name="Island")]
        out = self.diagram(active, archived)
        self.assertIn('P1["✅ Phase 1 — Linked (1/1)"]', out)
        self.assertIn("P1 --> T10", out)
        self.assertNotIn("Island", out)


class TestFullRender(FullPortBase):
    def standard_env(self):
        return self.make_env(
            active=[task(1, "Finished", "1", phase_name="Build", completion_date="2026-06-10",
                         task_verification={"result": "pass"}),
                    task(2, "In Progress", "1", phase_name="Build", updated_date="2026-06-09"),
                    task(3, "Pending", "1", phase_name="Build", dependencies=["2"])],
            decisions=[decision_md(1, "Pick", "approved", selected="A")],
            sidecar={"user_notes": "KEEP-ME", "section_toggles": {
                "action_required": True, "progress": True, "tasks": True,
                "decisions": False, "notes": True, "custom_views": False}})

    def test_byte_identical_full_render(self):
        root = self.standard_env()
        self.assertEqual(self.render(root), self.render(root))

    def test_placeholder_and_notes_preserved(self):
        out = self.render(self.standard_env())
        self.assertIn("<!-- CLAUDE: fill — Action Required", out)
        self.assertIn("KEEP-ME", out)
        self.assertIn("<!-- USER SECTION -->", out)

    def test_toggle_excludes_section(self):
        out = self.render(self.standard_env())
        self.assertNotIn("## 📋 Decisions", out)
        self.assertIn("- [ ] Decisions", out)

    def test_meta_and_footer(self):
        out = self.render(self.standard_env())
        self.assertIn("task_count: 3", out)
        self.assertIn("template_version: 9.9.9", out)
        self.assertIn('[Spec aligned](# "0 drift deferrals, 0 verification debt")', out)

    def test_verification_debt_in_footer(self):
        root = self.make_env(active=[task(1, "Finished", "1")])  # finished, no verification
        out = self.render(root)
        self.assertIn("⚠️ 0 drift deferrals, 1 verification debt", out)


if __name__ == "__main__":
    unittest.main()
