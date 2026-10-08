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
        self.assertIn("<!-- CUSTOM VIEWS INSTRUCTIONS -->\n**By owner:** group tasks\n"
                      "<!-- END CUSTOM VIEWS INSTRUCTIONS -->", out)
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


def recorded_md(num, title="Agent choice", status="recorded", decided_by="implement-agent"):
    """An agent-recorded decision (FB-129): no Select an Option section."""
    return (f"---\nid: DEC-{num:03d}\ntitle: {title}\nstatus: {status}\ndecided: 2026-06-01\n"
            f"decided_by: {decided_by}\n---\n\n## Decision\n\n**Selected:** A\n")


class TestRecordedDecisions(NeedsYouBase):
    """FB-129: status `recorded` = agent-made, verified, not yet ratified. Resolved
    for dependencies, not "Decided", and one Needs-you row for the whole project."""

    RATIFY = "ratification"

    def test_recorded_is_resolved_for_decision_dependencies(self):
        self.assertNotIn("recorded", dr.UNRESOLVED_DECISION)
        decs = [{"id": "DEC-001", "title": "Q", "status": "recorded", "selected": None, "file": "x.md"}]
        self.assertEqual(dr.resolved_decision_ids(decs), {"DEC-001"})
        nodes, _ = dr.build_graph([task(1, "Pending", decision_dependencies=["DEC-001"])], decs)
        self.assertNotIn("DDEC-001", nodes)  # no decision node gates the task

    def test_human_task_depending_on_recorded_decision_is_actionable(self):
        active = [task(1, "Pending", "1", owner="human", title="Sign the form",
                       decision_dependencies=["DEC-001"])]
        card = self.card_for(active, decisions=[recorded_md(1)])
        self.assertIn("Sign the form", card)
        self.assertIn("/work complete 1", card)
        self.assertNotIn("unresolved", card)
        # positive control: the same task behind a proposed record is not listed
        card = self.card_for(active, decisions=[recorded_md(1, status="proposed")])
        self.assertNotIn("Sign the form", card)

    def test_recorded_decision_does_not_block_a_phase(self):
        active = [task(1, "Pending", "1"),
                  task(2, "Pending", "2", decision_dependencies=["DEC-001"])]
        out = self.render(self.make_env(active=active, decisions=[recorded_md(1)]))
        self.assertNotIn("Blocked (DEC-001)", out)
        out = self.render(self.make_env(active=active,
                                        decisions=[recorded_md(1, status="proposed")]))
        self.assertIn("Blocked (DEC-001)", out)  # positive control

    def test_single_record_renders_one_singular_row(self):
        card = self.card_for([task(1, "Pending", "1")], decisions=[recorded_md(1)])
        self.assertIn(
            '<li>1 agent decision awaits ratification: '
            '<a href="support/decisions/decision-001-x.md">DEC-001</a> — run '
            '<code>/work ratify all</code> (or <code>/work ratify DEC-NNN</code>)</li>', card)
        self.assertEqual(card.count(self.RATIFY), 1)
        self.assertNotIn("Nothing blocked on you right now", card)

    def test_several_records_share_one_row_in_id_order(self):
        card = self.card_for([task(1, "Pending", "1")],
                             decisions=[recorded_md(n) for n in (3, 1, 2)])
        self.assertEqual(card.count(self.RATIFY), 1)
        self.assertIn("3 agent decisions await ratification: ", card)
        self.assertLess(card.index(">DEC-001<"), card.index(">DEC-002<"))
        self.assertLess(card.index(">DEC-002<"), card.index(">DEC-003<"))
        self.assertNotIn("more", card[card.index(self.RATIFY):])

    def test_more_than_eight_records_truncate_with_count(self):
        card = self.card_for([task(1, "Pending", "1")],
                             decisions=[recorded_md(n) for n in range(1, 12)])
        self.assertEqual(card.count(self.RATIFY), 1)
        self.assertIn("11 agent decisions await ratification: ", card)
        self.assertIn(">DEC-008</a>, +3 more — run", card)
        self.assertNotIn("DEC-009", card)

    def test_exactly_eight_records_list_all_ids(self):
        card = self.card_for([task(1, "Pending", "1")],
                             decisions=[recorded_md(n) for n in range(1, 9)])
        self.assertIn(">DEC-008</a> — run", card)

    def test_row_escapes_markup_in_the_record_id(self):
        md = recorded_md(1).replace("id: DEC-001", "id: DEC-<b>")
        card = self.card_for([task(1, "Pending", "1")], decisions=[md])
        row = card[card.rindex("<li>", 0, card.index(self.RATIFY)):]
        row = row[:row.index("</li>")]
        self.assertIn("1 agent decision awaits ratification: ", row)
        self.assertNotIn("<b>", row)
        self.assertIn(">DEC-&lt;b&gt;</a>", row)

    def test_no_recorded_records_no_row(self):
        card = self.card_for([task(1, "Pending", "1")],
                             decisions=[decision_md(1, "Pick", "approved", "A")])
        self.assertNotIn(self.RATIFY, card)
        self.assertIn("Nothing blocked on you right now", card)

    def test_legacy_agent_approved_records_get_no_row(self):
        decs = [recorded_md(1, status="approved"), recorded_md(2, status="implemented")]
        out = self.render(self.make_env(active=[task(1, "Pending", "1")], decisions=decs))
        self.assertNotIn(self.RATIFY, self.card(out))
        self.assertIn("decisions_recorded: 0\n", out)
        self.assertIn("decisions_approved: 2\n", out)

    def test_row_sits_with_the_unresolved_decision_rows(self):
        card = self.card_for([task(1, "Pending", "1")],
                             decisions=[recorded_md(1), decision_md(2, "Open", "proposed")])
        self.assertEqual(card.count("<b>Decisions</b>"), 1)
        start = card.index("<b>Decisions</b>")
        block = card[start:card.index("</ul>", start)]
        self.assertIn("unresolved", block)
        self.assertIn(self.RATIFY, block)

    def test_meta_counts_recorded_separately_from_approved(self):
        decs = [recorded_md(1), recorded_md(2, decided_by="orchestrator"),
                decision_md(3, "Pick", "approved", "A")]
        out = self.render(self.make_env(active=[task(1, "Pending", "1")], decisions=decs))
        head = out[:out.index("</head>")]
        self.assertIn("decision_count: 3\n", head)
        self.assertIn("decisions_recorded: 2\n", head)
        self.assertIn("decisions_approved: 1\n", head)

    def test_ratifying_changes_the_meta_block(self):
        # the freshness signal decisions already have (META counts) covers the row
        root = self.make_env(active=[task(1, "Pending", "1")], decisions=[recorded_md(1)])
        before = self.render(root)
        path = root / "support" / "decisions" / "decision-001-x.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "status: recorded", "status: approved\nratified: 2026-06-02"), encoding="utf-8")
        after = self.render(root)
        self.assertIn("decisions_recorded: 1\n", before)
        self.assertIn("decisions_recorded: 0\n", after)
        self.assertNotIn(self.RATIFY, self.card(after))

    def test_display_label_and_decisions_section(self):
        self.assertEqual(dr.DECISION_STATUS_DISPLAY["recorded"], "Recorded")
        out = self.render(self.make_env(
            active=[task(1, "Pending", "1")],
            decisions=[recorded_md(1), decision_md(2, "Pick", "approved", "A")]))
        self.assertIn('data-status="recorded"', out)
        self.assertIn('<span class="bdg warn">Recorded</span>', out)
        self.assertIn("1 decided · 1 recorded · 0 superseded", out)  # not counted as decided
        self.assertIn('data-f="recorded"', out)

    def test_decisions_section_unchanged_without_recorded(self):
        out = self.render(self.make_env(
            active=[task(1, "Pending", "1")],
            decisions=[decision_md(1, "Pick", "approved", "A")]))
        self.assertIn("1 decided · 0 superseded", out)
        self.assertNotIn('data-f="recorded"', out)


NON_OBJECTS = ("x", 5, 1.5, True, [], [1], ["a"], [{"a": 1}])


class TestNonObjectInputs(HtmlBase):
    """A state file or sidecar field of the wrong JSON shape reads as absent, with a
    one-line warning where a whole file or sidecar object is replaced. Each of these
    used to exit 1 on an AttributeError or TypeError."""

    def render_err(self, root):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = self.render(root)
        return out, err.getvalue()

    def two_phase(self, **kw):
        # phase 1 complete, phase 2 open: the Phase Transitions row is reachable
        return self.make_env(active=[task(1, "Finished", "1", task_verification={"result": "pass"}),
                                     task(2, "Pending", "2", owner="human")], **kw)

    def assert_like_baseline(self, baseline, variants, write, warning=None):
        for value in variants:
            with self.subTest(value=value):
                out, err = self.render_err(write(value))
                self.assertEqual(out, baseline)
                if warning:
                    self.assertIn(warning, err)
                    self.assertEqual(err.count("\n"), 1)
                else:
                    self.assertEqual(err, "")  # "skipped without a warning"

    def test_non_object_verification_result_renders_like_missing(self):
        baseline = self.render(self.two_phase())
        self.assertNotIn("Acceptance criteria", baseline)
        with_result = self.render(self.two_phase(verification={"criteria_passed": 1, "criteria_failed": 0}))
        self.assertIn("Acceptance criteria", with_result)  # positive control: the file is read
        self.assert_like_baseline(baseline, NON_OBJECTS, lambda v: self.two_phase(verification=v),
                                  "verification-result.json is not a JSON object")

    def test_non_object_section_toggles_render_like_defaults(self):
        notes = {"user_notes": "a note"}
        baseline = self.render(self.two_phase(sidecar=notes))
        off = self.render(self.two_phase(sidecar={**notes, "section_toggles": {"notes": False}}))
        self.assertNotEqual(off, baseline)  # positive control: an object is honoured
        self.assert_like_baseline(
            baseline, NON_OBJECTS, lambda v: self.two_phase(sidecar={**notes, "section_toggles": v}),
            "dashboard-state.json section_toggles is not a JSON object")
        out, err = self.render_err(self.two_phase(sidecar={**notes, "section_toggles": None}))
        self.assertEqual((out, err), (baseline, ""))  # null reads as absent, no warning

    def test_non_object_audit_digest_renders_like_missing(self):
        baseline = self.render(self.two_phase(sidecar={}))
        self.assertNotIn("Audit Findings", baseline)
        digest = {"items": [{"id": "A1", "status": "pending", "description": "finding"}]}
        self.assertIn("Audit Findings", self.render(self.two_phase(sidecar={"audit_digest": digest})))
        self.assert_like_baseline(
            baseline, NON_OBJECTS, lambda v: self.two_phase(sidecar={"audit_digest": v}),
            "dashboard-state.json audit_digest is not a JSON object")

    def test_malformed_audit_digest_fields_are_skipped(self):
        good = {"id": "A1", "status": "pending", "description": "finding"}
        for digest in ({"items": "x"}, {"items": 5}, {"items": {"a": 1}}):
            with self.subTest(digest=digest):
                self.assertNotIn("Audit Findings", self.render(self.two_phase(sidecar={"audit_digest": digest})))
        for digest in ({"items": [good, "x", 5, None, [1]]},
                       {"items": [good, {"id": ["A2"], "status": "pending", "description": "odd id"}],
                        "dismissed_ids": [["A2"], {"a": 1}]},
                       {"items": [good], "dismissed_ids": 5}, {"items": [good], "dismissed_ids": "A1"}):
            with self.subTest(digest=digest):
                self.assertIn("finding", self.render(self.two_phase(sidecar={"audit_digest": digest})))
        dismissed = self.render(self.two_phase(sidecar={"audit_digest": {"items": [good], "dismissed_ids": ["A1"]}}))
        self.assertNotIn("finding", dismissed)  # a well-formed dismissal still applies

    def test_non_object_phase_gates_read_as_not_approved(self):
        baseline = self.render(self.two_phase(sidecar={}))
        self.assertIn("approve the gate", baseline)
        approved = self.render(self.two_phase(sidecar={"phase_gates": {"1→2": {"status": "approved"}}}))
        self.assertNotIn("approve the gate", approved)  # positive control
        self.assert_like_baseline(
            baseline, NON_OBJECTS, lambda v: self.two_phase(sidecar={"phase_gates": v}),
            "dashboard-state.json phase_gates is not a JSON object")
        # a gate object counts as approved only with status "approved"
        for gate in ({"status": "active"}, {"status": "pending"}, {}, {"status": None}):
            with self.subTest(gate=gate):
                out, err = self.render_err(self.two_phase(sidecar={"phase_gates": {"1→2": gate}}))
                self.assertEqual((out, err), (baseline, ""))
        # one gate entry of the wrong shape: not approved, no warning
        self.assert_like_baseline(baseline, NON_OBJECTS + (None,),
                                  lambda v: self.two_phase(sidecar={"phase_gates": {"1→2": v}}))

    def test_non_object_version_json_renders_like_missing(self):
        root = self.two_phase()
        (root / "version.json").unlink()
        baseline = self.render(root)
        self.assertIn("template_version: —", baseline)

        def write(value):
            (root / "version.json").write_text(json.dumps(value), encoding="utf-8")
            return root
        self.assert_like_baseline(baseline, NON_OBJECTS, write, "version.json is not a JSON object")

    def test_malformed_criteria_entries_are_skipped(self):
        good = {"criterion": "Loads", "status": "pass", "notes": "ok"}
        out = self.render(self.two_phase(verification={"criteria": [good, "x", 5, None, [1]]}))
        self.assertIn("Acceptance criteria · 1/1 passed", out)
        # nothing usable in criteria[]: the summary counts, when they are numbers
        out = self.render(self.two_phase(verification={"criteria": ["x"], "criteria_passed": 2,
                                                       "criteria_failed": 1}))
        self.assertIn("<b>2/3</b> criteria passed", out)
        # whole floats are counts too (the schema says "Number"), printed as ints
        out = self.render(self.two_phase(verification={"criteria_passed": 2.0, "criteria_failed": 1.0}))
        self.assertIn("<b>2/3</b> criteria passed", out)
        for passed, failed in (("2", 1), (2, "x"), ([2], 1), (2, {}), (True, 1), (2, None),
                               (2.5, 1), (2, 0.5), (2, False), (float("inf"), 1), (2, float("nan"))):
            with self.subTest(passed=passed, failed=failed):
                out = self.render(self.two_phase(verification={"criteria_passed": passed,
                                                               "criteria_failed": failed}))
                self.assertNotIn("Acceptance criteria", out)

    def test_malformed_spec_index_falls_back_to_link_only(self):
        baseline = self.render(self.two_phase())
        self.assertIn("Open the spec file to browse its sections.", baseline)
        self.assert_like_baseline(baseline, NON_OBJECTS, lambda v: self.two_phase(spec_index=v),
                                  "spec_v1.index.json is not a JSON object")
        out = self.render(self.two_phase(spec_index={"sections": [{"heading": "## Overview"}, "x", 5, None]}))
        self.assertIn("1 sections", out)
        self.assertIn("<li>Overview</li>", out)

    def test_malformed_archive_index_reads_as_no_archive(self):
        root = self.two_phase()
        (root / "tasks" / "archive").mkdir()
        index = root / "tasks" / "archive" / "archive-index.json"
        index.write_text(json.dumps({"tasks": []}), encoding="utf-8")
        baseline = self.render(root)
        index.write_text(json.dumps({"tasks": [{"id": "90"}]}), encoding="utf-8")
        self.assertNotEqual(self.render(root), baseline)  # positive control: entries count

        def write(value):
            index.write_text(json.dumps(value), encoding="utf-8")
            return root
        self.assert_like_baseline(baseline, NON_OBJECTS + ({"tasks": 5}, {"tasks": None}, {"tasks": "x"}),
                                  write, "archive-index.json has no tasks list")

    def test_non_string_custom_views_instructions_read_as_empty(self):
        on = {"section_toggles": {"custom_views": True}}
        baseline = self.render(self.two_phase(sidecar=on))
        self.assertIn("<!-- CUSTOM VIEWS INSTRUCTIONS -->\n\n<!-- END", baseline)
        self.assert_like_baseline(
            baseline, (5, 1.5, True, [1], {"a": 1}),
            lambda v: self.two_phase(sidecar={**on, "custom_views_instructions": v}))

    def test_malformed_archive_index_entry_fields_do_not_crash(self):
        # R1: an index entry is state-file content; a phase_name that isn't a string
        # is not counted as a name (it used to raise in build_phases)
        root = self.make_env(active=[task(1, "Pending", "1", phase_name="One")])
        (root / "tasks" / "archive").mkdir()
        index = root / "tasks" / "archive" / "archive-index.json"
        entry = {"id": "90", "status": "Finished", "phase": "1"}
        index.write_text(json.dumps({"tasks": [entry]}), encoding="utf-8")
        baseline = self.render(root)
        self.assertIn("2 tasks", baseline)  # positive control: the entry is counted
        self.assertIn("One", baseline)

        def write(value):
            index.write_text(json.dumps({"tasks": [{**entry, "phase_name": value}]}), encoding="utf-8")
            return root
        self.assert_like_baseline(baseline, (["x"], 5, 1.5, True, {"a": 1}, [], None, ""), write)
        # a string name still counts: two votes for "Two" outrank the active task's "One"
        index.write_text(json.dumps({"tasks": [{**entry, "phase_name": "Two"},
                                               {**entry, "id": "91", "phase_name": "Two"}]}),
                         encoding="utf-8")
        self.assertIn("Two", self.render(root))

    def test_non_string_task_phase_name_is_not_a_name(self):
        named = self.render(self.make_env(active=[task(1, "Pending", "1"),
                                                  task(2, "Pending", "1", phase_name="One")]))
        self.assertIn("One", named)
        for value in (["x"], 5, {"a": 1}, True):
            with self.subTest(value=value):
                out = self.render(self.make_env(active=[task(1, "Pending", "1", phase_name=value),
                                                        task(2, "Pending", "1", phase_name="One")]))
                self.assertEqual(out, named)

    def test_non_string_user_notes_read_as_empty(self):
        # R5: null used to render a Notes card holding <p>None</p>
        baseline = self.render(self.two_phase(sidecar={}))
        self.assertNotIn("notescard\">", baseline)
        self.assertIn("notescard\">", self.render(self.two_phase(sidecar={"user_notes": "a note"})))
        self.assert_like_baseline(baseline, (None,), lambda v: self.two_phase(sidecar={"user_notes": v}))
        self.assert_like_baseline(
            baseline, (False, True, 5, 0, [], ["a"], {}, {"a": 1}),
            lambda v: self.two_phase(sidecar={"user_notes": v}),
            "dashboard-state.json user_notes is not a string")
        # notes toggled off: the field is not read, so nothing is printed
        off = {"section_toggles": {"notes": False}}
        self.assert_like_baseline(self.render(self.two_phase(sidecar=off)), (5, ["a"]),
                                  lambda v: self.two_phase(sidecar={**off, "user_notes": v}))

    def test_object_fields_are_not_read_with_action_required_off(self):
        off = {"section_toggles": {"action_required": False}}
        baseline = self.render(self.two_phase(sidecar=off))
        for field in ("phase_gates", "audit_digest"):
            self.assert_like_baseline(baseline, ("x", [1]),
                                      lambda v: self.two_phase(sidecar={**off, field: v}))

    def test_cli_exits_zero_with_a_warning_on_a_wrong_shaped_file(self):
        root = self.two_phase(verification=["not", "an", "object"])
        proc = subprocess.run([sys.executable, str(SCRIPT), "--html", "--claude-dir", str(root),
                               "--now", "2026-06-24T00:00:00Z"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr.strip(),
                         "warning: verification-result.json is not a JSON object; rendering as if absent")
        self.assertTrue(proc.stdout.startswith("<!doctype html>"))
        self.assertEqual(proc.stdout, self.render(self.two_phase()) + "\n")

    def test_null_dependency_lists_in_a_phase_that_cannot_start(self):
        # R2: phase 1 still open, so phase_status() goes on to its dependency checks
        def env(extra=(), **kw):
            return self.make_env(
                active=[task(0, "Finished", "1", task_verification={"result": "pass"}),
                        task(1, "Pending", "1"), task(2, "Pending", "2", **kw), *extra],
                decisions=[decision_md(1, "Pick", "proposed")])
        # eligible early: explicit dependencies met, decision list null
        eligible = self.render(env(dependencies=["0"]))
        self.assertIn("Partially Actionable (1 eligible: 2)", eligible)
        self.assertEqual(self.render(env(dependencies=["0"], decision_dependencies=None)), eligible)
        # not eligible, nothing gated: the blockers scan reads the null list
        waiting = self.render(env())
        self.assertIn("Blocked (awaiting prior phase)", waiting)
        for value in (None, 0, False, ""):
            with self.subTest(value=value):
                self.assertEqual(self.render(env(decision_dependencies=value)), waiting)
                self.assertEqual(self.render(env(dependencies=value)), waiting)
        # one task gated by a real unresolved decision, the other with a null list
        gated = [task(3, "Pending", "2", decision_dependencies=["DEC-001"])]
        mixed = self.render(env(extra=gated))
        self.assertIn("Blocked (DEC-001 gates 1 of 2; rest awaiting prior phase)", mixed)
        self.assertEqual(self.render(env(extra=gated, decision_dependencies=None)), mixed)

    def test_null_dependency_lists_read_as_empty(self):
        # null (and other falsy values) for either list; a truthy non-list still raises
        def env(**kw):
            return self.make_env(active=[task(1, "Finished", "1", task_verification={"result": "pass"})]
                                 + [task(i, "Pending", "2", **kw) for i in (2, 3)])
        baseline = self.render(env())
        for field in ("dependencies", "decision_dependencies"):
            for value in (None, 0, False, ""):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.render(env(**{field: value})), baseline)


class TestNotesHeadings(HtmlBase):
    """ATX headings in sidecar user_notes render as <h3>..<h6> inside the Notes card."""

    def notes(self, text):
        return dr._html_notes(text)

    def test_levels_map_below_the_page_headings(self):
        for hashes, tag, size in (("#", "h3", 17), ("##", "h4", 16), ("###", "h5", 15),
                                  ("####", "h6", 14), ("#####", "h6", 14), ("######", "h6", 14)):
            with self.subTest(hashes=hashes):
                out = self.notes(f"{hashes} Quick links")
                self.assertRegex(out, rf'^<{tag} style="[^"]*font-size:{size}px[^"]*">Quick links</{tag}>$')
                self.assertNotIn("#", out)
        for out in (self.notes("# Top"), self.notes("###### Deep")):
            self.assertNotRegex(out, r"<h[12][ >]")

    def test_heading_overrides_the_uppercase_card_label_rule(self):
        # .mini h3 (the card-label rule) would upper-case a command in a heading
        self.assertIn("text-transform:uppercase", re.search(r"\.mini h3\{[^}]*\}", dr.CSS_HTML).group(0))
        self.assertIn("text-transform:none", self.notes("# Run /model opus"))

    def test_heading_text_is_escaped(self):
        out = self.notes('### <script>alert(1)</script> & "more"')
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;more&quot;</h5>", out)
        self.assertNotIn("<script>", out)

    def test_inline_formatting_inside_a_heading(self):
        out = self.notes("## **Bold** `code` [docs](docs/x.md)")
        self.assertIn('<strong>Bold</strong> <code>code</code> <a href="docs/x.md">docs</a></h4>', out)

    def test_hash_without_a_space_is_not_a_heading(self):
        for line in ("#hashtag", "#1 priority", "#", "###", "####### seven hashes", "see issue # 4",
                     "`# in code`"):
            with self.subTest(line=line):
                self.assertEqual(self.notes(line), f"<p>{dr._mdi(line)}</p>")

    def test_closing_hashes_are_dropped(self):
        self.assertIn(">Title</h4>", self.notes("## Title ##"))
        self.assertIn(">C#</h3>", self.notes("# C#"))
        # only a run at the END of the line is a closing run
        self.assertIn(">a # b</h3>", self.notes("# a # b"))
        self.assertIn(">Issue #4 and #5</h4>", self.notes("## Issue #4 and #5 ##"))

    def test_heading_with_no_text_stays_a_paragraph(self):
        for line in ("## ##", "# #", "### ######", "#  ##"):
            with self.subTest(line=line):
                self.assertEqual(self.notes(line), f"<p>{line}</p>")

    def test_headings_are_larger_than_the_card_body_text(self):
        # body text in the card: paragraphs inherit body's 14.5px, list items are 13px
        self.assertRegex(dr.CSS_HTML, r"(?m)^body\{[^}]*font-size:14\.5px")
        self.assertIn(".notescard li{margin:3px 0;font-size:13px}", dr.CSS_HTML)
        self.assertNotRegex(dr.CSS_HTML, r"\.(mini|notescard)( p)?\{[^}]*font-size")
        sizes = [int(re.search(r"font-size:(\d+)px", self.notes(f"{'#' * n} x")).group(1))
                 for n in range(1, 7)]
        self.assertEqual(sizes, [17, 16, 15, 14, 14, 14])
        self.assertGreater(sizes[2], 14.5)   # h3..h5 above paragraph text
        self.assertGreater(min(sizes), 13)   # every level above list-item text

    def test_full_heading_style(self):
        self.assertEqual(
            self.notes("### Quick links"),
            '<h5 style="margin:12px 0 4px;font-size:15px;font-weight:600;line-height:1.3;'
            'text-transform:none;letter-spacing:0;color:var(--ink)">Quick links</h5>')

    def headings(self, text):
        return re.findall(r"<h\d[^>]*>(.*?)</h\d>", self.notes(text))

    def test_fence_closes_only_on_its_own_marker(self):
        ticks, tildes = "`" * 3, "~" * 3
        text = "\n".join([ticks, "# a", tildes, "# b", ticks, "# c", tildes, "# d", tildes, "# e"])
        self.assertEqual(self.headings(text), ["c", "e"])
        # an info string opens a fence but does not close one
        self.assertEqual(self.headings("\n".join([ticks + "python", "# a", ticks + "python", "# b",
                                                   ticks, "# c"])), ["c"])
        self.assertEqual(self.headings("\n".join([ticks * 2, "# a", ticks, "# b"])), ["b"])
        # a run shorter than three does not close
        self.assertEqual(self.headings("\n".join([ticks, "`" * 2, "# a", ticks, "# b"])), ["b"])

    def test_inline_triple_backtick_span_does_not_open_a_fence(self):
        ticks = "`" * 3
        self.assertEqual(self.headings(f"{ticks}code{ticks} then text\n# Still a heading"),
                         ["Still a heading"])
        # a marker later in a line is not a fence either
        self.assertEqual(self.headings(f"see {ticks} here\n# One\ntext ~~~\n# Two"), ["One", "Two"])

    def test_heading_closes_an_open_list_and_blocks_keep_order(self):
        out = self.notes("### One\n- a\n- b\n### Two\ntext\n\n- c")
        tags = re.sub(r' style="[^"]*"', "", out)
        self.assertEqual(tags, "<h5>One</h5><ul><li>a</li><li>b</li></ul><h5>Two</h5><p>text</p>"
                               "<ul><li>c</li></ul>")

    def test_hash_line_inside_a_fence_is_not_a_heading(self):
        out = self.notes("```\n# a shell comment\n```\n# Real heading\n~~~\n## also not\n~~~")
        self.assertIn("<p># a shell comment</p>", out)
        self.assertIn("<p>## also not</p>", out)
        self.assertIn(">Real heading</h3>", out)
        self.assertEqual(len(re.findall(r"<h\d", out)), 1)

    def test_notes_without_headings_render_as_before(self):
        text = "**Quick Links:**\n- [a](b)\n* `c`\n\nplain #tag line"
        self.assertEqual(self.notes(text),
                         '<p><strong>Quick Links:</strong></p><ul><li><a href="b">a</a></li>'
                         "<li><code>c</code></li></ul><p>plain #tag line</p>")

    def test_heading_renders_inside_the_notes_card(self):
        out = self.render(self.make_env(active=[task(1, "Pending", "1")],
                                        sidecar={"user_notes": "### Retired Features\n- none"}))
        card = out[out.index('<div class="mini notescard">'):]
        self.assertRegex(card, r"<h5 style=[^>]*>Retired Features</h5><ul><li>none</li></ul>")
        self.assertNotIn("### Retired", out)


BAD_BYTES = b"caf\xe9"  # Latin-1, not valid UTF-8
CODEC = "'utf-8' codec can't decode byte 0xe9"


class TestNonUtf8Files(HtmlBase):
    """A file that isn't valid UTF-8 is unreadable: one warning, and the render goes on
    as it does for any other unreadable file of that kind. Each used to exit 1 on a
    UnicodeDecodeError."""

    def env(self, **kw):
        kw.setdefault("active", [task(1, "Finished", "1", task_verification={"result": "pass"}),
                                 task(2, "Pending", "2", owner="human")])
        return self.make_env(**kw)

    def render_err(self, root):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = self.render(root)
        return out, err.getvalue()

    def assert_unreadable(self, root, baseline, warning):
        out, err = self.render_err(root)
        self.assertEqual(out, baseline)
        self.assertEqual(err.count("\n"), 1, err)
        self.assertTrue(err.startswith(f"warning: {warning}: {CODEC}"), err)

    def test_state_json_reads_as_absent(self):
        baseline = self.render(self.env())
        for name in ("verification-result.json", "dashboard-state.json", "drift-deferrals.json",
                     "spec_v1.index.json"):
            with self.subTest(name=name):
                root = self.env()
                (root / name).write_bytes(BAD_BYTES)
                self.assert_unreadable(root, baseline, f"unreadable {name}")
        root = self.env()
        (root / "version.json").unlink()
        no_version = self.render(root)
        (root / "version.json").write_bytes(BAD_BYTES)
        self.assert_unreadable(root, no_version, "unreadable version.json")
        # through the CLI: exit 0
        proc = subprocess.run([sys.executable, str(SCRIPT), "--html", "--claude-dir", str(root),
                               "--now", "2026-06-24T00:00:00Z"], capture_output=True, text=True)
        self.assertEqual((proc.returncode, proc.stdout), (0, no_version + "\n"))
        self.assertIn("warning: unreadable version.json", proc.stderr)

    def test_task_file_is_skipped(self):
        root = self.env()
        baseline = self.render(root)
        (root / "tasks" / "task-3.json").write_bytes(BAD_BYTES)
        self.assert_unreadable(root, baseline, "skipping unreadable task-3.json")
        out, err = io.StringIO(), io.StringIO()  # --task-hash reads the same files
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = dr.main(["--task-hash", "--tasks-dir", str(root / "tasks")])
        self.assertEqual(code, 0)
        self.assertIn(out.getvalue().strip(), baseline)
        self.assertIn("warning: skipping unreadable task-3.json", err.getvalue())

    def test_archived_task_file_is_skipped_and_archive_index_ignored(self):
        root = self.env(archived=[task(90, "Finished", "1")])
        baseline = self.render(root)
        self.assertIn("3 tasks", baseline)  # positive control: the archive is read
        (root / "tasks" / "archive" / "task-91.json").write_bytes(BAD_BYTES)
        self.assert_unreadable(root, baseline, "skipping unreadable task-91.json")
        root = self.env()
        (root / "tasks" / "archive").mkdir()
        baseline = self.render(root)
        (root / "tasks" / "archive" / "archive-index.json").write_bytes(BAD_BYTES)
        self.assert_unreadable(root, baseline, "unreadable archive-index.json")

    def test_decision_record_is_skipped(self):
        root = self.env(decisions=[decision_md(1, "Pick", "approved", "A")])
        baseline = self.render(root)
        self.assertIn("DEC-001", baseline)
        (root / "support" / "decisions" / "decision-002-latin1.md").write_bytes(
            b"---\nid: DEC-002\ntitle: caf\xe9\nstatus: proposed\n---\n")
        self.assert_unreadable(root, baseline, "skipping unreadable decision-002-latin1.md")

    def test_spec_reads_as_unreadable(self):
        # the existing unreadable-spec result: the version is kept, the rest is unknown.
        # Baseline: a spec path that can't be read (a directory), with drift unchecked,
        # because fingerprint.py can't read the bytes either.
        root = self.env()
        (root / "spec_v1.md").unlink()
        (root / "spec_v1.md").mkdir()
        with mock.patch.object(dr, "load_drift_check", return_value=None), \
                contextlib.redirect_stderr(io.StringIO()):
            baseline = self.render(root)
        self.assertIn("spec_version: spec_v1\nspec_status: —\nspec_fingerprint: —\n", baseline)
        (root / "spec_v1.md").rmdir()
        (root / "spec_v1.md").write_bytes(b"---\ntitle: caf\xe9\n---\n\n## Overview\n")
        out, err = self.render_err(root)
        self.assertEqual(out, baseline)
        self.assertIn(f"warning: unreadable spec_v1.md: {CODEC}", err)
        self.assertIn("warning: drift unchecked: compute_drift failed", err)
        self.assertEqual(err.count("\n"), 2, err)

    def test_feedback_file_reads_as_absent(self):
        root = self.env()
        baseline = self.render(root)
        (root / "support" / "feedback").mkdir()
        fb = root / "support" / "feedback" / "feedback.md"
        fb.write_text("## FB-001\n**Status:** new\n", encoding="utf-8")
        self.assertIn("1 feedback items", self.render(root))  # positive control
        fb.write_bytes(b"## FB-001\n**Status:** new\ncaf\xe9\n")
        self.assert_unreadable(root, baseline, "unreadable feedback.md")


if __name__ == "__main__":
    unittest.main()
