#!/usr/bin/env python3
"""dashboard-render.py — deterministic renderer for the project dashboard.

DEC-024 (HTML render target): the dashboard is a single read-only, offline,
file://-openable HTML page. Every visualization is inline SVG generated here
in Python — zero runtime/CDN deps (the file:// crux: fetch() and ES-module CDN
imports both fail from a double-clicked file). The Markdown render target was
hard-retired in this change; HTML is the only surface.

Division of labor (per support/reference/dashboard-regeneration.md
§ Script-First Rendering): the script renders every structural/data section
deterministically, including every mechanical Action Required ("Needs you")
row (FB-105); the LLM fills only the Custom Views placeholder, via the
`<!-- CLAUDE: fill ... -->` HTML comment this script emits, with HTML. The
sidecar (dashboard-state.json) owns user content: section_toggles control which
sections render; user_notes seeds the read-only Notes card; augment_rows[]
carries the Needs-you card's judgment rows, rendered as its final "Also Needs
You" sub-section (FB-118). Nobody hand-edits the HTML — there are no in-file
editable markers (DEC-024), and a full regen would wipe any hand edit.

Modes:
  --html                   render the FULL dashboard as HTML to stdout
  --task-hash              print the canonical META task_hash and exit

Canonical task_hash (this script is the single authority — fixes the
three-way divergence observed in styler 2026-06-11):
  sha256 over "\\n".join(sorted("{id}:{status}:{difficulty}:{owner}:{review}"
  for each ACTIVE task)) + "\\n"   — review = 1 when user_review_pending is
  truthy, else 0 (FB-118: toggling a review flag must read as stale); string
  sort, archive excluded, rendered with a "sha256:" prefix. Carried in the
  <!-- DASHBOARD META --> comment (relocated to <head>) for freshness consumers
  (/work Step 1a, /status, /health-check) — they string-parse it
  byte-identically in HTML.

Spec drift (FB-128): compute_drift() is loaded from the sibling fingerprint.py
by path (importlib) and runs on every render. It feeds META drift_sections, the
footer indicator, the pulse "drift" number and the Needs-you Spec Drift rows. If
it can't load or fails, drift reads as unchecked and nothing else breaks.

Archive awareness: {tasks-dir}/archive/task-*.json are read for COUNTS and
phase-name canonicalization only. Archived Finished count toward phase
done/total; archived Absorbed are excluded; archived tasks in any other status
are excluded from counts. When no task files exist in archive/ but
archive-index.json does, its entries are used at count fidelity.

Phase names: most-common phase_name across active+archived tasks per phase
key (ties: lexicographically smallest).

Dependency graph (hand-rolled, DEC-024): a layered-DAG → inline SVG over
build_graph/longest_path. Auto-hidden when degenerate (<4 incomplete task
nodes, no edges, or a cycle); >15 task nodes reduce to the critical path plus
immediate neighbors. No mermaid (its ESM-from-file:// breakage was FB-007).

Determinism contract: same inputs + same --now -> byte-identical output
(tested in tests/test_dashboard_render_html.py). No Date/random in output.

Read-only. Stdout: HTML. Stderr: diagnostics.
Exit codes: 0 success, 2 runtime/usage error.
"""

import argparse
import hashlib
import html
import importlib.util
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.version_info < (3, 10):  # Python floor (FB-120); see README § Invocation contract
    print(f"error: {Path(__file__).name} needs Python 3.10+; this is Python "
          f"{'.'.join(map(str, sys.version_info[:3]))} ({sys.executable})", file=sys.stderr)
    sys.exit(2)

OWNER_EMOJI = {"human": "❗", "claude": "🤖", "both": "👥"}
UNRESOLVED_DECISION = {"draft", "proposed"}
# FB-129: an agent made the choice during implementation, the work is verified and
# the user has not ratified it. Resolved for decision_dependencies (deliberately not
# in UNRESOLVED_DECISION, so it never blocks), but not "Decided".
RECORDED_DECISION = "recorded"
RATIFY_ROW_MAX_IDS = 8


def numeric_key(value):
    """Numeric-aware sort key for ids/phases like '2', '2_1', '10', 'A'."""
    parts = []
    for chunk in str(value).replace("-", "_").split("_"):
        parts.append((0, int(chunk)) if chunk.isdigit() else (1, chunk))
    return parts


# ---------------------------------------------------------------- loaders

# What json.loads() raises on a file it can't use: bad JSON and bytes that aren't UTF-8
# (both ValueError), an integer literal past the digit limit (a plain ValueError), and
# nesting too deep to parse (RecursionError).
JSON_UNREADABLE = (ValueError, RecursionError, OSError)

# Task fields the render reads by type, with the type's name in the warning.
TASK_FIELD_TYPES = (("status", str, "a string"), ("owner", str, "a string"),
                    ("dependencies", list, "a list"), ("decision_dependencies", list, "a list"),
                    ("task_verification", dict, "a JSON object"), ("due_date", str, "a string"))


def _typed_task(task, name):
    """The task with each wrong-typed field in TASK_FIELD_TYPES, and a non-string
    external_dependency.expected_date, removed: it reads as absent, with one warning
    line per task. Null is absent already and stays silent."""
    bad = []
    for field, kind, label in TASK_FIELD_TYPES:
        if task.get(field) is not None and not isinstance(task[field], kind):
            del task[field]
            bad.append(f"{field} is not {label}")
    ext = task.get("external_dependency")
    if isinstance(ext, dict) and not isinstance(ext.get("expected_date"), (str, type(None))):
        del ext["expected_date"]
        bad.append("external_dependency.expected_date is not a string")
    if bad:
        print(f"warning: {name}: {', '.join(bad)}; reading as absent", file=sys.stderr)
    return task


def load_tasks(tasks_dir: Path):
    tasks = []
    for path in sorted(tasks_dir.glob("task-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except JSON_UNREADABLE as exc:  # incl. not UTF-8
            print(f"warning: skipping unreadable {path.name}: {exc}", file=sys.stderr)
            continue
        if isinstance(data, dict) and data.get("id") is not None:
            tasks.append(_typed_task(data, path.name))
        else:
            print(f"warning: skipping {path.name}: no id field", file=sys.stderr)
    return tasks


def load_archived(tasks_dir: Path):
    """Archived tasks for counts + phase names. Full task files preferred;
    archive-index.json entries as count-fidelity fallback."""
    archive_dir = tasks_dir / "archive"
    if not archive_dir.is_dir():
        return []
    archived = load_tasks(archive_dir)
    if archived:
        return archived
    index = archive_dir / "archive-index.json"
    if index.is_file():
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
            entries = data.get("tasks", []) if isinstance(data, dict) else None
            if not isinstance(entries, list):
                print("warning: archive-index.json has no tasks list; ignoring it", file=sys.stderr)
                return []
            return [_typed_task(t, f"archive-index.json task {t['id']!r}")
                    for t in entries if isinstance(t, dict) and t.get("id") is not None]
        except JSON_UNREADABLE as exc:
            print(f"warning: unreadable archive-index.json: {exc}", file=sys.stderr)
    return []


def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fields = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^(\w[\w_]*):\s*(.*)$", line.strip())
        if m:
            fields[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fields


def load_decisions(decisions_dir: Path):
    decisions = []
    if not decisions_dir.is_dir():
        return decisions
    for path in sorted(decisions_dir.glob("decision-*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            print(f"warning: skipping unreadable {path.name}: {exc}", file=sys.stderr)
            continue
        fm = parse_frontmatter(text)
        selected = None
        section = re.search(r"^## Select an Option\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        if section:
            box = re.search(r"^\s*-\s*\[(?:x|X|✓|✔)\]\s*(.+)$", section.group(1), re.M)
            if box:
                selected = re.sub(r"\*\*", "", box.group(1)).strip()
        decisions.append({
            "id": fm.get("id", path.stem),
            "title": fm.get("title", path.stem),
            "status": fm.get("status", "draft"),
            "selected": selected,
            "file": path.name,
        })
    return decisions


def load_json_file(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except JSON_UNREADABLE as exc:
        print(f"warning: unreadable {path.name}: {exc}", file=sys.stderr)
        return None


def load_json_object(path: Path):
    """load_json_file() for a state file that must be a JSON object. Any other JSON
    value (list, string, number, bool) reads as absent, with a one-line warning."""
    data = load_json_file(path)
    if data is not None and not isinstance(data, dict):
        print(f"warning: {path.name} is not a JSON object; rendering as if absent",
              file=sys.stderr)
        return None
    return data


def _sidecar_object(sidecar, key):
    """A sidecar field that must be an object. Absent or null reads as {}; any other
    non-object reads as {} with a one-line warning."""
    value = sidecar.get(key)
    if value is None or isinstance(value, dict):
        return value or {}
    print(f"warning: dashboard-state.json {key} is not a JSON object; using the default",
          file=sys.stderr)
    return {}


def _sidecar_notes(sidecar):
    """Sidecar user_notes, which must be a string. Absent or null reads as ""; any
    other non-string reads as "" with a one-line warning."""
    value = sidecar.get("user_notes")
    if value is None or isinstance(value, str):
        return value or ""
    print("warning: dashboard-state.json user_notes is not a string; using the default",
          file=sys.stderr)
    return ""


def load_spec(claude_dir: Path):
    specs = sorted(claude_dir.glob("spec_v*.md"),
                   key=lambda p: numeric_key(p.stem.replace("spec_v", "")))
    if not specs:
        return {"version": "—", "status": "—", "fingerprint": "—", "title": None}
    path = specs[-1]
    try:
        text = path.read_text(encoding="utf-8")
        # bytes, not decoded text (A7): the same hash as fingerprint.py --spec and
        # compute_drift, so a CRLF spec doesn't read as changed on every /work
        fingerprint = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except (UnicodeDecodeError, OSError) as exc:
        print(f"warning: unreadable {path.name}: {exc}", file=sys.stderr)
        return {"version": path.stem, "status": "—", "fingerprint": "—", "title": None}
    fm = parse_frontmatter(text)
    title = fm.get("title")
    if not title:
        h1 = re.search(r"^# (.+)$", text, re.M)
        title = h1.group(1).strip() if h1 else None
    return {
        "version": path.stem,
        "status": fm.get("status", "active"),
        "fingerprint": fingerprint,
        "title": title,
    }


def _deferral_items(drift):
    """Usable drift-deferrals.json entries: `{"deferrals": [...]}` or a bare list, keeping
    only objects with a string `section`, the same entries fingerprint.py's
    load_drift_deferrals() reads. Any other shape counts as no deferrals (it used to
    crash the render)."""
    items = drift.get("deferrals") if isinstance(drift, dict) else drift
    if not isinstance(items, list):
        return []
    return [e for e in items if isinstance(e, dict) and isinstance(e.get("section"), str)]


def _load_compute_drift():
    """compute_drift() from the sibling fingerprint.py, loaded by path so it resolves
    both when this file runs as a CLI and when tests load it by path. None when it
    can't be loaded: the render goes on with drift unchecked."""
    path = Path(__file__).resolve().with_name("fingerprint.py")
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # read-only: no __pycache__ beside the scripts
    try:
        mod_spec = importlib.util.spec_from_file_location("fingerprint", path)
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)
        return module.compute_drift
    except (Exception, SystemExit) as exc:  # absent, broken, older, or its version guard
        print(f"warning: drift unchecked: can't load compute_drift from {path.name} ({exc})",
              file=sys.stderr)
        return None
    finally:
        sys.dont_write_bytecode = saved


def load_drift_check(claude_dir: Path):
    """What the render needs from compute_drift(): the unreconciled section count, the
    unreconciled drifted sections with their non-deferred task statuses, and the
    missing sections with their task counts. None = drift unchecked (never raises)."""
    compute = _load_compute_drift()
    if compute is None:
        return None
    try:
        result = compute(claude_dir)
        return {
            "unreconciled": int(result["unreconciled_sections"]),
            "drifted": [(str(d["section"]),
                         [str(t["status"]) for t in d["tasks"] if not t["deferred"]])
                        for d in result["drifted"] if not d["deferred"]],
            "missing": [(str(m["section"]), len(m["tasks"])) for m in result["missing"]],
        }
    except Exception as exc:
        print(f"warning: drift unchecked: compute_drift failed ({exc})", file=sys.stderr)
        return None


# ------------------------------------------------------------ phase model

def phase_key_of(task):
    phase = task.get("phase")
    return "?" if phase in (None, "", "None") else str(phase)


def build_phases(active, archived):
    """Per-phase model: canonical name + active tasks + archived counts."""
    phases = {}
    for task in active:
        phases.setdefault(phase_key_of(task), {"active": [], "arch_finished": 0,
                                               "arch_other": 0, "names": Counter()})["active"].append(task)
    for task in archived:
        entry = phases.setdefault(phase_key_of(task), {"active": [], "arch_finished": 0,
                                                       "arch_other": 0, "names": Counter()})
        status = task.get("status", "Finished")
        if status == "Finished":
            entry["arch_finished"] += 1
        elif status != "Absorbed":
            entry["arch_other"] += 1
        if task.get("phase_name") and isinstance(task["phase_name"], str):
            entry["names"][task["phase_name"]] += 1
    for task in active:
        if task.get("phase_name") and isinstance(task["phase_name"], str):  # a name is a string
            phases[phase_key_of(task)]["names"][task["phase_name"]] += 1
    for entry in phases.values():
        if entry["names"]:
            top = max(entry["names"].values())
            entry["name"] = sorted(n for n, c in entry["names"].items() if c == top)[0]
        else:
            entry["name"] = None
    return phases


def phase_counts(entry):
    """(done, total, archived_other) — On Hold excluded from done, in total;
    Absorbed excluded from both; archived Finished included in both."""
    non_absorbed = [t for t in entry["active"] if t.get("status") != "Absorbed"]
    done = sum(1 for t in non_absorbed if t.get("status") == "Finished") + entry["arch_finished"]
    total = len(non_absorbed) + entry["arch_finished"]
    return done, total, entry["arch_other"]


# --------------------------------------------------- phase status (Progress)

def resolved_decision_ids(decisions):
    return {d["id"] for d in decisions if d["status"] not in UNRESOLVED_DECISION}


def phase_status(key, entry, all_complete_before, decisions):
    done, total, _ = phase_counts(entry)
    open_tasks = [t for t in entry["active"]
                  if t.get("status") not in {"Finished", "Absorbed"}]
    if total and not open_tasks:
        return "Complete"
    if all_complete_before:
        return "Active"
    resolved = resolved_decision_ids(decisions)
    # "Tasks with empty dependencies arrays in future phases are NOT
    # automatically eligible" — only explicit-dep tasks count as eligible early.
    eligible = [t for t in open_tasks if t.get("status") == "Pending"
                and t.get("dependencies")
                and all(str(d) in _GLOBAL_FINISHED for d in t.get("dependencies", []))
                and all(str(d) in resolved for d in t.get("decision_dependencies") or [])]
    if eligible:
        ids = ", ".join(str(t.get("id")) for t in sorted(eligible, key=lambda t: numeric_key(t.get("id")))[:3])
        return f"Partially Actionable ({len(eligible)} eligible: {ids})"
    blockers = sorted({str(d) for t in open_tasks for d in t.get("decision_dependencies") or []
                       if str(d) not in resolved}, key=numeric_key)
    if blockers:
        gated = [t for t in open_tasks
                 if any(str(d) not in resolved for d in t.get("decision_dependencies") or [])]
        if len(gated) < len(open_tasks):
            # Only some tasks are decision-gated — a whole-phase "Blocked" label
            # would misread as "nothing here can start"
            return (f"Blocked ({blockers[0]} gates {len(gated)} of {len(open_tasks)}; "
                    f"rest awaiting prior phase)")
        return f"Blocked ({blockers[0]})"
    return "Blocked (awaiting prior phase)"


_GLOBAL_FINISHED = set()  # finished ids (active + archived), set by render_full_html


# ----------------------------------------- dependency graph topology (shared)

def build_graph(active, decisions):
    """Nodes: incomplete tasks (not Finished/Absorbed/On Hold) + unresolved
    decisions referenced by them. Edges: dep -> task."""
    resolved = resolved_decision_ids(decisions)
    incomplete = {str(t.get("id")): t for t in active
                  if t.get("status") not in {"Finished", "Absorbed", "On Hold"}}
    nodes, edges = {}, {}
    for tid, t in incomplete.items():
        nodes[f"T{tid}"] = {"kind": "task", "task": t}
    for tid, t in incomplete.items():
        for d in t.get("decision_dependencies") or []:
            d = str(d)
            if d not in resolved:
                nodes.setdefault(f"D{d}", {"kind": "decision", "id": d})
                edges.setdefault(f"D{d}", set()).add(f"T{tid}")
        for dep in t.get("dependencies") or []:
            dep = str(dep)
            if dep in incomplete:
                edges.setdefault(f"T{dep}", set()).add(f"T{tid}")
    return nodes, {k: sorted(v, key=numeric_key) for k, v in edges.items()}


def longest_path(nodes, edges):
    """Longest chain by node count; deterministic; None on cycle."""
    memo, visiting = {}, set()

    def walk(n):
        if n in memo:
            return memo[n]
        if n in visiting:
            raise ValueError("cycle")
        visiting.add(n)
        best = [n]
        for s in edges.get(n, []):
            cand = [n] + walk(s)
            if len(cand) > len(best) or (len(cand) == len(best) and cand < best):
                best = cand
        visiting.discard(n)
        memo[n] = best
        return best

    targets = set(t for succ in edges.values() for t in succ)
    entries = sorted((n for n in nodes if n not in targets), key=numeric_key) or sorted(nodes, key=numeric_key)
    try:
        paths = [walk(n) for n in entries]
    except ValueError:
        return None
    if not paths:
        return []
    return max(paths, key=lambda p: (len(p), [-ord(c) for c in p[0]]))


# ------------------------------------------- activity (dates approximate)

def parse_date(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def week_activity(active, now):
    cutoff = now.date() - timedelta(days=7)
    completed = [(parse_date(t.get("completion_date")), t) for t in active
                 if t.get("status") == "Finished" and parse_date(t.get("completion_date"))]
    completed = [(d, t) for d, t in completed if d >= cutoff]
    started = [(parse_date(t.get("updated_date")), t) for t in active
               if t.get("status") == "In Progress" and parse_date(t.get("updated_date"))]
    started = [(d, t) for d, t in started if d >= cutoff]
    created = [(parse_date(t.get("created_date")), t) for t in active
               if parse_date(t.get("created_date"))]
    created = [(d, t) for d, t in created if d >= cutoff]
    return completed, started, created


# ------------------------------------------------- decision status (shared)

DECISION_STATUS_DISPLAY = {"approved": "Decided", "implemented": "Decided",
                           "draft": "Pending", "proposed": "Pending",
                           RECORDED_DECISION: "Recorded",
                           "superseded": "Superseded",
                           "partially_superseded": "Partially Superseded"}


# --------------------------------------------- META + task_hash (shared)

def _review_pending(task):
    """The user's review/testing half is still open (user_review_pending truthy)."""
    return bool(task.get("user_review_pending"))


def canonical_task_hash(active):
    """sha256 over sorted "{id}:{status}:{difficulty}:{owner}:{review}" rows
    (review = 1 when user_review_pending is truthy, else 0), newline-joined
    plus a trailing newline. The review field makes setting or clearing a
    review flag a freshness change (FB-118)."""
    rows = sorted(f"{t.get('id')}:{t.get('status')}:{t.get('difficulty')}:{t.get('owner')}:"
                  f"{1 if _review_pending(t) else 0}"
                  for t in active)
    return "sha256:" + hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()


_META_BREAKS = re.compile("[\x00-\x1f\x7f\x85\u2028\u2029]+")


def _meta_value(value):
    """One META line's value, safe inside the HTML comment: line breaks and
    control characters become a space (a value can't add a META line), and
    & < > are written as entities (a comment only ends at ">"). Ordinary
    values pass through unchanged."""
    s = _META_BREAKS.sub(" ", str(value))
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_meta(active, decisions, spec, version, drift, verification_result, now,
                drift_check=None):
    debt = sum(1 for t in active if t.get("status") == "Finished"
               and (t.get("task_verification") or {}).get("result") != "pass")
    debt += sum(1 for t in active if t.get("status") == "Awaiting Verification")
    counts = Counter(d["status"] for d in decisions)
    drift_count = len(_deferral_items(drift))
    # spec_fingerprint = the spec this page was rendered from; drift_sections = the
    # live check (FB-128), "unchecked" when compute_drift couldn't run
    drift_sections = drift_check["unreconciled"] if drift_check is not None else "unchecked"
    return "\n".join([
        "<!-- DASHBOARD META",
        f"generated: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"task_count: {len(active)}",
        f"task_hash: {canonical_task_hash(active)}",
        f"spec_version: {_meta_value(spec['version'])}",
        f"spec_status: {_meta_value(spec['status'])}",
        f"spec_fingerprint: {_meta_value(spec['fingerprint'])}",
        f"template_version: {_meta_value(version.get('template_version', '—'))}",
        f"verification_debt: {debt}",
        f"drift_deferrals: {drift_count}",
        f"drift_sections: {drift_sections}",
        f"decision_count: {len(decisions)}",
        f"decisions_approved: {counts.get('approved', 0) + counts.get('implemented', 0)}",
        f"decisions_recorded: {counts.get(RECORDED_DECISION, 0)}",
        f"decisions_superseded: {counts.get('superseded', 0)}",
        f"decisions_partially_superseded: {counts.get('partially_superseded', 0)}",
        "-->",
    ])


# ============================================================ HTML rendering
# DEC-024 Option A: a single read-only, offline, file://-openable HTML file.
# Every visualization is inline SVG rendered HERE in Python — zero runtime/CDN
# deps. (The file:// crux: fetch() and ES-module CDN imports both fail from a
# double-clicked file; classic CDN <script> needs network. Only an all-inline,
# build-time-rendered file is single-file + offline + double-click-openable.)
# This layer REUSES the data layer above (load_tasks/build_phases/phase_status/
# build_graph/longest_path/…); it never scrapes rendered Markdown (the prototype
# viz.py's sin). Determinism: byte-identical for a fixed --now (no Date/random).

STATUS_COLOR = {
    "Finished": "#2f7d4f", "Pending": "#9a6212", "In Progress": "#1565c0",
    "Awaiting Verification": "#3b7fc4", "Blocked": "#a8331f",
    "On Hold": "#5a6b86", "Broken Down": "#7a6f57", "Absorbed": "#b8ad97",
}
DONUT_STATUS_ORDER = ["Finished", "In Progress", "Awaiting Verification",
                      "Pending", "Blocked", "On Hold"]
# Owner → (fill, stroke) for dependency-graph nodes (❗ human / 🤖 claude / 👥 both).
OWNER_FILL = {"human": ("#fff9c4", "#f57f17"), "claude": ("#bbdefb", "#1565c0"),
              "both": ("#d4eae4", "#0f5f54")}


def _esc(value):
    return html.escape(str(value))


def _clip(text, limit, word=True):
    """Clip to `limit` chars with a trailing ellipsis. Returns (display, full):
    `full` is the untruncated text when clipping occurred (use it for a title=
    tooltip so nothing is lost), else None. word=True prefers a word boundary
    unless that would drop too much of the content (then hard-clips)."""
    text = str(text).strip()
    if len(text) <= limit:
        return text, None
    cut = text[:limit]
    if word:
        head = cut.rsplit(" ", 1)[0].rstrip(" ,;:.—-–")
        if len(head) >= limit * 0.6:
            cut = head
    return cut.rstrip(" ,;:.—-–") + "…", text


_LINK_SCHEMES = {"http", "https", "mailto"}
_LINK_IGNORED = re.compile("[\x00-\x20\x7f]")


def _md_link(match):
    """A markdown link becomes <a> only when its target is a path, an anchor,
    or http/https/mailto. Any other scheme (javascript:, data:, file: ...) and
    a target that starts with two slashes or backslashes (a network host)
    render as plain "label (target)". The scheme is read the way a browser
    reads it: whitespace and control characters don't count."""
    label, target = match.group(1), match.group(2)
    probe = _LINK_IGNORED.sub("", html.unescape(target))
    scheme = re.match(r"([^/?#:]*):", probe)
    if scheme and scheme.group(1).lower() not in _LINK_SCHEMES:
        return f"{label} ({target})"
    if re.match(r"[/\\]{2}", probe):  # //host or \\host: another machine, from a file:// page
        return f"{label} ({target})"
    return f'<a href="{target}">{label}</a>'


def _mdi(text):
    """Minimal inline markdown → HTML: escape + links + bold + code. The curated
    overview needs almost no markdown (DEC-024 research: 3 regexes suffice)."""
    s = html.escape(str(text))
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _md_link, s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def _status_class(status):
    s = str(status).lower()
    if "complete" in s or "finished" in s:
        return "ok"
    if "active" in s or "in progress" in s:
        return "active"
    if "partial" in s:
        return "warn"
    if "blocked" in s:
        return "bad"
    if "hold" in s:
        return "hold"
    return "mute"


# ---- inline SVG charts (ported from viz.py; data-driven here) ----------------

def _polar(cx, cy, r, f):
    a = 2 * math.pi * f - math.pi / 2
    return cx + r * math.cos(a), cy + r * math.sin(a)


def _ring(segs, frac, size=150, th=16):
    """Hero ring: status segments around the track + % complete in the center.
    Merges the former completion-ring + status-donut into a single circle (the
    Finished sweep visually corresponds to the % complete; the legend beside it
    carries the per-status counts)."""
    cx = cy = size / 2
    r = (size - th) / 2
    nonzero = [(lbl, v, col) for lbl, v, col in segs if v > 0]
    tot = sum(v for _, v, _ in nonzero)
    parts = [f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" '
             f'stroke="var(--paper-2)" stroke-width="{th}"/>']
    if tot and len(nonzero) == 1:  # one status — a full-circle arc can't draw, use a circle
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" '
                     f'stroke="{nonzero[0][2]}" stroke-width="{th}"/>')
    elif tot:
        acc = 0.0
        for _, v, col in nonzero:
            f0, f1 = acc / tot, (acc + v) / tot
            acc += v
            x0, y0 = _polar(cx, cy, r, f0)
            x1, y1 = _polar(cx, cy, r, f1)
            lg = 1 if f1 - f0 > 0.5 else 0
            parts.append(f'<path d="M {x0:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 {lg} 1 '
                         f'{x1:.1f} {y1:.1f}" fill="none" stroke="{col}" stroke-width="{th}"/>')
    parts.append(f'<text x="50%" y="48%" class="ringn">{int(round(frac * 100))}'
                 f'<tspan class="rp">%</tspan></text>')
    parts.append(f'<text x="50%" y="63%" class="ringl">COMPLETE</text>')
    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
            f'class="ring">{"".join(parts)}</svg>')


# ---- per-phase status map (mirrors render_phase_table's stateful loop) --------

def _phase_status_map(phases_model, decisions):
    ordered = sorted(phases_model.keys(), key=lambda k: (k == "?", numeric_key(k)))
    all_complete, out = True, {}
    for key in ordered:
        status = phase_status(key, phases_model[key], all_complete, decisions)
        if status != "Complete":
            all_complete = False
        out[key] = status
    return out


# ---- dependency graph: hand-rolled layered-DAG → inline SVG (DEC-024) ---------

def _adjacent_in(path, a, b):
    return any(path[i] == a and path[i + 1] == b for i in range(len(path) - 1))


def render_svg_graph(active, decisions):
    """Layered-DAG → inline SVG over build_graph/longest_path. Returns '' when
    degenerate (auto-hide): <4 incomplete task nodes, no edges, or a dependency
    cycle. >15 task nodes reduce to the critical path + immediate neighbors."""
    nodes, edges = build_graph(active, decisions)
    task_nodes = [k for k, v in nodes.items() if v["kind"] == "task"]
    if len(task_nodes) < 4 or not edges:
        return ""
    crit = longest_path(nodes, edges)
    if crit is None:  # cycle
        return ""
    crit_set = set(crit)

    note = ""
    if len(task_nodes) > 15:  # scale: critical path + immediate neighbors only
        keep = set(crit)
        for n in list(crit):
            keep.update(edges.get(n, []))
            for src, succs in edges.items():
                if n in succs:
                    keep.add(src)
        omitted = len(task_nodes) - sum(1 for k in keep if nodes.get(k, {}).get("kind") == "task")
        nodes = {k: v for k, v in nodes.items() if k in keep}
        edges = {k: [s for s in v if s in keep] for k, v in edges.items() if k in keep}
        if omitted > 0:
            note = f"Showing critical path + immediate neighbors — {omitted} more tasks omitted"

    preds = {}
    for src, succs in edges.items():
        for d in succs:
            preds.setdefault(d, []).append(src)
    depth = {}

    def _depth(n):
        if n in depth:
            return depth[n]
        depth[n] = -1  # cycle backstop (shouldn't trigger — longest_path checked)
        ps = preds.get(n, [])
        depth[n] = 0 if not ps else 1 + max(_depth(p) for p in ps)
        return depth[n]

    for n in nodes:
        _depth(n)
    layers = {}
    for n in sorted(nodes, key=numeric_key):
        layers.setdefault(depth[n], []).append(n)

    NW, NH, DX, DY, MX, MY = 168, 38, 224, 64, 14, 44
    pos = {}
    for layer in sorted(layers):
        for i, n in enumerate(layers[layer]):
            pos[n] = (MX + layer * DX, MY + i * DY)
    width = MX * 2 + max(layers) * DX + NW
    height = MY * 2 + (max(len(c) for c in layers.values()) - 1) * DY + NH

    edge_svg = []
    for src, succs in sorted(edges.items(), key=lambda kv: numeric_key(kv[0])):
        if src not in pos:
            continue
        sx, sy = pos[src]
        x1, y1 = sx + NW, sy + NH / 2
        for d in succs:
            if d not in pos:
                continue
            dx, dy = pos[d]
            x2, y2 = dx, dy + NH / 2
            on_crit = src in crit_set and d in crit_set and _adjacent_in(crit, src, d)
            mx = (x1 + x2) / 2
            edge_svg.append(f'<path class="{"gedge gcrit" if on_crit else "gedge"}" '
                            f'd="M {x1:.0f} {y1:.0f} C {mx:.0f} {y1:.0f} {mx:.0f} {y2:.0f} {x2:.0f} {y2:.0f}" '
                            f'marker-end="url(#{"ahc" if on_crit else "ah"})"/>')

    node_svg = []
    for n in sorted(nodes, key=numeric_key):
        x, y = pos[n]
        info = nodes[n]
        if info["kind"] == "decision":
            fill, stroke = "#f4ddd5", "#a8331f"
            label = full_label = f"❗ {info['id']}"
        else:
            t = info["task"]
            fill, stroke = OWNER_FILL.get(t.get("owner", "claude"), OWNER_FILL["claude"])
            emoji = OWNER_EMOJI.get(t.get("owner", "claude"), "🤖")
            title_full = str(t.get("title", ""))
            disp, _full = _clip(title_full, 22, word=False)
            label, full_label = f"{emoji} {disp}", f"{emoji} {title_full}"
        crit_cls = " gncrit" if n in crit_set else ""
        node_svg.append(
            f'<g class="gnode{crit_cls}"><title>{_esc(full_label)}</title>'
            f'<rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="8" '
            f'fill="{fill}" stroke="{stroke}"/>'
            f'<text x="{x + NW / 2:.0f}" y="{y + NH / 2 + 4:.0f}" text-anchor="middle">{_esc(label)}</text></g>')

    cap = "Owners: ❗ you · 🤖 Claude · 👥 both · heavier stroke = critical path"
    cap = f"{_esc(note)} · {cap}" if note else cap
    return (
        f'<section><h2 class="st">Flow · dependency &amp; critical path</h2>'
        f'<div class="flowcard"><svg class="depgraph" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" aria-label="dependency graph">'
        f'<defs>'
        f'<marker id="ah" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" refX="6.5" refY="3.2" orient="auto"><path d="M0 0 L7 3.2 L0 6.4 Z" fill="#cabfa8"/></marker>'
        f'<marker id="ahc" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" refX="7" refY="3.6" orient="auto"><path d="M0 0 L8 3.6 L0 7.2 Z" fill="#0f5f54"/></marker>'
        f'</defs>'
        f'{"".join(edge_svg)}{"".join(node_svg)}</svg></div><div class="cap">{cap}</div></section>'
    )


# ---- curated HTML sections (all data-driven) ---------------------------------

def _html_heatmap(phases_model, status_map):
    ordered = sorted(phases_model.keys(), key=lambda k: (k == "?", numeric_key(k)))
    cells = []
    for key in ordered:
        entry = phases_model[key]
        done, total, _ = phase_counts(entry)
        pct = round(100 * done / total) if total else 100
        status = status_map.get(key, "")
        label = "U" if key == "?" else str(key)
        name = entry.get("name") or ("Unphased" if key == "?" else f"Phase {key}")
        head = "Unphased" if key == "?" else f"Phase {key} — {name}"
        cells.append(
            f'<div class="cell {_status_class(status)}" title="{_esc(head)} · {done}/{total} · {_esc(status)}">'
            f'<span class="cn">{_esc(label)}</span>'
            f'<span class="cbar"><i style="height:{pct}%"></i></span></div>')
    return "".join(cells)


def _html_front(phases_model, status_map):
    ordered = sorted(phases_model.keys(), key=lambda k: (k == "?", numeric_key(k)))
    active = [k for k in ordered if status_map.get(k) != "Complete"]
    cards = []
    for key in active[:8]:
        entry = phases_model[key]
        done, total, _ = phase_counts(entry)
        status = status_map.get(key, "")
        pct = round(100 * done / total) if total else 0
        name = entry.get("name") or ("Unphased" if key == "?" else "")
        head = "Unphased" if key == "?" else f"Phase {key}"
        cards.append(
            f'<div class="af"><div class="afh"><b>{_esc(head)}</b> '
            f'<span class="bdg {_status_class(status)}">{_esc(status)}</span>'
            f'<span class="affrac">{done}/{total}</span></div>'
            f'<div class="afn">{_esc(name)}</div>'
            f'<div class="afbar"><i style="width:{pct}%"></i></div></div>')
    return "".join(cards)


def _html_recent(active, now):
    completed, started, _ = week_activity(active, now)
    entries = [(d, t, "Finished") for d, t in completed] + [(d, t, "Started") for d, t in started]
    entries.sort(key=lambda e: (e[0], numeric_key(e[1].get("id"))), reverse=True)
    if not entries:
        return '<div class="rr"><span class="rt" style="color:var(--soft)">No activity in the last 7 days</span></div>'
    rows = []
    for d, t, _verb in entries[:7]:
        disp, full = _clip(str(t.get("title", "")), 90)
        rt_title = f' title="{_esc(full)}"' if full else ""
        rows.append(
            f'<div class="rr"><span class="rd">{d.isoformat()[5:]}</span>'
            f'<span class="tid">{_esc(t.get("id"))}</span>'
            f'<span class="rt"{rt_title}>{_esc(disp)}</span></div>')
    return "".join(rows)


def _html_decisions(decisions):
    if not decisions:
        return ""
    rows = []
    for d in sorted(decisions, key=lambda d: numeric_key(d["id"])):
        display = DECISION_STATUS_DISPLAY.get(d["status"], d["status"].title())
        st = "superseded" if "superseded" in d["status"].lower() else \
             ("decided" if display == "Decided" else
              "recorded" if d["status"] == RECORDED_DECISION else "pending")
        badge = "warn" if st == "recorded" else _status_class(display)  # awaits ratification
        search = html.escape((d["id"] + " " + d["title"] + " " + (d.get("selected") or "")).lower(), quote=True)
        href = f"support/decisions/{d['file']}"
        sel = d.get("selected")
        sel_html = f'<span class="sel">{_mdi(sel)}</span>' if (display == "Decided" and sel) else ""
        rows.append(
            f'<details class="dec" data-status="{st}" data-search="{search}"><summary>'
            f'<span class="did">{_esc(d["id"])}</span><span class="dt">{_esc(d["title"])}</span>'
            f'<span class="bdg {badge}">{_esc(display)}</span></summary>'
            f'<div class="dbody">{sel_html}<a href="{_esc(href)}">open record →</a></div></details>')
    ndec = len(decisions)
    nsup = sum(1 for d in decisions if "superseded" in d["status"].lower())
    ndecided = sum(1 for d in decisions if DECISION_STATUS_DISPLAY.get(d["status"], "") == "Decided")
    # recorded (FB-129): own count + filter, shown only when a record awaits ratification
    nrec = sum(1 for d in decisions if d["status"] == RECORDED_DECISION)
    rec_sum = f" · {nrec} recorded" if nrec else ""
    rec_btn = '<button class="fbtn" data-f="recorded">recorded</button>' if nrec else ""
    return (
        f'<details class="decwrap"><summary><b>📋 Decisions</b> <span class="pill">{ndec}</span>'
        f'<span class="decsum">{ndecided} decided{rec_sum} · {nsup} superseded</span>'
        f'<span class="open">browse ▾</span></summary><div class="decin">'
        f'<div class="dtools"><input id="dq" placeholder="search {ndec} decisions… ( / )" oninput="decFilter()">'
        f'<button class="fbtn on" data-f="all">all</button>'
        f'<button class="fbtn" data-f="decided">decided</button>'
        f'{rec_btn}<button class="fbtn" data-f="superseded">superseded</button>'
        f'<span class="pill" id="dcount">{ndec}</span></div>'
        f'<div class="declist">{"".join(rows)}<div class="empty" id="dempty" style="display:none">no match</div></div>'
        f'</div></details>')


def _html_timeline(active, now):
    today = now.date()
    rows = []
    for t in active:
        if t.get("status") in {"Finished", "Absorbed"}:
            continue
        owner_note = "❗ Human task" if t.get("owner") == "human" else ""
        if t.get("due_date"):
            rows.append((t["due_date"], f"Task {t.get('id')} — {t.get('title', '')}",
                         t.get("status", "Pending"), owner_note))
        ext = t.get("external_dependency") or {}
        if isinstance(ext, dict) and ext.get("expected_date"):
            note = ext.get("contact", "")
            rows.append((ext["expected_date"], f"External: {ext.get('name', 'dependency')}",
                         "Waiting", f"Contact: {note}" if note else ""))
    if not rows:
        return ""
    out = []
    for date_s, item, status, note in sorted(rows, key=lambda r: (r[0], r[1])):
        overdue = False
        try:
            overdue = datetime.strptime(date_s, "%Y-%m-%d").date() < today
        except ValueError:
            pass
        item_disp = f"⚠️ OVERDUE: {item}" if overdue else item
        note_html = f'<span class="tln">{_esc(note)}</span>' if note else ""
        out.append(
            f'<div class="{"tlr over" if overdue else "tlr"}"><span class="tld">{_esc(date_s)}</span>'
            f'<span class="tli">{_esc(item_disp)}</span>'
            f'<span class="bdg {_status_class(status)}">{_esc(status)}</span>{note_html}</div>')
    return f'<section><h2 class="st">Timeline</h2><div class="tlcard">{"".join(out)}</div></section>'


def _html_acceptance(verification_result):
    """Acceptance-criteria status surface (DEC-022): the live phase-acceptance
    status from verification-result.json's criteria[] — NOT the spec's authored
    - [ ] boxes."""
    if not verification_result:
        return ""
    criteria = verification_result.get("criteria")
    if isinstance(criteria, list):
        criteria = [c for c in criteria if isinstance(c, dict)]  # skip malformed entries
    if isinstance(criteria, list) and criteria:
        rows = []
        for c in criteria:
            ok = c.get("status") == "pass"
            # verify-agent.md writes the text under "name"; "criterion" is the older key
            criterion = str(c.get("name") or c.get("criterion") or "").strip()
            note = str(c.get("notes", "")).strip()
            if criterion:
                disp, full = _clip(note, 240)
                title = f' title="{_esc(full)}"' if full else ""
                note_html = (f' <span class="acnote"{title}>— {_esc(disp)}</span>'
                             if note else "")
                body = f'<span class="actext">{_esc(criterion)}{note_html}</span>'
            else:
                # Some verify-agents omit a criterion name — the note IS the
                # description, so promote it rather than rendering "(unnamed)".
                disp, full = _clip(note or "(no description)", 240)
                title = f' title="{_esc(full)}"' if full else ""
                body = f'<span class="actext"{title}>{_esc(disp)}</span>'
            rows.append(f'<li class="{"acok" if ok else "acno"}">'
                        f'<span class="acmark">{"✓" if ok else "○"}</span>{body}</li>')
        passed = sum(1 for c in criteria if c.get("status") == "pass")
        return (f'<section><h2 class="st">Acceptance criteria · {passed}/{len(criteria)} passed</h2>'
                f'<div class="accard"><ul class="aclist">{"".join(rows)}</ul></div></section>')
    passed, failed = verification_result.get("criteria_passed"), verification_result.get("criteria_failed")
    # counts: ints, or whole floats (the schema says "Number"), printed as ints
    if all((isinstance(n, int) and not isinstance(n, bool))
           or (isinstance(n, float) and n.is_integer()) for n in (passed, failed)):
        passed, failed = int(passed), int(failed)
        return (f'<section><h2 class="st">Acceptance criteria</h2>'
                f'<div class="accard"><b>{passed}/{passed + failed}</b> criteria passed</div></section>')
    return ""


def _html_spec_card(claude_dir, spec):
    version = spec.get("version")
    if not version or version == "—":
        return ""
    headings = []
    index = load_json_object(claude_dir / f"{version}.index.json")
    if index and isinstance(index.get("sections"), list):
        headings = [str(s.get("heading", "")).lstrip("# ").strip() for s in index["sections"]
                    if isinstance(s, dict)]
        headings = [h for h in headings if h]
    title = spec.get("title") or version
    if headings:
        body = (f'<div class="specsum">{len(headings)} sections (linked, not embedded — single-source)</div>'
                f'<ul class="specsecs">{"".join(f"<li>{_esc(h)}</li>" for h in headings)}</ul>')
    else:
        body = '<div class="specsum">Open the spec file to browse its sections.</div>'
    return (
        f'<details class="speccard"><summary><b>📄 Specification</b> <span class="pill">{_esc(version)}</span>'
        f'<span class="decsum">{_esc(title)}</span><span class="open">sections ▾</span></summary>'
        f'<div class="specin"><a class="speclink" href="{_esc(version)}.md">open {_esc(version)}.md →</a>{body}</div></details>')


# Notes-card headings (FB-127 n): ATX level -> (tag, font-size). The card sits under
# the page <h1> and the section <h2>s, so a notes "#" starts at <h3>. Styled inline:
# the only stylesheet rule that reaches them (.mini h3, an uppercase label) would
# upper-case commands and paths in a heading.
# Sizes sit above the card's body text (paragraphs 14.5px from body, list items 13px).
_NOTE_HEADINGS = {1: ("h3", 17), 2: ("h4", 16), 3: ("h5", 15), 4: ("h6", 14), 5: ("h6", 14),
                  6: ("h6", 14)}
_NOTE_HEADING_STYLE = ("margin:12px 0 4px;font-size:{size}px;font-weight:600;line-height:1.3;"
                       "text-transform:none;letter-spacing:0;color:var(--ink)")
_NOTE_HEADING_RE = re.compile(r"(#{1,6})\s+(.*)$")


def _html_notes(user_notes, spec=None):
    """Render sidecar user_notes (Quick Links etc.) as read-only HTML — minimal
    block markdown, one block per line: ATX headings (`#` to `######` plus a
    space; `#` -> <h3>, `##` -> <h4>, `###` -> <h5>, deeper -> <h6>; an optional
    closing ` ##` is dropped), `- ` / `* ` bullets, and paragraphs, each with
    _mdi inline markup (links, bold, code) over escaped text. Not supported:
    nested or numbered lists, tables, code blocks. A fenced block's lines still
    render as paragraphs, but a `#` line between the fences is not a heading
    (a fence opens on a line starting with three or more backticks or tildes,
    with no later backtick on a backtick line, and closes on a line of only the
    same character). A heading with no text (`## ##`) stays a paragraph.
    A live spec quick-link is auto-prepended from the current spec version so it
    can never go stale; the seeded user notes must NOT hand-author one (see
    dashboard-regeneration.md § "Notes first-regeneration seeding")."""
    out, in_list, fence = [], False, None  # fence: the open fence's character
    version = (spec or {}).get("version")
    if version and version != "—":
        out.append(f'<p class="qlinks">📄 <strong>Spec:</strong> '
                   f'<a href="{_esc(version)}.md"><code>{_esc(version)}.md</code></a>'
                   f'<span class="qlauto">auto-linked · always current</span></p>')
    for raw in str(user_notes).splitlines():
        line = raw.strip()
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        heading = None
        if fence:
            if len(line) >= 3 and not line.strip(fence):  # only the opening character
                fence = None
        elif line.startswith("~~~") or (line.startswith("```") and "`" not in line.lstrip("`")):
            fence = line[0]
        else:
            heading = _NOTE_HEADING_RE.match(line)
        # an optional closing run of hashes is dropped; nothing left = not a heading
        text = re.sub(r"(^|\s+)#+$", "", heading.group(2)) if heading else ""
        if line.startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_mdi(line[2:])}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            if text:
                tag, size = _NOTE_HEADINGS[len(heading.group(1))]
                out.append(f'<{tag} style="{_NOTE_HEADING_STYLE.format(size=size)}">'
                           f'{_mdi(text)}</{tag}>')
            else:
                out.append(f"<p>{_mdi(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "".join(out)


CSS_HTML = r"""
*{box-sizing:border-box} html{scroll-behavior:smooth}
:root{--paper:#f4f1ea;--paper-2:#e6dfd0;--card:#fbf9f4;--ink:#211d17;--soft:#5d564a;--line:#ddd5c5;--line2:#cabfa8;
 --brand:#0f5f54;--brand2:#27a18c;--brandink:#0a4138;--ok:#2f7d4f;--active:#1565c0;--warn:#9a6212;--bad:#a8331f;--hold:#5a6b86;--mute:#b8ad97;
 --sh:0 1px 0 #fff inset,0 1px 3px rgba(40,32,16,.07),0 10px 30px rgba(40,32,16,.05);}
body{margin:0;background:var(--paper);color:var(--ink);font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:14.5px;line-height:1.5}
.mono,code{font-family:"IBM Plex Mono",ui-monospace,monospace} a{color:var(--brandink)}
.wrap{max-width:1080px;margin:0 auto;padding:0 22px 90px}
header.mast{position:sticky;top:0;z-index:20;background:rgba(244,241,234,.86);backdrop-filter:blur(10px);border-bottom:1px solid var(--line2)}
.mast-in{max-width:1080px;margin:0 auto;padding:11px 22px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.mast .crumb{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:var(--soft);font-weight:600}
.mast h1{font-family:"Fraunces",Georgia,serif;font-weight:600;font-size:18px;margin:0}
.mast .tv{margin-left:auto;font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--soft)}
h2.st{font-family:"Fraunces",serif;font-size:13px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--soft);margin:0 0 12px;display:flex;align-items:center;gap:9px}
h2.st::after{content:"";flex:1;height:1px;background:var(--line2)}
section{margin:28px 0}
.pulse{display:grid;grid-template-columns:auto auto 1fr;gap:26px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px 26px;box-shadow:var(--sh)}
.ring .ringn{font-family:"Fraunces",serif;font-weight:600;font-size:38px;fill:var(--ink);text-anchor:middle}
.ring .rp{font-size:18px;fill:var(--soft)} .ring .ringl{font-size:9px;letter-spacing:.18em;fill:var(--soft);text-anchor:middle;font-family:"IBM Plex Mono",monospace}
.donwrap{display:flex;align-items:center;gap:16px} .legend{display:flex;flex-direction:column;gap:3px}
.lg{display:flex;align-items:center;gap:8px;font-size:12.5px} .lg b{margin-left:auto;font-family:"IBM Plex Mono",monospace} .dot{width:10px;height:10px;border-radius:3px} .lgn{color:var(--soft)}
.pmeta{display:flex;flex-direction:column;gap:10px;justify-self:end;text-align:right} .pmeta .big{font-family:"Fraunces",serif;font-size:30px;font-weight:600;line-height:1}
.pmeta .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--soft)} .pmeta .row{display:flex;gap:18px;justify-content:flex-end}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(46px,1fr));gap:6px}
.cell{position:relative;aspect-ratio:1;border-radius:8px;border:1px solid var(--line);background:var(--card);display:flex;align-items:center;justify-content:center;overflow:hidden;transition:transform .1s}
.cell:hover{transform:translateY(-2px);box-shadow:var(--sh);z-index:2} .cell .cn{font-family:"IBM Plex Mono",monospace;font-size:12px;font-weight:600;z-index:2}
.cell .cbar{position:absolute;inset:0;display:flex;align-items:flex-end;opacity:.5} .cell .cbar>i{width:100%}
.cell.ok{border-color:#bcdcc4}.cell.ok .cbar>i{background:var(--ok)}.cell.ok .cn{color:#1d5435}
.cell.active{border-color:#aecbeb}.cell.active .cbar>i{background:var(--active)}.cell.active .cn{color:#0d3f7a}
.cell.warn .cbar>i{background:var(--warn)}.cell.warn{border-color:#e6cfa0}
.cell.bad{border-color:#e3b6ac}.cell.bad .cbar>i{background:var(--bad)}.cell.bad .cn{color:#7a2417}
.cell.hold .cbar>i{background:var(--hold)} .cell.mute .cbar>i{background:var(--mute)}
.glegend{display:flex;gap:16px;margin-top:12px;font-size:11.5px;color:var(--soft)} .glegend span b{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px}
.front{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:16px}
.af{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px;box-shadow:var(--sh)}
.afh{display:flex;align-items:center;gap:8px;font-size:13px}.affrac{margin-left:auto;font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--soft)}
.afn{font-size:12.5px;color:var(--soft);margin:6px 0 9px;min-height:2.4em}
.afbar{height:6px;border-radius:99px;background:var(--paper-2);overflow:hidden}.afbar>i{display:block;height:100%;background:linear-gradient(90deg,var(--brand),var(--brand2))}
.bdg{font-family:"IBM Plex Mono",monospace;font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:5px;white-space:nowrap}
.bdg.ok{color:var(--ok);background:#e3efe3}.bdg.active{color:var(--active);background:#e2ecf7}.bdg.warn{color:var(--warn);background:#f6ead0}.bdg.bad{color:var(--bad);background:#f4ddd5}.bdg.hold{color:var(--hold);background:#e4e8f0}.bdg.mute{color:var(--soft);background:#eae5da}
.two{display:grid;grid-template-columns:1.4fr 1fr;gap:22px}@media(max-width:760px){.two{grid-template-columns:1fr}.pulse{grid-template-columns:1fr;text-align:center}.pmeta{justify-self:center;text-align:center}.pmeta .row{justify-content:center}}
.att{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:6px 18px 14px;box-shadow:var(--sh)} .att ul{list-style:none;margin:0;padding:0}
.att li{padding:11px 0;border-bottom:1px solid var(--line);font-size:13px}.att li:last-child{border:0}
.tid{font-family:"IBM Plex Mono",monospace;font-weight:600;color:var(--brandink);margin-right:8px}
.att li.arsub{padding-bottom:4px}.att li.arsub>b{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--soft)}
.att li.arsub>ul{margin:6px 0 0;padding:0}.att li.arsub>ul>li{padding:7px 0;border-bottom:0}
.att li.arsub>ul>li+li{border-top:1px solid var(--line)}
.side{display:flex;flex-direction:column;gap:18px} .mini{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 18px;box-shadow:var(--sh)}
.mini h3{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--soft);margin:0 0 10px}
.notescard p{margin:4px 0}.notescard ul{margin:4px 0;padding-left:20px}.notescard li{margin:3px 0;font-size:13px}
.notescard{max-height:340px;overflow:auto}
.qlinks{margin:0 0 10px;padding-bottom:9px;border-bottom:1px solid var(--line)} .qlinks code{font-size:12px} .qlauto{color:var(--soft);font-size:11px;margin-left:8px}
.notesblock>summary{cursor:pointer;list-style:none;display:flex;align-items:center;font-family:"Fraunces",serif;font-size:13px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--soft);margin:0 0 12px}
.notesblock>summary::-webkit-details-marker{display:none}
.notesblock>summary::after{content:"";order:2;flex:1;height:1px;background:var(--line2);margin:0 9px}
.notesblock .ntoggle{order:3;flex:none;text-transform:none;letter-spacing:0;color:var(--brandink);font-size:12px}
.notesblock[open] .ntoggle::after{content:"collapse ▴"} .notesblock:not([open]) .ntoggle::after{content:"expand ▾"}
.rr{display:flex;gap:9px;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--line);font-size:12.5px}.rr:last-child{border:0}
.rd{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--soft);white-space:nowrap} .rt{color:var(--ink)}
/* decisions + spec — collapsed cards */
.decwrap,.speccard{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh);overflow:hidden}
.decwrap>summary,.speccard>summary{cursor:pointer;list-style:none;padding:14px 18px;display:flex;align-items:center;gap:10px}
.decwrap>summary::-webkit-details-marker,.speccard>summary::-webkit-details-marker{display:none}
.decwrap>summary:hover,.speccard>summary:hover{background:var(--paper-2)}
.decsum{color:var(--soft);font-size:12.5px} .decwrap .open,.speccard .open{margin-left:auto;font-size:12px;color:var(--brandink);font-weight:600}
.decwrap[open] .open::after{content:" (close)"} .pill{font-family:"IBM Plex Mono",monospace;font-size:11px;padding:1px 7px;border-radius:99px;border:1px solid var(--line2);color:var(--soft)}
.decin{padding:4px 14px 14px;border-top:1px solid var(--line)} .dtools{display:flex;gap:8px;align-items:center;margin:10px 0;flex-wrap:wrap}
.dtools input{flex:1;min-width:160px;font-size:13px;padding:7px 12px;border:1px solid var(--line2);border-radius:8px;background:var(--card);font-family:inherit}
.dtools input:focus{outline:2px solid var(--brand)} .fbtn{font-family:"IBM Plex Mono",monospace;font-size:11px;padding:5px 11px;border-radius:99px;border:1px solid var(--line2);background:var(--card);color:var(--soft);cursor:pointer}
.fbtn.on{background:var(--brand);color:#fff;border-color:var(--brand)} .declist{max-height:460px;overflow:auto}
.dec{border-bottom:1px solid var(--line)} .dec>summary{cursor:pointer;list-style:none;padding:9px 4px;display:grid;grid-template-columns:74px 1fr auto;gap:10px;align-items:center}
.dec>summary::-webkit-details-marker{display:none} .dec>summary:hover{background:var(--paper-2)} .did{font-family:"IBM Plex Mono",monospace;font-weight:600;font-size:12px;color:var(--brandink)} .dt{font-size:12.5px}
.dbody{padding:2px 4px 12px 88px;font-size:12.5px;color:var(--soft)} .sel{display:block;background:var(--paper-2);color:var(--ink);padding:8px 11px;border-radius:7px;margin-bottom:6px} .empty{padding:16px;text-align:center;color:var(--soft)}
.specin{padding:10px 18px 16px;border-top:1px solid var(--line)} .speclink{display:inline-block;margin-bottom:10px;font-weight:600}
.specsum{font-size:12px;color:var(--soft);margin-bottom:8px} .specsecs{columns:2;font-size:12px;margin:0;padding-left:18px} .specsecs li{margin:2px 0;break-inside:avoid}
@media(max-width:600px){.specsecs{columns:1}}
/* flow graph + timeline */
.flowcard{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh);padding:18px;overflow:auto;text-align:center}
.depgraph{display:block;margin:0 auto;max-width:100%;height:auto}
.gnode text{font-family:"IBM Plex Sans",sans-serif;font-size:11px;fill:var(--ink)} .gnode rect{stroke-width:1.5}
.gnode.gncrit rect{stroke-width:3} .gedge{fill:none;stroke:var(--line2);stroke-width:1.5} .gedge.gcrit{stroke:var(--brand);stroke-width:2.5}
.cap{font-size:12px;color:var(--soft);font-style:italic;margin-top:8px}
.tlcard{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh);padding:6px 18px}
.tlr{display:flex;gap:12px;align-items:baseline;padding:11px 0;border-bottom:1px solid var(--line);font-size:13px}.tlr:last-child{border:0}
.tld{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--soft);white-space:nowrap;min-width:84px} .tli{flex:1} .tln{color:var(--soft);font-size:12px}
.tlr.over .tld{color:var(--bad);text-decoration:line-through} .tlr.over{background:#fbf0ec;margin:0 -18px;padding-left:18px;padding-right:18px}
.accard{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh);padding:6px 18px}
.aclist{list-style:none;margin:0;padding:0} .aclist li{display:flex;gap:10px;align-items:baseline;padding:9px 0;border-bottom:1px solid var(--line);font-size:13px}.aclist li:last-child{border:0}
.acmark{font-weight:700;width:14px;flex:none} .acok .acmark{color:var(--ok)} .acno .acmark{color:var(--soft)}
.actext{flex:1;min-width:0} .acnote{color:var(--soft);font-size:12px}
footer{margin-top:34px;padding-top:14px;border-top:1px solid var(--line2);color:var(--mute);font-family:"IBM Plex Mono",monospace;font-size:11px}
"""

JS_HTML = r"""
function decFilter(){var b=document.querySelector('.fbtn.on');if(!b)return;var q=(document.getElementById('dq').value||'').toLowerCase(),f=b.dataset.f,n=0;
 document.querySelectorAll('.dec').forEach(function(d){var ok=(f==='all'||d.dataset.status===f)&&(!q||d.dataset.search.includes(q));d.style.display=ok?'':'none';if(ok)n++;});
 document.getElementById('dcount').textContent=n;document.getElementById('dempty').style.display=n?'none':'';}
document.addEventListener('click',function(e){if(e.target.classList.contains('fbtn')){document.querySelectorAll('.fbtn').forEach(function(b){b.classList.remove('on');});e.target.classList.add('on');decFilter();}});
document.addEventListener('keydown',function(e){if(e.key==='/'&&e.target.tagName!=='INPUT'){var dq=document.getElementById('dq');if(dq){e.preventDefault();dq.closest('details').open=true;dq.focus();}}});
"""


def _load_feedback_counts(claude_dir: Path):
    """(new, refined, ready) counts from support/feedback/feedback.md. Missing → zeros."""
    path = claude_dir / "support" / "feedback" / "feedback.md"
    if not path.is_file():
        return (0, 0, 0)
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        print(f"warning: unreadable feedback.md: {exc}", file=sys.stderr)
        return (0, 0, 0)
    counts = {"new": 0, "refined": 0, "ready": 0}
    # one status per FB entry: the first **Status:** line after each heading
    for block in re.split(r"(?m)^## FB-\d+", text)[1:]:
        m = re.search(r"(?m)^\*\*Status:\*\*\s*(\w+)", block)
        if m and m.group(1).lower() in counts:
            counts[m.group(1).lower()] += 1
    return (counts["new"], counts["refined"], counts["ready"])


def _attempts(task):
    """verification_attempts as an int; 0 when absent or malformed."""
    try:
        return int(task.get("verification_attempts") or 0)
    except (TypeError, ValueError):
        return 0


def _augment_items(sidecar, active, archived):
    """Sidecar augment_rows[] → (action_texts, fyi_texts), the valid and unexpired
    rows in sidecar order (FB-118). Each item: {"text": str (required),
    "task_id": str, "kind": "action" | "fyi" (default "action"), "created":
    "YYYY-MM-DD"}. Malformed input is skipped, never fatal: a non-list
    augment_rows, items that aren't objects, items without non-empty string text.
    Expiry: a row whose task_id names a known task (active, else archived) is
    dropped once that task is Absorbed, or Finished without user_review_pending.
    An unknown task_id keeps the row — never silently hide a user-gated item."""
    items = sidecar.get("augment_rows") if isinstance(sidecar, dict) else None
    if not isinstance(items, list):
        return [], []
    # archived entries default to Finished (load_archived's index fallback may omit status)
    known = {str(t.get("id")): (t.get("status", "Finished"), _review_pending(t)) for t in archived}
    known.update({str(t.get("id")): (t.get("status"), _review_pending(t)) for t in active})
    actions, fyis = [], []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        task_id = item.get("task_id")
        state = known.get(str(task_id).strip()) if task_id is not None else None
        if state and (state[0] == "Absorbed" or (state[0] == "Finished" and not state[1])):
            continue
        kind = str(item.get("kind") or "action").strip().lower()
        (fyis if kind == "fyi" else actions).append(text.strip())
    return actions, fyis


def _status_counts_text(statuses):
    """'3 Finished, 1 Pending': counts in DONUT_STATUS_ORDER, any other status after."""
    counts = Counter(statuses)
    order = DONUT_STATUS_ORDER + sorted(s for s in counts if s not in DONUT_STATUS_ORDER)
    return ", ".join(f"{counts[s]} {_esc(s)}" for s in order if counts.get(s))


def _html_needs_you(active, decisions, phases_model, status_map, sidecar,
                    verification_result, drift, claude_dir, archived=(), drift_check=None):
    """Deterministic Action Required rows (FB-105, FB-118).

    The script owns every mechanically-derivable row so the human-gated coverage
    invariant cannot be silently dropped by an unfilled placeholder (observed: a
    regen left the card empty while 5 user-gated items were outstanding).
    Judgment items the script can't derive (unanswered questions from a paused
    session, context a mechanical row would miss) come from sidecar augment_rows[]
    and render as the final "Also Needs You" sub-section, so a regen never wipes
    them. Sub-section order follows dashboard-regeneration.md § Section Display
    Rules.
    """
    out = []

    def sub(title, rows):
        if rows:
            out.append(f'<li class="arsub"><b>{title}</b><ul>' + "".join(rows) + "</ul></li>")

    def row(body):
        return f"<li>{body}</li>"

    finished_ids = set(_GLOBAL_FINISHED)
    resolved = resolved_decision_ids(decisions)

    # Phase Transitions — boundary reached, gate not yet approved
    gates = _sidecar_object(sidecar, "phase_gates")
    keys = sorted(phases_model.keys(), key=numeric_key)
    rows = []
    for i, key in enumerate(keys[:-1]):
        nxt = keys[i + 1]
        if status_map.get(key) == "Complete" and status_map.get(nxt) != "Complete":
            gate = gates.get(f"{key}→{nxt}")
            if not (isinstance(gate, dict) and gate.get("status") == "approved"):
                rows.append(row(f'Phase {_esc(key)} complete — approve the gate to start '
                                f'phase {_esc(nxt)} → run <code>/work</code>'))
    sub("Phase Transitions", rows)

    # Verification Pending / Debt
    non_absorbed = [t for t in active if t.get("status") != "Absorbed"]
    open_tasks = [t for t in non_absorbed if t.get("status") != "Finished"]
    # Held while any review is open, even when every task is Finished: a
    # display-order choice (the user's open review comes first), not a readiness
    # gate; /work's phase routing doesn't check the flag (FB-118, from LTP).
    review_open = any(_review_pending(t) for t in non_absorbed)
    if non_absorbed and not open_tasks and not verification_result and not review_open:
        sub("Verification Pending", [row(
            "All tasks Finished but no phase verification result — run <code>/work</code> "
            "to dispatch phase-level verification")])
    debt = [t for t in active if (t.get("status") == "Finished"
            and (t.get("task_verification") or {}).get("result") != "pass")
            or t.get("status") == "Awaiting Verification"]
    sub("Verification Debt", [row(
        f'<span class="tid">{_esc(t.get("id"))}</span>{_esc(t.get("title") or "")} — '
        f'verification incomplete → run <code>/work</code>') for t in debt])

    # Spec Drift — one row per unreconciled section (FB-128: drifted, then missing),
    # then the deferral row
    rows = []
    if drift_check is not None:
        rows += [row(f'<code>{_esc(section)}</code> changed since its tasks were built '
                     f'({_status_counts_text(statuses)}) → run <code>/work</code> to reconcile')
                 for section, statuses in drift_check["drifted"]]
        rows += [row(f'<code>{_esc(section)}</code> is no longer in the spec ({n} open task(s) '
                     f'reference it) → run <code>/work</code> to reconcile')
                 for section, n in drift_check["missing"]]
    d_items = _deferral_items(drift)
    if d_items:
        rows.append(row(f'{len(d_items)} deferred spec-drift reconciliation(s) '
                        f'→ run <code>/work</code> to review'))
    sub("Spec Drift", rows)

    # Audit Findings
    digest = _sidecar_object(sidecar, "audit_digest")
    # lists, not sets: a malformed (unhashable) id must not crash the render
    dismissed = digest.get("dismissed_ids") if isinstance(digest.get("dismissed_ids"), list) else []
    items = digest.get("items") if isinstance(digest.get("items"), list) else []
    pending = [i for i in items if isinstance(i, dict)
               and i.get("status") == "pending" and i.get("id") not in dismissed]
    if pending:
        sub("Audit Findings", [row(
            f'<span class="tid">{_esc(i.get("id"))}</span>'
            f'{_esc(i.get("description") or i.get("title") or "")}') for i in pending])
    elif digest.get("latest_audit"):
        sub("Audit Findings", [row(
            f'<i>No pending audit findings. Last audit: {_esc(digest.get("latest_audit"))}.</i>')])

    # Feedback
    fb_new, fb_ref, fb_ready = _load_feedback_counts(claude_dir)
    if fb_new or fb_ref or fb_ready:
        sub("Feedback", [row(
            f'📝 <b>{fb_new + fb_ref + fb_ready} feedback items</b> awaiting attention '
            f'({fb_new} new, {fb_ref} refined, {fb_ready} ready) → run '
            f'<code>/feedback review</code>')])

    # Decisions — unresolved records, then ONE row for every agent-recorded decision
    # awaiting ratification (FB-129). Keyed on status alone: a legacy approved or
    # implemented record with decided_by: implement-agent gets no row (/health-check's).
    rows = [row(
        f'<span class="tid">{_esc(d["id"])}</span>{_esc(d.get("title") or "")} — unresolved '
        f'({_esc(d["status"])}) → tick your option in '
        f'<a href="support/decisions/{_esc(d["file"])}">{_esc(d["file"])}</a>')
        for d in decisions if d["status"] in UNRESOLVED_DECISION]
    recorded = sorted((d for d in decisions if d["status"] == RECORDED_DECISION),
                      key=lambda d: numeric_key(d["id"]))
    if recorded:
        n = len(recorded)
        ids = [f'<a href="support/decisions/{_esc(d["file"])}">{_esc(d["id"])}</a>'
               for d in recorded[:RATIFY_ROW_MAX_IDS]]
        if n > RATIFY_ROW_MAX_IDS:
            ids.append(f"+{n - RATIFY_ROW_MAX_IDS} more")
        noun = "agent decision awaits" if n == 1 else "agent decisions await"
        rows.append(row(
            f'{n} {noun} ratification: {", ".join(ids)} — run <code>/work ratify all</code> '
            f'(or <code>/work ratify DEC-NNN</code>)'))
    sub("Decisions", rows)

    # Your Tasks — at most one row per task, first match wins (FB-118). Scans all
    # non-Absorbed tasks: user_review_pending is set together with Finished, so
    # scanning open_tasks made every review row unreachable.
    #   (a) On Hold  (b) review pending: Finished + user_review_pending, any owner
    #   (the flag is only set with Finished; a stale flag on reworked work is ignored
    #   so the card never offers /work complete for unverified work)  (c) Blocked on the user: owner both/human, or
    #   verification escalated (>= 3 attempts)  (d) human-owned, actionable, deps met
    #   (not Broken Down: /work complete rejects a parent; its subtasks carry the work)
    rows = []
    for t in sorted(non_absorbed, key=lambda t: numeric_key(t.get("id"))):
        owner, status = t.get("owner"), t.get("status")
        deps_ok = all(str(d) in finished_ids for d in (t.get("dependencies") or [])) and \
                  all(str(d) in resolved for d in (t.get("decision_dependencies") or []))
        attempts = _attempts(t)
        tid = f'<span class="tid">{_esc(t.get("id"))}</span>{_esc(t.get("title") or "")}'
        cmd = f' → run <code>/work complete {_esc(t.get("id"))}</code>'
        resume = f' → run <code>/work {_esc(t.get("id"))}</code>'
        if status == "On Hold":
            rows.append(row(f'{tid} — On Hold; only you can resume it{resume}'))
        elif status == "Finished" and _review_pending(t):
            half = ("Claude's half verified; your review closes it" if owner == "both"
                    else "verified; your review or testing closes it")
            rows.append(row(f'{tid} — {half}{cmd}'))
        elif status == "Blocked" and (owner in ("both", "human") or attempts >= 3):
            why = (f"verification escalated after {attempts} attempts" if attempts >= 3
                   else "needs you")
            rows.append(row(f"{tid} — Blocked — {why}; the blocker is in the task's notes{resume}"))
        elif owner == "human" and status not in ("Blocked", "Broken Down", "Finished", "On Hold") and deps_ok:
            rows.append(row(f'{tid} — yours to do{cmd}'))
    sub("Your Tasks", rows)

    # Reviews — out-of-spec awaiting approval
    sub("Reviews", [row(
        f'<span class="tid">{_esc(t.get("id"))}</span>{_esc(t.get("title") or "")} — '
        f'out-of-spec task awaiting your approval → run <code>/work</code>')
        for t in open_tasks if t.get("out_of_spec")
        and not t.get("out_of_spec_approved") and not t.get("out_of_spec_rejected")])

    # Also Needs You — judgment rows from sidecar augment_rows[] (FB-118): action
    # rows first, then muted FYI rows; same inline markdown as the Notes card.
    script_rows = bool(out)
    actions, fyis = _augment_items(sidecar, active, archived)
    out.append(
        "<!-- Judgment rows come from sidecar augment_rows[] in dashboard-state.json"
        " (contract: dashboard-regeneration.md); the HTML is generated and not"
        " hand-edited. -->")
    sub("Also Needs You", [row(_mdi(text)) for text in actions] +
        [f'<li style="color:var(--soft)">FYI — {_mdi(text)}</li>' for text in fyis])
    if not script_rows and not actions:  # fyi rows ask nothing of the user
        out.insert(0, '<li style="color:var(--soft)">Nothing blocked on you right now.</li>')
    return "".join(out)


def render_full_html(claude_dir: Path, now: datetime):
    global _GLOBAL_FINISHED
    tasks_dir = claude_dir / "tasks"
    active = load_tasks(tasks_dir) if tasks_dir.is_dir() else []
    archived = load_archived(tasks_dir) if tasks_dir.is_dir() else []
    decisions = load_decisions(claude_dir / "support" / "decisions")
    # missing, unreadable, or valid JSON that isn't an object: all read as absent
    sidecar = load_json_object(claude_dir / "dashboard-state.json") or {}
    version = load_json_object(claude_dir / "version.json") or {}
    verification_result = load_json_object(claude_dir / "verification-result.json")
    drift = load_json_file(claude_dir / "drift-deferrals.json")
    drift_check = load_drift_check(claude_dir)  # None = drift unchecked (FB-128)
    spec = load_spec(claude_dir)
    _GLOBAL_FINISHED = {str(t.get("id")) for t in active if t.get("status") == "Finished"} | \
                       {str(t.get("id")) for t in archived if t.get("status", "Finished") == "Finished"}
    phases_model = build_phases(active, archived)
    toggles = _sidecar_object(sidecar, "section_toggles")
    status_map = _phase_status_map(phases_model, decisions)
    title = spec.get("title") or "Project"

    # completion (done/total folds archived-finished in, same basis as render_header_lines)
    total_done = sum(phase_counts(e)[0] for e in phases_model.values())
    total_all = sum(phase_counts(e)[1] for e in phases_model.values())
    frac = (total_done / total_all) if total_all else 0.0
    n_phases = len(phases_model)
    done_ph = sum(1 for s in status_map.values() if s == "Complete")
    active_ph = n_phases - done_ph

    # status distribution (donut + legend); archived-finished folded into Finished,
    # labeled so the count doesn't read as wrong beside the active-task total
    status_counts = Counter(t.get("status", "Pending") for t in active)
    arch_finished = sum(1 for t in archived if t.get("status", "Finished") == "Finished")
    status_counts["Finished"] += arch_finished
    segs = [(s, status_counts.get(s, 0), STATUS_COLOR.get(s, "#b8ad97"))
            for s in DONUT_STATUS_ORDER if status_counts.get(s, 0)]

    def _legend_label(s):
        if s == "Finished" and arch_finished:
            return (f'Finished <span style="color:var(--soft);font-weight:400">'
                    f'(incl. {arch_finished} archived)</span>')
        return s

    legend = "".join(
        f'<div class="lg"><span class="dot" style="background:{STATUS_COLOR.get(s, "#b8ad97")}"></span>'
        f'<span class="lgn">{_legend_label(s)}</span><b>{status_counts.get(s, 0)}</b></div>'
        for s in DONUT_STATUS_ORDER if status_counts.get(s, 0))

    meta_block = render_meta(active, decisions, spec, version, drift, verification_result, now,
                             drift_check)
    debt = sum(1 for t in active if t.get("status") == "Finished"
               and (t.get("task_verification") or {}).get("result") != "pass")
    debt += sum(1 for t in active if t.get("status") == "Awaiting Verification")
    drift_count = len(_deferral_items(drift))
    unreconciled = drift_check["unreconciled"] if drift_check is not None else 0
    drift_total = unreconciled + drift_count  # just the deferrals when unchecked
    debt_color = "var(--bad)" if debt else "var(--ok)"
    drift_color = "var(--bad)" if drift_total else "var(--ok)"

    pulse = (
        f'<section><div class="pulse">{_ring(segs, frac)}'
        f'<div class="legend">{legend}</div>'
        f'<div class="pmeta"><div class="row">'
        f'<div><div class="big">{done_ph}<span style="color:var(--soft);font-size:18px">/{n_phases}</span></div>'
        f'<div class="lbl">phases done</div></div>'
        f'<div><div class="big">{active_ph}</div><div class="lbl">active now</div></div></div>'
        f'<div class="row">'
        f'<div><div class="big" style="color:{debt_color}">{debt}</div><div class="lbl">verif debt</div></div>'
        f'<div><div class="big" style="color:{drift_color}">{drift_total}</div><div class="lbl">drift</div></div>'
        f'</div></div></div></section>')

    heatmap = _html_heatmap(phases_model, status_map)
    front = _html_front(phases_model, status_map)
    graph = render_svg_graph(active, decisions)
    accept = _html_acceptance(verification_result)
    timeline = _html_timeline(active, now)

    if toggles.get("action_required", True):
        needs_you = _html_needs_you(active, decisions, phases_model, status_map, sidecar,
                                    verification_result, drift, claude_dir, archived, drift_check)
    else:
        needs_you = '<li style="color:var(--soft)">Action Required section is toggled off.</li>'
    twocol = (
        f'<section><div class="two">'
        f'<div><h2 class="st">Needs you</h2><div class="att"><ul>{needs_you}</ul></div></div>'
        f'<div class="side"><div class="mini"><h3>Recent — last 7 days</h3>{_html_recent(active, now)}</div></div>'
        f'</div></section>')

    decisions_block = _html_decisions(decisions) if toggles.get("decisions", True) else ""
    spec_card = _html_spec_card(claude_dir, spec)

    custom = ""
    if toggles.get("custom_views", False):
        instr = sidecar.get("custom_views_instructions")
        instr = instr if isinstance(instr, str) else ""
        custom = (
            f'<section><h2 class="st">Custom Views</h2>'
            f'<!-- CUSTOM VIEWS INSTRUCTIONS -->\n{html.escape(instr)}\n<!-- END CUSTOM VIEWS INSTRUCTIONS -->'
            f'<div class="att"><!-- CLAUDE: fill — render one block per bold-labeled instruction above, as HTML --></div>'
            f'</section>')

    notes_card = ""
    user_notes = _sidecar_notes(sidecar) if toggles.get("notes", True) else ""
    if user_notes.strip():
        # Collapsible + height-capped so the (often long, append-only) notes stop
        # dominating the page; open by default so quick-links stay visible.
        notes_card = (f'<section><details class="notesblock" open>'
                      f'<summary>Notes<span class="ntoggle"></span></summary>'
                      f'<div class="mini notescard">{_html_notes(user_notes, spec)}</div></details></section>')

    if drift_check is None:
        indicator = f'drift unchecked · {drift_count} drift deferrals, {debt} verification debt'
    elif unreconciled or drift_count or debt:
        indicator = (f'⚠️ {unreconciled} changed spec section(s), {drift_count} drift deferrals, '
                     f'{debt} verification debt')
    else:
        indicator = 'spec aligned · 0 drift deferrals, 0 verification debt'
    # task count == the completion-ring / phase-map basis (total_all: active
    # non-absorbed + archived-finished), NOT len(active) which omits archived
    # tasks and contradicts the ring/donut/phase totals on archived projects.
    footer = (f'<footer>generated {now.strftime("%Y-%m-%dT%H:%M:%SZ")} · {total_all} tasks · {indicator} · '
              f'single read-only HTML view · state of record = task JSON</footer>')

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_esc(title)} — Dashboard</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">'
        f'\n{meta_block}\n'
        f'<style>{CSS_HTML}</style>'
        '<svg width="0" height="0"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="var(--brand)"/><stop offset="1" stop-color="var(--brand2)"/>'
        '</linearGradient></defs></svg></head>'
        f'<body><header class="mast"><div class="mast-in"><span class="crumb">Execute</span>'
        f'<h1>{_esc(title)}</h1>'
        f'<span class="tv">{total_all} tasks · {n_phases} phases · read-only view</span></div></header>'
        f'<div class="wrap">{pulse}'
        f'<section><h2 class="st">Phase map · {n_phases} phases</h2><div class="grid">{heatmap}</div>'
        f'<div class="glegend"><span><b style="background:var(--ok)"></b>complete</span>'
        f'<span><b style="background:var(--active)"></b>active</span>'
        f'<span><b style="background:var(--warn)"></b>partial</span>'
        f'<span><b style="background:var(--bad)"></b>blocked</span>'
        f'<span style="margin-left:auto">fill = % done · hover for detail</span></div>'
        f'<div class="front">{front}</div></section>'
        f'{accept}{graph}{timeline}{twocol}'
        f'<section>{decisions_block}</section>'
        f'<section>{spec_card}</section>'
        f'{custom}{notes_card}{footer}</div>'
        f'<script>{JS_HTML}</script></body></html>')


# ------------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(description="Deterministic dashboard renderer (Family C full port).")
    parser.add_argument("--html", action="store_true", help="render the full dashboard as HTML (DEC-024)")
    parser.add_argument("--task-hash", action="store_true", help="print the canonical META task_hash and exit")
    parser.add_argument("--tasks-dir", default=".claude/tasks", help="task JSON directory (for --task-hash)")
    parser.add_argument("--claude-dir", default=".claude", help="environment root (for --html)")
    parser.add_argument("--now", default=None, help="ISO timestamp for deterministic output (default: current UTC)")
    args = parser.parse_args(argv)

    modes = sum(bool(m) for m in (args.html, args.task_hash))
    if modes != 1:
        parser.print_usage(sys.stderr)
        print("error: exactly one of --html / --task-hash is required", file=sys.stderr)
        return 2

    if args.now:
        try:
            now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            print(f"error: invalid --now timestamp: {args.now}", file=sys.stderr)
            return 2
    else:
        now = datetime.now(timezone.utc)

    if args.task_hash:
        tasks_dir = Path(args.tasks_dir)
        if not tasks_dir.is_dir():
            print(f"error: tasks dir not found: {tasks_dir}", file=sys.stderr)
            return 2
        print(canonical_task_hash(load_tasks(tasks_dir)))
        return 0

    claude_dir = Path(args.claude_dir)
    if not claude_dir.is_dir():
        print(f"error: claude dir not found: {claude_dir}", file=sys.stderr)
        return 2
    print(render_full_html(claude_dir, now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
