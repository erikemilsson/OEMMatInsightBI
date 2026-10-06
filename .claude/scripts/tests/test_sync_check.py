#!/usr/bin/env python3
"""Tests for sync-check.py (FB-126, FB-136), run against temporary git repos.

One template repo is built per module. Its history: c0 has no manifest; c1 (1.0.0)
uses the flat manifest format; c2 (1.1.0) drops a pattern; cX commits an
unparseable manifest; c3 restores it with an unreadable version.json and deletes a
file; c4 (2.0.0) drops two patterns and deletes sync files (one listed exactly in
`sync`, as `.claude/vision/README.md` is in the real manifest), never-sync files, an
ignore-category example task and `.claude/README.md`; c5 (2.1.0) moves a pattern
to customize, re-adds `.claude/README.md` (as the real template did) and adds sync
files: one listed exactly that an upstream ignore glob also matches, and one that a
wildcard sync pattern and a customize glob both match (amendment A1: an exact sync
entry beats customize/ignore globs, a wildcard never does). Projects are plain
directories or git repos built per test. A second template repo (F, built by
build_files_template) carries the history the per-file classification tests need:
several versions of one path, a version whose version.json is unreadable, content that
returns to an earlier version, an executable file, and customize/ignore lists that
changed. Git is isolated from the user's config
(GIT_CONFIG_GLOBAL=/dev/null, GIT_CONFIG_NOSYSTEM=1) with fixed identities and dates.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "sync-check.py"
_spec = importlib.util.spec_from_file_location("sync_check", SCRIPT)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
           GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com")

IGNORE = [".claude/tasks/*.json", ".claude/version.json", ".claude/sync-manifest.json"]
SYNC_V1 = [".claude/commands/*.md", ".claude/old/*.md", ".claude/moved.md", ".claude/worktrees/*.md",
           ".claude/vision/_scaffold.md"]
UPSTREAM_SYNC = [".claude/commands/*.md", ".claude/rules/*.md", ".claude/vision/README.md",
                 ".claude/commands/*.md"]  # the duplicate is deliberate


def manifest(sync, customize=(), ignore=(), flat=False):
    cats = {"sync": list(sync), "customize": list(customize), "ignore": list(ignore)}
    return json.dumps(cats if flat else {"manifest_version": "1.0.0", "categories": cats},
                      indent=2) + "\n"


def version(v):
    return json.dumps({"template_version": v}) + "\n"


UPSTREAM_CUSTOMIZE = [".claude/README.md", ".claude/moved.md", ".claude/custom/*.md",
                      ".claude/rules/project-*.md"]
UPSTREAM_IGNORE = IGNORE + [".claude/vision/*.md", ".claude/old/local-*.md"]
UPSTREAM_MANIFEST = manifest(UPSTREAM_SYNC, UPSTREAM_CUSTOMIZE, UPSTREAM_IGNORE)

TEMPLATE_C1 = {
    ".claude/version.json": version("1.0.0"),
    ".claude/sync-manifest.json": manifest(SYNC_V1 + [".claude/flat-only/*.md"],
                                           [".claude/README.md"], IGNORE, flat=True),
    ".claude/commands/work.md": "work v1\n",
    ".claude/commands/legacy.md": "legacy v1\n",
    ".claude/commands/linked.md": "linked v1\n",
    ".claude/commands/oops.md": "oops v1\n",
    ".claude/commands/revived.md": "revived v1\n",  # deleted at c4, re-added at c5
    ".claude/commands/twice.md": "twice v1\n",      # deleted at c2 and again at c4
    ".claude/old/guide.md": "guide v1\n",
    ".claude/moved.md": "moved v1\n",
    ".claude/notes/scratch.md": "scratch v1\n",
    ".claude/notes/other.md": "other v1\n",
    ".claude/extra/a.md": "extra a v1\n",
    ".claude/extra/b.md": "extra b v1\n",
    ".claude/custom/c.md": "custom c v1\n",
    ".claude/worktrees/x.md": "x v1\n",
    ".claude/tasks/task-1.json": '{"id": "1"}\n',
    ".claude/README.md": "readme v1\n",
    ".claude/vision/_scaffold.md": "scaffold v1\n",     # exact sync entry; upstream ignore glob
    ".claude/old/local-notes.md": "local notes v1\n",  # wildcard sync; upstream ignore glob
}
DELETED_AT_C4 = [".claude/old/guide.md", ".claude/commands/legacy.md", ".claude/commands/linked.md",
                 ".claude/notes/scratch.md", ".claude/notes/other.md", ".claude/extra/a.md",
                 ".claude/extra/b.md", ".claude/custom/c.md", ".claude/worktrees/x.md",
                 ".claude/tasks/task-1.json", ".claude/README.md", ".claude/vision/_scaffold.md",
                 ".claude/old/local-notes.md", ".claude/commands/revived.md",
                 ".claude/commands/twice.md"]

BASE = None  # TemporaryDirectory holding every repo
ROOT = None  # its realpath
T = None     # template repo
C = {}       # commit name -> sha
F = None     # second template repo: per-file classification (FB-136)
D = {}       # its commits

F_SYNC = [".claude/commands/*.md", ".claude/scripts/*.py", ".claude/rules/*.md",
          ".claude/vision/README.md"]
F_IGNORE_V1 = [".claude/version.json", ".claude/sync-manifest.json", ".claude/dashboard.md",
               ".claude/vision/*.md", ".claude/to-customize.md"]
F_CUSTOMIZE = [".claude/README.md", ".claude/rules/project-*.md", ".claude/to-customize.md",
               ".claude/README.md"]  # the duplicate is deliberate
F_IGNORE = [".claude/version.json", ".claude/sync-manifest.json", ".claude/dashboard.html",
            ".claude/vision/*.md"]
WORK_V1 = "# Work\nstep one\nstep two\n"
WORK_V2 = "# Work\nstep one\nstep two\nstep three\n"   # committed with a broken version.json
WORK_V4 = "# Work\nstep one\nstep 2\nstep three\nstep four\n"
F_FILES = [".claude/commands/added.md", ".claude/commands/flip.md", ".claude/commands/same.md",
           ".claude/commands/work.md", ".claude/rules/core.md", ".claude/scripts/plain.py",
           ".claude/scripts/tool.py", ".claude/vision/README.md"]  # the compare-set files at d4


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


def build_files_template(path):
    """d1 (1.0.0) → d2 (unreadable version.json) → d3 (1.2.0) → d4 (1.3.0)."""
    repo = Repo(path)
    write(path, {".claude/scripts/tool.py": "print('tool v1')\n"})
    os.chmod(path / ".claude/scripts/tool.py", 0o755)  # mode 100755 in the tree
    D["d1"] = repo.commit("1.0.0", {
        ".claude/version.json": version("1.0.0"),
        ".claude/sync-manifest.json": manifest(F_SYNC + [".claude/old/*.md"],
                                               F_CUSTOMIZE[:2], F_IGNORE_V1),
        ".claude/commands/work.md": WORK_V1,
        ".claude/commands/flip.md": "flip A\n",
        ".claude/commands/same.md": "same\n",
        ".claude/scripts/plain.py": "print('plain')\n",
        ".claude/rules/core.md": "core v1\n",
        ".claude/rules/project-x.md": "project x\n",  # wildcard sync; customize glob
        ".claude/vision/README.md": "vision v1\n",    # exact sync entry; ignore glob
        ".claude/README.md": "readme\n"})
    D["d2"] = repo.commit("unreadable version", {
        ".claude/version.json": "{ broken\n",
        ".claude/commands/work.md": WORK_V2,
        ".claude/commands/flip.md": "flip B\n"})
    D["d3"] = repo.commit("1.2.0: lists change, flip.md returns to A", {
        ".claude/version.json": version("1.2.0"),
        ".claude/sync-manifest.json": manifest(F_SYNC, F_CUSTOMIZE, F_IGNORE),
        ".claude/commands/flip.md": "flip A\n",
        ".claude/commands/added.md": "added v1\n",
        ".claude/rules/core.md": "core v2\n",
        ".claude/scripts/tool.py": "print('tool v2')\n"})
    D["d4"] = repo.commit("1.3.0", {
        ".claude/version.json": version("1.3.0"),
        ".claude/commands/work.md": WORK_V4,
        ".claude/commands/flip.md": "flip C\n",
        ".claude/vision/README.md": "vision v2\n"})
    return repo


def setUpModule():
    global BASE, ROOT, T, F
    BASE = tempfile.TemporaryDirectory()
    ROOT = Path(os.path.realpath(BASE.name))
    ENV["GIT_CEILING_DIRECTORIES"] = str(ROOT)  # plain dirs under ROOT are never "in a repo"
    T = ROOT / "template"
    repo = Repo(T)
    C["c0"] = repo.commit("init, no manifest", {"README.md": "template\n"})
    C["c1"] = repo.commit("1.0.0, flat manifest", TEMPLATE_C1)
    C["c2"] = repo.commit("1.1.0: drop flat-only", {
        ".claude/version.json": version("1.1.0"),
        ".claude/sync-manifest.json": manifest(SYNC_V1, [".claude/README.md"], IGNORE),
        ".claude/commands/legacy.md": "legacy v2\n",
        ".claude/commands/work.md": "work v2\n",
        ".claude/commands/twice.md": None})
    C["cX"] = repo.commit("unparseable manifest", {".claude/sync-manifest.json": "{ not json\n"})
    C["c3"] = repo.commit("restore manifest, delete oops, unreadable version", {
        ".claude/sync-manifest.json": manifest(SYNC_V1, [".claude/README.md"], IGNORE),
        ".claude/version.json": "{ broken\n",
        ".claude/commands/oops.md": None,
        ".claude/commands/twice.md": "twice v2\n"})
    C["c4"] = repo.commit("2.0.0: drop old/ and worktrees/, delete files", {
        ".claude/version.json": version("2.0.0"),
        ".claude/sync-manifest.json": manifest([".claude/commands/*.md", ".claude/moved.md"],
                                               [".claude/README.md"], IGNORE),
        **{p: None for p in DELETED_AT_C4}})
    C["c5"] = repo.commit("2.1.0: moved.md to customize, new files", {
        ".claude/version.json": version("2.1.0"),
        ".claude/sync-manifest.json": UPSTREAM_MANIFEST,
        ".claude/README.md": "readme v1\n",
        ".claude/commands/work.md": "work v3\n",
        ".claude/commands/new.md": "new v1\n",
        ".claude/commands/revived.md": "revived v2\n",
        ".claude/commands/osync.md": "osync v1\n",
        ".claude/rules/core.md": "core v1\n",
        ".claude/rules/style.md": "style v1\n",
        ".claude/rules/project-example.md": "project example v1\n",  # wildcard sync; customize glob
        ".claude/vision/README.md": "vision v1\n",  # exact sync entry; ignore glob
        ".claude/unlisted.md": "unlisted v1\n"})  # in no manifest category
    F = ROOT / "files-template"
    build_files_template(F)


def tearDownModule():
    BASE.cleanup()


def run(*args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env=ENV, cwd=cwd, timeout=120)


class Case(unittest.TestCase):
    def new_dir(self):
        return Path(tempfile.mkdtemp(dir=ROOT))

    def check(self, *args, cwd=None):
        r = run(*args, cwd=cwd)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def check_against_template(self, project, *extra):
        return self.check("--project", str(project), "--template-repo", str(T), "--ref", "main", *extra)

    def isolated(self):
        """For direct calls into the module: its git subprocesses get ENV, not the user's config."""
        return mock.patch.dict(os.environ, ENV, clear=True)


# ---------------------------------------------------------------- plain-directory project

LOCAL_MANIFEST = manifest(
    [".claude/zz-own/*.md", ".claude/commands/*.md", ".claude/old/*.md", ".claude/moved.md",
     ".claude/flat-only/*.md", ".claude/tasks/*.json", ".claude/aa-own/*.md", ".claude/zz-own/*.md"],
    [".claude/extra/a.md"], [".claude/extra/b.md", ".claude/vision/*.md"])

PLAIN_PROJECT = {
    ".claude/version.json": version("1.1.0"),
    ".claude/sync-manifest.json": LOCAL_MANIFEST,
    ".claude/commands/work.md": "work v2\n",           # shipped at REF: never retired
    ".claude/commands/legacy.md": "legacy v1\n",       # older template blob: unmodified, owned
    ".claude/commands/oops.md": "oops v1\n",           # deleted after an unparseable manifest
    ".claude/commands/my-own.md": "mine\n",            # the template never shipped it
    ".claude/commands/revived.md": "revived v1\n",     # shipped at REF again: never retired
    ".claude/commands/twice.md": "twice v1\n",         # deleted twice: newest deletion counts
    ".claude/old/guide.md": "guide v1 edited\n",       # modified, owned
    ".claude/notes/scratch.md": "scratch v1\n",        # unmodified, never a sync file
    ".claude/notes/other.md": "other edited\n",        # modified, never a sync file
    ".claude/extra/a.md": "extra a v1\n",              # local customize
    ".claude/extra/b.md": "extra b v1\n",              # local ignore
    ".claude/custom/c.md": "custom c v1\n",            # upstream customize
    ".claude/worktrees/x.md": "x v1\n",                # pruned directory
    ".claude/tasks/task-1.json": '{"id": "1"}\n',      # upstream ignore (example task)
    ".claude/README.md": "readme v1\n",                # deleted upstream, then re-added
    ".claude/vision/_scaffold.md": "scaffold v1\n",    # exact sync entry when deleted (A1)
    ".claude/old/local-notes.md": "local notes v1\n",  # wildcard sync when deleted; ignore glob
    "linked-target.md": "linked v1\n",
}


class PlainProjectTests(Case):
    @classmethod
    def setUpClass(cls):
        cls.project = Path(tempfile.mkdtemp(dir=ROOT))
        write(cls.project, PLAIN_PROJECT)
        os.symlink("../../linked-target.md", cls.project / ".claude/commands/linked.md")
        r = run("--project", str(cls.project), "--template-repo", str(T), "--ref", "main")
        assert r.returncode == 0, r.stderr
        cls.out = json.loads(r.stdout)

    def test_every_key_present(self):
        self.assertEqual(list(self.out), ["ref", "ref_commit", "upstream_version", "local_version",
                                          "git", "patterns", "retired_files", "uncommitted_sync",
                                          "history_complete", "files", "manifest", "sidecar",
                                          "warnings"])
        self.assertEqual(list(self.out["patterns"]), ["compare", "project_added", "retired"])
        self.assertEqual(self.out["ref"], "main")
        self.assertEqual(self.out["ref_commit"], C["c5"])
        self.assertEqual(self.out["upstream_version"], "2.1.0")
        self.assertEqual(self.out["local_version"], "1.1.0")

    def test_not_a_git_work_tree(self):
        self.assertIs(self.out["git"], False)
        self.assertEqual(self.out["uncommitted_sync"], [])
        self.assertEqual(self.out["warnings"], ["project is not a git work tree; uncommitted_sync skipped"])

    def test_patterns(self):
        p = self.out["patterns"]
        # compare = upstream order (deduplicated), then project-added in local order (deduplicated)
        self.assertEqual(p["compare"], [".claude/commands/*.md", ".claude/rules/*.md",
                                        ".claude/vision/README.md", ".claude/zz-own/*.md",
                                        ".claude/aa-own/*.md"])
        self.assertEqual(p["project_added"], [".claude/zz-own/*.md", ".claude/aa-own/*.md"])
        self.assertEqual(p["retired"], [
            {"pattern": ".claude/flat-only/*.md", "removed_in": "1.1.0"},  # only in the flat c1 manifest
            {"pattern": ".claude/moved.md", "removed_in": "2.1.0"},        # moved to customize
            {"pattern": ".claude/old/*.md", "removed_in": "2.0.0"},        # dropped
            {"pattern": ".claude/tasks/*.json", "removed_in": None},       # upstream ignore, never sync
        ])

    def test_retired_files(self):
        self.assertEqual(self.out["retired_files"], [
            {"path": ".claude/commands/legacy.md", "state": "unmodified", "owned": True,
             "removed_in": "2.0.0", "removed_commit": C["c4"]},
            # removed_commit^ has an unparseable manifest (not owned); version.json unreadable there
            {"path": ".claude/commands/oops.md", "state": "unmodified", "owned": False,
             "removed_in": None, "removed_commit": C["c3"]},
            {"path": ".claude/commands/twice.md", "state": "unmodified", "owned": True,
             "removed_in": "2.0.0", "removed_commit": C["c4"]},
            {"path": ".claude/notes/scratch.md", "state": "unmodified", "owned": False,
             "removed_in": "2.0.0", "removed_commit": C["c4"]},
            {"path": ".claude/old/guide.md", "state": "modified", "owned": True,
             "removed_in": "2.0.0", "removed_commit": C["c4"]},
            {"path": ".claude/vision/_scaffold.md", "state": "unmodified", "owned": True,
             "removed_in": "2.0.0", "removed_commit": C["c4"]},
        ])

    def test_exact_sync_entry_at_deletion_beats_customize_ignore_globs(self):
        """A1: `.claude/vision/_scaffold.md` matches the upstream and local ignore glob
        `.claude/vision/*.md`, but the manifest at removed_commit^ listed it exactly in
        `sync`, so it is a retired file. `.claude/old/local-notes.md` was owned only through
        the wildcard `.claude/old/*.md`, so the upstream ignore glob still excludes it."""
        listed = {f["path"]: f for f in self.out["retired_files"]}
        self.assertEqual(listed[".claude/vision/_scaffold.md"]["owned"], True)
        self.assertNotIn(".claude/old/local-notes.md", listed)
        with self.isolated():
            t = sc.Template(str(T), C["c5"])
            before = t.manifest(t.deleted()[".claude/vision/_scaffold.md"] + "^")["sync"]
            upstream_ignore = t.manifest(C["c5"])["ignore"]
        self.assertIn(".claude/vision/_scaffold.md", before)  # exact entry, not a glob match
        self.assertTrue(sc.matches(".claude/vision/_scaffold.md", upstream_ignore))

    def test_excluded_files_meet_the_other_rules(self):
        """Positive control: each excluded file was deleted upstream and is owned or
        byte-identical, so the exclusion under test is what keeps it out."""
        with self.isolated():
            t = sc.Template(str(T), C["c5"])
            deleted = t.deleted()
            for path in (".claude/worktrees/x.md", ".claude/commands/linked.md",
                         ".claude/old/local-notes.md", ".claude/commands/revived.md"):  # owned
                self.assertTrue(sc.matches(path, t.manifest(deleted[path] + "^")["sync"]), path)
            for path in (".claude/extra/a.md", ".claude/extra/b.md", ".claude/custom/c.md",
                         ".claude/tasks/task-1.json", ".claude/README.md",
                         ".claude/old/local-notes.md", ".claude/commands/revived.md"):  # unmodified
                self.assertIn(path, deleted)
                local_id = t.hash_files([str(self.project / path)])[str(self.project / path)]
                self.assertIn(local_id, t.blob_ids(path), path)
        listed = [f["path"] for f in self.out["retired_files"]]
        for path in (".claude/worktrees/x.md", ".claude/commands/linked.md", ".claude/extra/a.md",
                     ".claude/extra/b.md", ".claude/custom/c.md", ".claude/tasks/task-1.json",
                     ".claude/README.md", ".claude/notes/other.md", ".claude/commands/my-own.md",
                     ".claude/commands/work.md", ".claude/old/local-notes.md",
                     ".claude/commands/revived.md"):
            self.assertNotIn(path, listed)

    def test_symlink_replaced_by_a_regular_file_is_listed(self):
        project = self.new_dir()
        shutil.copytree(self.project, project, symlinks=True, dirs_exist_ok=True)
        link = project / ".claude/commands/linked.md"
        link.unlink()
        link.write_text("linked v1\n")
        out = self.check_against_template(project)
        self.assertIn({"path": ".claude/commands/linked.md", "state": "unmodified", "owned": True,
                       "removed_in": "2.0.0", "removed_commit": C["c4"]}, out["retired_files"])

    def test_template_repo_subdirectory_or_bare_clone(self):
        bare = self.new_dir() / "template.git"
        git(ROOT, "clone", "-q", "--bare", str(T), str(bare))
        for repo in (T / ".claude", bare):
            with self.subTest(repo=repo.name):
                out = self.check("--project", str(self.project), "--template-repo", str(repo),
                                 "--ref", "main")
                self.assertEqual(out, self.out)


class LocalManifestWarningTests(Case):
    def test_missing_or_unreadable_local_manifest(self):
        for content in (None, "{ nope\n", "[1, 2]\n"):
            with self.subTest(content=content):
                project = self.new_dir()
                files = {".claude/commands/legacy.md": "legacy v2\n"}  # no version.json
                if content is not None:
                    files[".claude/sync-manifest.json"] = content
                write(project, files)
                out = self.check_against_template(project)
                self.assertEqual(out["warnings"], [
                    "local sync-manifest.json missing or unreadable; local patterns treated as empty",
                    "project is not a git work tree; uncommitted_sync skipped"])
                self.assertEqual(out["patterns"], {
                    "compare": [".claude/commands/*.md", ".claude/rules/*.md", ".claude/vision/README.md"],
                    "project_added": [], "retired": []})
                self.assertIsNone(out["local_version"])
                self.assertEqual([f["path"] for f in out["retired_files"]], [".claude/commands/legacy.md"])


# ---------------------------------------------------------------- git projects

class UncommittedSyncTests(Case):
    def test_default_args_template_remote(self):
        """--project ., --template-repo = project, --ref template/main; every change type."""
        repo = Repo(self.new_dir() / "proj")
        git(repo.path, "remote", "add", "template", str(T))
        git(repo.path, "fetch", "-q", "template")
        repo.commit("project at 1.1.0", {
            ".claude/version.json": version("1.1.0"),
            ".claude/sync-manifest.json": manifest(SYNC_V1, [".claude/README.md"], IGNORE),
            ".claude/commands/work.md": "work v2\n",
            ".claude/commands/legacy.md": "legacy v2\n",
            ".claude/commands/osync.md": "osync v0\n",
            ".claude/commands/mine.md": "mine\n",
            ".claude/commands/drift.md": "drift old\n",
            ".claude/commands/revived.md": "revived v1\n",
            ".claude/old/guide.md": "guide local\n",
            ".claude/notes/scratch.md": "scratch v1\n",
            ".claude/notes/other.md": "other local\n",
            ".claude/tasks/task-1.json": '{"id": "1"}\n',
            ".claude/README.md": "readme v1\n",
            ".claude/rules/style-old.md": "style v1\n",
            ".claude/vision/README.md": "vision v0\n",
            "src/app.py": "print('hi')\n"})
        write(repo.path, {
            ".claude/version.json": version("2.1.0"),                   # piggyback
            ".claude/sync-manifest.json": UPSTREAM_MANIFEST,            # piggyback
            ".claude/commands/work.md": "work v3\n",                    # modified, equals REF
            ".claude/commands/new.md": "new v1\n",                      # untracked, equals REF
            ".claude/rules/core.md": "core v1\n",                       # staged below, equals REF
            ".claude/commands/osync.md": "osync local\n",               # differs from REF
            ".claude/commands/drift.md": "drift new\n",                 # not at REF
            ".claude/commands/brand-new-own.md": "own\n",               # untracked, not at REF
            ".claude/unlisted.md": "unlisted v1\n",                     # equals REF; no compare pattern
            ".claude/vision/README.md": "vision v1\n",                  # equals REF; exact sync entry
            ".claude/old/guide.md": None,                               # owned at deletion
            ".claude/notes/scratch.md": None,                           # committed blob in history
            ".claude/notes/other.md": None,                             # neither
            ".claude/tasks/task-1.json": None,                          # upstream ignore
            ".claude/README.md": None,                                  # shipped at REF
            ".claude/commands/mine.md": None,                           # never shipped
            ".claude/commands/revived.md": None,                        # shipped at REF again
            "src/app.py": "print('changed')\n"})                       # outside .claude/
        git(repo.path, "add", "--", ".claude/rules/core.md")
        git(repo.path, "rm", "-q", "--", ".claude/commands/legacy.md")
        git(repo.path, "mv", ".claude/rules/style-old.md", ".claude/rules/style.md")  # rename: skipped
        status = git(repo.path, "status", "--porcelain")
        self.assertIn("R  .claude/rules/style-old.md -> .claude/rules/style.md", status)
        self.assertIn("A  .claude/rules/core.md", status)
        self.assertIn("D  .claude/commands/legacy.md", status)
        out = self.check(cwd=repo.path)
        self.assertEqual(out["ref"], "template/main")
        self.assertEqual(out["ref_commit"], C["c5"])
        self.assertIs(out["git"], True)
        self.assertEqual(out["warnings"], [])
        self.assertEqual(out["retired_files"], [])
        self.assertEqual(out["uncommitted_sync"], [
            {"path": ".claude/commands/legacy.md", "change": "deleted"},
            {"path": ".claude/commands/new.md", "change": "added"},
            {"path": ".claude/commands/work.md", "change": "modified"},
            {"path": ".claude/notes/scratch.md", "change": "deleted"},
            {"path": ".claude/old/guide.md", "change": "deleted"},
            {"path": ".claude/rules/core.md", "change": "added"},
            {"path": ".claude/sync-manifest.json", "change": "modified"},
            {"path": ".claude/version.json", "change": "modified"},
            {"path": ".claude/vision/README.md", "change": "modified"},
        ])

    def test_exact_sync_entry_beats_customize_ignore_globs(self):
        """A1, both directions. Listed: `.claude/vision/README.md` (upstream `sync` names it
        exactly; the ignore glob `.claude/vision/*.md` also matches) synced but uncommitted,
        and `.claude/vision/_scaffold.md` (named exactly in `sync` when the template deleted
        it) deleted. Not listed: `.claude/rules/project-example.md` (equal to REF, but only
        the wildcard `.claude/rules/*.md` covers it against the customize glob
        `.claude/rules/project-*.md`) and `.claude/old/local-notes.md` (a wildcard-owned
        retired file under the ignore glob `.claude/old/local-*.md`), deleted."""
        repo = Repo(self.new_dir() / "proj")
        repo.commit("project", {
            ".claude/version.json": version("2.1.0"),
            ".claude/sync-manifest.json": UPSTREAM_MANIFEST,
            ".claude/vision/README.md": "vision v0\n",
            ".claude/vision/_scaffold.md": "scaffold v1\n",
            ".claude/old/local-notes.md": "local notes v1\n"})
        write(repo.path, {".claude/vision/README.md": "vision v1\n",
                          ".claude/rules/project-example.md": "project example v1\n",
                          ".claude/vision/_scaffold.md": None,
                          ".claude/old/local-notes.md": None})
        out = self.check_against_template(repo.path)
        self.assertEqual(out["uncommitted_sync"], [
            {"path": ".claude/vision/README.md", "change": "modified"},
            {"path": ".claude/vision/_scaffold.md", "change": "deleted"},
        ])
        # Positive control: without the two globs (in a template clone and in the local
        # manifest, which rule 2 also reads), both files are listed.
        widened = manifest(UPSTREAM_SYNC,
                           [p for p in UPSTREAM_CUSTOMIZE if p != ".claude/rules/project-*.md"],
                           [p for p in UPSTREAM_IGNORE if p != ".claude/old/local-*.md"])
        clone = self.new_dir() / "tpl"
        git(ROOT, "clone", "-q", str(T), str(clone))
        write(clone, {".claude/sync-manifest.json": widened})
        git(clone, "commit", "-q", "-am", "drop two globs", n=10)
        write(repo.path, {".claude/sync-manifest.json": widened})
        out = self.check("--project", str(repo.path), "--template-repo", str(clone), "--ref", "HEAD")
        self.assertEqual(out["uncommitted_sync"], [
            {"path": ".claude/old/local-notes.md", "change": "deleted"},
            {"path": ".claude/rules/project-example.md", "change": "added"},
            {"path": ".claude/sync-manifest.json", "change": "modified"},
            {"path": ".claude/vision/README.md", "change": "modified"},
            {"path": ".claude/vision/_scaffold.md", "change": "deleted"},
        ])

    def test_earlier_sync_is_listed_after_ref_moves_on(self):
        """A sync to 1.1.0 was never committed, then the template moved on to 2.1.0. Its
        files equal older template versions of their paths, not REF's, and are still
        listed, so Part 5 Step 5 commits the whole sync. A hand edit equal to no template
        version is not listed."""
        repo = Repo(self.new_dir() / "proj")
        repo.commit("project at 1.0.0", {
            ".claude/version.json": version("1.0.0"),
            ".claude/sync-manifest.json": manifest(SYNC_V1, [".claude/README.md"], IGNORE),
            ".claude/commands/work.md": "work v1\n"})
        write(repo.path, {".claude/version.json": version("1.1.0"),       # the 1.1.0 sync
                          ".claude/commands/work.md": "work v2\n",        # 1.1.0's copy
                          ".claude/commands/revived.md": "revived v1\n"})  # untracked
        expected = [{"path": ".claude/commands/revived.md", "change": "added"},
                    {"path": ".claude/commands/work.md", "change": "modified"},
                    {"path": ".claude/version.json", "change": "modified"}]
        # At the sync's own version, every file equals REF.
        at_sync = self.check("--project", str(repo.path), "--template-repo", str(T),
                             "--ref", C["c2"])
        self.assertEqual(at_sync["uncommitted_sync"], expected)
        # The template moved on: REF's copies differ, older template copies match.
        with self.isolated():
            t = sc.Template(str(T), C["c5"])
            ref_tree = t.tree()
            for path in (".claude/commands/work.md", ".claude/commands/revived.md"):
                local = t.hash_files([str(repo.path / path)])[str(repo.path / path)]
                self.assertNotEqual(local, ref_tree[path][1], path)
                self.assertIn(local, t.blob_ids(path), path)
        self.assertEqual(self.check_against_template(repo.path)["uncommitted_sync"], expected)
        # A hand edit matches no template version: work.md drops out.
        write(repo.path, {".claude/commands/work.md": "work v2\nlocal tweak\n"})
        self.assertEqual(self.check_against_template(repo.path)["uncommitted_sync"], [
            {"path": ".claude/commands/revived.md", "change": "added"},
            {"path": ".claude/version.json", "change": "modified"},
        ])

    def test_symlinks_are_not_listed(self):
        """Modified and added paths are listed only as regular files: `git hash-object`
        follows a symlink and would hash its target. A tracked file replaced by a symlink
        (status ` T`) and an untracked symlink, both to a copy of REF's content, are not
        listed; the same content as regular files is (positive control)."""
        repo = Repo(self.new_dir() / "proj")
        repo.commit("project", {
            ".claude/version.json": version("2.1.0"),
            ".claude/sync-manifest.json": UPSTREAM_MANIFEST,
            ".claude/commands/work.md": "work v2\n",
            "copies/work.md": "work v3\n",
            "copies/new.md": "new v1\n"})
        commands = repo.path / ".claude/commands"
        (commands / "work.md").unlink()
        os.symlink("../../copies/work.md", commands / "work.md")
        os.symlink("../../copies/new.md", commands / "new.md")
        status = {line.strip() for line in git(repo.path, "status", "--porcelain").splitlines()}
        self.assertEqual(status, {"T .claude/commands/work.md", "?? .claude/commands/new.md"})
        self.assertEqual(self.check_against_template(repo.path)["uncommitted_sync"], [])
        for name in ("work.md", "new.md"):
            (commands / name).unlink()
            (commands / name).write_text((repo.path / "copies" / name).read_text())
        self.assertEqual(self.check_against_template(repo.path)["uncommitted_sync"], [
            {"path": ".claude/commands/new.md", "change": "added"},
            {"path": ".claude/commands/work.md", "change": "modified"},
        ])

    def test_git_status_does_not_write_the_index(self):
        """Read-only: stale stat data makes a plain `git status` rewrite the index; the
        script's (GIT_OPTIONAL_LOCKS=0) must not."""
        repo = Repo(self.new_dir() / "proj")
        repo.commit("project", {".claude/sync-manifest.json": UPSTREAM_MANIFEST,
                                ".claude/commands/work.md": "work v3\n"})
        work = repo.path / ".claude/commands/work.md"
        os.utime(work, (work.stat().st_mtime - 3600,) * 2)  # same content, new stat data
        index = repo.path / ".git/index"
        before = index.read_bytes()
        self.check_against_template(repo.path)
        self.assertEqual(index.read_bytes(), before)
        git(repo.path, "status", "--porcelain")  # positive control: plain status refreshes it
        self.assertNotEqual(index.read_bytes(), before)

    def test_status_parser_skips_a_rename_and_its_source_path(self):
        repo = Repo(self.new_dir() / "proj")
        repo.commit("project", {".claude/a.md": "a\n", ".claude/b.md": "b\n", ".claude/c.md": "c\n"})
        git(repo.path, "mv", ".claude/a.md", ".claude/a2.md")
        write(repo.path, {".claude/b.md": "b edited\n", ".claude/c.md": None, ".claude/d.md": "d\n"})
        with self.isolated():
            entries = sc.git_status(str(repo.path))
        self.assertEqual(sorted(entries), [(".claude/b.md", "modified", ".claude/b.md"),
                                           (".claude/c.md", "deleted", ".claude/c.md"),
                                           (".claude/d.md", "added", ".claude/d.md")])

    def test_no_piggyback_when_nothing_else_is_listed(self):
        repo = Repo(self.new_dir() / "proj")
        repo.commit("project", {
            ".claude/version.json": version("1.1.0"),
            ".claude/sync-manifest.json": manifest(SYNC_V1, [], IGNORE),
            ".claude/commands/own.md": "own\n"})
        write(repo.path, {".claude/version.json": version("2.1.0"),
                          ".claude/sync-manifest.json": UPSTREAM_MANIFEST,
                          ".claude/commands/own.md": "own edited\n"})
        out = self.check_against_template(repo.path)
        self.assertIs(out["git"], True)
        self.assertEqual(out["uncommitted_sync"], [])

    def test_project_in_a_subdirectory_of_its_repo(self):
        repo = Repo(self.new_dir() / "mono")
        repo.commit("app at 1.1.0", {
            "app/.claude/version.json": version("1.1.0"),
            "app/.claude/sync-manifest.json": UPSTREAM_MANIFEST,
            "app/.claude/commands/work.md": "work v2\n",
            "app/.claude/notes/scratch.md": "scratch v1\n",
            "lib/.claude/commands/work.md": "work v2\n"})
        write(repo.path, {"app/.claude/version.json": version("2.1.0"),
                          "app/.claude/commands/work.md": "work v3\n",
                          "app/.claude/notes/scratch.md": None,  # listed via HEAD:app/.claude/...
                          "lib/.claude/commands/work.md": "work v3\n"})  # outside the project
        out = self.check_against_template(repo.path / "app")
        self.assertEqual(out["uncommitted_sync"], [
            {"path": ".claude/commands/work.md", "change": "modified"},
            {"path": ".claude/notes/scratch.md", "change": "deleted"},
            {"path": ".claude/version.json", "change": "modified"},
        ])


# ---------------------------------------------------------------- files[] (FB-136)

def sha(content):
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()


def sidecar(files, **extra):
    return json.dumps({"schema_version": "1.0", **extra,
                       "files": {p: {"synced_hash": h} for p, h in files.items()}}) + "\n"


def entry(path, status, mode="100644", mode_matches=True, version=None, basis=None,
          shared_lines=None):
    return {"path": path, "status": status, "mode": mode, "mode_matches": mode_matches,
            "version": version, "basis": basis, "shared_lines": shared_lines}


# One file per status and basis; see ClassificationTests.test_statuses for the expectations.
F_PROJECT = {
    ".claude/version.json": version("1.0.0"),
    ".claude/sync-manifest.json": manifest(F_SYNC, F_CUSTOMIZE[:2], F_IGNORE_V1),
    ".claude/commands/flip.md": "flip A\n",
    ".claude/commands/same.md": "same\n",
    ".claude/commands/work.md": WORK_V2,
    ".claude/rules/core.md": "core v1\n",
    ".claude/rules/project-x.md": "project x\n",
    ".claude/scripts/plain.py": "print('plain')\nprint('mine')\n",
    ".claude/scripts/tool.py": "print('tool v2')\n",
    ".claude/vision/README.md": "vision v1\n",
    ".claude/README.md": "readme\n",
}


class FilesCase(Case):
    def project(self, files=None, **changes):
        """A plain-directory project: F_PROJECT (or files) with changes applied
        (None deletes a path)."""
        project = self.new_dir()
        write(project, {p: c for p, c in {**(F_PROJECT if files is None else files),
                                          **changes}.items() if c is not None})
        return project

    def files(self, project, *extra, repo=None, ref="main"):
        out = self.check("--project", str(project), "--template-repo", str(repo or F),
                         "--ref", ref, *extra)
        return out, {f["path"]: f for f in out["files"]}


class ClassificationTests(FilesCase):
    def test_statuses(self):
        project = self.project()
        os.chmod(project / ".claude/scripts/plain.py", 0o755)
        out, files = self.files(project)
        self.assertIs(out["history_complete"], True)
        self.assertEqual(out["warnings"], ["project is not a git work tree; uncommitted_sync skipped"])
        self.assertEqual(out["files"], [
            entry(".claude/commands/added.md", "new", mode_matches=None),
            # A at d1 (1.0.0), B at d2, A again at d3 (1.2.0): the newest commit that set it
            entry(".claude/commands/flip.md", "template_copy", version="1.2.0", basis="history"),
            entry(".claude/commands/same.md", "up_to_date"),
            # version.json is unreadable at the commit that set this content
            entry(".claude/commands/work.md", "template_copy", basis="history"),
            entry(".claude/rules/core.md", "template_copy", version="1.0.0", basis="history"),
            # 1 of its 2 lines is a template line; local mode 0755 against 100644
            entry(".claude/scripts/plain.py", "modified", mode_matches=False, shared_lines=0.5),
            # equals REF's blob (set at d3, unchanged at d4); local mode 0644 against 100755
            entry(".claude/scripts/tool.py", "up_to_date", mode="100755", mode_matches=False),
            # named exactly in upstream `sync`, so the ignore glob doesn't exclude it (A1)
            entry(".claude/vision/README.md", "template_copy", version="1.0.0", basis="history"),
        ])
        self.assertEqual(sorted(files), F_FILES)

    def test_compare_set_membership(self):
        """Not in files[]: a path under an upstream customize glob that only a wildcard
        sync pattern covers, customize/ignore files, and a project file the template
        never shipped. Positive control: each exists locally, and the excluded template
        paths are blobs at REF."""
        project = self.project(**{".claude/commands/mine.md": "mine\n"})
        _out, files = self.files(project)
        with self.isolated():
            tree = sc.Template(str(F), D["d4"]).tree()
        for path in (".claude/rules/project-x.md", ".claude/README.md", ".claude/version.json",
                     ".claude/sync-manifest.json"):
            self.assertEqual(tree[path][0], "blob", path)
            self.assertTrue((project / path).is_file(), path)
            self.assertNotIn(path, files)
        self.assertNotIn(".claude/commands/mine.md", files)
        self.assertEqual(tree[".claude/scripts/tool.py"][2], "100755")
        self.assertEqual(tree[".claude/scripts/plain.py"][2], "100644")

    def test_symlink_blob_at_ref_is_not_a_compare_set_file(self):
        """A mode-120000 blob that matches a sync pattern stays out of files[]: its
        content is a link target, never file content to write."""
        repo = Repo(self.new_dir() / "linked-template")
        write(repo.path, {".claude/version.json": version("1.0.0"),
                          ".claude/sync-manifest.json": manifest([".claude/commands/*.md"]),
                          ".claude/commands/work.md": "work\n"})
        os.symlink("work.md", repo.path / ".claude/commands/link.md")
        repo.commit("1.0.0", {})
        with self.isolated():
            tree = sc.Template(str(repo.path), git(repo.path, "rev-parse", "HEAD")).tree()
        self.assertEqual(tree[".claude/commands/link.md"][::2], ("blob", "120000"))
        self.assertTrue(sc.matches(".claude/commands/link.md", [".claude/commands/*.md"]))
        project = self.project(files={".claude/commands/work.md": "work\n"})
        _out, files = self.files(project, repo=repo.path)
        self.assertEqual(sorted(files), [".claude/commands/work.md"])

    def test_project_added_pattern_joins_the_compare_set(self):
        """`.claude/README.md` is an upstream customize file, so a local sync pattern can't
        pull it in; `.claude/extra/*.md` matches nothing at REF. Neither adds an entry."""
        project = self.project(**{".claude/sync-manifest.json": manifest(
            F_SYNC + [".claude/README.md", ".claude/extra/*.md"], F_CUSTOMIZE, F_IGNORE)})
        out, files = self.files(project)
        self.assertEqual(out["patterns"]["retired"], [{"pattern": ".claude/README.md",
                                                       "removed_in": None}])
        self.assertEqual(out["patterns"]["project_added"], [".claude/extra/*.md"])
        self.assertEqual(sorted(files), F_FILES)

    def test_mode_matches(self):
        project = self.project()
        os.chmod(project / ".claude/scripts/tool.py", 0o700)   # owner-execute is what counts
        os.chmod(project / ".claude/commands/same.md", 0o600)
        _out, files = self.files(project)
        self.assertIs(files[".claude/scripts/tool.py"]["mode_matches"], True)
        self.assertIs(files[".claude/commands/same.md"]["mode_matches"], True)
        os.chmod(project / ".claude/commands/same.md", 0o744)
        _out, files = self.files(project)
        self.assertIs(files[".claude/commands/same.md"]["mode_matches"], False)
        self.assertEqual(files[".claude/commands/same.md"]["status"], "up_to_date")

    def test_non_regular_local_paths(self):
        """A symlink (even to identical content) and a directory are `modified` with null
        mode_matches and shared_lines: the script never reads through them."""
        project = self.project(**{".claude/commands/same.md": None, ".claude/rules/core.md": None,
                                  "elsewhere/same.md": "same\n"})
        os.symlink("../../elsewhere/same.md", project / ".claude/commands/same.md")
        (project / ".claude/rules/core.md").mkdir()
        self.assertEqual((project / ".claude/commands/same.md").read_text(), "same\n")
        _out, files = self.files(project)
        for path in (".claude/commands/same.md", ".claude/rules/core.md"):
            self.assertEqual(files[path], entry(path, "modified", mode_matches=None))
        # Positive control: the same content as a regular file is up to date.
        (project / ".claude/commands/same.md").unlink()
        write(project, {".claude/commands/same.md": "same\n"})
        _out, files = self.files(project)
        self.assertEqual(files[".claude/commands/same.md"], entry(".claude/commands/same.md",
                                                                  "up_to_date"))

    def test_shared_lines(self):
        cases = {
            # template lines of work.md across d1, d2, d4: "# Work", "step one", "step two",
            # "step three", "step 2", "step four"
            "  # Work  \r\n\n\tstep two\nmine\n": 0.67,           # whitespace-stripped: 2 of 3
            "step four\nstep one\nx\ny\nz\nq\n": 0.33,            # 2 of 6
            "nothing\nin common\n": 0.0,
            "step one\nstep one\nstep one\nstep 9\n": 0.75,       # counts lines, not distinct lines
            "# Work\nstep two\nstep four\n": 1.0,                 # a mix of versions: all shared
            "\n   \n\t\n": None,                                  # no non-blank line
            "": None,
        }
        for content, expected in cases.items():
            with self.subTest(content=content):
                project = self.project(**{".claude/commands/work.md": content})
                _out, files = self.files(project)
                self.assertEqual(files[".claude/commands/work.md"],
                                 entry(".claude/commands/work.md", "modified",
                                       shared_lines=expected))

    def test_shared_lines_reads_the_blob_at_ref(self):
        """The template set includes REF's blob even when no `--raw` line carries it: at a
        root commit with log.showRoot the id is listed, so drop it from blob_ids to show
        the union with REF's blob is what supplies the lines."""
        project = self.project(**{".claude/commands/same.md": "same\nmine\n"})
        with self.isolated(), mock.patch.object(sc.Template, "blob_ids", return_value=set()):
            out = sc.check(str(project), str(F), "main")
        files = {f["path"]: f for f in out["files"]}
        self.assertEqual(files[".claude/commands/same.md"]["shared_lines"], 0.5)

    def test_version_helpers(self):
        with self.isolated():
            t = sc.Template(str(F), D["d4"])
            history = t.blob_history(".claude/commands/flip.md")
            self.assertEqual([c for c, _old, _new in history],
                             [D["d4"], D["d3"], D["d2"], D["d1"]])
            a = history[1][2]
            self.assertEqual(history[3][2], a)                       # set twice
            self.assertEqual(t.set_by(".claude/commands/flip.md", a), D["d3"])  # newest wins
            self.assertIsNone(t.set_by(".claude/commands/flip.md", "f" * 40))
            self.assertEqual(t.blob_ids(".claude/commands/flip.md"),
                             {new for _c, _old, new in history})
            self.assertEqual(sorted(t.read_blobs({a, history[0][2], "f" * 40})),
                             [b"flip A\n", b"flip C\n"])
            self.assertEqual(t.read_blobs(set()), [])

    def test_older_ref_classifies_against_its_own_history(self):
        """At d3, d4's content is not a template version yet."""
        project = self.project(**{".claude/commands/work.md": WORK_V4,
                                  ".claude/commands/flip.md": "flip B\n"})
        _out, files = self.files(project, ref=D["d3"])
        self.assertEqual(files[".claude/commands/work.md"]["status"], "modified")
        self.assertEqual(files[".claude/commands/flip.md"],
                         entry(".claude/commands/flip.md", "template_copy", basis="history"))
        _out, files = self.files(project)
        self.assertEqual(files[".claude/commands/work.md"]["status"], "up_to_date")


class SidecarTests(FilesCase):
    LOCAL = "a project edit\n"

    def shallow(self):
        """A depth-1 clone of F: history that can't place an older copy."""
        clone = self.new_dir() / "shallow"
        git(ROOT, "clone", "-q", "--depth", "1", F.as_uri(), str(clone))
        return clone

    def test_sidecar_is_the_fallback(self):
        """Read only when the template history is shallow. With the whole history a
        recorded hash never makes a file a template copy: content no template version
        holds is the project's own (a project's own file at a path the template later
        ships, recorded by an earlier sync, must not update under bare [A])."""
        project = self.project(**{
            ".claude/commands/same.md": self.LOCAL,      # no template version; recorded
            ".claude/scripts/plain.py": self.LOCAL,      # no template version; stale record
            ".claude/.sync-state.json": sidecar({
                ".claude/commands/same.md": sha(self.LOCAL),
                ".claude/scripts/plain.py": sha("something else\n"),
                ".claude/commands/flip.md": sha("flip A\n"),
                ".claude/commands/work.md": "not-a-hash"})})
        out, files = self.files(project, repo=self.shallow(), ref="HEAD")
        self.assertIs(out["history_complete"], False)
        self.assertEqual(files[".claude/commands/same.md"],
                         entry(".claude/commands/same.md", "template_copy", basis="sidecar"))
        self.assertEqual(files[".claude/scripts/plain.py"],
                         entry(".claude/scripts/plain.py", "modified", shared_lines=0.0))
        self.assertEqual(out["sidecar"], {"exists": True, "gitignored": None, "tracked": None})
        out, files = self.files(project)
        self.assertIs(out["history_complete"], True)
        self.assertEqual(out["warnings"], ["project is not a git work tree; uncommitted_sync skipped"])
        self.assertEqual(files[".claude/commands/same.md"],
                         entry(".claude/commands/same.md", "modified", shared_lines=0.0))
        self.assertEqual(files[".claude/commands/flip.md"]["basis"], "history")
        self.assertNotIn("sidecar", [f["basis"] for f in out["files"]])

    def test_missing_sidecar_is_silent_and_unreadable_warns(self):
        project = self.project(**{".claude/commands/same.md": self.LOCAL})
        shallow = self.shallow()
        out, files = self.files(project, repo=shallow, ref="HEAD")
        self.assertNotIn("sync-state sidecar unreadable; ignored", out["warnings"])
        self.assertEqual(out["sidecar"]["exists"], False)
        entries = {".claude/commands/same.md": {"synced_hash": sha(self.LOCAL)}}
        bad = ["{ nope\n", "[]\n", json.dumps({"files": [entries]}), json.dumps(entries), ""]
        for content in bad:
            with self.subTest(content=content):
                write(project, {".claude/.sync-state.json": content})
                out, files = self.files(project, repo=shallow, ref="HEAD")
                self.assertIn("sync-state sidecar unreadable; ignored", out["warnings"])
                self.assertEqual(files[".claude/commands/same.md"]["status"], "modified")
        # Positive control: the same entries in the right shape are read.
        write(project, {".claude/.sync-state.json": json.dumps({"files": entries})})
        out, files = self.files(project, repo=shallow, ref="HEAD")
        self.assertNotIn("sync-state sidecar unreadable; ignored", out["warnings"])
        self.assertEqual(files[".claude/commands/same.md"]["basis"], "sidecar")

    def test_shallow_template_history(self):
        """A depth-1 clone can't place older copies: they fall to the sidecar, or to
        `modified`. The full history places the same files (positive control)."""
        shallow = self.shallow()
        project = self.project(**{".claude/.sync-state.json": sidecar(
            {".claude/commands/flip.md": sha("flip A\n")})})
        out, files = self.files(project, repo=shallow, ref="HEAD")
        self.assertIs(out["history_complete"], False)
        self.assertEqual(out["warnings"], [
            "project is not a git work tree; uncommitted_sync skipped",
            "template history is shallow; files it cannot place are classified from the "
            "sync-state sidecar"])
        self.assertEqual(files[".claude/commands/flip.md"],
                         entry(".claude/commands/flip.md", "template_copy", basis="sidecar"))
        self.assertEqual(files[".claude/rules/core.md"],
                         entry(".claude/rules/core.md", "modified", shared_lines=0.0))
        self.assertEqual(files[".claude/commands/same.md"]["status"], "up_to_date")
        self.assertEqual(files[".claude/commands/added.md"]["status"], "new")
        out, files = self.files(project)
        self.assertIs(out["history_complete"], True)
        self.assertEqual(files[".claude/commands/flip.md"]["basis"], "history")
        self.assertEqual(files[".claude/rules/core.md"]["basis"], "history")

    def test_history_complete_is_about_the_ref(self):
        """The repository being shallow is not the test: REF's own history is. A full
        project repo that fetched the template at depth 1 has a cut template history; a
        shallow project clone that fetched the whole template does not."""
        full = Repo(self.new_dir() / "proj")
        full.commit("project", F_PROJECT)
        full.commit("more", {"src/app.py": "print('hi')\n"})
        git(full.path, "remote", "add", "template", F.as_uri())
        git(full.path, "fetch", "-q", "--depth", "1", "template")
        self.assertEqual(git(full.path, "rev-list", "--count", "HEAD"), "2")  # its own history is whole
        out, files = self.files(full.path, repo=full.path, ref="template/main")
        self.assertIs(out["history_complete"], False)
        self.assertIn("template history is shallow; files it cannot place are classified from "
                      "the sync-state sidecar", out["warnings"])
        self.assertEqual(files[".claude/rules/core.md"]["status"], "modified")
        # The advice Part 5 prints for this case completes it.
        git(full.path, "fetch", "-q", "--unshallow", "template")
        out, files = self.files(full.path, repo=full.path, ref="template/main")
        self.assertIs(out["history_complete"], True)
        self.assertEqual(files[".claude/rules/core.md"]["basis"], "history")

        clone = self.new_dir() / "clone"
        git(ROOT, "clone", "-q", "--depth", "1", full.path.as_uri(), str(clone))
        git(clone, "remote", "add", "template", F.as_uri())
        git(clone, "fetch", "-q", "template")
        self.assertEqual(git(clone, "rev-parse", "--is-shallow-repository"), "true")
        self.assertEqual(git(clone, "rev-list", "--count", "HEAD"), "1")
        out, files = self.files(clone, repo=clone, ref="template/main")
        self.assertIs(out["history_complete"], True)
        self.assertNotIn("template history is shallow; files it cannot place are classified from "
                         "the sync-state sidecar", out["warnings"])
        self.assertEqual(files[".claude/rules/core.md"]["basis"], "history")

    def test_gitignored_and_tracked(self):
        path = ".claude/.sync-state.json"
        cases = {  # name: (.gitignore content, add the sidecar to the index, expected)
            "ignored": (".claude/.sync-state.json\n", False, (True, True, False)),
            "ignored by a glob": (".claude/**\n", False, (True, True, False)),
            "untracked, no rule": ("", False, (True, False, False)),
            "tracked, no rule": ("", True, (True, False, True)),
            "tracked, with a rule": (".claude/.sync-state.json\n", True, (True, True, True)),
            "no sidecar, rule present": (".claude/.sync-state.json\n", None, (False, True, False)),
            "no sidecar, no rule": ("", None, (False, False, False)),
        }
        for name, (ignore, tracked, expected) in cases.items():
            with self.subTest(name):
                repo = Repo(self.new_dir() / "proj")
                files = {".gitignore": ignore, ".claude/commands/same.md": "same\n"}
                if tracked is not None:
                    files[path] = sidecar({})
                write(repo.path, files)
                git(repo.path, "add", "-f", "--", ".gitignore", ".claude/commands/same.md")
                if tracked:
                    git(repo.path, "add", "-f", "--", path)
                git(repo.path, "commit", "-q", "-m", "project", n=1)
                out, _files = self.files(repo.path)
                self.assertIs(out["git"], True)
                self.assertEqual(tuple(out["sidecar"][k] for k in ("exists", "gitignored", "tracked")),
                                 expected)

    def test_gitignored_in_a_project_below_its_repo_root(self):
        repo = Repo(self.new_dir() / "mono")
        repo.commit("app", {"app/.claude/commands/same.md": "same\n",
                            "app/.claude/.sync-state.json": sidecar({}),
                            ".gitignore": "lib/.claude/.sync-state.json\n"})
        out, _files = self.files(repo.path / "app")
        self.assertEqual(out["sidecar"], {"exists": True, "gitignored": False, "tracked": True})
        write(repo.path, {".gitignore": "app/.claude/.sync-state.json\n"})
        out, _files = self.files(repo.path / "app")
        self.assertEqual(out["sidecar"], {"exists": True, "gitignored": True, "tracked": True})


class ManifestListTests(FilesCase):
    def lists(self, local_manifest):
        project = self.project(**{".claude/sync-manifest.json": local_manifest})
        out, _files = self.files(project)
        self.assertEqual(list(out["manifest"]), ["customize", "ignore"])
        for cat in out["manifest"].values():
            self.assertEqual(list(cat), ["add", "drop", "list"])
        return out["manifest"]

    def test_add_drop_list(self):
        m = self.lists(manifest(
            F_SYNC,
            [".claude/mine-first.md", ".claude/README.md", ".claude/commands/*.md",
             ".claude/dashboard.html", ".claude/mine-first.md", ".claude/dashboard.md"],
            [".claude/version.json", ".claude/dashboard.md", ".claude/local/*",
             ".claude/to-customize.md", ".claude/README.md", ".claude/scripts/*.py",
             ".claude/secrets.md", ".claude/dashboard.md"]))
        self.assertEqual(m["customize"], {
            "add": [".claude/rules/project-*.md", ".claude/to-customize.md"],  # upstream order
            # in upstream `sync`; in upstream `ignore` (the other category)
            "drop": [".claude/commands/*.md", ".claude/dashboard.html"],
            # upstream (deduplicated), then the project's own in local order. dashboard.md was
            # only ever an ignore entry, so as a customize entry it is the project's own.
            "list": [".claude/README.md", ".claude/rules/project-*.md", ".claude/to-customize.md",
                     ".claude/mine-first.md", ".claude/dashboard.md"]})
        self.assertEqual(m["ignore"], {
            "add": [".claude/sync-manifest.json", ".claude/dashboard.html", ".claude/vision/*.md"],
            # once an upstream ignore entry (twice); upstream customize; upstream sync
            "drop": [".claude/dashboard.md", ".claude/to-customize.md", ".claude/README.md",
                     ".claude/scripts/*.py"],
            "list": F_IGNORE + [".claude/local/*", ".claude/secrets.md"]})

    def test_lists_in_step_with_upstream(self):
        m = self.lists(manifest(F_SYNC, F_CUSTOMIZE, F_IGNORE, flat=True))
        self.assertEqual(m["customize"], {"add": [], "drop": [], "list": F_CUSTOMIZE[:3]})
        self.assertEqual(m["ignore"], {"add": [], "drop": [], "list": F_IGNORE})

    def test_missing_or_unparseable_local_manifest(self):
        for content in (None, "{ nope\n"):
            with self.subTest(content=content):
                m = self.lists(content)
                self.assertEqual(m["customize"], {"add": F_CUSTOMIZE[:3], "drop": [],
                                                  "list": F_CUSTOMIZE[:3]})
                self.assertEqual(m["ignore"], {"add": F_IGNORE, "drop": [], "list": F_IGNORE})


# ---------------------------------------------------------------- exit 2

class ExitCodeTests(Case):
    def assert_exit_2(self, args, needle, cwd=None):
        r = run(*args, cwd=cwd)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(r.stdout, "")
        self.assertIn(needle, r.stderr)

    def test_exit_2_cases(self):
        plain = self.new_dir()
        write(plain, {".claude/version.json": version("1.0.0")})
        empty = self.new_dir()
        tpl = ["--project", str(plain), "--template-repo", str(T)]
        cases = {
            "project without .claude/": (["--project", str(empty), "--template-repo", str(T),
                                          "--ref", "main"], "no .claude/ directory"),
            "template repo not a git repository": (["--project", str(plain), "--template-repo",
                                                    str(empty), "--ref", "main"],
                                                   "not a git repository"),
            "default template repo = plain project": (["--project", str(plain), "--ref", "main"],
                                                      "not a git repository"),
            "unknown ref": (tpl + ["--ref", "no-such-ref"], "does not resolve to a commit"),
            "ref to a tree": (tpl + ["--ref", "main:.claude"], "does not resolve to a commit"),
            "no manifest at ref": (tpl + ["--ref", C["c0"]], "no parseable .claude/sync-manifest.json"),
            "unparseable manifest at ref": (tpl + ["--ref", C["cX"]],
                                            "no parseable .claude/sync-manifest.json"),
            "usage error": (tpl + ["--bogus"], "unrecognized arguments"),
        }
        for name, (args, needle) in cases.items():
            with self.subTest(name):
                self.assert_exit_2(args, needle)

    def test_python_below_floor(self):
        fake_old = ("import collections, runpy, sys; "
                    "sys.version_info = collections.namedtuple("
                    "'version_info', 'major minor micro releaselevel serial')(3, 9, 6, 'final', 0); "
                    "sys.argv = [sys.argv[1]]; runpy.run_path(sys.argv[0], run_name='__main__')")
        r = subprocess.run([sys.executable, "-c", fake_old, str(SCRIPT)], capture_output=True,
                           text=True, env=ENV, timeout=30)
        self.assertEqual(r.returncode, 2)
        self.assertIn("needs Python 3.10+", r.stderr)


# ---------------------------------------------------------------- units

class UnitTests(unittest.TestCase):
    def test_glob_semantics(self):
        cases = [
            (".claude/**", ".claude/a/b/c.md", True),
            (".claude/*.md", ".claude/a.md", True),
            (".claude/*.md", ".claude/a/b.md", False),
            (".claude/?.md", ".claude/a.md", True),
            (".claude/?.md", ".claude/ab.md", False),
            (".claude/a?b", ".claude/a/b", False),
            (".claude/[ab].md", ".claude/[ab].md", True),  # brackets are literal
            (".claude/[ab].md", ".claude/a.md", False),
            (".claude/a.md", ".claude/aXmd", False),        # dot is literal
            (".claude/**/x.md", ".claude/x.md", False),     # `/` after `**` is literal
            (".claude/**/x.md", ".claude/a/b/x.md", True),
            (".claude/commands/*.md", ".claude/commands/work.md", True),
            (".claude/commands/*.md", "x/.claude/commands/work.md", False),  # anchored
        ]
        for pattern, path, expected in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertIs(sc.matches(path, [pattern]), expected)

    def test_parse_manifest(self):
        self.assertEqual(sc.parse_manifest('{"categories": {"sync": ["a"], "ignore": "b"}}'),
                         {"sync": ["a"], "customize": [], "ignore": []})
        self.assertEqual(sc.parse_manifest('{"sync": ["a", 1], "customize": ["c"]}'),
                         {"sync": ["a"], "customize": ["c"], "ignore": []})
        self.assertEqual(sc.parse_manifest('{"categories": [], "sync": ["a"]}'),
                         {"sync": ["a"], "customize": [], "ignore": []})
        for bad in ("{ nope", "[]", '"text"', b"\xff\xfe\x00"):
            self.assertIsNone(sc.parse_manifest(bad))

    def test_project_files_prunes_and_skips_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, {".claude/a.md": "", ".claude/sub/b.md": "",
                      ".claude/node_modules/n.md": "", ".claude/sub/__pycache__/p.pyc": "",
                      ".claude/sub/.git/g": "", ".claude/worktrees/w/.claude/c.md": "",
                      ".claude/sub/worktrees/kept.md": "", "outside.md": ""})
            os.symlink("../outside.md", os.path.join(d, ".claude/link.md"))
            os.symlink("sub", os.path.join(d, ".claude/linkdir"))
            self.assertEqual(sc.project_files(d), [".claude/a.md", ".claude/sub/b.md",
                                                   ".claude/sub/worktrees/kept.md"])


if __name__ == "__main__":
    unittest.main()
