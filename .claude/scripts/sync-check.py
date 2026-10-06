#!/usr/bin/env python3
"""Template-sync check for /health-check Part 5 (FB-126): retired sync patterns,
retired template files, and synced files left uncommitted.

Mirrors .claude/commands/health-check.md Part 5 Step 2 (and its prose fallback).
Any change to the rules here MUST be mirrored there, and vice versa
(README § "Dual-location risk").

Template history is read from TEMPLATE_REPO at REF. In Part 5 that is the project
repo itself after `git fetch template` (`--ref template/{branch}`). To check a
project against a separate template clone: `--template-repo CLONE --ref HEAD`.

Output: one JSON object on stdout (indent=2); every key is always present.
  patterns.compare        upstream sync patterns, then project_added: the Step 2 set
  patterns.project_added  local sync patterns the template never listed (local order)
  patterns.retired        local sync patterns the template once listed (or now lists
                          as customize/ignore); removed_in = the version that dropped it
  retired_files           local files the template deleted: absent at REF, matching no
                          customize/ignore pattern (upstream or local), deleted in REF's
                          history, and either in the sync patterns when deleted (owned)
                          or byte-identical to a template version (unmodified)
  uncommitted_sync        `git status` changes under .claude/ that a sync made: files
                          present at REF that match `compare` (and no upstream
                          customize/ignore pattern) and equal any template version of
                          their path, not only REF's (an earlier sync, left uncommitted
                          while the template moved on); deletions of retired files;
                          plus version.json and sync-manifest.json when changed
Globs: `**` matches any characters including `/`, `*` any except `/`, `?` one
character except `/`; every other character is literal. An exact `sync` entry beats
customize/ignore globs (amendment A1): upstream `sync` for uncommitted_sync, the
manifest at the deleting commit's parent for retired_files. A wildcard never does.

Read-only: never writes files, never fetches. Git runs with GIT_OPTIONAL_LOCKS=0,
so `git status` doesn't refresh the index.

Exit codes: 0 success, findings or none; 2 usage/runtime error (no .claude/ under
--project, --template-repo not a git repository, --ref not a commit, no parseable
.claude/sync-manifest.json at REF, Python below 3.10).
"""
import argparse
import functools
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 10):  # Python floor (FB-120); see README § Invocation contract
    print(f"error: {Path(__file__).name} needs Python 3.10+; this is Python "
          f"{'.'.join(map(str, sys.version_info[:3]))} ({sys.executable})", file=sys.stderr)
    sys.exit(2)

MANIFEST = ".claude/sync-manifest.json"
VERSION_FILE = ".claude/version.json"
CATEGORIES = ("sync", "customize", "ignore")
PRUNE_NAMES = {".git", "node_modules", "__pycache__"}  # pruned at any depth
PRUNE_PATHS = {".claude/worktrees"}  # project-root-relative
WARN_LOCAL_MANIFEST = "local sync-manifest.json missing or unreadable; local patterns treated as empty"
WARN_NOT_GIT = "project is not a git work tree; uncommitted_sync skipped"
# `git log` with the user config that would change its output pinned to the defaults
# the parsers below expect.
LOG = ("-c", "log.follow=false", "-c", "log.showSignature=false", "-c", "log.showRoot=true",
       "log", "--no-color")
OID = re.compile(rb"[0-9a-f]{40}|[0-9a-f]{64}")


class CheckError(Exception):
    """An exit-2 condition; main() prints the message to stderr."""


def git(cwd, *args, check=True):
    """Run git in cwd and return the CompletedProcess (stdout and stderr as bytes).

    GIT_OPTIONAL_LOCKS=0: `git status` doesn't refresh (write) the index.
    GIT_LITERAL_PATHSPECS=1: paths after `--` are literal paths, never globs.
    """
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_LITERAL_PATHSPECS="1")
    try:
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, env=env)
    except OSError as e:
        raise CheckError(f"cannot run git: {e}") from e
    if check and r.returncode != 0:
        detail = r.stderr.decode(errors="replace").strip()
        raise CheckError(f"git {' '.join(args)} failed in {cwd}: {detail}")
    return r


@functools.lru_cache(maxsize=None)
def glob_regex(pattern):
    """Compile a manifest glob: `**` = any characters including `/`, `*` = any
    characters except `/`, `?` = one character except `/`; all else is literal."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        c = pattern[i]
        out.append("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c))
        i += 1
    return re.compile("".join(out), re.DOTALL)


def matches(path, patterns):
    """True when the project-root-relative POSIX path matches any of the globs."""
    return any(glob_regex(p).fullmatch(path) for p in patterns)


def dedupe(items):
    return list(dict.fromkeys(items))


def parse_manifest(raw):
    """{sync, customize, ignore} lists from sync-manifest.json content; None if unparseable.

    Reads the `categories` object if present, else the top-level object. A missing or
    non-list key is an empty list; non-string entries are dropped.
    """
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    cats = data.get("categories")
    if not isinstance(cats, dict):
        cats = data
    return {k: [p for p in cats[k] if isinstance(p, str)] if isinstance(cats.get(k), list) else []
            for k in CATEGORIES}


def parse_version(raw):
    """`template_version` from version.json content; None when missing or unreadable."""
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    value = data.get("template_version") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def read_local(path):
    try:
        return Path(path).read_bytes()
    except OSError:
        return None


class Template:
    """Read-only views of the template repository's history at one commit (cached)."""

    def __init__(self, repo, commit):
        self.repo, self.commit = repo, commit
        self._blobs, self._blob_ids = {}, {}

    def read(self, rev, path):
        """Content of path at rev (bytes), or None when absent."""
        key = (rev, path)
        if key not in self._blobs:
            r = git(self.repo, "cat-file", "blob", f"{rev}:{path}", check=False)
            self._blobs[key] = r.stdout if r.returncode == 0 else None
        return self._blobs[key]

    def manifest(self, rev):
        raw = self.read(rev, MANIFEST)
        return None if raw is None else parse_manifest(raw)

    def version(self, rev):
        return parse_version(self.read(rev, VERSION_FILE))

    def tree(self):
        """{path: (object type, blob id)} for every entry in the tree at the commit."""
        out = {}
        raw = git(self.repo, "ls-tree", "-r", "-z", "--full-tree", self.commit).stdout
        for rec in raw.split(b"\0"):
            if rec:
                meta, _, path = rec.partition(b"\t")
                _mode, kind, oid = meta.split()
                out[os.fsdecode(path)] = (kind.decode(), oid.decode())
        return out

    def manifest_history(self):
        """[(commit, categories or None)] for `git log REF -- .claude/sync-manifest.json`,
        newest first; None marks an unparseable (or deleted) manifest version."""
        raw = git(self.repo, *LOG, "--format=%H", self.commit, "--", MANIFEST).stdout
        return [(c, self.manifest(c)) for c in raw.decode().split()]

    def deleted(self):
        """{path: newest commit that deleted it} from
        `git log REF --no-renames --diff-filter=D --name-only -- .claude/`."""
        raw = git(self.repo, *LOG, "--no-renames", "--diff-filter=D", "--name-only", "-z",
                  "--format=%H", self.commit, "--", ".claude/").stdout
        out, commit = {}, None
        # -z output: "<sha>\0\n<path>\0<path>\0<sha>\0\n<path>\0..."; every path
        # starts with ".claude/", so a bare object id is always a commit line.
        for tok in raw.split(b"\0"):
            tok = tok.lstrip(b"\n")
            if OID.fullmatch(tok):
                commit = tok.decode()
            elif tok and commit:
                out.setdefault(os.fsdecode(tok), commit)
        return out

    def blob_ids(self, path):
        """Every blob id path had in the template's history: old and new ids of
        `git log REF --no-renames --raw --no-abbrev --format= -- path`, zeros excluded."""
        if path not in self._blob_ids:
            raw = git(self.repo, *LOG, "--no-renames", "--raw", "--no-abbrev", "--format=",
                      self.commit, "--", path).stdout
            ids = set()
            for line in raw.split(b"\n"):
                if line.startswith(b":"):  # ":<mode> <mode> <old id> <new id> <status>\t<path>"
                    for oid in line.split(b"\t", 1)[0].split()[2:4]:
                        if oid.strip(b"0"):
                            ids.add(oid.decode())
            self._blob_ids[path] = ids
        return self._blob_ids[path]

    def hash_files(self, paths):
        """{absolute path: blob id} via `git hash-object --no-filters` in the template repo,
        so ids use its hash algorithm. A file git can't hash is left out."""
        if not paths:
            return {}
        r = git(self.repo, "hash-object", "--no-filters", "--", *paths, check=False)
        ids = r.stdout.decode().split()
        if r.returncode == 0 and len(ids) == len(paths):
            return dict(zip(paths, ids))
        out = {}
        for p in paths:  # the batch failed on some file: hash one at a time
            r = git(self.repo, "hash-object", "--no-filters", "--", p, check=False)
            if r.returncode == 0:
                out[p] = r.stdout.decode().strip()
        return out


def template_root(path):
    """Where to run template-history commands: the work-tree top level (so `.claude/`
    pathspecs are root-relative), or the repository itself when it is bare."""
    r = git(path, "rev-parse", "--git-dir", check=False)
    if r.returncode != 0:
        detail = r.stderr.decode(errors="replace").strip()
        raise CheckError(f"--template-repo is not a git repository: {path} ({detail})")
    top = git(path, "rev-parse", "--show-toplevel", check=False)  # fails in a bare repo
    top_dir = os.fsdecode(top.stdout.rstrip(b"\n"))
    return top_dir if top.returncode == 0 and top_dir else path


def project_files(project):
    """Regular files (not symlinks) under PROJECT/.claude/ as project-root-relative POSIX
    paths, pruning .git, node_modules, __pycache__ and .claude/worktrees."""
    out = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(project, ".claude")):
        rel_dir = os.path.relpath(dirpath, project).replace(os.sep, "/")
        dirnames[:] = sorted(d for d in dirnames
                             if d not in PRUNE_NAMES and f"{rel_dir}/{d}" not in PRUNE_PATHS)
        for name in filenames:
            try:
                regular = stat.S_ISREG(os.lstat(os.path.join(dirpath, name)).st_mode)
            except OSError:
                continue
            if regular:
                out.append(f"{rel_dir}/{name}")
    return sorted(out)


def git_status(project):
    """[(project-relative path, change, repo-relative path)] for
    `git status --porcelain=v1 -z --untracked-files=all -- .claude`; renames and copies
    are skipped."""
    prefix = os.fsdecode(git(project, "rev-parse", "--show-prefix").stdout.rstrip(b"\n"))
    raw = git(project, "status", "--porcelain=v1", "-z", "--untracked-files=all",
              "--", ".claude").stdout
    tokens = raw.split(b"\0")
    out, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if len(tok) < 4:
            continue
        xy, repo_path = tok[:2].decode(errors="replace"), os.fsdecode(tok[3:])
        if xy[0] in "RC" or xy[1] in "RC":
            i += 1  # a rename/copy is followed by its source path
            continue
        if not repo_path.startswith(prefix):
            continue
        if "D" in xy:
            change = "deleted"
        elif xy == "??" or xy[0] == "A":
            change = "added"
        else:
            change = "modified"
        out.append((repo_path[len(prefix):], change, repo_path))
    return out


def check(project, template_repo, ref):
    """The sync-check result dict; raises CheckError for every exit-2 condition."""
    if not os.path.isdir(os.path.join(project, ".claude")):
        raise CheckError(f"--project has no .claude/ directory: {project}")
    project = os.path.abspath(project)
    repo = template_root(template_repo)
    r = git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    ref_commit = r.stdout.decode().strip()
    if r.returncode != 0 or not ref_commit:
        raise CheckError(f"--ref {ref!r} does not resolve to a commit in {repo}")
    tpl = Template(repo, ref_commit)
    upstream = tpl.manifest(ref_commit)
    if upstream is None:
        raise CheckError(f"no parseable {MANIFEST} at {ref} ({ref_commit[:12]}) in {repo}")

    warnings = []
    local_raw = read_local(os.path.join(project, MANIFEST))
    local = None if local_raw is None else parse_manifest(local_raw)
    if local is None:
        warnings.append(WARN_LOCAL_MANIFEST)
        local = {k: [] for k in CATEGORIES}

    # patterns: retired = the template once listed it (H) or now lists it as
    # customize/ignore; anything else the template doesn't list is the project's own.
    history = tpl.manifest_history()
    in_history = {p for _c, cats in history if cats for p in cats["sync"]}
    upstream_sync = dedupe(upstream["sync"])
    upstream_excluded = upstream["customize"] + upstream["ignore"]
    retired, project_added = [], []
    for p in dedupe(local["sync"]):
        if p in upstream_sync:
            continue
        if p in in_history or p in upstream_excluded:
            retired.append({"pattern": p, "removed_in": pattern_removed_in(tpl, history, p)})
        else:
            project_added.append(p)
    retired.sort(key=lambda e: e["pattern"])
    compare = upstream_sync + project_added

    # retired_files: rules 1-6 of the contract.
    ref_tree = tpl.tree()
    deleted = tpl.deleted()
    excluded = upstream_excluded + local["customize"] + local["ignore"]
    sync_before = {}  # removed_commit -> `sync` list at removed_commit^ ([] if unparseable)

    def sync_at_deletion(path):
        commit = deleted[path]
        if commit not in sync_before:
            cats = tpl.manifest(f"{commit}^")
            sync_before[commit] = cats["sync"] if cats else []
        return sync_before[commit]

    def owned(path):  # rule 4
        return matches(path, sync_at_deletion(path))

    def retired_path(path):
        # Rules 1-3: absent at REF, deleted in history, not customize/ignore. An exact
        # `sync` entry at deletion beats customize/ignore globs (amendment A1); a
        # wildcard `sync` pattern never does.
        return (path not in ref_tree and path in deleted
                and (not matches(path, excluded) or path in sync_at_deletion(path)))

    candidates = [p for p in project_files(project) if retired_path(p)]
    local_ids = tpl.hash_files([os.path.join(project, p) for p in candidates])
    retired_files = []
    for path in candidates:
        is_owned = owned(path)
        unmodified = local_ids.get(os.path.join(project, path)) in tpl.blob_ids(path)
        if is_owned or unmodified:
            commit = deleted[path]
            retired_files.append({"path": path, "state": "unmodified" if unmodified else "modified",
                                  "owned": is_owned, "removed_in": tpl.version(commit),
                                  "removed_commit": commit})

    # uncommitted_sync
    is_git = project_is_git(project)
    uncommitted = []
    if not is_git:
        warnings.append(WARN_NOT_GIT)
    else:
        status = git_status(project)
        listed = {}
        sync_changes = []
        for path, change, repo_path in status:
            if change == "deleted":
                if retired_path(path) and (owned(path) or committed_blob(project, repo_path)
                                           in tpl.blob_ids(path)):
                    listed[path] = change
            elif (matches(path, compare)
                  # an exact upstream `sync` entry beats customize/ignore globs (A1)
                  and (path in upstream_sync or not matches(path, upstream_excluded))
                  and ref_tree.get(path, ("", ""))[0] == "blob"
                  and is_regular(os.path.join(project, path))):
                sync_changes.append(path)
        abs_ids = tpl.hash_files([os.path.join(project, p) for p in sync_changes])
        changes = {path: change for path, change, _r in status}
        for path in sync_changes:
            # Any template version of the path, not only REF's: after the template moves
            # on, an earlier uncommitted sync matches an older version. REF's blob is
            # checked first; a merge that produced it has no `--raw` diff.
            local_id = abs_ids.get(os.path.join(project, path))
            if local_id is not None and (local_id == ref_tree[path][1]
                                         or local_id in tpl.blob_ids(path)):
                listed[path] = changes[path]
        if listed:
            for path in (VERSION_FILE, MANIFEST):
                if path in changes:
                    listed.setdefault(path, "modified")
        uncommitted = [{"path": p, "change": listed[p]} for p in sorted(listed)]

    return {
        "ref": ref,
        "ref_commit": ref_commit,
        "upstream_version": tpl.version(ref_commit),
        "local_version": parse_version(read_local(os.path.join(project, VERSION_FILE))),
        "git": is_git,
        "patterns": {"compare": compare, "project_added": project_added, "retired": retired},
        "retired_files": sorted(retired_files, key=lambda e: e["path"]),
        "uncommitted_sync": uncommitted,
        "warnings": warnings,
    }


def pattern_removed_in(tpl, history, pattern):
    """Version that dropped pattern from `sync`: walking manifest commits newest → oldest,
    the newest one listing it was superseded by the next newer one, which dropped it.
    None when the template never listed it or that version is unavailable."""
    for i, (_commit, cats) in enumerate(history):
        if cats is not None and pattern in cats["sync"]:
            return tpl.version(history[i - 1][0]) if i > 0 else None
    return None


def project_is_git(project):
    r = git(project, "rev-parse", "--is-inside-work-tree", check=False)
    return r.returncode == 0 and r.stdout.strip() == b"true"


def committed_blob(project, repo_path):
    """Blob id of repo_path at the project's HEAD, or None."""
    r = git(project, "rev-parse", "--verify", "--quiet", f"HEAD:{repo_path}", check=False)
    if r.returncode != 0:
        return None
    return r.stdout.decode().strip() or None


def is_regular(path):
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Template-sync check for /health-check Part 5: retired sync patterns, "
                    "retired template files and synced files left uncommitted, as JSON on "
                    "stdout. Read-only; never fetches.")
    parser.add_argument("--project", default=".", metavar="DIR",
                        help="project root, the directory that contains .claude/ (default: .)")
    parser.add_argument("--template-repo", metavar="DIR",
                        help="git repository whose history holds the template (default: the "
                             "--project value, with the `template` remote fetched)")
    parser.add_argument("--ref", default="template/main",
                        help="template commit-ish (default: template/main; Part 5 passes "
                             "template/{branch}; with --template-repo, a ref of that repo, "
                             "e.g. HEAD)")
    args = parser.parse_args(argv)
    try:
        result = check(args.project, args.template_repo or args.project, args.ref)
    except CheckError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
