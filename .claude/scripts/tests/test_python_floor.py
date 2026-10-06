#!/usr/bin/env python3
"""Python-floor tests for every script in .claude/scripts/ (FB-120).

README promises Python 3.10+. Pins the two ways that promise broke:
- syntax newer than the floor: dashboard-render.py once put backslashes inside
  f-string expressions, legal only from 3.12 (PEP 701). `ast.parse(...,
  feature_version=(3, 10))` accepts that on 3.12+, so the scripts are compiled
  with a real 3.10 interpreter instead; the test skips when none is found.
- a missing version guard: below the floor each script must exit 2 with a
  message naming itself, the version found and sys.executable, not a
  SyntaxError/TypeError from deep in the file.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = sorted(Path(__file__).resolve().parents[1].glob("*.py"))

COMPILE = "import py_compile, sys; py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)"

# Run `<script> --help` as __main__ with sys.version_info faked to 3.9.6
# (--help, so a script missing its guard still does nothing harmful).
FAKE_OLD = ("import collections, runpy, sys; "
            "sys.version_info = collections.namedtuple("
            "'version_info', 'major minor micro releaselevel serial')(3, 9, 6, 'final', 0); "
            "sys.argv = [sys.argv[1], '--help']; "
            "runpy.run_path(sys.argv[0], run_name='__main__')")


def _run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _is_310(exe):
    r = _run([exe, "-c", "import sys; print(sys.version_info[:2] == (3, 10))"])
    return r is not None and r.stdout.strip() == "True"


def find_python310():
    """A 3.10 interpreter: python3.10 on PATH, else `uv python find 3.10`; None if neither."""
    exe = shutil.which("python3.10")
    if exe and _is_310(exe):
        return exe
    if shutil.which("uv"):
        r = _run(["uv", "python", "find", "3.10"])
        exe = r.stdout.strip() if r is not None and r.returncode == 0 else ""
        if exe and _is_310(exe):
            return exe
    return None


class PythonFloorTests(unittest.TestCase):
    def test_scripts_found(self):
        """Positive control: the glob sees the scripts, so the loops below aren't vacuous."""
        self.assertIn("dashboard-render.py", [s.name for s in SCRIPTS])

    def test_scripts_compile_on_python_3_10(self):
        py310 = find_python310()
        if py310 is None:
            self.skipTest("no Python 3.10 interpreter (python3.10 on PATH or `uv python find 3.10`)")
        with tempfile.TemporaryDirectory() as d:  # bytecode goes here, not next to the scripts
            for script in SCRIPTS:
                with self.subTest(script=script.name):
                    r = _run([py310, "-c", COMPILE, str(script), str(Path(d) / f"{script.stem}.pyc")])
                    self.assertIsNotNone(r)
                    self.assertEqual(r.returncode, 0, r.stderr)

    def test_old_python_exits_with_clear_message(self):
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                r = subprocess.run([sys.executable, "-c", FAKE_OLD, str(script)],
                                   input="", capture_output=True, text=True, timeout=10)
                self.assertEqual(r.returncode, 2, r.stderr)
                for expected in (script.name, "3.10+", "3.9.6", sys.executable):
                    self.assertIn(expected, r.stderr)


if __name__ == "__main__":
    unittest.main()
