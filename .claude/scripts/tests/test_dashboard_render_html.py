"""Tests for dashboard-render.py --html (DEC-024).

The dashboard is a single read-only, offline, file://-openable HTML page.
These tests pin the load-bearing invariants: determinism, the META block in
<head> (freshness consumers string-parse it), the synthesis placeholders, the
inline-SVG charts, the adaptive dependency graph, and — critically — the
absence of any file://-breaking runtime dep (no type="module", no CDN
import/fetch). The only permitted external ref is the Google Fonts <link>.
"""

import importlib.util
import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "dashboard-render.py"
spec = importlib.util.spec_from_file_location("dashboard_render", SCRIPT)
dr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dr)

NOW = datetime(2026, 6, 24, 0, 0, 0, tzinfo=timezone.utc)


def task(id, status="Pending", phase="1", **kw):
    base = {"id": str(id), "title": f"Task {id}", "status": status,
            "difficulty": 3, "owner": "claude", "dependencies": [], "phase": str(phase)}
    base.update(kw)
    return base


def decision_md(num, title, status, selected=None):
    body = f"---\nid: DEC-{num:03d}\ntitle: {title}\nstatus: {status}\ncreated: 2026-01-01\n---\n\n## Select an Option\n"
    body += f"- [x] **{selected}**\n" if selected else "- [ ] Option A\n"
    return body


class HtmlBase(unittest.TestCase):
    def make_env(self, active=(), archived=(), decisions=(), sidecar=None,
                 verification=None, spec_text="---\ntitle: Fixture Project\n---\n\n## Overview\n\nBody.\n",
                 spec_index=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        tasks = root / "tasks"
        tasks.mkdir()
        for t in active:
            (tasks / f"task-{t['id']}.json").write_text(json.dumps(t), encoding="utf-8")
        if archived:
            (tasks / "archive").mkdir()
            for t in archived:
                (tasks / "archive" / f"task-{t['id']}.json").write_text(json.dumps(t), encoding="utf-8")
        dec_dir = root / "support" / "decisions"
        dec_dir.mkdir(parents=True)
        for i, d in enumerate(decisions, start=1):
            (dec_dir / f"decision-{i:03d}-x.md").write_text(d, encoding="utf-8")
        if sidecar is not None:
            (root / "dashboard-state.json").write_text(json.dumps(sidecar), encoding="utf-8")
        if verification is not None:
            (root / "verification-result.json").write_text(json.dumps(verification), encoding="utf-8")
        (root / "spec_v1.md").write_text(spec_text, encoding="utf-8")
        if spec_index is not None:
            (root / "spec_v1.index.json").write_text(json.dumps(spec_index), encoding="utf-8")
        (root / "version.json").write_text(json.dumps({"template_version": "9.9.9"}), encoding="utf-8")
        return root

    def render(self, root):
        return dr.render_full_html(root, NOW)

    def chain(self, n):
        """n-task dependency chain → a non-degenerate graph."""
        out = [task(1, "Pending", "1")]
        for i in range(2, n + 1):
            out.append(task(i, "Pending", "1", dependencies=[str(i - 1)]))
        return out


class TestDeterminism(HtmlBase):
    def test_byte_identical_for_fixed_now(self):
        root = self.make_env(active=[task(1, "Finished", "1"), task(2, "In Progress", "1")],
                             decisions=[decision_md(1, "Pick", "approved", "A")])
        self.assertEqual(self.render(root).encode(), self.render(root).encode())

    def test_no_date_or_random_in_output(self):
        out = self.render(self.make_env(active=[task(1, "Pending", "1")]))
        # the only timestamp is the fixed --now
        self.assertIn("2026-06-24T00:00:00Z", out)
        self.assertNotIn("Math.random", out)
        self.assertNotIn("Date.now", out)


class TestMetaInHead(HtmlBase):
    def head(self, out):
        return out[:out.index("</head>")]

    def test_meta_block_in_head_with_task_hash(self):
        out = self.render(self.make_env(active=[task(1, "Pending", "1")]))
        head = self.head(out)
        self.assertIn("<!-- DASHBOARD META", head)
        self.assertRegex(head, r"task_hash:\s*sha256:[0-9a-f]{64}")
        self.assertIn("template_version: 9.9.9", head)

    def test_meta_task_hash_matches_canonical(self):
        active = [task(1, "Pending", "1"), task(2, "Finished", "1")]
        out = self.render(self.make_env(active=active))
        expect = dr.canonical_task_hash(active)
        self.assertIn(f"task_hash: {expect}", out)


class TestPlaceholders(HtmlBase):
    def test_action_required_augment_placeholder_emitted(self):
        # FB-105: Action Required is script-rendered; the LLM placeholder is now an
        # APPEND-ONLY augment slot (judgment items), not a fill-the-whole-card slot.
        out = self.render(self.make_env(active=[task(1, "Pending", "1")]))
        self.assertIn("<!-- CLAUDE: augment", out)
        self.assertNotIn("<!-- CLAUDE: fill — Action Required", out)
        self.assertIn("Needs you", out)

    def test_custom_views_placeholder_when_toggled(self):
        root = self.make_env(active=[task(1, "Pending", "1")],
                             sidecar={"section_toggles": {"custom_views": True},
                                      "custom_views_instructions": "**By owner:** group tasks"})
        out = self.render(root)
        self.assertIn("<!-- CUSTOM VIEWS INSTRUCTIONS -->", out)
        self.assertEqual(out.count("<!-- CLAUDE: fill"), 1)  # custom-views only


class TestActionRequiredAutoRender(HtmlBase):
    """FB-105: the human-gated coverage invariant is script-enforced — an unfilled
    card can no longer silently drop user-gated items (observed downstream)."""

    def test_human_task_with_satisfied_deps_renders_with_command(self):
        active = [task(1, "Finished", "1", task_verification={"result": "pass"}),
                  task(2, "Pending", "1", owner="human", dependencies=["1"],
                       title="Set up API credentials")]
        out = self.render(self.make_env(active=active))
        self.assertIn("Your Tasks", out)
        self.assertIn("Set up API credentials", out)
        self.assertIn("/work complete 2", out)

    def test_human_task_with_unsatisfied_deps_is_not_listed(self):
        active = [task(1, "Pending", "1"),
                  task(2, "Pending", "1", owner="human", dependencies=["1"],
                       title="Blocked human task")]
        out = self.render(self.make_env(active=active))
        self.assertNotIn("Blocked human task", out)

    def test_both_owned_awaiting_review_and_on_hold_render(self):
        active = [task(1, "Pending", "1", owner="both", user_review_pending=True,
                       title="Review the drape output"),
                  task(2, "On Hold", "1", title="Parked work")]
        out = self.render(self.make_env(active=active))
        self.assertIn("Review the drape output", out)
        self.assertIn("Parked work", out)
        self.assertIn("only you can resume", out)

    def test_unresolved_decision_renders_with_file_link(self):
        dec = ("---\nid: DEC-001\ntitle: Pick a store\nstatus: proposed\n---\n\n"
               "## Select an Option\n\n- [ ] Option A\n")
        out = self.render(self.make_env(active=[task(1, "Pending", "1")], decisions=[dec]))
        self.assertIn("DEC-001", out)
        self.assertIn("unresolved", out)

    def test_verification_debt_renders(self):
        active = [task(1, "Finished", "1")]  # Finished without passing verification
        out = self.render(self.make_env(active=active))
        self.assertIn("Verification Debt", out)

    def test_empty_state_when_nothing_is_user_gated(self):
        active = [task(1, "Pending", "1", owner="claude")]
        out = self.render(self.make_env(active=active))
        self.assertIn("Nothing blocked on you right now", out)


class TestNoFileBreakers(HtmlBase):
    def test_no_module_script_no_cdn(self):
        out = self.render(self.make_env(active=self.chain(5),
                                        decisions=[decision_md(1, "Pick", "approved", "A")]))
        self.assertNotIn('type="module"', out)
        self.assertNotIn("import ", out.split("<style>")[0] + out.split("</style>")[-1])  # no JS import
        self.assertNotIn("cdn.", out)
        self.assertNotIn("fetch(", out)
        self.assertNotIn("jsdelivr", out)

    def test_only_external_ref_is_google_fonts(self):
        out = self.render(self.make_env(active=[task(1, "Pending", "1")]))
        ext = set(re.findall(r'https?://[^\s"\')]+', out))
        nonfont = [u for u in ext if "fonts.googleapis" not in u and "fonts.gstatic" not in u]
        self.assertEqual(nonfont, [])

    def test_well_formed_document(self):
        out = self.render(self.make_env(active=[task(1, "Pending", "1")]))
        self.assertTrue(out.startswith("<!doctype html>"))
        self.assertTrue(out.rstrip().endswith("</html>"))


class TestSvgCharts(HtmlBase):
    def test_ring_and_donut_present(self):
        out = self.render(self.make_env(active=[task(1, "Finished", "1"), task(2, "Pending", "1")]))
        self.assertIn('class="ring"', out)        # completion ring
        self.assertIn("COMPLETE", out)
        self.assertIn("<svg", out)
        self.assertIn('class="grid"', out)         # phase heatmap container
        self.assertIn('class="cell', out)

    def test_completion_ring_reflects_done_fraction(self):
        # 1 of 2 finished → 50%
        out = self.render(self.make_env(active=[task(1, "Finished", "1"), task(2, "Pending", "1")]))
        self.assertIn(">50<", out)


class TestDependencyGraph(HtmlBase):
    def test_graph_renders_with_chain(self):
        out = self.render(self.make_env(active=self.chain(5)))
        self.assertIn('class="depgraph"', out)
        self.assertIn('class="gnode', out)
        self.assertIn('class="gedge', out)
        self.assertIn("gcrit", out)  # critical-path emphasis present

    def test_graph_omitted_under_4_task_nodes(self):
        out = self.render(self.make_env(active=self.chain(3)))
        self.assertNotIn('class="depgraph"', out)

    def test_graph_omitted_when_no_edges(self):
        out = self.render(self.make_env(active=[task(i, "Pending", "1") for i in range(1, 6)]))
        self.assertNotIn('class="depgraph"', out)  # 5 disconnected nodes → degenerate

    def test_graph_omitted_on_cycle(self):
        active = [task(1, "Pending", "1", dependencies=["2"]),
                  task(2, "Pending", "1", dependencies=["1"]),
                  task(3, "Pending", "1", dependencies=["1"]),
                  task(4, "Pending", "1", dependencies=["1"])]
        out = self.render(self.make_env(active=active))
        self.assertNotIn('class="depgraph"', out)

    def test_graph_scale_reduction_over_15(self):
        # 5-chain + 14 disconnected tasks (19 > 15 nodes) → reduction keeps the
        # critical path + neighbors and omits the off-path islands, with a note.
        active = self.chain(5) + [task(100 + i, "Pending", "1") for i in range(14)]
        out = self.render(self.make_env(active=active))
        self.assertIn('class="depgraph"', out)
        self.assertIn("more tasks omitted", out)

    def test_pure_chain_over_15_renders_whole(self):
        # a pure chain has no off-path nodes — reduction omits nothing (correct)
        out = self.render(self.make_env(active=self.chain(20)))
        self.assertIn('class="depgraph"', out)
        self.assertNotIn("more tasks omitted", out)


class TestSections(HtmlBase):
    def test_decisions_card_present_and_links_out(self):
        out = self.render(self.make_env(
            active=[task(1, "Pending", "1")],
            decisions=[decision_md(1, "Pick a vendor", "approved", "Acme")]))
        self.assertIn("📋 Decisions", out)
        self.assertIn("support/decisions/decision-001-x.md", out)  # link-out
        self.assertIn("decFilter", out)  # search/filter JS retained

    def test_decisions_omitted_when_none(self):
        out = self.render(self.make_env(active=[task(1, "Pending", "1")]))
        self.assertNotIn("📋 Decisions", out)

    def test_decisions_toggle_off(self):
        root = self.make_env(active=[task(1, "Pending", "1")],
                             decisions=[decision_md(1, "Q", "approved", "A")],
                             sidecar={"section_toggles": {"decisions": False}})
        self.assertNotIn("📋 Decisions", self.render(root))

    def test_spec_card_links_out_with_index_headings(self):
        out = self.render(self.make_env(
            active=[task(1, "Pending", "1")],
            spec_index={"sections": [{"heading": "## Overview"}, {"heading": "## Architecture"}]}))
        self.assertIn("📄 Specification", out)
        self.assertIn("spec_v1.md", out)
        self.assertIn("Overview", out)
        self.assertIn("Architecture", out)
        self.assertNotIn("<!-- spec body -->", out)  # headings only, no embedded spec text

    def test_notes_card_from_sidecar(self):
        out = self.render(self.make_env(active=[task(1, "Pending", "1")],
                                        sidecar={"user_notes": "**Quick Links:**\n- [spec](spec_v1.md)"}))
        self.assertIn("Quick Links", out)
        self.assertIn('href="spec_v1.md"', out)

    def test_acceptance_criteria_status_surface(self):
        # DEC-022: criteria[] from verification-result.json is the live status surface
        out = self.render(self.make_env(active=[task(1, "Pending", "1")],
            verification={"criteria": [
                {"criterion": "User can log in", "status": "pass", "notes": "ok"},
                {"criterion": "Session expires", "status": "fail"}]}))
        self.assertIn("Acceptance criteria", out)
        self.assertIn("1/2 passed", out)
        self.assertIn("User can log in", out)

    def test_timeline_renders_with_due_dates(self):
        out = self.render(self.make_env(active=[
            task(1, "Pending", "1", due_date="2026-01-01", owner="human"),
            task(2, "Pending", "1", due_date="2026-12-01")]))
        self.assertIn("Timeline", out)
        self.assertIn("OVERDUE", out)  # 2026-01-01 < NOW


class TestLegibilityFixes(HtmlBase):
    """Regression tests for the 2026-06-24 renderer legibility/consistency pass:
    task count incl. archived, note-promotion over "(unnamed)", soft truncation."""

    def test_task_count_includes_archived_finished(self):
        # Header + footer count == ring/phase basis (active non-absorbed +
        # archived-finished), NOT len(active). Pins the 275-vs-867 contradiction.
        active = [task(1, "Pending", "1"), task(2, "In Progress", "1")]
        archived = [task(i, "Finished", "1") for i in range(10, 18)]  # 8 archived-finished
        out = self.render(self.make_env(active=active, archived=archived))
        self.assertIn("10 tasks · 1 phases · read-only view", out)  # 2 active + 8 archived
        self.assertIn("· 10 tasks · spec aligned", out)
        self.assertNotIn("2 tasks · 1 phases", out)  # the old len(active) behavior

    def test_finished_legend_labels_archived_count(self):
        # The Finished legend chip folds archived-finished in; unlabeled, the
        # number reads as wrong beside the active total (v5.2.0, styler 06-25).
        active = [task(1, "Pending", "1"),
                  task(2, "Finished", "1", task_verification={"result": "pass"})]
        archived = [task(i, "Finished", "1") for i in range(10, 18)]
        out = self.render(self.make_env(active=active, archived=archived))
        self.assertIn("(incl. 8 archived)", out)
        out_no_arch = self.render(self.make_env(active=active))
        self.assertNotIn("archived)</span>", out_no_arch)

    def test_acceptance_unnamed_criterion_promotes_note(self):
        # No criterion name → render the note as the description, never "(unnamed)".
        out = self.render(self.make_env(active=[task(1, "Pending", "1")],
            verification={"criteria": [
                {"status": "pass", "notes": "grep returns no body_shape field; migration done"}]}))
        self.assertNotIn("(unnamed)", out)
        self.assertIn("grep returns no body_shape field; migration done", out)

    def test_acceptance_long_note_not_hard_cut_at_80(self):
        # The old code did notes[:80] with no ellipsis; a sub-limit note renders whole.
        note = ("shoulder_hip_balance (4 options) at line 1254; waist_definition (3) "
                "at 1294; torso_leg_ratio (3) at 1329 all present and verified")
        self.assertGreater(len(note), 80)
        out = self.render(self.make_env(active=[task(1, "Pending", "1")],
            verification={"criteria": [{"criterion": "C1", "status": "pass", "notes": note}]}))
        self.assertIn(note, out)

    def test_acceptance_overlong_note_clips_with_title_fallback(self):
        # A note past the limit clips with an ellipsis AND keeps the full text in title=.
        note = "alpha " * 60  # ~360 chars, well past the 240 limit
        out = self.render(self.make_env(active=[task(1, "Pending", "1")],
            verification={"criteria": [{"criterion": "C1", "status": "pass", "notes": note.strip()}]}))
        self.assertIn("…", out)
        self.assertIn(f'title="{note.strip()}"', out)

    def test_graph_nodes_have_title_tooltip_and_arrowheads(self):
        out = self.render(self.make_env(active=self.chain(5)))
        self.assertIn('class="depgraph"', out)
        self.assertIn("marker-end=", out)        # arrowheads applied to edges
        self.assertIn('<marker id="ah"', out)    # marker defs present
        self.assertIn("<title>🤖 Task", out)      # node hover carries the full label

    def test_hero_ring_merges_status_segments(self):
        # One hero ring carries the status-segment colors (former donut) + the %
        # center text; the separate second-circle wrapper is gone.
        out = self.render(self.make_env(active=[task(1, "Finished", "1"), task(2, "Pending", "1")]))
        self.assertIn('class="ring"', out)
        self.assertIn('stroke="#2f7d4f"', out)   # Finished segment drawn on the ring
        self.assertIn('class="legend"', out)      # per-status counts beside it
        self.assertNotIn('class="donwrap"', out)  # old donut wrapper removed

    def test_notes_card_is_collapsible(self):
        out = self.render(self.make_env(active=[task(1, "Pending", "1")],
            sidecar={"user_notes": "Quick links: see the spec."}))
        self.assertIn('class="notesblock"', out)
        self.assertIn("<summary>Notes", out)

    def test_notes_autoprepends_live_spec_link(self):
        # Spec quick-link is derived from the current spec version each regen
        # (never hand-seeded → can't go stale). Fixture spec is spec_v1.md;
        # the <code>-wrapped link is unique to the Notes qlinks strip.
        out = self.render(self.make_env(active=[task(1, "Pending", "1")],
            sidecar={"user_notes": "Add wardrobe items: /wardrobe"}))
        self.assertIn('class="qlinks"', out)
        self.assertIn("<code>spec_v1.md</code>", out)


if __name__ == "__main__":
    unittest.main()
