#!/usr/bin/env python3
"""Template-sync writer for /health-check Part 5 Step 4 (FB-136): brings the selected
compare-set files to the template's content at REF and does the sync bookkeeping.

Mirrors .claude/commands/health-check.md Part 5 Step 4 (and its prose fallback).
Any change to the rules here MUST be mirrored there, and vice versa
(README § "Dual-location risk").

Classification comes from sync-check.py, loaded from this script's own directory;
its check() decides every file's status and this script never re-derives one.
--project, --template-repo and --ref mean what they mean there.

Selection (the union; with neither flag only the bookkeeping runs):
  --status new,template_copy   every `files[]` entry with one of those statuses
  --paths-from FILE            one project-root-relative path per line (`-` = stdin);
                               each must be in `files[]`. The only way to select a
                               `modified` file.
A selected file that is already up to date is touched only to fix its mode.

Writes, all inside PROJECT/.claude/, in this order:
  1. files           the blob at REF, via a temp file in the target directory and
                     os.replace; mode 0755 or 0644 as at REF. Refused (`failed`) when
                     the local path is not a regular file or its parent directory
                     resolves outside PROJECT/.claude.
  2. version.json    template_version and template_release_date set to REF's values,
                     every other byte kept; only when a file's content was written, or
                     when every compare-set file now equals REF and the local
                     template_version differs (an interrupted run's bump).
  3. sync-manifest.json  `sync` = patterns.compare + the --keep-pattern retired
                     patterns; with --manifest-lists also `customize` and `ignore`.
  4. .sync-state.json    a synced_hash for every compare-set file that now equals
                     REF (not only the files written). Every other entry is dropped:
                     a path outside the compare set, or a compare-set file that
                     differs from REF (unless shallow history still classifies the
                     file by that entry). Unknown top-level keys are kept.
Each bookkeeping file is written only when its content changes, so a second run
changes nothing. --dry-run prints the same result and writes nothing.

Not done here (Part 5 prose): removing retired files, .gitignore edits,
`git rm --cached`, staging, committing, dashboard regeneration. Never fetches.

Output: one JSON object on stdout (indent=2); every key is always present.
  written        [{path, status, mode}]: files whose content was written; status is
                 the one sync-check.py gave the file before the run
  mode_fixed     up-to-date files whose mode was corrected
  failed         [{path, error}]: refused or failed writes
  version        {from, to, bumped}: local template_version before and after
  manifest       {changed, sync_added, sync_dropped, lists_updated}
  sidecar        {recorded, dropped, created, changed}
  changed_paths  every path the run changed, sorted
  remaining      [{path, status}]: files[] entries still not up to date

Exit codes: 0 success; 1 when `failed` is non-empty (everything else was still
applied); 2 usage/runtime error (every sync-check.py exit-2 condition, an unknown
--status value, an unreadable --paths-from, a path that is not in `files[]`,
PROJECT/template-maintenance/ being a directory (the template repository itself)
without --dry-run; nothing is written), Python below 3.10. One exit 2 comes after
file writes may have landed: an I/O error writing version.json, the manifest or the
sidecar. A re-run finishes that bookkeeping, the version bump included.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 10):  # Python floor (FB-120); see README § Invocation contract
    print(f"error: {Path(__file__).name} needs Python 3.10+; this is Python "
          f"{'.'.join(map(str, sys.version_info[:3]))} ({sys.executable})", file=sys.stderr)
    sys.exit(2)

STATUSES = ("new", "template_copy")  # what --status may select; `modified` needs a path
VERSION_KEYS = ("template_version", "template_release_date")
WARN_VERSION_LOCAL = "local version.json missing or unreadable; not updated"
WARN_VERSION_UPSTREAM = "template version.json has no template_version at the ref; version.json not updated"
WARN_MANIFEST = "local sync-manifest.json missing or unreadable; not written"
WARN_SIDECAR = "sync-state sidecar is not a regular file; not written"
TEMPLATE_SENTINEL = "template-maintenance"  # a directory only the template repository has


def load_sync_check():
    """sync-check.py from this script's directory, as a module (its name has a hyphen).
    Raises RuntimeError when it is absent or doesn't load."""
    path = Path(__file__).resolve().with_name("sync-check.py")
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # no __pycache__ beside the scripts
    try:
        spec = importlib.util.spec_from_file_location("sync_check", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (Exception, SystemExit) as e:  # absent, broken, or its version guard
        raise RuntimeError(f"cannot load {path.name} from {path.parent}: {e}") from e
    finally:
        sys.dont_write_bytecode = saved


def read_regular(path):
    """Bytes of a regular file; None when it is absent, unreadable or anything else
    (a symlink is never read through or written over)."""
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None
        return Path(path).read_bytes()
    except OSError:
        return None


def parse_object(raw):
    """A JSON object from file bytes; None when missing, unparseable or not an object."""
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def dump(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()


def write_atomic(path, content, mode=None):
    """Write bytes through a temp file in the same directory and os.replace it in.
    mode: permission bits to set; None keeps the existing file's (0644 for a new one)."""
    if mode is None:
        try:
            mode = stat.S_IMODE(os.lstat(path).st_mode)
        except OSError:
            mode = 0o644
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".sync-apply-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def refusal(project, path):
    """Why path must not be written, or None. Two guards keep every write inside
    PROJECT/.claude: the local path is a regular file or absent, and its parent
    directory, symlinks resolved, is PROJECT/.claude or below it."""
    target = os.path.join(project, path)
    if os.path.lexists(target) and not stat.S_ISREG(os.lstat(target).st_mode):
        return "local path is not a regular file"
    base = os.path.realpath(os.path.join(project, ".claude"))
    parent = os.path.realpath(os.path.dirname(target))
    if parent != base and not parent.startswith(base + os.sep):
        return "parent directory resolves outside the project's .claude/"
    return None


def read_paths(source):
    """Paths from --paths-from: one per line, surrounding whitespace and blank lines dropped."""
    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


def set_version_text(raw, values):
    """version.json bytes with the given top-level string values set, or None when raw
    is not a JSON object. A key that already holds a string is replaced in the text, so
    every other byte (key order, indentation, escapes) is kept; an absent key, or a
    replacement that doesn't parse to exactly the intended object, falls back to a
    parsed rewrite."""
    data = parse_object(raw)
    if data is None:
        return None
    wanted = dict(data, **values)
    if wanted == data:
        return raw
    try:
        text = raw.decode("utf-8")
        for key, value in values.items():
            pattern = re.compile(r'("%s"\s*:\s*)"(?:[^"\\]|\\.)*"' % re.escape(key))
            if not isinstance(data.get(key), str) or len(pattern.findall(text)) != 1:
                raise ValueError(key)
            # a function replacement: the value is never read as a regex template
            text = pattern.sub(lambda m, v=value: m.group(1) + json.dumps(v, ensure_ascii=False),
                               text)
        if json.loads(text) == wanted:
            return text.encode("utf-8")
    except ValueError:
        pass
    return dump(wanted)


def apply(sc, project, template_repo, ref, statuses=(), paths=(), keep_patterns=(),
          manifest_lists=False, dry_run=False):
    """Run the sync and return (result dict, exit code). Raises sc.CheckError for
    every exit-2 condition, before anything is written."""
    state = sc.check(project, template_repo, ref)
    project = os.path.abspath(project)
    if not dry_run and os.path.isdir(os.path.join(project, TEMPLATE_SENTINEL)):
        raise sc.CheckError(f"--project is the template repository itself (it has "
                            f"{TEMPLATE_SENTINEL}/): {project}; nothing written "
                            f"(--dry-run still reports)")
    repo = sc.template_root(template_repo)
    commit = state["ref_commit"]
    files = {f["path"]: f for f in state["files"]}
    unknown = [p for p in paths if p not in files]
    if unknown:
        raise sc.CheckError("not a compare-set file (not in sync-check.py's files[]): "
                            + ", ".join(unknown))
    warnings = list(state["warnings"])
    selected = set(paths) | {p for p, f in files.items() if f["status"] in statuses}

    def blob(path):
        return sc.git(repo, "cat-file", "blob", f"{commit}:{path}").stdout

    def local(path):
        return os.path.join(project, path)

    def write_file(path, entry, fix_mode_only):
        """Write one selected file (or fix its mode); returns (error or None, content)."""
        error = refusal(project, path)
        if error is not None:
            return error, None
        mode = 0o755 if entry["mode"] == "100755" else 0o644
        try:
            if fix_mode_only:
                if not dry_run:
                    os.chmod(local(path), mode)
                return None, None
            content = blob(path)
            if not dry_run:
                os.makedirs(os.path.dirname(local(path)), exist_ok=True)
                write_atomic(local(path), content, mode)
            return None, content
        except OSError as e:
            return f"{type(e).__name__}: {e.strerror or e}", None

    # 1. Files. `equal` = sha256 of every compare-set file that equals REF after the
    # run (already up to date, or written now), for the sidecar.
    written, mode_fixed, failed, equal = [], [], [], {}
    for path in sorted(files):
        entry = files[path]
        up_to_date = entry["status"] == "up_to_date"
        if path in selected and not (up_to_date and entry["mode_matches"]):
            error, content = write_file(path, entry, fix_mode_only=up_to_date)
            if error is not None:
                failed.append({"path": path, "error": error})
            elif up_to_date:
                mode_fixed.append(path)
            else:
                written.append({"path": path, "status": entry["status"], "mode": entry["mode"]})
                equal[path] = hashlib.sha256(content).hexdigest()
        if up_to_date:
            content = read_regular(local(path))
            if content is not None:
                equal[path] = hashlib.sha256(content).hexdigest()
    changed = [f["path"] for f in written] + mode_fixed

    # 2. version.json: only when a file's content was written, so a run that only
    # drops a pattern or fixes a mode doesn't claim a sync to a new version; or when
    # every compare-set file equals REF and the version differs, so the re-run after
    # an interrupted one (files written, bump lost) still bumps.
    version = {"from": state["local_version"], "to": state["local_version"], "bumped": False}
    if written or (files and len(equal) == len(files)
                   and state["local_version"] != state["upstream_version"]):
        upstream = parse_object(sc.git(repo, "cat-file", "blob", f"{commit}:{sc.VERSION_FILE}",
                                       check=False).stdout) or {}
        values = {k: upstream[k] for k in VERSION_KEYS if isinstance(upstream.get(k), str)}
        raw = read_regular(local(sc.VERSION_FILE))
        new = set_version_text(raw, values) if raw is not None else None
        if "template_version" not in values:
            warnings.append(WARN_VERSION_UPSTREAM)
        elif new is None:
            warnings.append(WARN_VERSION_LOCAL)
        elif new != raw:
            if not dry_run:
                write_atomic(local(sc.VERSION_FILE), new)
            version.update(to=values["template_version"], bumped=True)
            changed.append(sc.VERSION_FILE)

    # 3. sync-manifest.json
    retired = [r["pattern"] for r in state["patterns"]["retired"]]
    for pattern in sc.dedupe(keep_patterns):
        if pattern not in retired:
            warnings.append(f"--keep-pattern {pattern!r} is not a retired sync pattern; ignored")
    lists = {"sync": state["patterns"]["compare"] + [p for p in retired if p in keep_patterns]}
    if manifest_lists:
        lists.update({cat: state["manifest"][cat]["list"] for cat in ("customize", "ignore")})
    manifest = {"changed": False, "sync_added": [], "sync_dropped": [], "lists_updated": False}
    raw = read_regular(local(sc.MANIFEST))
    data = parse_object(raw)
    if data is None:
        warnings.append(WARN_MANIFEST)
    else:
        cats = data["categories"] if isinstance(data.get("categories"), dict) else data
        old_sync = sc.parse_manifest(raw)["sync"]
        differing = [k for k, v in lists.items() if cats.get(k) != v]
        if differing:
            manifest.update(changed=True,
                            sync_added=[p for p in lists["sync"] if p not in old_sync],
                            sync_dropped=[p for p in sc.dedupe(old_sync) if p not in lists["sync"]],
                            lists_updated=differing != ["sync"])
            cats.update(lists)
            if not dry_run:
                write_atomic(local(sc.MANIFEST), dump(data))
            changed.append(sc.MANIFEST)

    # 4. Sidecar: every compare-set file that equals REF gets its hash recorded, so the
    # fallback classification works for the whole set, not only for files this run wrote.
    # Nothing else stays, except the entry a shallow-history classification still rests
    # on (basis "sidecar", file not written in this run): an entry for a path outside the
    # compare set, or for a file that differs from REF, could later pass a project's own
    # file off as a template copy.
    sidecar = {"recorded": 0, "dropped": 0, "created": False, "changed": False}
    target = local(sc.SIDECAR)
    if os.path.lexists(target) and not stat.S_ISREG(os.lstat(target).st_mode):
        warnings.append(WARN_SIDECAR)
    else:
        raw = read_regular(target)
        old = parse_object(raw)
        sidecar["created"] = raw is None
        new = dict(old) if old is not None else {"schema_version": "1.0"}
        if version["bumped"]:
            new["last_full_sync_version"] = version["to"]
            new["last_full_sync_date"] = datetime.date.today().isoformat()
        entries = new.get("files") if isinstance(new.get("files"), dict) else {}
        kept = {p: e for p, e in entries.items()
                if p in equal or (p in files and files[p]["basis"] == "sidecar")}
        sidecar["dropped"] = len(entries) - len(kept)
        for path in sorted(equal):
            entry = dict(kept[path]) if isinstance(kept.get(path), dict) else {}
            entry["synced_hash"] = "sha256:" + equal[path]
            kept[path] = entry
        new["files"] = kept
        sidecar["recorded"] = len(equal)
        if new != old:
            sidecar["changed"] = True
            if not dry_run:
                write_atomic(target, dump(new))
            changed.append(sc.SIDECAR)

    result = {
        "ref": ref,
        "ref_commit": commit,
        "dry_run": dry_run,
        "written": written,
        "mode_fixed": mode_fixed,
        "failed": failed,
        "version": version,
        "manifest": manifest,
        "sidecar": sidecar,
        "changed_paths": sorted(changed),
        "remaining": [{"path": p, "status": files[p]["status"]} for p in sorted(files)
                      if files[p]["status"] != "up_to_date" and p not in equal],
        "warnings": warnings,
    }
    return result, 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Template-sync writer for /health-check Part 5 Step 4: writes the selected "
                    "template files at --ref into PROJECT/.claude/ and updates version.json, "
                    "sync-manifest.json and the sync-state sidecar; the result is JSON on "
                    "stdout. Classification comes from sync-check.py. Never fetches, stages "
                    "or commits.")
    parser.add_argument("--project", default=".", metavar="DIR",
                        help="project root, the directory that contains .claude/ (default: .)")
    parser.add_argument("--template-repo", metavar="DIR",
                        help="git repository whose history holds the template (default: the "
                             "--project value, with the `template` remote fetched)")
    parser.add_argument("--ref", default="template/main",
                        help="template commit-ish (default: template/main)")
    parser.add_argument("--status", default="", metavar="LIST",
                        help="comma-separated statuses to select: new, template_copy")
    parser.add_argument("--paths-from", metavar="FILE",
                        help="file of project-root-relative paths to select, one per line "
                             "(- = stdin); the only way to select a locally modified file")
    parser.add_argument("--keep-pattern", action="append", default=[], metavar="PATTERN",
                        help="a retired sync pattern to keep in the local sync list (repeatable)")
    parser.add_argument("--manifest-lists", action="store_true",
                        help="also update the local customize and ignore lists")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would change; write nothing")
    args = parser.parse_args(argv)
    statuses = [s.strip() for s in args.status.split(",")] if args.status else []
    bad = [s for s in statuses if s not in STATUSES]
    if bad:
        parser.error(f"--status takes a comma-separated subset of {', '.join(STATUSES)}; "
                     f"got {', '.join(repr(s) for s in bad)}")
    try:
        paths = read_paths(args.paths_from) if args.paths_from else []
    except (OSError, UnicodeDecodeError) as e:
        print(f"error: cannot read --paths-from {args.paths_from}: {e}", file=sys.stderr)
        return 2
    try:
        sc = load_sync_check()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        result, code = apply(sc, args.project, args.template_repo or args.project, args.ref,
                             statuses=statuses, paths=paths, keep_patterns=args.keep_pattern,
                             manifest_lists=args.manifest_lists, dry_run=args.dry_run)
    except sc.CheckError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except OSError as e:  # a bookkeeping write failed, after file writes may have landed;
        # a re-run finishes the bookkeeping (the version bump included)
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
