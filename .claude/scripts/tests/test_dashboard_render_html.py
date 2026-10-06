"""Tests for dashboard-render.py --html (DEC-024).

The dashboard is a single read-only, offline, file://-openable HTML page.
These tests pin the load-bearing invariants: determinism, the META block in
<head> (freshness consumers string-parse it), the synthesis placeholders, the
inline-SVG charts, the adaptive dependency graph, and — critically — the
absence of any file://-breaking runtime dep (no type="module", no CDN
import/fetch). The only permitted external ref is the Google Fonts <link>.
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock
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

    def test_meta_spec_fingerprint_hashes_bytes_like_fingerprint_spec(self):
        # A7: for a CRLF spec META must carry the --spec hash, or /work Step 1a
        # would see a changed spec on every run
        root = self.make_env(active=[task(1, "Pending", "1")])
        spec_path = root / "spec_v1.md"
        spec_path.write_bytes(b"---\r\ntitle: CRLF Project\r\n---\r\n\r\n## Overview\r\n\r\nBody.\r\n")
        out = self.render(root)
        cli = subprocess.run([sys.executable, str(SCRIPT.with_name("fingerprint.py")), "--spec",
                              str(spec_path)], capture_output=True, text=True, timeout=10)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn(f"spec_fingerprint: {cli.stdout.strip()}\n", self.head(out))
        self.assertIn("<h1>CRLF Project</h1>", out)
        # positive control: the decoded-text hash (the old META value) differs here
        text_hash = hashlib.sha256(spec_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        self.assertNotEqual("sha256:" + text_hash, cli.stdout.strip())

    def test_meta_task_hash_matches_canonical(self):
        active = [task(1, "Pending", "1"), task(2, "Finished", "1")]
        out = self.render(self.make_env(active=active))
        expect = dr.canonical_task_hash(active)
        self.assertIn(f"task_hash: {expect}", out)


class TestPlaceholders(HtmlBase):
    def test_action_required_points_to_sidecar_augment_rows(self):
        # FB-105 made Action Required script-rendered; FB-118 moved its judgment rows
        # from a hand-edited HTML slot (wiped by every regen) to sidecar augment_rows[].
        out = self.render(self.make_env(active=[task(1, "Pending", "1")]))
        self.assertIn("<!-- Judgment rows come from sidecar augment_rows[]", out)
        self.assertIn("dashboard-regeneration.md", out)
        self.assertNotIn("CLAUDE: augment", out)
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
        active = [task(1, "Finished", "1", owner="both", user_review_pending=True,
                       task_verification=PASS, title="Review the drape output"),
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


PASS = {"result": "pass"}


class NeedsYouBase(HtmlBase):
    def card(self, out):
        """The Needs-you card only — task titles also render in Recent, the graph, etc."""
        start = out.index('<h2 class="st">Needs you</h2>')
        return out[start:out.index('<div class="side">', start)]

    def card_for(self, active=(), **kw):
        return self.card(self.render(self.make_env(active=active, **kw)))


class TestYourTasksCoverage(NeedsYouBase):
    """FB-118 (a): every task blocked on the user gets exactly one Your Tasks row.
    Precedence: On Hold > review pending > Blocked on the user > yours to do."""

    def test_both_owned_finished_review_row(self):
        # The old unreachable case: user_review_pending is set together with
        # Finished, but the loop scanned only non-Finished tasks.
        card = self.card_for([task(1, "Finished", owner="both", user_review_pending=True,
                                   task_verification=PASS, title="Drape review")])
        self.assertIn("Drape review — Claude's half verified; your review closes it", card)
        self.assertIn("<code>/work complete 1</code>", card)

    def test_claude_owned_finished_review_row(self):
        card = self.card_for([task(1, "Finished", owner="claude", user_review_pending=True,
                                   task_verification=PASS, title="Export flow")])
        self.assertIn("Export flow — verified; your review or testing closes it", card)
        self.assertIn("<code>/work complete 1</code>", card)
        self.assertNotIn("Claude's half", card)

    def test_blocked_both_or_human_row(self):
        for owner in ("both", "human"):
            with self.subTest(owner=owner):
                card = self.card_for([task(1, "Blocked", owner=owner, title="Pick a layout")])
                self.assertIn("Pick a layout — Blocked — needs you; "
                              "the blocker is in the task's notes", card)
                self.assertIn("<code>/work 1</code>", card)

    def test_escalated_claude_owned_blocked_row(self):
        card = self.card_for([task(1, "Blocked", verification_attempts=3, title="Flaky parser")])
        self.assertIn("Flaky parser — Blocked — verification escalated after 3 attempts; "
                      "the blocker is in the task's notes", card)
        self.assertIn("<code>/work 1</code>", card)
        self.assertNotIn("Blocked — needs you", card)

    def test_claude_owned_blocked_below_escalation_has_no_row(self):
        card = self.card_for([task(1, "Blocked", verification_attempts=2, title="Parser stall")])
        self.assertNotIn("Parser stall", card)
        self.assertIn("Nothing blocked on you right now", card)  # the card did render

    def test_one_row_per_task_first_match_wins(self):
        card = self.card_for([
            # On Hold beats a review flag and a human owner
            task(1, "On Hold", owner="human", user_review_pending=True, title="Parked review"),
            # a stale review flag on an unfinished task is ignored; Blocked wins
            task(2, "Blocked", owner="human", user_review_pending=True, title="Blocked review")])
        self.assertEqual(card.count("Parked review"), 1)
        self.assertIn("Parked review — On Hold; only you can resume it", card)
        self.assertEqual(card.count("Blocked review"), 1)
        self.assertIn("Blocked review — Blocked — needs you", card)

    def test_stale_review_flag_on_unfinished_task_is_ignored(self):
        # user_review_pending is only set with Finished; a leftover flag on reworked
        # work must not offer /work complete (that would skip re-verification)
        card = self.card_for([task(1, "In Progress", owner="claude", user_review_pending=True,
                                   title="Rework underway"),
                              task(2, "Finished", owner="claude", user_review_pending=True,
                                   task_verification=PASS, title="Ready for review")])
        self.assertNotIn("Rework underway", card)
        self.assertIn("Ready for review — verified; your review or testing closes it", card)  # positive control

    def test_yours_to_do_excludes_finished(self):
        card = self.card_for([task(1, "Finished", owner="human", task_verification=PASS,
                                   title="Done by you"),
                              task(2, "Pending", owner="human", title="Still yours")])
        self.assertNotIn("Done by you", card)
        self.assertIn("Still yours — yours to do", card)  # positive control

    def test_yours_to_do_excludes_broken_down_parent(self):
        # /work complete rejects a Broken Down parent; its subtasks carry the work
        card = self.card_for([task(1, "Broken Down", owner="human", subtasks=["2"],
                                   title="Parent job"),
                              task(2, "Pending", owner="human", title="Child job")])
        self.assertNotIn("Parent job", card)
        self.assertIn("Child job — yours to do", card)  # positive control


class TestVerificationPendingGate(NeedsYouBase):
    """Verification Pending waits while a review is open: the user's open review comes first."""

    def test_suppressed_while_a_review_is_pending(self):
        card = self.card_for([task(1, "Finished", task_verification=PASS),
                              task(2, "Finished", owner="both", user_review_pending=True,
                                   task_verification=PASS)])
        self.assertNotIn("Verification Pending", card)
        self.assertIn("your review closes it", card)

    def test_shown_when_no_review_is_pending(self):
        card = self.card_for([task(1, "Finished", task_verification=PASS),
                              task(2, "Finished", owner="both", task_verification=PASS)])
        self.assertIn("Verification Pending", card)


class TestAugmentRows(NeedsYouBase):
    """FB-118 (b): judgment rows live in sidecar augment_rows[], so regens keep them."""

    def with_rows(self, rows, active=None, **kw):
        active = [task(1, "Pending", "1")] if active is None else active
        return self.card_for(active, sidecar={"augment_rows": rows}, **kw)

    def also(self, card):
        return card[card.index("<b>Also Needs You</b>"):]  # the final sub-section

    def test_rows_render_as_final_subsection(self):
        card = self.with_rows([{"text": "Answer the cache-size question from the last session"}],
                              active=[task(1, "Pending", owner="human", title="Collect invoices")])
        self.assertIn("<li>Answer the cache-size question from the last session</li>",
                      self.also(card))
        self.assertLess(card.index("<b>Your Tasks</b>"), card.index("<b>Also Needs You</b>"))

    def test_text_is_escaped(self):
        card = self.with_rows([{"text": "Compare <script>x()</script> & pick one"}])
        self.assertIn("Compare &lt;script&gt;x()&lt;/script&gt; &amp; pick one", card)
        self.assertNotIn("<script>x()", card)

    def test_backtick_spans_become_code(self):
        card = self.with_rows([{"text": "Run `/work complete 7` once the scan looks right"},
                               {"text": "Then check `a<b` holds"}])
        self.assertIn("Run <code>/work complete 7</code> once the scan looks right", card)
        self.assertIn("<code>a&lt;b</code>", card)  # escaped before the span conversion

    def test_fyi_rows_muted_after_action_rows(self):
        card = self.with_rows([{"text": "Staging deploy is paused", "kind": "fyi"},
                               {"text": "Choose the export format", "kind": "action"},
                               {"text": "Confirm the vendor list"}])  # kind defaults to action
        self.assertIn('<li style="color:var(--soft)">FYI — Staging deploy is paused</li>', card)
        fyi = card.index("FYI — Staging deploy is paused")
        self.assertLess(card.index("<li>Choose the export format</li>"), fyi)
        self.assertLess(card.index("<li>Confirm the vendor list</li>"), fyi)
        self.assertLess(card.index("Choose the export format"),
                        card.index("Confirm the vendor list"))  # sidecar order kept

    def test_expiry_by_task_state(self):
        active = [task(1, "Finished", task_verification=PASS),
                  task(2, "Finished", owner="both", user_review_pending=True, task_verification=PASS),
                  task(3, "Absorbed", absorbed_into="4"),
                  task(4, "Pending")]
        card = self.with_rows([{"text": "Row for finished task", "task_id": "1"},
                               {"text": "Row for task in review", "task_id": "2"},
                               {"text": "Row for absorbed task", "task_id": "3"},
                               {"text": "Row for pending task", "task_id": "4"},
                               {"text": "Row for unknown task", "task_id": "999"}], active=active)
        self.assertNotIn("Row for finished task", card)
        self.assertNotIn("Row for absorbed task", card)
        for kept in ("Row for task in review", "Row for pending task", "Row for unknown task"):
            self.assertIn(kept, card)

    def test_archived_finished_task_expires_row(self):
        # archiving moves a task out of tasks/, but it is still known: no resurrection
        card = self.with_rows([{"text": "Row for archived task", "task_id": "5"},
                               {"text": "Control row"}], archived=[task(5, "Finished")])
        self.assertNotIn("Row for archived task", card)
        self.assertIn("Control row", card)

    def test_malformed_rows_skipped(self):
        card = self.with_rows(["just a string", 42, None, ["text"], {}, {"text": ""},
                               {"text": "   "}, {"text": 7}, {"task_id": "1"},
                               {"text": "The one valid row", "kind": 5, "task_id": ["x"]}])
        also = self.also(card)
        self.assertIn("<li>The one valid row</li>", also)
        self.assertEqual(also.count("<li"), 1)

    def test_non_list_augment_rows_ignored(self):
        for bad in ({"text": "a dict, not a list"}, "a string", 3, None):
            with self.subTest(augment_rows=bad):
                card = self.with_rows(bad)
                self.assertNotIn("Also Needs You", card)
                self.assertIn("Nothing blocked on you right now", card)

    def test_nothing_blocked_accounts_for_augment_rows(self):
        # no script rows + a rendered augment row: the empty-state line is wrong
        card = self.with_rows([{"text": "Reply to the open question about fonts"}])
        self.assertIn("Reply to the open question about fonts", card)
        self.assertNotIn("Nothing blocked on you right now", card)
        # no script rows + only an expired augment row: the empty-state line returns
        card = self.with_rows([{"text": "Stale row", "task_id": "1"}],
                              active=[task(1, "Finished", task_verification=PASS), task(2, "Pending")])
        self.assertNotIn("Stale row", card)
        self.assertNotIn("Also Needs You", card)
        self.assertIn("Nothing blocked on you right now", card)

    def test_fyi_only_rows_keep_nothing_blocked(self):
        # fyi rows ask nothing of the user, so only action rows displace the empty-state line
        card = self.with_rows([{"text": "Staging deploy is paused", "kind": "fyi"}])
        self.assertIn("FYI — Staging deploy is paused", card)  # the row did render
        self.assertIn("Nothing blocked on you right now", card)


class TestSidecarShape(HtmlBase):
    def test_non_object_sidecar_renders_like_missing(self):
        # Valid JSON that isn't an object used to crash render_full_html
        # (sidecar.get on a list). It now renders exactly as a missing sidecar.
        root = self.make_env(active=[task(1, "Pending", "1"),
                                     task(2, "Pending", "1", owner="human")])
        missing = self.render(root)
        self.assertIn("yours to do", missing)  # positive control: the card has content
        for raw in ("[]", '[{"text": "x"}]', '"notes"', "42", "true", "null"):
            with self.subTest(sidecar=raw):
                (root / "dashboard-state.json").write_text(raw, encoding="utf-8")
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    out = self.render(root)
                self.assertEqual(out, missing)
                if raw != "null":  # null loads as None, indistinguishable from absent
                    self.assertIn("dashboard-state.json is not a JSON object", err.getvalue())


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


class TestSpecDrift(NeedsYouBase):
    """FB-128: drift found by fingerprint.py's compute_drift() reaches the page: META
    drift_sections, the footer indicator, the pulse number and the Needs-you rows."""

    SPEC = "---\ntitle: Fixture Project\n---\n\n## Auth & <Login>\n\nBody.\n\n## Billing\n\nBody.\n"

    def env(self, active, deferrals=None):
        root = self.make_env(active=active, spec_text=self.SPEC)
        if deferrals is not None:
            (root / "drift-deferrals.json").write_text(json.dumps(deferrals), encoding="utf-8")
        return root

    def drifted(self, id, status="Finished", section="## Auth & <Login>"):
        kw = {"task_verification": PASS} if status == "Finished" else {}
        return task(id, status, "1", spec_section=section, section_fingerprint="sha256:stale", **kw)

    def footer(self, out):
        return out[out.index("<footer>"):out.index("</footer>")]

    def unchecked(self, compute=None):
        return mock.patch.object(dr, "_load_compute_drift", return_value=compute)

    def test_meta_drift_sections_follows_drift_deferrals(self):
        out = self.render(self.env([self.drifted(1), self.drifted(2, "Pending", "## Gone")]))
        self.assertIn("drift_deferrals: 0\ndrift_sections: 2\n", out[:out.index("</head>")])

    def test_meta_drift_sections_unchecked(self):
        with self.unchecked():
            out = self.render(self.env([self.drifted(1)]))
        self.assertIn("drift_deferrals: 0\ndrift_sections: unchecked\n", out)

    def test_footer_spec_aligned_when_clean(self):
        out = self.render(self.env([task(1, "Pending", "1")]))
        self.assertIn(" · spec aligned · 0 drift deferrals, 0 verification debt · ", self.footer(out))
        self.assertIn("drift_sections: 0\n", out)

    def test_footer_counts_changed_sections(self):
        out = self.render(self.env([self.drifted(1)], deferrals={"deferrals": [{"section": "## Billing"}]}))
        self.assertIn(" · ⚠️ 1 changed spec section(s), 1 drift deferrals, 0 verification debt · ",
                      self.footer(out))

    def test_footer_drift_unchecked(self):
        with self.unchecked():
            out = self.render(self.env([self.drifted(1)]))
        self.assertIn(" · drift unchecked · 0 drift deferrals, 0 verification debt · ", self.footer(out))
        self.assertNotIn("spec aligned", out)

    def test_pulse_drift_number_is_sections_plus_deferrals(self):
        big = '<div class="big" style="color:var(--{})">{}</div><div class="lbl">drift</div>'
        deferrals = [{"section": "## Billing"}]  # bare-list form
        out = self.render(self.env([self.drifted(1)], deferrals=deferrals))
        self.assertIn(big.format("bad", 2), out)
        with self.unchecked():
            out = self.render(self.env([self.drifted(1)], deferrals=deferrals))
        self.assertIn(big.format("bad", 1), out)  # unchecked: deferrals only
        self.assertIn(big.format("ok", 0), self.render(self.env([task(1, "Pending", "1")])))

    def test_needs_you_rows_drifted_then_missing_then_deferral(self):
        active = [self.drifted(3), self.drifted(1, "Pending"), self.drifted(2),
                  self.drifted(4, "Blocked", "## Gone"),
                  self.drifted(5, "Pending", "## Billing")]  # deferred below
        card = self.card(self.render(self.env(active, deferrals={"deferrals": [{"section": "## Billing"}]})))
        rows = ["<code>## Auth &amp; &lt;Login&gt;</code> changed since its tasks were built "
                "(2 Finished, 1 Pending) → run <code>/work</code> to reconcile",
                "<code>## Gone</code> is no longer in the spec (1 open task(s) reference it) "
                "→ run <code>/work</code> to reconcile",
                "1 deferred spec-drift reconciliation(s) → run <code>/work</code> to review"]
        self.assertIn("<b>Spec Drift</b>", card)
        positions = [card.index(r) for r in rows]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("<code>## Billing</code>", card)  # fully deferred: the deferral row covers it

    def test_drifted_row_counts_only_non_deferred_tasks(self):
        # contract order, not alphabetical: In Progress before Awaiting Verification
        active = [self.drifted(1), self.drifted(2), self.drifted(3, "Awaiting Verification"),
                  self.drifted(4, "In Progress")]
        card = self.card(self.render(self.env(active, deferrals={"deferrals": [
            {"section": "Auth & <Login>", "affected_tasks": ["1"]}]})))
        self.assertIn("were built (1 Finished, 1 In Progress, 1 Awaiting Verification) → run", card)

    def test_no_spec_drift_subsection_when_aligned(self):
        self.assertNotIn("Spec Drift", self.card(self.render(self.env([task(1, "Pending", "1")]))))

    def test_compute_drift_failure_reads_unchecked(self):
        def boom(_claude_dir):
            raise RuntimeError("boom")
        for compute in (boom, lambda _claude_dir: {"unexpected": 1}):
            with self.subTest(compute=compute), self.unchecked(compute), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                out = self.render(self.env([self.drifted(1)]))
                self.assertIn("drift_sections: unchecked", out)
                self.assertIn("drift unchecked", err.getvalue())

    def test_renderer_without_fingerprint_py_reads_unchecked(self):
        # The real fallback: the renderer copied alone, with no sibling fingerprint.py.
        with tempfile.TemporaryDirectory() as d:
            lone = Path(d) / "dashboard-render.py"
            lone.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            mod_spec = importlib.util.spec_from_file_location("lone_render", lone)
            lone_dr = importlib.util.module_from_spec(mod_spec)
            mod_spec.loader.exec_module(lone_dr)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                out = lone_dr.render_full_html(self.env([self.drifted(1)]), NOW)
        self.assertIn("drift_sections: unchecked", out)
        self.assertIn(" · drift unchecked · 0 drift deferrals, 0 verification debt · ", out)
        self.assertIn("fingerprint.py", err.getvalue())
        # positive control: beside its sibling, the same render checks drift
        self.assertIn("drift_sections: 1", self.render(self.env([self.drifted(1)])))

    def test_deferral_file_shapes_do_not_crash(self):
        for data, count in (([{"section": "## Billing"}], 1), ({"deferrals": 5}, 0), ("text", 0),
                            ({"deferrals": [{"section": "## Billing"}, "junk", {"section": 3}]}, 1)):
            with self.subTest(data=data):
                out = self.render(self.env([task(1, "Pending", "1")], deferrals=data))
                self.assertIn(f"drift_deferrals: {count}\n", out)


if __name__ == "__main__":
    unittest.main()
