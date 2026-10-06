#!/usr/bin/env python3
"""Tests for sync-apply.py (FB-136), run against temporary git repos.

One template repo is built per module: d1 (1.0.0) → d2 (unreadable version.json) →
d3 (1.2.0: drops the sync pattern `.claude/old/*.md`, changes the customize and
ignore lists) → d4 (1.3.0, release date 2026-04-04). Its compare set at d4 is eight
files (FILES), one of them executable. Each test builds its own project, a plain
directory unless it says otherwise, from PROJECT: one file per sync-check.py status.
Git is isolated from the user's config (GIT_CONFIG_GLOBAL=/dev/null,
GIT_CONFIG_NOSYSTEM=1) with fixed identities and dates.
"""
import datetime
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "sync-apply.py"
CHECK = SCRIPTS / "sync-check.py"
_spec = importlib.util.spec_from_file_location("sync_apply", SCRIPT)
sa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sa)

ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
           GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com")

SYNC = [".claude/commands/*.md", ".claude/scripts/*.py", ".claude/rules/*.md",
        ".claude/vision/README.md"]
RETIRED = ".claude/old/*.md"
CUSTOMIZE_V1 = [".claude/README.md"]
IGNORE_V1 = [".claude/version.json", ".claude/sync-manifest.json", ".claude/dashboard.md",
             ".claude/vision/*.md"]
CUSTOMIZE = [".claude/README.md", ".claude/rules/project-*.md"]
IGNORE = [".claude/version.json", ".claude/sync-manifest.json", ".claude/dashboard.html",
          ".claude/vision/*.md"]
WORK_V1 = "# Work\nstep one\nstep two\n"
WORK_V4 = "# Work\nstep one\nstep 2\nstep three\n"
FILES = [".claude/commands/added.md", ".claude/commands/flip.md", ".claude/commands/same.md",
         ".claude/commands/work.md", ".claude/rules/core.md", ".claude/scripts/plain.py",
         ".claude/scripts/tool.py", ".claude/vision/README.md"]
UPSTREAM = {  # content of each compare-set file at d4
    ".claude/commands/added.md": "added v1\n",
    ".claude/commands/flip.md": "flip C\n",
    ".claude/commands/same.md": "same\n",
    ".claude/commands/work.md": WORK_V4,
    ".claude/rules/core.md": "core v2\n",
    ".claude/scripts/plain.py": "print('plain')\n",
    ".claude/scripts/tool.py": "print('tool v2')\n",
    ".claude/vision/README.md": "vision v2\n",
}
SIDECAR = ".claude/.sync-state.json"

BASE = None  # TemporaryDirectory holding every repo
ROOT = None  # its realpath
T = None     # template repo


def manifest(sync, customize=(), ignore=(), flat=False, **extra):
    cats = {"sync": list(sync), "customize": list(customize), "ignore": list(ignore)}
    data = {**extra, **cats} if flat else {"manifest_version": "1.0.0", **extra, "categories": cats}
    return json.dumps(data, indent=2) + "\n"


def version(v, date=None):
    data = {"template_version": v}
    if date:
        data["template_release_date"] = date
    return json.dumps(data) + "\n"


def sha(content):
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()


def git(cwd, *args, n=None):
    env = dict(ENV)
    if n is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{1700000000 + 60 * n} +0000"
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise AssertionError(f"git {args} failed: {r.stderr}")
    return r.stdout.strip()


def write(root, files):
    """files: {relative path: content, or None to delete}."""
    for rel, content in files.items():
        p = Path(root) / rel
        if content is None:
            p.unlink()
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)


class Repo:
    def __init__(self, path):
        self.path, self.n = Path(path), 0
        self.path.mkdir(parents=True)
        git(self.path, "init", "-q", "-b", "main")

    def commit(self, message, files):
        write(self.path, files)
        git(self.path, "add", "-A")
        self.n += 1
        git(self.path, "commit", "-q", "-m", message, n=self.n)
        return git(self.path, "rev-parse", "HEAD")


def setUpModule():
    global BASE, ROOT, T
    BASE = tempfile.TemporaryDirectory()
    ROOT = Path(os.path.realpath(BASE.name))
    ENV["GIT_CEILING_DIRECTORIES"] = str(ROOT)  # plain dirs under ROOT are never "in a repo"
    T = ROOT / "template"
    repo = Repo(T)
    write(T, {".claude/scripts/tool.py": "print('tool v1')\n"})
    os.chmod(T / ".claude/scripts/tool.py", 0o755)  # mode 100755 in the tree
    repo.commit("1.0.0", {
        ".claude/version.json": version("1.0.0", "2026-01-01"),
        ".claude/sync-manifest.json": manifest(SYNC + [RETIRED], CUSTOMIZE_V1, IGNORE_V1),
        ".claude/commands/work.md": WORK_V1,
        ".claude/commands/flip.md": "flip A\n",
        ".claude/commands/same.md": "same\n",
        ".claude/scripts/plain.py": "print('plain')\n",
        ".claude/rules/core.md": "core v1\n",
        ".claude/rules/project-x.md": "project x\n",
        ".claude/vision/README.md": "vision v1\n",
        ".claude/README.md": "readme\n"})
    repo.commit("unreadable version", {".claude/version.json": "{ broken\n",
                                       ".claude/commands/flip.md": "flip B\n"})
    repo.commit("1.2.0", {
        ".claude/version.json": version("1.2.0", "2026-03-03"),
        ".claude/sync-manifest.json": manifest(SYNC, CUSTOMIZE, IGNORE),
        ".claude/commands/added.md": "added v1\n",
        ".claude/rules/core.md": "core v2\n",
        ".claude/scripts/tool.py": "print('tool v2')\n"})
    repo.commit("1.3.0", {
        ".claude/version.json": version("1.3.0", "2026-04-04"),
        ".claude/commands/work.md": WORK_V4,
        ".claude/commands/flip.md": "flip C\n",
        ".claude/vision/README.md": "vision v2\n"})


def tearDownModule():
    BASE.cleanup()


# version.json with a layout a parsed rewrite would not reproduce: tabs, key order, an
# escaped character, no trailing newline, and a nested key of the same name.
LOCAL_VERSION = ('{\n\t"project_version": "0.4.0",\n\t"template_release_date" :"2026-01-01",\n'
                 '\t"notes": "caf\\u00e9 \\"template_version\\": x",\n'
                 '\t"template_version":   "1.0.0",\n\t"template_repo": "https://example.com/t"\n}')

PROJECT = {
    ".claude/version.json": LOCAL_VERSION,
    ".claude/sync-manifest.json": manifest(SYNC + [".claude/mine/*.md", RETIRED], CUSTOMIZE_V1,
                                           IGNORE_V1 + [".claude/secrets.md"]),
    # .claude/commands/added.md is absent                  new
    ".claude/commands/flip.md": "flip A\n",              # template_copy
    ".claude/commands/same.md": "same\n",                # up_to_date
    ".claude/commands/work.md": WORK_V1 + "my step\n",   # modified
    ".claude/rules/core.md": "core v1\n",                # template_copy
    ".claude/scripts/plain.py": "print('plain')\n",      # up_to_date
    ".claude/scripts/tool.py": "print('tool v1')\n",     # template_copy (0644 here, 100755 upstream)
    ".claude/vision/README.md": "vision v2\n",           # up_to_date
    ".claude/commands/mine.md": "my own command\n",      # not a template file
    ".claude/README.md": "my readme\n",                  # customize
    "src/app.py": "print('hi')\n",
}
COPIES = [".claude/commands/flip.md", ".claude/rules/core.md", ".claude/scripts/tool.py"]
UP_TO_DATE = [".claude/commands/same.md", ".claude/scripts/plain.py", ".claude/vision/README.md"]


def snapshot(root):
    """{relative path: (permission bits, bytes or symlink target)} for everything under root."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            rel = str(p.relative_to(root))
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("link", os.readlink(p))
            elif stat.S_ISREG(st.st_mode):
                out[rel] = (stat.S_IMODE(st.st_mode), p.read_bytes())
            else:
                out[rel] = ("dir", None)
    return out


def mode_of(path):
    return stat.S_IMODE(os.lstat(path).st_mode)


class Case(unittest.TestCase):
    maxDiff = None

    def project(self, **changes):
        """A plain-directory project: PROJECT with changes applied (None leaves a path out)."""
        project = Path(tempfile.mkdtemp(dir=ROOT))
        write(project, {p: c for p, c in {**PROJECT, **changes}.items() if c is not None})
        return project

    def run_script(self, project, *args, stdin=None, script=SCRIPT, cwd=None):
        return subprocess.run([sys.executable, str(script), "--project", str(project),
                               "--template-repo", str(T), "--ref", "main", *args],
                              capture_output=True, text=True, env=ENV, input=stdin, cwd=cwd,
                              timeout=120)

    def apply(self, project, *args, code=0, stdin=None):
        r = self.run_script(project, *args, stdin=stdin)
        self.assertEqual(r.returncode, code, r.stderr + r.stdout)
        return json.loads(r.stdout)

    def statuses(self, project):
        r = self.run_script(project, script=CHECK)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {f["path"]: f["status"] for f in json.loads(r.stdout)["files"]}

    def sidecar(self, project):
        return json.loads((project / SIDECAR).read_text())

    def assert_exit_2(self, project, args, needle, stdin=None):
        """Exit 2, nothing on stdout, and the project byte-for-byte as it was."""
        before = snapshot(project)
        r = self.run_script(project, *args, stdin=stdin)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(r.stdout, "")
        self.assertIn(needle, r.stderr)
        self.assertEqual(snapshot(project), before)


# ---------------------------------------------------------------- selection and file writes

class StatusSelectionTests(Case):
    def test_new_and_template_copy(self):
        project = self.project()
        self.assertEqual(self.statuses(project), {
            ".claude/commands/added.md": "new", ".claude/commands/flip.md": "template_copy",
            ".claude/commands/same.md": "up_to_date", ".claude/commands/work.md": "modified",
            ".claude/rules/core.md": "template_copy", ".claude/scripts/plain.py": "up_to_date",
            ".claude/scripts/tool.py": "template_copy", ".claude/vision/README.md": "up_to_date"})
        before = snapshot(project)
        out = self.apply(project, "--status", "new,template_copy")
        self.assertEqual(list(out), ["ref", "ref_commit", "dry_run", "written", "mode_fixed",
                                     "failed", "version", "manifest", "sidecar", "changed_paths",
                                     "remaining", "warnings"])
        self.assertEqual(out["ref"], "main")
        self.assertEqual(out["ref_commit"], git(T, "rev-parse", "main"))
        self.assertIs(out["dry_run"], False)
        self.assertEqual(out["written"], [
            {"path": ".claude/commands/added.md", "status": "new", "mode": "100644"},
            {"path": ".claude/commands/flip.md", "status": "template_copy", "mode": "100644"},
            {"path": ".claude/rules/core.md", "status": "template_copy", "mode": "100644"},
            {"path": ".claude/scripts/tool.py", "status": "template_copy", "mode": "100755"}])
        self.assertEqual(out["mode_fixed"], [])
        self.assertEqual(out["failed"], [])
        self.assertEqual(out["version"], {"from": "1.0.0", "to": "1.3.0", "bumped": True})
        self.assertEqual(out["manifest"], {"changed": True, "sync_added": [],
                                           "sync_dropped": [RETIRED], "lists_updated": False})
        self.assertEqual(out["sidecar"], {"recorded": 7, "dropped": 0, "created": True,
                                          "changed": True})
        self.assertEqual(out["changed_paths"], [
            SIDECAR, ".claude/commands/added.md", ".claude/commands/flip.md",
            ".claude/rules/core.md", ".claude/scripts/tool.py", ".claude/sync-manifest.json",
            ".claude/version.json"])
        self.assertEqual(out["remaining"], [{"path": ".claude/commands/work.md",
                                             "status": "modified"}])
        self.assertEqual(out["warnings"], ["project is not a git work tree; uncommitted_sync skipped"])

        # Files: upstream content and mode; nothing else in the project moved.
        after = snapshot(project)
        for path in (".claude/commands/added.md", *COPIES):
            self.assertEqual(after[path], (0o755 if path.endswith("tool.py") else 0o644,
                                           UPSTREAM[path].encode()), path)
        self.assertEqual({p for p in set(before) | set(after) if before.get(p) != after.get(p)},
                         set(out["changed_paths"]))
        self.assertEqual(after[".claude/commands/work.md"][1], (WORK_V1 + "my step\n").encode())
        self.assertEqual([p for p in after if ".sync-apply-" in p], [])  # no temp file left

        # sync-check agrees: everything up to date but the modified file.
        self.assertEqual(self.statuses(project),
                         {p: "modified" if p == ".claude/commands/work.md" else "up_to_date"
                          for p in FILES})

        # The sidecar records every file equal to upstream, not only the four written.
        state = self.sidecar(project)
        self.assertEqual(state, {
            "schema_version": "1.0", "last_full_sync_version": "1.3.0",
            "last_full_sync_date": datetime.date.today().isoformat(),
            "files": {p: {"synced_hash": sha(UPSTREAM[p])} for p in FILES
                      if p != ".claude/commands/work.md"}})
        for path in UP_TO_DATE:
            self.assertNotIn(path, [w["path"] for w in out["written"]])
            self.assertIn(path, state["files"])

        # Idempotence: a second run changes nothing.
        again = self.apply(project, "--status", "new,template_copy")
        self.assertEqual(again["changed_paths"], [])
        self.assertEqual(again["written"], [])
        self.assertEqual(again["version"], {"from": "1.3.0", "to": "1.3.0", "bumped": False})
        self.assertEqual(again["manifest"], {"changed": False, "sync_added": [],
                                             "sync_dropped": [], "lists_updated": False})
        self.assertEqual(again["sidecar"], {"recorded": 7, "dropped": 0, "created": False,
                                            "changed": False})
        self.assertEqual(again["remaining"], out["remaining"])
        self.assertEqual(snapshot(project), after)

    def test_one_status(self):
        project = self.project()
        out = self.apply(project, "--status", "new")
        self.assertEqual([w["path"] for w in out["written"]], [".claude/commands/added.md"])
        self.assertEqual(out["remaining"],
                         [{"path": ".claude/commands/flip.md", "status": "template_copy"},
                          {"path": ".claude/commands/work.md", "status": "modified"},
                          {"path": ".claude/rules/core.md", "status": "template_copy"},
                          {"path": ".claude/scripts/tool.py", "status": "template_copy"}])
        self.assertEqual((project / ".claude/commands/flip.md").read_text(), "flip A\n")
        self.assertEqual(out["sidecar"]["recorded"], 4)  # the new file + three already up to date
        self.assertEqual(sorted(self.sidecar(project)["files"]),
                         sorted([".claude/commands/added.md", *UP_TO_DATE]))

    def test_status_never_selects_a_modified_file(self):
        project = self.project()
        for value in ("modified", "new,modified", "up_to_date", "new,", "all"):
            with self.subTest(value=value):
                self.assert_exit_2(project, ["--status", value], "--status takes")

    def test_new_file_in_a_missing_directory(self):
        project = self.project(**{".claude/vision/README.md": None})
        self.assertFalse((project / ".claude/vision").exists())
        out = self.apply(project, "--status", "new")
        self.assertEqual([w["path"] for w in out["written"]],
                         [".claude/commands/added.md", ".claude/vision/README.md"])
        self.assertEqual((project / ".claude/vision/README.md").read_text(), "vision v2\n")


class PathSelectionTests(Case):
    PATHS = "\n.claude/commands/work.md\n\n  .claude/commands/added.md  \r\n\n"

    def check_result(self, project, out):
        self.assertEqual(out["written"], [
            {"path": ".claude/commands/added.md", "status": "new", "mode": "100644"},
            {"path": ".claude/commands/work.md", "status": "modified", "mode": "100644"}])
        self.assertEqual((project / ".claude/commands/work.md").read_text(), WORK_V4)
        self.assertEqual((project / ".claude/commands/flip.md").read_text(), "flip A\n")
        self.assertEqual([r["path"] for r in out["remaining"]], COPIES)
        self.assertIs(out["version"]["bumped"], True)

    def test_paths_from_a_file(self):
        project = self.project()
        listing = Path(tempfile.mkdtemp(dir=ROOT)) / "paths.txt"
        listing.write_text(self.PATHS)
        self.check_result(project, self.apply(project, "--paths-from", str(listing)))

    def test_paths_from_stdin(self):
        project = self.project()
        self.check_result(project, self.apply(project, "--paths-from", "-", stdin=self.PATHS))

    def test_union_with_status(self):
        project = self.project()
        out = self.apply(project, "--status", "template_copy", "--paths-from", "-",
                         stdin=".claude/commands/work.md\n.claude/commands/flip.md\n")
        self.assertEqual([w["path"] for w in out["written"]],
                         [".claude/commands/flip.md", ".claude/commands/work.md",
                          ".claude/rules/core.md", ".claude/scripts/tool.py"])
        self.assertEqual(out["remaining"], [{"path": ".claude/commands/added.md", "status": "new"}])

    def test_unknown_path_writes_nothing(self):
        """Every path must be a compare-set file: a project file, a customize file, a
        retired-pattern path, a path outside .claude/ and a `./` spelling are all refused,
        even next to a valid path and a --status selection."""
        project = self.project(**{".claude/old/guide.md": "guide\n"})
        for path in (".claude/commands/mine.md", ".claude/README.md", ".claude/old/guide.md",
                     "src/app.py", "./.claude/commands/work.md", "../outside.md",
                     ".claude/version.json"):
            with self.subTest(path=path):
                self.assert_exit_2(project, ["--status", "new,template_copy", "--paths-from", "-"],
                                   "not a compare-set file",
                                   stdin=f".claude/commands/work.md\n{path}\n")
        # Positive control: the same run without the bad path writes.
        out = self.apply(project, "--status", "new,template_copy", "--paths-from", "-",
                         stdin=".claude/commands/work.md\n")
        self.assertEqual(len(out["written"]), 5)

    def test_unreadable_paths_file(self):
        project = self.project()
        self.assert_exit_2(project, ["--paths-from", str(ROOT / "no-such-file.txt")],
                           "cannot read --paths-from")

    def test_selected_up_to_date_file_is_left_alone(self):
        project = self.project()
        target = project / ".claude/commands/same.md"
        before = os.lstat(target)
        out = self.apply(project, "--paths-from", "-", stdin=".claude/commands/same.md\n")
        self.assertEqual((out["written"], out["mode_fixed"]), ([], []))
        self.assertIs(out["version"]["bumped"], False)
        after = os.lstat(target)
        self.assertEqual((after.st_ino, after.st_mtime_ns), (before.st_ino, before.st_mtime_ns))


class ModeTests(Case):
    def test_mode_fix_is_a_chmod(self):
        """Up-to-date files with the wrong mode: fixed only when selected by path, with a
        chmod (same inode), and without a version bump."""
        project = self.project(**{".claude/scripts/tool.py": "print('tool v2')\n"})
        tool, plain = project / ".claude/scripts/tool.py", project / ".claude/scripts/plain.py"
        os.chmod(plain, 0o755)
        self.assertEqual((mode_of(tool), mode_of(plain)), (0o644, 0o755))
        out = self.apply(project, "--status", "new,template_copy")
        self.assertEqual(out["mode_fixed"], [])
        self.assertEqual((mode_of(tool), mode_of(plain)), (0o644, 0o755))
        inode = os.lstat(tool).st_ino
        version_before = (project / ".claude/version.json").read_bytes()
        sidecar_before = (project / SIDECAR).read_bytes()
        dry = self.apply(project, "--paths-from", "-", "--dry-run",
                         stdin=".claude/scripts/tool.py\n.claude/scripts/plain.py\n")
        self.assertEqual((mode_of(tool), mode_of(plain)), (0o644, 0o755))
        out = self.apply(project, "--paths-from", "-",
                         stdin=".claude/scripts/tool.py\n.claude/scripts/plain.py\n")
        self.assertEqual(out["mode_fixed"], [".claude/scripts/plain.py", ".claude/scripts/tool.py"])
        self.assertEqual(out["written"], [])
        self.assertEqual(out["changed_paths"], out["mode_fixed"])
        self.assertEqual(dict(dry, dry_run=False), out)
        self.assertEqual((mode_of(tool), mode_of(plain)), (0o755, 0o644))
        self.assertEqual(os.lstat(tool).st_ino, inode)
        self.assertEqual((project / ".claude/version.json").read_bytes(), version_before)
        self.assertEqual((project / SIDECAR).read_bytes(), sidecar_before)

    def test_written_files_take_the_upstream_mode(self):
        """Whatever the local mode and the umask were."""
        project = self.project()
        os.chmod(project / ".claude/commands/flip.md", 0o755)   # 100644 upstream
        os.chmod(project / ".claude/scripts/tool.py", 0o600)    # 100755 upstream
        old = os.umask(0o077)
        try:
            r = self.run_script(project, "--status", "new,template_copy")
        finally:
            os.umask(old)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(mode_of(project / ".claude/commands/flip.md"), 0o644)
        self.assertEqual(mode_of(project / ".claude/commands/added.md"), 0o644)
        self.assertEqual(mode_of(project / ".claude/scripts/tool.py"), 0o755)


class RefusalTests(Case):
    def test_symlink_and_directory_at_the_path(self):
        """A local path that is not a regular file is refused: `failed`, exit 1, the link
        and its target untouched, everything else still applied."""
        project = self.project(**{".claude/commands/flip.md": None, ".claude/rules/core.md": None,
                                  "elsewhere/flip.md": "flip A\n"})
        os.symlink("../../elsewhere/flip.md", project / ".claude/commands/flip.md")
        (project / ".claude/rules/core.md").mkdir(parents=True)
        out = self.apply(project, "--status", "new,template_copy", "--paths-from", "-", code=1,
                         stdin=".claude/commands/flip.md\n.claude/rules/core.md\n")
        self.assertEqual(out["failed"], [
            {"path": ".claude/commands/flip.md", "error": "local path is not a regular file"},
            {"path": ".claude/rules/core.md", "error": "local path is not a regular file"}])
        self.assertTrue((project / ".claude/commands/flip.md").is_symlink())
        self.assertEqual((project / "elsewhere/flip.md").read_text(), "flip A\n")
        self.assertTrue((project / ".claude/rules/core.md").is_dir())
        self.assertEqual([w["path"] for w in out["written"]],
                         [".claude/commands/added.md", ".claude/scripts/tool.py"])
        self.assertIs(out["version"]["bumped"], True)
        self.assertEqual(out["remaining"], [
            {"path": ".claude/commands/flip.md", "status": "modified"},
            {"path": ".claude/commands/work.md", "status": "modified"},
            {"path": ".claude/rules/core.md", "status": "modified"}])
        self.assertNotIn(".claude/commands/flip.md", self.sidecar(project)["files"])

    def test_parent_directory_that_escapes_the_project(self):
        """`.claude/rules` is a symlink to a directory outside `.claude/`: sync-check reads
        through it (template_copy), the writer refuses. A symlinked directory that stays
        inside `.claude/` is written through (positive control)."""
        project = self.project(**{".claude/rules/core.md": None, "outside/core.md": "core v1\n",
                                  ".claude/commands/flip.md": None,
                                  ".claude/real-commands/flip.md": "flip A\n",
                                  ".claude/real-commands/same.md": "same\n",
                                  ".claude/real-commands/work.md": WORK_V1,
                                  ".claude/commands/same.md": None,
                                  ".claude/commands/work.md": None,
                                  ".claude/commands/mine.md": None})
        self.assertFalse((project / ".claude/rules").exists())
        self.assertFalse((project / ".claude/commands").exists())
        os.symlink("../outside", project / ".claude/rules")
        os.symlink("real-commands", project / ".claude/commands")
        self.assertEqual(self.statuses(project)[".claude/rules/core.md"], "template_copy")
        dry = self.apply(project, "--status", "new,template_copy", "--dry-run", code=1)
        out = self.apply(project, "--status", "new,template_copy", code=1)
        self.assertEqual(dict(dry, dry_run=False), out)
        self.assertEqual(out["failed"], [{
            "path": ".claude/rules/core.md",
            "error": "parent directory resolves outside the project's .claude/"}])
        self.assertEqual((project / "outside/core.md").read_text(), "core v1\n")
        self.assertEqual(sorted(os.listdir(project / "outside")), ["core.md"])
        self.assertEqual((project / ".claude/real-commands/flip.md").read_text(), "flip C\n")
        self.assertEqual((project / ".claude/real-commands/added.md").read_text(), "added v1\n")
        self.assertEqual(out["remaining"], [{"path": ".claude/rules/core.md",
                                             "status": "template_copy"}])

    def test_sibling_directory_sharing_the_prefix_is_outside(self):
        """`.claude/commands` is a symlink to `PROJECT/.claude-x/`, whose path starts with
        that of `PROJECT/.claude` but is not inside it: refused, nothing written there."""
        commands = {p: c for p, c in PROJECT.items() if p.startswith(".claude/commands/")}
        project = self.project(**{p: None for p in commands},
                               **{p.replace(".claude/commands/", ".claude-x/"): c
                                  for p, c in commands.items()})
        self.assertFalse((project / ".claude/commands").exists())
        os.symlink("../.claude-x", project / ".claude/commands")
        statuses = self.statuses(project)
        self.assertEqual((statuses[".claude/commands/added.md"],
                          statuses[".claude/commands/flip.md"]), ("new", "template_copy"))
        before = snapshot(project / ".claude-x")
        out = self.apply(project, "--status", "new,template_copy", code=1)
        error = "parent directory resolves outside the project's .claude/"
        self.assertEqual(out["failed"], [{"path": ".claude/commands/added.md", "error": error},
                                         {"path": ".claude/commands/flip.md", "error": error}])
        self.assertEqual(snapshot(project / ".claude-x"), before)
        self.assertEqual([w["path"] for w in out["written"]],   # positive control: it wrote
                         [".claude/rules/core.md", ".claude/scripts/tool.py"])

    def test_file_is_replaced_not_written_in_place(self):
        """The write is a temp file + os.replace: a second hard link to the old file keeps
        the old content (an in-place write would change both)."""
        project = self.project()
        target = project / ".claude/commands/flip.md"
        os.link(target, project / "kept.md")
        inode = os.lstat(target).st_ino
        self.apply(project, "--status", "template_copy")
        self.assertEqual(target.read_text(), "flip C\n")
        self.assertEqual((project / "kept.md").read_text(), "flip A\n")
        self.assertNotEqual(os.lstat(target).st_ino, inode)

    def test_mode_fix_through_an_escaping_parent_is_refused(self):
        project = self.project(**{".claude/scripts/tool.py": None, ".claude/scripts/plain.py": None,
                                  "outside/tool.py": "print('tool v2')\n",
                                  "outside/plain.py": "print('plain')\n"})
        self.assertFalse((project / ".claude/scripts").exists())
        os.symlink("../outside", project / ".claude/scripts")
        out = self.apply(project, "--paths-from", "-", code=1, stdin=".claude/scripts/tool.py\n")
        self.assertEqual([f["path"] for f in out["failed"]], [".claude/scripts/tool.py"])
        self.assertEqual(out["mode_fixed"], [])
        self.assertEqual(mode_of(project / "outside/tool.py"), 0o644)

    def test_write_error_is_a_failed_entry(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        project = self.project()
        os.chmod(project / ".claude/rules", 0o555)
        try:
            out = self.apply(project, "--status", "new,template_copy", code=1)
        finally:
            os.chmod(project / ".claude/rules", 0o755)
        self.assertEqual([f["path"] for f in out["failed"]], [".claude/rules/core.md"])
        self.assertIn("PermissionError", out["failed"][0]["error"])
        self.assertEqual((project / ".claude/rules/core.md").read_text(), "core v1\n")
        self.assertEqual(len(out["written"]), 3)


# ---------------------------------------------------------------- bookkeeping

class VersionTests(Case):
    def test_textual_replacement_keeps_every_other_byte(self):
        project = self.project()
        self.apply(project, "--status", "new")
        expected = (LOCAL_VERSION.replace('"template_version":   "1.0.0"',
                                          '"template_version":   "1.3.0"')
                    .replace('"template_release_date" :"2026-01-01"',
                             '"template_release_date" :"2026-04-04"'))
        self.assertNotEqual(expected, LOCAL_VERSION)
        self.assertEqual((project / ".claude/version.json").read_bytes(), expected.encode())

    def test_missing_key_is_added_by_a_parsed_rewrite(self):
        project = self.project(**{".claude/version.json": '{"template_version":"1.0.0","x":"é"}'})
        out = self.apply(project, "--status", "new")
        self.assertEqual(out["version"], {"from": "1.0.0", "to": "1.3.0", "bumped": True})
        self.assertEqual((project / ".claude/version.json").read_text(encoding="utf-8"),
                         '{\n  "template_version": "1.3.0",\n  "x": "é",\n'
                         '  "template_release_date": "2026-04-04"\n}\n')

    def test_missing_or_unparseable_is_skipped_with_a_warning(self):
        for content in (None, "{ nope\n", "[]\n"):
            with self.subTest(content=content):
                project = self.project(**{".claude/version.json": content})
                out = self.apply(project, "--status", "new")
                self.assertEqual(out["version"], {"from": None, "to": None, "bumped": False})
                self.assertIn("local version.json missing or unreadable; not updated",
                              out["warnings"])
                self.assertNotIn(".claude/version.json", out["changed_paths"])
                if content is None:
                    self.assertFalse((project / ".claude/version.json").exists())
                else:
                    self.assertEqual((project / ".claude/version.json").read_text(), content)
                self.assertNotIn("last_full_sync_version", self.sidecar(project))

    def test_not_bumped_without_a_content_write(self):
        """A run that writes no file content leaves version.json alone even though it
        differs from upstream; so does a run whose only write failed."""
        project = self.project()
        out = self.apply(project)
        self.assertEqual(out["version"], {"from": "1.0.0", "to": "1.0.0", "bumped": False})
        self.assertEqual((project / ".claude/version.json").read_text(), LOCAL_VERSION)
        self.assertNotIn("last_full_sync_version", self.sidecar(project))
        (project / ".claude/commands/flip.md").unlink()
        os.symlink("same.md", project / ".claude/commands/flip.md")
        out = self.apply(project, "--paths-from", "-", code=1, stdin=".claude/commands/flip.md\n")
        self.assertIs(out["version"]["bumped"], False)

    def test_empty_compare_set_never_bumps(self):
        """A template ref whose `sync` list is empty has no file to equal REF, so the
        "every compare-set file equals REF" bump must not fire on an empty set."""
        template = Path(tempfile.mkdtemp(dir=ROOT)) / "template"
        git(ROOT, "clone", "-q", str(T), str(template))
        write(template, {".claude/sync-manifest.json":
                         json.dumps({"sync": [], "customize": [], "ignore": []})})
        git(template, "add", "-A")
        git(template, "commit", "-q", "-m", "sync nothing", n=9)
        project = self.project(**{".claude/sync-manifest.json": json.dumps({"sync": []})})
        r = subprocess.run([sys.executable, str(SCRIPT), "--project", str(project),
                            "--template-repo", str(template), "--ref", "HEAD"],
                           capture_output=True, text=True, env=ENV, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["remaining"], [])                      # the set really is empty
        self.assertNotEqual(out["version"]["from"], git(template, "show", "HEAD:.claude/version.json"))
        self.assertIs(out["version"]["bumped"], False)
        self.assertEqual((project / ".claude/version.json").read_text(), LOCAL_VERSION)

    def test_bumped_by_the_rerun_after_an_interrupted_run(self):
        """Files written, then the run died before version.json: the re-run writes no
        file content, yet every compare-set file equals REF and the version differs, so
        it bumps (and refreshes the sidecar's last-full-sync fields)."""
        project = self.project()
        args = ["--status", "new,template_copy", "--paths-from", "-"]
        self.apply(project, *args, stdin=".claude/commands/work.md\n")
        write(project, {".claude/version.json": LOCAL_VERSION})   # the bump never landed
        state = self.sidecar(project)
        del state["last_full_sync_version"], state["last_full_sync_date"]
        write(project, {SIDECAR: json.dumps(state)})
        self.assertEqual(set(self.statuses(project).values()), {"up_to_date"})
        out = self.apply(project)
        self.assertEqual(out["written"], [])
        self.assertEqual(out["version"], {"from": "1.0.0", "to": "1.3.0", "bumped": True})
        self.assertEqual(out["changed_paths"], [SIDECAR, ".claude/version.json"])
        self.assertIn('"template_version":   "1.3.0"',
                      (project / ".claude/version.json").read_text())
        self.assertEqual(self.sidecar(project)["last_full_sync_version"], "1.3.0")
        again = self.apply(project)
        self.assertEqual((again["version"]["bumped"], again["changed_paths"]), (False, []))

    def test_set_version_text(self):
        values = {"template_version": "2.0.0", "template_release_date": "2026-05-05"}
        raw = b'{"template_version": "1.0.0",\r\n "template_release_date": "x\\"y"}'
        self.assertEqual(sa.set_version_text(raw, values),
                         b'{"template_version": "2.0.0",\r\n "template_release_date": "2026-05-05"}')
        same = b'{ "template_release_date":"2026-05-05", "template_version":"2.0.0" }'
        self.assertIs(sa.set_version_text(same, values), same)
        # The key text appears twice (a nested object): the textual route is not taken.
        nested = b'{"a": {"template_version": "9"}, "template_version": "1.0.0", "template_release_date": "d"}'
        self.assertEqual(json.loads(sa.set_version_text(nested, values)),
                         {"a": {"template_version": "9"}, **values})
        # A non-string value is replaced by a parsed rewrite.
        self.assertEqual(json.loads(sa.set_version_text(b'{"template_version": 1}', values)), values)
        # A value with characters JSON must escape, and regex-template characters.
        odd = {"template_version": 'a"b\\1\\g<0>'}
        self.assertEqual(json.loads(sa.set_version_text(b'{"template_version": "1"}', odd)), odd)
        for bad in (b"{ nope", b"[]", b"\xff\xfe"):
            self.assertIsNone(sa.set_version_text(bad, values))


class ManifestTests(Case):
    def read(self, project):
        return json.loads((project / ".claude/sync-manifest.json").read_text())

    def test_sync_list_and_keep_pattern(self):
        project = self.project()
        out = self.apply(project, "--keep-pattern", RETIRED, "--keep-pattern", ".claude/bogus/*",
                         "--keep-pattern", ".claude/mine/*.md")
        self.assertEqual(out["manifest"], {"changed": False, "sync_added": [], "sync_dropped": [],
                                           "lists_updated": False})
        self.assertEqual(out["warnings"][1:], [
            "--keep-pattern '.claude/bogus/*' is not a retired sync pattern; ignored",
            "--keep-pattern '.claude/mine/*.md' is not a retired sync pattern; ignored"])
        self.assertEqual((project / ".claude/sync-manifest.json").read_text(),
                         PROJECT[".claude/sync-manifest.json"])  # untouched: no list changed
        out = self.apply(project)
        self.assertEqual(out["manifest"], {"changed": True, "sync_added": [],
                                           "sync_dropped": [RETIRED], "lists_updated": False})
        data = self.read(project)
        self.assertEqual(data["categories"], {
            "sync": SYNC + [".claude/mine/*.md"],  # upstream, then the project's own
            "customize": CUSTOMIZE_V1, "ignore": IGNORE_V1 + [".claude/secrets.md"]})
        self.assertEqual(data["manifest_version"], "1.0.0")

    def test_kept_pattern_goes_after_the_compare_set(self):
        project = self.project(**{".claude/sync-manifest.json": manifest(
            [RETIRED, ".claude/mine/*.md", ".claude/commands/*.md"], CUSTOMIZE, IGNORE)})
        out = self.apply(project, "--keep-pattern", RETIRED)
        self.assertEqual(out["manifest"], {
            "changed": True, "sync_dropped": [], "lists_updated": False,
            "sync_added": [".claude/scripts/*.py", ".claude/rules/*.md", ".claude/vision/README.md"]})
        self.assertEqual(self.read(project)["categories"]["sync"],
                         SYNC + [".claude/mine/*.md", RETIRED])

    def test_manifest_lists(self):
        for flat in (False, True):
            with self.subTest(flat=flat):
                local = manifest(SYNC, CUSTOMIZE_V1 + [".claude/my-doc.md"],
                                 [".claude/secrets.md"] + IGNORE_V1, flat=flat, note="kept")
                project = self.project(**{".claude/sync-manifest.json": local})
                out = self.apply(project)  # without the flag the two lists are left alone
                self.assertIs(out["manifest"]["changed"], False)
                self.assertEqual((project / ".claude/sync-manifest.json").read_text(), local)
                out = self.apply(project, "--manifest-lists")
                self.assertEqual(out["manifest"], {"changed": True, "sync_added": [],
                                                   "sync_dropped": [], "lists_updated": True})
                data = self.read(project)
                cats = data if flat else data["categories"]
                self.assertEqual("categories" in data, not flat)
                self.assertEqual(data["note"], "kept")
                self.assertEqual({k: cats[k] for k in ("sync", "customize", "ignore")}, {
                    "sync": SYNC,
                    # upstream list, then project-added entries; the stale dashboard.md is gone
                    "customize": CUSTOMIZE + [".claude/my-doc.md"],
                    "ignore": IGNORE + [".claude/secrets.md"]})
                self.assertTrue((project / ".claude/sync-manifest.json").read_text().endswith("}\n"))
                again = self.apply(project, "--manifest-lists")
                self.assertEqual(again["changed_paths"], [])

    def test_non_ascii_entries_are_written_unescaped(self):
        local = manifest(SYNC + [RETIRED], CUSTOMIZE, IGNORE + [".claude/café/*"])
        project = self.project(**{".claude/sync-manifest.json": local})
        (project / ".claude/sync-manifest.json").write_text(
            json.dumps(json.loads(local), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.apply(project)
        self.assertIn(".claude/café/*",
                      (project / ".claude/sync-manifest.json").read_text(encoding="utf-8"))

    def test_missing_or_unparseable_is_never_created(self):
        for content in (None, "{ nope\n"):
            with self.subTest(content=content):
                project = self.project(**{".claude/sync-manifest.json": content})
                out = self.apply(project, "--status", "new", "--manifest-lists")
                self.assertEqual(out["manifest"], {"changed": False, "sync_added": [],
                                                   "sync_dropped": [], "lists_updated": False})
                self.assertIn("local sync-manifest.json missing or unreadable; not written",
                              out["warnings"])
                if content is None:
                    self.assertFalse((project / ".claude/sync-manifest.json").exists())
                else:
                    self.assertEqual((project / ".claude/sync-manifest.json").read_text(), content)


class SidecarTests(Case):
    def test_existing_entries_and_keys(self):
        existing = {
            "schema_version": "1.0", "last_full_sync_version": "1.0.0",
            "last_full_sync_date": "2026-01-02", "project_key": {"kept": True},
            "files": {
                ".claude/commands/gone.md": {"synced_hash": sha("gone\n")},        # no such file
                ".claude/commands/mine.md": {"synced_hash": sha("old\n")},         # not in files[]
                ".claude/commands/work.md": {"synced_hash": sha(WORK_V1)},         # modified
                ".claude/commands/same.md": {"synced_hash": sha("stale\n"), "note": "n"},
                ".claude/commands/flip.md": {"synced_hash": sha("flip A\n")}}}     # not selected
        project = self.project(**{SIDECAR: json.dumps(existing)})
        out = self.apply(project)   # bookkeeping only
        # Dropped: every entry but the one for a compare-set file that equals REF.
        self.assertEqual(out["sidecar"], {"recorded": 3, "dropped": 4, "created": False,
                                          "changed": True})
        state = self.sidecar(project)
        self.assertEqual({k: v for k, v in state.items() if k != "files"},
                         {k: v for k, v in existing.items() if k != "files"})
        self.assertEqual(state["files"], {
            ".claude/commands/same.md": {"synced_hash": sha("same\n"), "note": "n"},
            ".claude/scripts/plain.py": {"synced_hash": sha("print('plain')\n")},
            ".claude/vision/README.md": {"synced_hash": sha("vision v2\n")}})
        # A version bump refreshes the last-full-sync fields.
        out = self.apply(project, "--status", "template_copy")
        state = self.sidecar(project)
        self.assertEqual((state["last_full_sync_version"], state["last_full_sync_date"]),
                         ("1.3.0", datetime.date.today().isoformat()))
        self.assertEqual(state["project_key"], {"kept": True})
        self.assertEqual(state["files"][".claude/commands/flip.md"], {"synced_hash": sha("flip C\n")})

    def test_shallow_history_keeps_the_entry_it_classifies_by(self):
        """Template history is shallow, so same.md (content no reachable version holds)
        is a template copy only by its sidecar entry. A run that doesn't select the file
        keeps that entry: dropping it would turn the file into `modified` next time."""
        mine = "an older template version\n"
        shallow = Path(tempfile.mkdtemp(dir=ROOT)) / "shallow"
        git(ROOT, "clone", "-q", "--depth", "1", T.as_uri(), str(shallow))
        existing = {"schema_version": "1.0",
                    "files": {".claude/commands/same.md": {"synced_hash": sha(mine)},
                              ".claude/commands/mine.md": {"synced_hash": sha("old\n")}}}
        project = self.project(**{".claude/commands/same.md": mine,
                                  SIDECAR: json.dumps(existing)})
        args = ["--project", str(project), "--template-repo", str(shallow), "--ref", "HEAD"]

        def basis():
            r = subprocess.run([sys.executable, str(CHECK), *args], capture_output=True,
                               text=True, env=ENV, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            state = json.loads(r.stdout)
            self.assertIs(state["history_complete"], False)
            same = {f["path"]: f for f in state["files"]}[".claude/commands/same.md"]
            return same["status"], same["basis"]

        self.assertEqual(basis(), ("template_copy", "sidecar"))
        r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                           env=ENV, timeout=120)   # bookkeeping only
        self.assertEqual(r.returncode, 0, r.stderr)
        files = self.sidecar(project)["files"]
        self.assertEqual(files[".claude/commands/same.md"], {"synced_hash": sha(mine)})
        self.assertNotIn(".claude/commands/mine.md", files)   # outside files[]: still dropped
        self.assertEqual(basis(), ("template_copy", "sidecar"))

    def test_own_file_at_a_path_the_template_ships(self):
        """The template ships `.claude/commands/talk.md` at REF; the project has its own,
        different talk.md, and a sidecar entry with that file's hash (an earlier sync
        recorded it). With the whole history the file is `modified`, never a sidecar
        template copy, so `--status new,template_copy` leaves it alone, and the entry goes."""
        mine = "# Talk\nthe project's own command\n"
        template = Path(tempfile.mkdtemp(dir=ROOT)) / "template"
        git(ROOT, "clone", "-q", str(T), str(template))
        write(template, {".claude/commands/talk.md": "# Talk\nthe template's command\n"})
        git(template, "add", "-A")
        git(template, "commit", "-q", "-m", "ship talk.md", n=9)
        existing = {"schema_version": "1.0",
                    "files": {".claude/commands/talk.md": {"synced_hash": sha(mine)}}}
        project = self.project(**{".claude/commands/talk.md": mine,
                                  SIDECAR: json.dumps(existing)})
        args = ["--project", str(project), "--template-repo", str(template), "--ref", "HEAD"]
        r = subprocess.run([sys.executable, str(CHECK), *args], capture_output=True, text=True,
                           env=ENV, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        state = json.loads(r.stdout)
        self.assertIs(state["history_complete"], True)
        talk = {f["path"]: f for f in state["files"]}[".claude/commands/talk.md"]
        self.assertEqual((talk["status"], talk["basis"]), ("modified", None))
        r = subprocess.run([sys.executable, str(SCRIPT), *args, "--status", "new,template_copy"],
                           capture_output=True, text=True, env=ENV, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((project / ".claude/commands/talk.md").read_text(), mine)
        self.assertNotIn(".claude/commands/talk.md", [w["path"] for w in out["written"]])
        self.assertEqual(len(out["written"]), 4)  # positive control: the run did write
        self.assertEqual(out["sidecar"], {"recorded": 7, "dropped": 1, "created": False,
                                          "changed": True})
        self.assertNotIn(".claude/commands/talk.md", self.sidecar(project)["files"])
        self.assertIn({"path": ".claude/commands/talk.md", "status": "modified"}, out["remaining"])

    def test_unparseable_or_misshapen_is_replaced(self):
        for content in ("{ nope\n", "[]\n", '{"schema_version": "1.0", "files": []}\n'):
            with self.subTest(content=content):
                project = self.project(**{SIDECAR: content})
                out = self.apply(project)
                self.assertEqual(out["sidecar"], {"recorded": 3, "dropped": 0, "created": False,
                                                  "changed": True})
                self.assertIn("sync-state sidecar unreadable; ignored", out["warnings"])
                self.assertEqual(self.sidecar(project), {
                    "schema_version": "1.0",
                    "files": {p: {"synced_hash": sha(UPSTREAM[p])} for p in UP_TO_DATE}})

    def test_unchanged_sidecar_is_not_rewritten(self):
        """Content is compared, not formatting: a compact sidecar that already holds the
        right entries keeps its bytes."""
        compact = json.dumps({"files": {p: {"synced_hash": sha(UPSTREAM[p])} for p in UP_TO_DATE},
                              "schema_version": "1.0"})
        project = self.project(**{SIDECAR: compact})
        out = self.apply(project, "--keep-pattern", RETIRED)
        self.assertEqual(out["sidecar"], {"recorded": 3, "dropped": 0, "created": False,
                                          "changed": False})
        self.assertEqual(out["changed_paths"], [])
        self.assertEqual((project / SIDECAR).read_text(), compact)

    def test_symlinked_sidecar_is_not_written(self):
        project = self.project(**{"elsewhere/state.json": "{}\n"})
        os.symlink("../elsewhere/state.json", project / SIDECAR)
        out = self.apply(project, "--status", "new")
        self.assertIn("sync-state sidecar is not a regular file; not written", out["warnings"])
        self.assertEqual(out["sidecar"], {"recorded": 0, "dropped": 0, "created": False,
                                          "changed": False})
        self.assertEqual((project / "elsewhere/state.json").read_text(), "{}\n")
        self.assertTrue((project / SIDECAR).is_symlink())
        self.assertEqual([w["path"] for w in out["written"]], [".claude/commands/added.md"])


class RunModeTests(Case):
    ARGS = ["--status", "new,template_copy", "--paths-from", "-", "--manifest-lists"]

    def test_dry_run_writes_nothing_and_predicts_the_run(self):
        existing = {"schema_version": "1.0",
                    "files": {".claude/commands/gone.md": {"synced_hash": sha("gone\n")},
                              # absent now, written by this run: not a stale entry
                              ".claude/commands/added.md": {"synced_hash": sha("old\n")}}}
        project = self.project(**{SIDECAR: json.dumps(existing)})
        before = snapshot(project)
        dry = self.apply(project, *self.ARGS, "--dry-run", stdin=".claude/commands/work.md\n")
        self.assertEqual(snapshot(project), before)
        self.assertIs(dry["dry_run"], True)
        self.assertEqual(len(dry["written"]), 5)
        self.assertEqual(dry["sidecar"], {"recorded": 8, "dropped": 1, "created": False,
                                          "changed": True})
        real = self.apply(project, *self.ARGS, stdin=".claude/commands/work.md\n")
        self.assertEqual(dict(dry, dry_run=False), real)
        self.assertEqual(real["remaining"], [])
        self.assertEqual(set(self.statuses(project).values()), {"up_to_date"})
        self.assertEqual(sorted(self.sidecar(project)["files"]), FILES)
        self.assertNotEqual(snapshot(project), before)   # positive control: the real run wrote

    def test_dry_run_with_no_sidecar_reports_created(self):
        project = self.project()
        dry = self.apply(project, "--dry-run")
        self.assertEqual(dry["sidecar"], {"recorded": 3, "dropped": 0, "created": True,
                                          "changed": True})
        self.assertFalse((project / SIDECAR).exists())

    def test_bookkeeping_only_run(self):
        """No selection flags: no file content, no version bump; the manifest's sync list
        and the sidecar are still brought up to date."""
        project = self.project()
        before = snapshot(project)
        out = self.apply(project)
        self.assertEqual((out["written"], out["mode_fixed"], out["failed"]), ([], [], []))
        self.assertIs(out["version"]["bumped"], False)
        self.assertEqual(out["changed_paths"], [SIDECAR, ".claude/sync-manifest.json"])
        self.assertEqual(len(out["remaining"]), 5)
        after = snapshot(project)
        self.assertEqual({p for p in set(before) | set(after) if before.get(p) != after.get(p)},
                         set(out["changed_paths"]))
        self.assertEqual(self.apply(project)["changed_paths"], [])

    def test_git_project_with_the_template_remote(self):
        """Default arguments from the project root. The script edits the work tree only:
        nothing is staged, and gitignored bookkeeping still lands in changed_paths."""
        repo = Repo(Path(tempfile.mkdtemp(dir=ROOT)) / "proj")
        git(repo.path, "remote", "add", "template", str(T))
        git(repo.path, "fetch", "-q", "template")
        repo.commit("project", {**PROJECT, ".gitignore": SIDECAR + "\n"})
        r = subprocess.run([sys.executable, str(SCRIPT), "--status", "new,template_copy"],
                           capture_output=True, text=True, env=ENV, cwd=repo.path, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["ref"], "template/main")
        self.assertEqual(out["warnings"], [])
        self.assertEqual(len(out["written"]), 4)
        self.assertIn(SIDECAR, out["changed_paths"])
        self.assertEqual(git(repo.path, "diff", "--cached", "--name-only"), "")
        status = {line.strip() for line in
                  git(repo.path, "status", "--porcelain", "-uall").splitlines()}
        self.assertEqual(status, {"?? .claude/commands/added.md", "M .claude/commands/flip.md",
                                  "M .claude/rules/core.md", "M .claude/scripts/tool.py",
                                  "M .claude/sync-manifest.json", "M .claude/version.json"})

    def test_exit_2_cases(self):
        project = self.project()
        empty = Path(tempfile.mkdtemp(dir=ROOT))
        before = snapshot(project)
        cases = {
            "project without .claude/": (["--project", str(empty), "--template-repo", str(T),
                                          "--ref", "main"], "no .claude/ directory"),
            "template repo not a git repository": (["--project", str(project), "--template-repo",
                                                    str(empty), "--ref", "main"],
                                                   "not a git repository"),
            "unknown ref": (["--project", str(project), "--template-repo", str(T),
                             "--ref", "no-such-ref", "--status", "new"],
                            "does not resolve to a commit"),
            "usage error": (["--project", str(project), "--template-repo", str(T),
                             "--bogus"], "unrecognized arguments"),
        }
        for name, (args, needle) in cases.items():
            with self.subTest(name):
                r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                                   text=True, env=ENV, timeout=120)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertEqual(r.stdout, "")
                self.assertIn(needle, r.stderr)
        self.assertEqual(snapshot(project), before)

    def test_template_repository_is_refused(self):
        """A project root with a `template-maintenance/` directory is the template
        repository itself: exit 2 and nothing written; --dry-run still reports."""
        project = self.project(**{"template-maintenance/ship-log.md": "log\n"})
        self.assert_exit_2(project, ["--status", "new,template_copy"],
                           "--project is the template repository itself")
        before = snapshot(project)
        dry = self.apply(project, "--status", "new,template_copy", "--dry-run")
        self.assertEqual(len(dry["written"]), 4)
        self.assertEqual(snapshot(project), before)
        # Positive control: the same project without the directory is written.
        shutil.rmtree(project / "template-maintenance")
        self.assertEqual(len(self.apply(project, "--status", "new,template_copy")["written"]), 4)

    def test_help_names_every_flag(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True,
                           env=ENV, timeout=30)
        self.assertEqual(r.returncode, 0)
        for flag in ("--project", "--template-repo", "--ref", "--status", "--paths-from",
                     "--keep-pattern", "--manifest-lists", "--dry-run"):
            self.assertIn(flag, r.stdout)

    def test_classification_comes_from_sync_check(self):
        """The script loads sync-check.py from its own directory, leaves no __pycache__
        there, and exits 2 when it isn't there."""
        sc = sa.load_sync_check()
        self.assertEqual(Path(sc.__file__).resolve(), CHECK)
        self.assertTrue(callable(sc.check))
        scripts = Path(tempfile.mkdtemp(dir=ROOT))
        shutil.copy(SCRIPT, scripts)
        project = self.project()
        before = snapshot(project)
        r = self.run_script(project, "--status", "new", script=scripts / SCRIPT.name)
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("cannot load sync-check.py", r.stderr)
        self.assertEqual(snapshot(project), before)
        shutil.copy(CHECK, scripts)
        env = {k: v for k, v in ENV.items() if k != "PYTHONDONTWRITEBYTECODE"}
        r = subprocess.run([sys.executable, str(scripts / SCRIPT.name), "--project", str(project),
                            "--template-repo", str(T), "--ref", "main", "--status", "new"],
                           capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(os.listdir(scripts)), ["sync-apply.py", "sync-check.py"])


if __name__ == "__main__":
    unittest.main()
