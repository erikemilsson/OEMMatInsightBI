#!/usr/bin/env python3
"""Template-sync check for /health-check Part 5 (FB-126, FB-136): per-file
classification against the template's blob history, retired sync patterns, retired
template files, stale local manifest lists, and synced files left uncommitted.

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
  history_complete        false when REF's history in TEMPLATE_REPO is cut short: a commit
                          listed in the repository's `shallow` file is reachable from REF
                          (history may not place an older copy; only then is the sidecar
                          read as the fallback)
  files                   one entry per compare-set file: a regular-file blob at REF that
                          matches `compare` and that upstream `sync` names exactly or no
                          upstream customize/ignore pattern matches. Sorted by path.
    status                up_to_date    = the path's blob at REF
                          template_copy = an older template version of the path
                                          (basis "history"), or, only when history_complete
                                          is false, the content the sync-state sidecar
                                          recorded (basis "sidecar"): no local edits
                          modified      = matches no template version, or the local path
                                          is not a regular file
                          new           = absent locally
    mode, mode_matches    "100644"/"100755" at REF; whether the local owner-execute bit
                          agrees (null for new and non-regular paths)
    version, basis        template_copy only: the template_version that introduced that
                          content (history; null when unavailable), and "history"/"sidecar"
    shared_lines          modified regular files only: share (0..1, 2 decimals) of the
                          local non-blank lines, whitespace-stripped, found in any
                          template version of the path; null when it has no such line
  manifest.<cat>          for customize and ignore: `add` = upstream entries the local
                          list lacks; `drop` = local entries the template once listed
                          there (or now lists in another category); `list` = upstream
                          entries followed by the project's own
  sidecar                 .claude/.sync-state.json: exists; gitignored and tracked in the
                          project repo (null when the project is not a git work tree)
Globs: `**` matches any characters including `/`, `*` any except `/`, `?` one
character except `/`; every other character is literal. An exact `sync` entry beats
customize/ignore globs (amendment A1): upstream `sync` for uncommitted_sync, the
manifest at the deleting commit's parent for retired_files. A wildcard never does.

Read-only: never writes files, never fetches. Git runs with GIT_OPTIONAL_LOCKS=0,
so `git status` doesn't refresh the index. sync-apply.py is the writer; it imports
check() from this file.

Exit codes: 0 success, findings or none; 2 usage/runtime error (no .claude/ under
--project, --template-repo not a git repository, --ref not a commit, no parseable
.claude/sync-manifest.json at REF, Python below 3.10).
"""
import argparse
import functools
import hashlib
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
WARN_SHALLOW = ("template history is shallow; files it cannot place are classified from the "
                "sync-state sidecar")
WARN_SIDECAR = "sync-state sidecar unreadable; ignored"
SIDECAR = ".claude/.sync-state.json"
# `git log` with the user config that would change its output pinned to the defaults
# the parsers below expect.
LOG = ("-c", "log.follow=false", "-c", "log.showSignature=false", "-c", "log.showRoot=true",
       "log", "--no-color")
OID = re.compile(rb"[0-9a-f]{40}|[0-9a-f]{64}")


class CheckError(Exception):
    """An exit-2 condition; main() prints the message to stderr."""


def git(cwd, *args, check=True, stdin=None, literal=True):
    """Run git in cwd and return the CompletedProcess (stdout and stderr as bytes).
    stdin: bytes for the command's standard input.

    GIT_OPTIONAL_LOCKS=0: `git status` doesn't refresh (write) the index.
    GIT_LITERAL_PATHSPECS=1: paths after `--` are literal paths, never globs.
    literal=False leaves that out, for commands that reject it (`check-ignore`).
    """
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    if literal:
        env["GIT_LITERAL_PATHSPECS"] = "1"
    try:
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, env=env,
                           input=stdin)
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
        self._blobs, self._blob_history = {}, {}

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
        """{path: (object type, blob id, mode)} for every entry in the tree at the commit."""
        out = {}
        raw = git(self.repo, "ls-tree", "-r", "-z", "--full-tree", self.commit).stdout
        for rec in raw.split(b"\0"):
            if rec:
                meta, _, path = rec.partition(b"\t")
                mode, kind, oid = meta.split()
                out[os.fsdecode(path)] = (kind.decode(), oid.decode(), mode.decode())
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

    def blob_history(self, path):
        """[(commit, old id, new id)], newest first, for every change to path in
        `git log REF --no-renames --raw --no-abbrev --format=%H -- path`."""
        if path not in self._blob_history:
            raw = git(self.repo, *LOG, "--no-renames", "--raw", "--no-abbrev", "--format=%H",
                      self.commit, "--", path).stdout
            out, commit = [], None
            for line in raw.split(b"\n"):
                if line.startswith(b":"):  # ":<mode> <mode> <old id> <new id> <status>\t<path>"
                    old, new = line.split(b"\t", 1)[0].split()[2:4]
                    out.append((commit, old.decode(), new.decode()))
                elif OID.fullmatch(line):
                    commit = line.decode()
            self._blob_history[path] = out
        return self._blob_history[path]

    def blob_ids(self, path):
        """Every blob id path had in the template's history: old and new ids of
        blob_history(path), zeros excluded."""
        return {oid for _c, old, new in self.blob_history(path) for oid in (old, new)
                if oid.strip("0")}

    def set_by(self, path, blob_id):
        """The newest commit that set path to blob_id (the new id of a `--raw` line);
        None when the id only ever appears as an old id."""
        return next((c for c, _old, new in self.blob_history(path) if new == blob_id), None)

    def read_blobs(self, ids):
        """Contents of the given blob ids (one `git cat-file --batch`); ids git can't
        read are left out."""
        ids = sorted(ids)
        if not ids:
            return []
        raw = git(self.repo, "cat-file", "--batch", stdin="\n".join(ids).encode() + b"\n").stdout
        out, pos = [], 0
        while pos < len(raw):  # "<id> blob <size>\n<content>\n" or "<id> missing\n"
            end = raw.index(b"\n", pos)
            header = raw[pos:end].split()
            pos = end + 1
            if len(header) == 3 and header[2].isdigit():
                size = int(header[2])
                if header[1] == b"blob":
                    out.append(raw[pos:pos + size])
                pos += size + 1
        return out

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

    history_complete = ref_history_complete(repo, ref_commit)
    files, sidecar_warning = classify_files(tpl, project, ref_tree, compare, upstream_sync,
                                            upstream_excluded, history_complete)
    if not history_complete:
        warnings.append(WARN_SHALLOW)
    if sidecar_warning:
        warnings.append(WARN_SIDECAR)

    return {
        "ref": ref,
        "ref_commit": ref_commit,
        "upstream_version": tpl.version(ref_commit),
        "local_version": parse_version(read_local(os.path.join(project, VERSION_FILE))),
        "git": is_git,
        "patterns": {"compare": compare, "project_added": project_added, "retired": retired},
        "retired_files": sorted(retired_files, key=lambda e: e["path"]),
        "uncommitted_sync": uncommitted,
        "history_complete": history_complete,
        "files": files,
        "manifest": {cat: manifest_lists(cat, upstream, local, history)
                     for cat in ("customize", "ignore")},
        "sidecar": sidecar_state(project, is_git),
        "warnings": warnings,
    }


def ref_history_complete(repo, commit):
    """True when no commit listed in the repository's `shallow` file is reachable from
    the commit: its history is whole, whatever other histories in the repository (a
    shallow project clone) are cut short. An absent or empty file means no cut."""
    shallow = os.fsdecode(git(repo, "rev-parse", "--git-path", "shallow").stdout.rstrip(b"\n"))
    cut = set((read_local(os.path.join(repo, shallow)) or b"").split())
    if not cut:
        return True
    return cut.isdisjoint(git(repo, "rev-list", commit).stdout.split())


def classify_files(tpl, project, ref_tree, compare, upstream_sync, upstream_excluded,
                   history_complete):
    """(`files` entries, sidecar-unreadable flag). The test for "did the project edit
    this file" is the template's own history: content equal to any template version of
    the path is an unchanged copy. The sidecar is consulted only when that history is
    incomplete (history_complete false) and can't place the content: with the whole
    history, content it doesn't hold is the project's own, whatever a sidecar says."""
    paths = sorted(p for p, (kind, _oid, mode) in ref_tree.items()
                   if kind == "blob" and mode.startswith("100")  # regular files, not symlinks
                   and matches(p, compare)
                   # an exact upstream `sync` entry beats customize/ignore globs (A1)
                   and (p in upstream_sync or not matches(p, upstream_excluded)))
    local_modes = {}  # path -> st_mode; absent paths are left out
    for path in paths:
        try:
            local_modes[path] = os.lstat(os.path.join(project, path)).st_mode
        except OSError:
            pass
    regular = [p for p in paths if p in local_modes and stat.S_ISREG(local_modes[p])]
    local_ids = tpl.hash_files([os.path.join(project, p) for p in regular])
    recorded, sidecar_warning = read_sidecar(project)

    files = []
    for path in paths:
        _kind, ref_id, ref_mode = ref_tree[path]
        mode = "100755" if ref_mode == "100755" else "100644"
        entry = {"path": path, "status": "modified", "mode": mode, "mode_matches": None,
                 "version": None, "basis": None, "shared_lines": None}
        files.append(entry)
        if path not in local_modes:
            entry["status"] = "new"
            continue
        if not stat.S_ISREG(local_modes[path]):  # symlink, directory: never read through
            continue
        entry["mode_matches"] = (local_modes[path] & 0o100 != 0) == (mode == "100755")
        local_id = local_ids.get(os.path.join(project, path))
        if local_id is not None and local_id == ref_id:
            entry["status"] = "up_to_date"
        elif local_id is not None and local_id in tpl.blob_ids(path):
            commit = tpl.set_by(path, local_id)
            entry.update(status="template_copy", basis="history",
                         version=tpl.version(commit) if commit else None)
        else:
            content = read_local(os.path.join(project, path))
            if (not history_complete and content is not None and path in recorded
                    and recorded[path] == "sha256:" + hashlib.sha256(content).hexdigest()):
                entry.update(status="template_copy", basis="sidecar")
            elif content is not None:
                entry["shared_lines"] = shared_lines(
                    content, tpl.read_blobs(tpl.blob_ids(path) | {ref_id}))
    return files, sidecar_warning


def content_lines(content):
    """Non-blank lines of a file's bytes, each stripped of surrounding whitespace."""
    return [line for line in (raw.strip() for raw in content.split(b"\n")) if line]


def shared_lines(content, template_blobs):
    """Share of the local non-blank lines found in any template version of the path
    (2 decimals); None when the local file has no non-blank line. A low value means the
    file is not a variant of the template file (a project's own file at that path)."""
    local = content_lines(content)
    if not local:
        return None
    known = {line for blob in template_blobs for line in content_lines(blob)}
    return round(sum(line in known for line in local) / len(local), 2)


def read_sidecar(project):
    """({path: synced_hash}, unreadable flag) from the sync-state sidecar. Missing: no
    entries. Present but unparseable or not an object with a `files` object: no
    entries and the flag set."""
    path = os.path.join(project, SIDECAR)
    if not os.path.lexists(path):
        return {}, False
    raw = read_local(path)
    try:
        data = json.loads(raw) if raw is not None else None
    except (ValueError, RecursionError):
        data = None
    entries = data.get("files") if isinstance(data, dict) else None
    if not isinstance(entries, dict):
        return {}, True
    return {p: e["synced_hash"] for p, e in entries.items()
            if isinstance(e, dict) and isinstance(e.get("synced_hash"), str)}, False


def sidecar_state(project, is_git):
    """The `sidecar` object. The file is per-clone state and must be gitignored, so
    Part 5 offers to ignore it, and to untrack it when it was committed."""
    out = {"exists": is_regular(os.path.join(project, SIDECAR)), "gitignored": None,
           "tracked": None}
    if is_git:
        # --no-index: a tracked file still reports the ignore rule that covers it.
        out["gitignored"] = git(project, "check-ignore", "-q", "--no-index", "--", SIDECAR,
                                check=False, literal=False).returncode == 0
        out["tracked"] = git(project, "ls-files", "--error-unmatch", "--", SIDECAR,
                             check=False).returncode == 0
    return out


def manifest_lists(cat, upstream, local, history):
    """{add, drop, list} for one of the local customize/ignore lists. A local entry is
    stale (drop) when the template once listed it in this category, or now lists it as
    `sync` or in the other category; any other local entry is the project's own (kept)."""
    other = "ignore" if cat == "customize" else "customize"
    up = dedupe(upstream[cat])
    in_history = {p for _c, cats in history if cats for p in cats[cat]}
    moved = set(upstream["sync"]) | set(upstream[other])
    mine = dedupe(local[cat])
    drop = [p for p in mine if p not in up and (p in in_history or p in moved)]
    return {"add": [p for p in up if p not in mine], "drop": drop,
            "list": up + [p for p in mine if p not in up and p not in drop]}


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
        description="Template-sync check for /health-check Part 5: per-file classification "
                    "against the template's history, retired sync patterns, retired template "
                    "files, stale manifest lists and synced files left uncommitted, as JSON "
                    "on stdout. Read-only; never fetches.")
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
