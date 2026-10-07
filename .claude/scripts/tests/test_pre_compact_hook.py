#!/usr/bin/env python3
"""End-to-end tests for .claude/hooks/pre-compact-handoff.sh via subprocess.

The hook writes a structural handoff from the task files when Claude Code
compacts. Pins its guarantees and the whole-file bound (FB-127 z):
- over 2560 bytes the hook cuts, in this order: the per-task notes heads
  (longest first), overlong titles, `recently_completed`, the rest of the
  titles, and last every active_work entry down to its id and flag, with
  titles (60 characters at most) put back for the first entries that fit;
- no active_work entry is ever dropped: when ids and flags alone are over the
  bound, the handoff is written over it, with `truncated` set;
- a handoff that fits (2560 bytes exactly included) is written exactly as
  before, with no `truncated` key;
- an existing handoff is never overwritten;
- task files that are not a readable JSON object are skipped; the hook exits 0.

The hook's embedded Python runs under the interpreter running these tests (a
`python3` link placed first on PATH), so a 3.10 test run exercises it on 3.10.
Skips when `bash` or the hook file is missing.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# <root>/.claude/scripts/tests/this file -> <root>/.claude/hooks/
HOOK = Path(__file__).resolve().parents[2] / "hooks" / "pre-compact-handoff.sh"
BASH = shutil.which("bash")
MAX_BYTES = 2560

SMALL_KEYS = ["version", "trigger", "timestamp", "spec_version", "position", "active_work",
              "parallel_state", "decisions_in_flight", "session_knowledge", "recovery_action"]
IMPLEMENT_KEYS = ["task_id", "task_title", "agent", "agent_step", "partial", "partial_notes",
                  "files_modified_this_session", "ready_for_verify"]
VERIFY_KEYS = ["task_id", "task_title", "agent", "agent_step", "partial", "ready_for_verify"]
REDUCED_KEYS = ["task_id", "ready_for_verify"]
TITLED_KEYS = ["task_id", "task_title", "ready_for_verify"]


def task(task_id, status="In Progress", notes="", **extra):
    data = {"id": str(task_id), "title": f"Task number {task_id}", "status": status,
            "phase": "1", "owner": "claude", "notes": notes}
    data.update(extra)
    return data


@unittest.skipUnless(BASH, "bash not found")
@unittest.skipUnless(HOOK.is_file(), f"hook not found at {HOOK}")
class PreCompactHookTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name).resolve()
        self.project = tmp / "project"
        self.tasks_dir = self.project / ".claude" / "tasks"
        self.tasks_dir.mkdir(parents=True)
        self.handoff = self.tasks_dir / ".handoff.json"
        (self.project / ".claude" / "spec_v3.md").write_text("# Spec\n", encoding="utf-8")
        self.env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        try:
            os.symlink(sys.executable, bin_dir / "python3")
            self.env["PATH"] = str(bin_dir) + os.pathsep + self.env.get("PATH", "")
        except OSError:
            pass  # no symlinks here: the hook uses whatever python3 is on PATH

    @staticmethod
    def today():
        # The hook's own notion of today (UTC), which `recently_completed` is matched against.
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def write_tasks(self, tasks):
        for t in tasks:
            (self.tasks_dir / f"task-{t['id']}.json").write_text(json.dumps(t), encoding="utf-8")

    def run_hook(self, stdin='{"trigger": "auto"}'):
        r = subprocess.run([BASH, str(HOOK)], input=stdin, capture_output=True, text=True,
                           timeout=30, env=self.env, cwd=str(self.project))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def read_handoff(self):
        raw = self.handoff.read_bytes()
        return raw, json.loads(raw.decode("utf-8"))

    def rerun(self, tasks):
        """Replace the task files and the handoff, run the hook, return (raw, data)."""
        for path in list(self.tasks_dir.glob("task-*.json")) + [self.handoff]:
            if path.exists():
                path.unlink()
        self.write_tasks(tasks)
        self.run_hook()
        return self.read_handoff()

    def assert_task_files_unchanged(self, tasks):
        for t in tasks:
            on_disk = json.loads((self.tasks_dir / f"task-{t['id']}.json").read_text("utf-8"))
            self.assertEqual(on_disk, t)

    def test_small_project_shape_unchanged(self):
        self.write_tasks([
            task(1, "Finished"),
            task(2, notes="[PARTIAL] Mapper done. Aggregation not started."),
            task(3, "Awaiting Verification"),
            task(4, "Pending"),
        ])
        self.run_hook()
        raw, data = self.read_handoff()
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertEqual(list(data), SMALL_KEYS)
        self.assertNotIn("truncated", data)
        self.assertEqual(raw.decode("utf-8"), json.dumps(data, indent=2))
        self.assertEqual(data["trigger"], "pre_compact")
        self.assertEqual(data["spec_version"], "spec_v3")
        self.assertEqual(data["position"], {"phase": "1", "recently_completed": [],
                                            "next_planned": "4"})
        by_id = {w["task_id"]: w for w in data["active_work"]}
        self.assertEqual(sorted(by_id), ["2", "3"])
        self.assertEqual(list(by_id["2"]), IMPLEMENT_KEYS)
        self.assertEqual(by_id["2"]["partial_notes"],
                         "[PARTIAL] Mapper done. Aggregation not started.")
        self.assertEqual(list(by_id["3"]), VERIFY_KEYS)

    def test_one_long_note_keeps_its_600_character_head(self):
        """Positive control for the cut: a single long note fits, so nothing is shortened."""
        self.write_tasks([task(1, notes="n" * 2000)])
        self.run_hook()
        raw, data = self.read_handoff()
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertNotIn("truncated", data)
        self.assertEqual(data["active_work"][0]["partial_notes"], "n" * 600 + "…")

    def test_long_notes_are_cut_longest_first(self):
        notes = {"1": "a" * 2000, "2": "b" * 2000, "3": "c" * 2000, "4": "short note"}
        self.write_tasks([task(i, notes=n) for i, n in notes.items()])
        self.run_hook()
        raw, data = self.read_handoff()
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        by_id = {w["task_id"]: w for w in data["active_work"]}
        self.assertEqual(sorted(by_id), ["1", "2", "3", "4"])
        self.assertEqual(by_id["4"]["partial_notes"], "short note")
        heads = [by_id[i]["partial_notes"] for i in "123"]
        self.assertEqual(len({len(h) for h in heads}), 1, "the long heads share one ceiling")
        for task_id, head in zip("123", heads):
            self.assertTrue(head.endswith("…"))
            self.assertLess(len(head), 600)
            self.assertGreater(len(head), 100, "the cut goes no further than the bound needs")
            self.assertTrue(notes[task_id].startswith(head[:-1]))
        # Task files are not modified by the hook.
        on_disk = json.loads((self.tasks_dir / "task-1.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["notes"], "a" * 2000)

    def test_non_ascii_notes_are_measured_in_bytes(self):
        """A non-ASCII character is 6 bytes in the file; the bound is on bytes, not characters."""
        self.write_tasks([task(1, notes="å" * 2000), task(2, notes="ä" * 2000)])
        self.run_hook()
        raw, data = self.read_handoff()
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        self.assertEqual(len(data["active_work"]), 2)

    def test_exactly_2560_bytes_is_untouched_and_2561_is_cut(self):
        """The bound is inclusive: the cut starts at 2561 bytes, not at 2560."""
        def tasks(pad):
            # One byte of title is one byte of handoff; notes give the cut something to take.
            return [task(1, notes="n" * 300, title="T" * pad), task(2, notes="m" * 300)]

        raw, _ = self.rerun(tasks(100))
        pad = 100 + MAX_BYTES - len(raw)
        self.assertGreater(pad, 0)

        raw, data = self.rerun(tasks(pad))
        self.assertEqual(len(raw), MAX_BYTES)
        self.assertNotIn("truncated", data)
        by_id = {w["task_id"]: w for w in data["active_work"]}
        self.assertEqual(by_id["1"]["partial_notes"], "n" * 300)
        self.assertEqual(by_id["2"]["partial_notes"], "m" * 300)
        self.assertEqual(by_id["1"]["task_title"], "T" * pad)

        raw, data = self.rerun(tasks(pad + 1))
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        by_id = {w["task_id"]: w for w in data["active_work"]}
        self.assertEqual(by_id["1"]["task_title"], "T" * (pad + 1), "notes are cut before titles")
        heads = [by_id[i]["partial_notes"] for i in "12"]
        self.assertTrue(all(h.endswith("…") and len(h) < 300 for h in heads), heads)
        self.assertGreater(len(heads[0]), 280, "one byte over costs a few characters, not the notes")

    def test_many_tasks_keep_every_id(self):
        """12 tasks in flight don't fit whole: entries are reduced, none is dropped, titles come back."""
        tasks = ([task(i, notes="x" * 900) for i in range(1, 9)]
                 + [task(i, "Awaiting Verification") for i in range(9, 13)]
                 + [task(i, "Finished", completion_date=self.today()) for i in range(13, 16)])
        raw, data = self.rerun(tasks)
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        self.assertEqual(list(data), SMALL_KEYS + ["truncated"])
        self.assertEqual(sorted((w["task_id"] for w in data["active_work"]), key=int),
                         [str(i) for i in range(1, 13)])
        for w in data["active_work"]:
            self.assertEqual(list(w), TITLED_KEYS)
            self.assertEqual(w["task_title"], f"Task number {w['task_id']}")
            self.assertIs(w["ready_for_verify"], int(w["task_id"]) >= 9)
        self.assert_task_files_unchanged(tasks)

    def test_titles_are_restored_from_the_front_while_they_fit(self):
        """25 tasks with 80-character titles: the first entries get a 60-character title back."""
        tasks = [task(i, title=f"{i:02d} " + "t" * 77) for i in range(1, 26)]
        raw, data = self.rerun(tasks)
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        work = data["active_work"]
        self.assertEqual(sorted((w["task_id"] for w in work), key=int),
                         [str(i) for i in range(1, 26)])
        titled = [i for i, w in enumerate(work) if "task_title" in w]
        self.assertGreater(len(titled), 0)
        self.assertLess(len(titled), 25)
        self.assertEqual(titled, list(range(len(titled))), "titles go back from the front")
        for i, w in enumerate(work):
            if i < len(titled):
                self.assertEqual(list(w), TITLED_KEYS)
                self.assertEqual(w["task_title"], f"{int(w['task_id']):02d} " + "t" * 57 + "…")
            else:
                self.assertEqual(list(w), REDUCED_KEYS)
        one_more = len('      "task_title": ,\n') + len(json.dumps(work[0]["task_title"]))
        self.assertLess(MAX_BYTES - len(raw), one_more, "no room left for another title")

    def test_nine_tasks_get_every_title_back(self):
        """Just past what fits whole: reduced entries keep their full (short) titles."""
        tasks = [task(i, notes="n" * 100) for i in range(1, 10)]
        raw, data = self.rerun(tasks)
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        self.assertEqual(len(data["active_work"]), 9)
        for w in data["active_work"]:
            self.assertEqual(list(w), TITLED_KEYS)
            self.assertEqual(w["task_title"], f"Task number {w['task_id']}")

    def test_a_cut_uses_the_whole_bound(self):
        """One byte of notes is one byte of handoff, so the best notes cut lands on 2560 exactly."""
        raw, data = self.rerun([task(1, notes="n" * 2000), task(2, title="T" * 1500)])
        self.assertEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        by_id = {w["task_id"]: w for w in data["active_work"]}
        self.assertEqual(by_id["2"]["task_title"], "T" * 1500)
        self.assertTrue(by_id["1"]["partial_notes"].endswith("…"))

    def test_a_title_that_is_not_a_string_is_never_cut_or_restored(self):
        tasks = [task(i) for i in range(1, 10)] + [task(10, title=12345), task(11, title=["a"])]
        raw, data = self.rerun(tasks)
        self.assertLessEqual(len(raw), MAX_BYTES)
        by_id = {w["task_id"]: w for w in data["active_work"]}
        self.assertEqual(sorted(by_id, key=int), [str(i) for i in range(1, 12)])
        for task_id, w in by_id.items():
            self.assertEqual(list(w), REDUCED_KEYS if task_id in ("10", "11") else TITLED_KEYS)

    def test_last_title_stage_can_be_the_one_that_fits(self):
        """8 tasks are a few bytes over with nothing else to cut: short titles are cut, entries stay whole."""
        tasks = [task(i) for i in range(1, 9)]
        raw, data = self.rerun(tasks)
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        self.assertEqual(len(data["active_work"]), 8)
        for w in data["active_work"]:
            self.assertEqual(list(w), IMPLEMENT_KEYS)
            self.assertTrue(w["task_title"].endswith("…"))
            self.assertTrue(f"Task number {w['task_id']}".startswith(w["task_title"][:-1]))
            self.assertLess(len(w["task_title"]), len("Task number 1"))

    def test_overlong_titles_stop_at_60_then_recently_completed_keeps_its_prefix(self):
        """Titles at 60 characters are not enough here, so recently_completed is cut next, from the end."""
        tasks = ([task(i, title=f"{i} " + "t" * 198) for i in range(1, 7)]
                 + [task(100 + i, "Finished", completion_date=self.today()) for i in range(40)])
        self.rerun(tasks)
        # The hook lists tasks in glob order; the same call here gives the uncut list.
        finished = {t["id"] for t in tasks if t["status"] == "Finished"}
        in_order = [json.loads(Path(p).read_text("utf-8"))["id"]
                    for p in glob.glob(os.path.join(str(self.tasks_dir), "task-*.json"))]
        uncut = [i for i in in_order if i in finished]
        raw, data = self.read_handoff()
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        for w in data["active_work"]:
            self.assertEqual(list(w), IMPLEMENT_KEYS)
            self.assertEqual(w["task_title"], f"{w['task_id']} " + "t" * 58 + "…")
        recent = data["position"]["recently_completed"]
        self.assertGreater(len(recent), 3)
        self.assertLess(len(recent), 40)
        self.assertEqual(recent, uncut[:len(recent)])
        self.assertNotEqual(recent, uncut[-len(recent):])

    def test_titles_are_cut_before_entries_are_reduced(self):
        """Four tasks with long notes and 400-character titles fit once the titles are shortened."""
        tasks = [task(i, notes="x" * 900, title=f"{i} " + "t" * 400) for i in range(1, 5)]
        raw, data = self.rerun(tasks)
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        self.assertEqual(sorted(w["task_id"] for w in data["active_work"]), ["1", "2", "3", "4"])
        for w in data["active_work"]:
            self.assertEqual(list(w), IMPLEMENT_KEYS)
            self.assertEqual(w["partial_notes"], "…", "notes heads go before titles")
            self.assertTrue(w["task_title"].startswith(w["task_id"] + " t"))
            self.assertTrue(w["task_title"].endswith("…"))
            self.assertGreaterEqual(len(w["task_title"]), 60)
            self.assertLess(len(w["task_title"]), 402)

    def test_one_5000_character_title_is_cut_not_its_entry(self):
        tasks = [task(1, notes="short note", title="A" * 5000), task(2, "Awaiting Verification"),
                 task(3, "Finished", completion_date=self.today())]
        raw, data = self.rerun(tasks)
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        by_id = {w["task_id"]: w for w in data["active_work"]}
        self.assertEqual(sorted(by_id), ["1", "2"])
        self.assertEqual(list(by_id["1"]), IMPLEMENT_KEYS)
        title = by_id["1"]["task_title"]
        self.assertTrue(title.endswith("…") and set(title[:-1]) == {"A"})
        self.assertGreater(len(title), 1000, "the title keeps what the bound allows")
        self.assertEqual(by_id["2"]["task_title"], "Task number 2")
        self.assertEqual(data["position"]["recently_completed"], ["3"],
                         "an overlong title is cut before recently_completed")
        self.assert_task_files_unchanged(tasks)

    def test_600_finished_today_and_one_in_progress(self):
        tasks = ([task(i, "Finished", completion_date=self.today()) for i in range(1, 601)]
                 + [task(601, notes="[PARTIAL] halfway")])
        raw, data = self.rerun(tasks)
        self.assertLessEqual(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        self.assertEqual(len(data["active_work"]), 1)
        entry = data["active_work"][0]
        self.assertEqual(list(entry), IMPLEMENT_KEYS)
        self.assertEqual(entry["task_id"], "601")
        self.assertEqual(entry["task_title"], "Task number 601")
        recent = data["position"]["recently_completed"]
        self.assertLess(len(recent), 600)
        self.assertGreater(len(recent), 50, "recently_completed keeps what the bound allows")
        self.assertEqual(len(set(recent)), len(recent))
        self.assertTrue(set(recent) <= {str(i) for i in range(1, 601)})

    def test_still_over_is_written_whole_with_the_flag(self):
        """60 tasks in flight: ids and flags alone are over the bound. Nothing is dropped."""
        tasks = ([task(i, notes="x" * 900) for i in range(1, 41)]
                 + [task(i, "Awaiting Verification") for i in range(41, 61)])
        raw, data = self.rerun(tasks)   # read_handoff parses it: valid JSON
        self.assertGreater(len(raw), MAX_BYTES)
        self.assertIs(data["truncated"], True)
        self.assertEqual(sorted((w["task_id"] for w in data["active_work"]), key=int),
                         [str(i) for i in range(1, 61)])
        for w in data["active_work"]:
            self.assertEqual(list(w), REDUCED_KEYS)
            self.assertIs(w["ready_for_verify"], int(w["task_id"]) >= 41)
        self.assertEqual(data["position"]["recently_completed"], [])
        self.assert_task_files_unchanged(tasks)

    def test_existing_handoff_left_untouched(self):
        original = '{"version": 1, "trigger": "user_pause", "session_knowledge": ["keep me"]}\n'
        self.handoff.write_text(original, encoding="utf-8")
        self.write_tasks([task(i, notes="x" * 900) for i in range(1, 9)])
        self.run_hook()
        self.assertEqual(self.handoff.read_text(encoding="utf-8"), original)

    def test_odd_task_files_and_stdin_do_not_crash(self):
        (self.tasks_dir / "task-9.json").write_text('{"id": "9", "status": "In Prog',
                                                    encoding="utf-8")
        (self.tasks_dir / "task-8.json").write_text("", encoding="utf-8")
        # Valid JSON that is not an object, and bytes that are not UTF-8.
        (self.tasks_dir / "task-7.json").write_text('[{"id": "7", "status": "In Progress"}]',
                                                    encoding="utf-8")
        (self.tasks_dir / "task-6.json").write_text('"In Progress"', encoding="utf-8")
        (self.tasks_dir / "task-5.json").write_text("null", encoding="utf-8")
        (self.tasks_dir / "task-4.json").write_bytes(b'{"id": "4", "status": "In Progress", '
                                                     b'"title": "caf\xe9 \xff\xfe"}')
        self.write_tasks([task(1, notes=None), task(2, notes=["a", "list"]),
                          {"id": "3", "status": "In Progress"}])
        self.run_hook(stdin="not json")
        raw, data = self.read_handoff()
        self.assertLessEqual(len(raw), MAX_BYTES)
        by_id = {w["task_id"]: w for w in data["active_work"]}
        self.assertEqual(sorted(by_id), ["1", "2", "3"])
        self.assertEqual(by_id["1"]["partial_notes"], "")
        self.assertEqual(by_id["3"]["task_title"], "Unknown")

    def test_no_tasks_directory_or_no_tasks_writes_nothing(self):
        self.run_hook()  # tasks directory exists, no task files
        self.assertFalse(self.handoff.exists())
        shutil.rmtree(self.project / ".claude")
        self.run_hook()
        self.assertFalse((self.project / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
