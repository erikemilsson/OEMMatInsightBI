#!/usr/bin/env python3
"""Tests for sync-check.py (FB-126), run against temporary git repos.

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
directories or git repos built per test. Git is isolated from the user's config
(GIT_CONFIG_GLOBAL=/dev/null, GIT_CONFIG_NOSYSTEM=1) with fixed identities and dates.
"""
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
