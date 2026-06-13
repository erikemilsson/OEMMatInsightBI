#!/usr/bin/env python3
"""dashboard-render.py — Family C full port (FB-011, v4.22.0): deterministic
renderer for the dashboard's STRUCTURAL sections.

Division of labor (per template-maintenance/scripts-candidates.md § Family C):
the script renders every structural/data section deterministically; the LLM
fills the SYNTHESIS sections — Action Required (judgment + coverage contract)
and Custom Views rendered content — via the `<!-- CLAUDE: fill ... -->`
placeholders this script emits. Notes is preserved verbatim from the sidecar.
The executable contract implements the prose specification in
support/reference/dashboard-regeneration.md (§ Regeneration Steps 3-6,
§ Section Format Reference, § Critical Path Generation, § Project Overview
Diagram); where this docstring notes a simplification, the script is the
shipped behavior and the prose is the aspiration.

Modes:
  --tasks-section          render only "## 📋 Tasks" (PoC mode, kept; now
                           archive-aware when {tasks-dir}/archive/ exists)
  --render                 render the FULL dashboard markdown to stdout
  --task-hash              print the canonical META task_hash and exit

Canonical task_hash (this script is the single authority — fixes the
three-way divergence observed in styler 2026-06-11):
  sha256 over "\\n".join(sorted("{id}:{status}:{difficulty}:{owner}"
  for each ACTIVE task)) + "\\n"   — string sort, archive excluded,
  rendered with a "sha256:" prefix.

Archive awareness: {tasks-dir}/archive/task-*.json are read for COUNTS and
phase-name canonicalization only — archived tasks never render as rows.
Archived Finished count toward phase done/total; archived Absorbed are
excluded (same as active); archived tasks in any other status are excluded
from counts and surfaced as a deterministic "(+N archived non-finished)"
note. When no task files exist in archive/ but archive-index.json does,
its entries are used at count fidelity (no phase names).

Phase names: most-common phase_name across active+archived tasks per phase
key (ties: lexicographically smallest) — the deterministic implementation of
"the descriptive name comes from the spec's phase definition" (decomposition
stamps spec phase names into task files).

Documented simplifications (full-port scope decisions, 2026-06-11):
- Mermaid: >15 active nodes switches straight to critical-path-only mode;
  the intermediate "subgraph clumping" visual-noise step is not implemented.
  Phase-gate hexagon nodes are not emitted (Action Required carries gates).
- Critical-path parallel branches: fork/join detection is bounded — fork =
  an on-path node, join = the nearest on-path descendant reachable from 2+
  of its successors; branches render by first step (per the rules).
- "This week" / Recent Activity transition source: completion_date (finished),
  updated_date on In Progress (started), created_date (created) — task JSON
  has no transition log, so dates approximate transitions.
- Header project line: title from spec frontmatter `title:` or first H1;
  stage derived (no tasks -> Spec, unfinished -> Execute, else Complete).
- Per-phase qualifier lines remain deterministic count enumerations.

Determinism contract: same inputs + same --now -> byte-identical output
(tested in tests/test_dashboard_render.py).

Read-only. Stdout: markdown. Stderr: diagnostics.
Exit codes: 0 success, 2 runtime/usage error.
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATUS_ORDER = ["In Progress", "Awaiting Verification", "Pending", "Blocked", "On Hold"]
SUMMARY_STATUS_ORDER = ["Finished", "Pending", "In Progress", "Awaiting Verification",
                        "Blocked", "On Hold", "Broken Down", "Absorbed"]
ACTIONABLE = {"Pending", "In Progress", "Awaiting Verification", "On Hold"}
OWNER_EMOJI = {"human": "❗", "claude": "🤖", "both": "👥"}
UNRESOLVED_DECISION = {"draft", "proposed"}
TOGGLE_ORDER = [("action_required", "Action Required"), ("progress", "Progress"),
                ("tasks", "Tasks"), ("decisions", "Decisions"), ("notes", "Notes"),
                ("custom_views", "Custom Views")]


def numeric_key(value):
    """Numeric-aware sort key for ids/phases like '2', '2_1', '10', 'A'."""
    parts = []
    for chunk in str(value).replace("-", "_").split("_"):
        parts.append((0, int(chunk)) if chunk.isdigit() else (1, chunk))
    return parts


def esc(cell):
    return str(cell).replace("|", "\\|")


# ---------------------------------------------------------------- loaders

def load_tasks(tasks_dir: Path):
    tasks = []
    for path in sorted(tasks_dir.glob("task-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"warning: skipping unreadable {path.name}: {exc}", file=sys.stderr)
            continue
        if isinstance(data, dict) and data.get("id") is not None:
            tasks.append(data)
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
            return [t for t in data.get("tasks", []) if isinstance(t, dict) and t.get("id") is not None]
        except (json.JSONDecodeError, OSError) as exc:
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
        except OSError as exc:
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
    except (json.JSONDecodeError, OSError) as exc:
        print(f"warning: unreadable {path.name}: {exc}", file=sys.stderr)
        return None


def load_spec(claude_dir: Path):
    specs = sorted(claude_dir.glob("spec_v*.md"),
                   key=lambda p: numeric_key(p.stem.replace("spec_v", "")))
    if not specs:
        return {"version": "—", "status": "—", "fingerprint": "—", "title": None}
    path = specs[-1]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"version": path.stem, "status": "—", "fingerprint": "—", "title": None}
    fm = parse_frontmatter(text)
    title = fm.get("title")
    if not title:
        h1 = re.search(r"^# (.+)$", text, re.M)
        title = h1.group(1).strip() if h1 else None
    return {
        "version": path.stem,
        "status": fm.get("status", "active"),
        "fingerprint": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "title": title,
    }


# ----------------------------------------------------------- task display

def display_status(task):
    status = task.get("status", "Pending")
    if status == "On Hold":
        return "⏸️ On Hold"
    if status == "Absorbed":
        return f"Absorbed → Task {task.get('absorbed_into', '?')}"
    if status == "Finished":
        retries = max(len(task.get("verification_history", [])) - 1, 0)
        return f"Finished ({retries} retries)" if retries >= 1 else "Finished"
    if status == "Pending" and task.get("conflict_note"):
        return f"Pending (held: conflict with Task {task['conflict_note']})"
    return status


def display_title(task):
    title = task.get("title", "(untitled)")
    if task.get("out_of_spec"):
        title = f"⚠️ {title}"
    if task.get("cross_phase"):
        title = f"{title} (cross-phase)"
    return title


def display_deps(task):
    deps = [str(d) for d in task.get("dependencies", [])]
    deps += [str(d) for d in task.get("decision_dependencies", [])]
    return ", ".join(deps) if deps else "—"


def task_row(task):
    cells = [str(task.get("id", "?")), display_title(task), display_status(task),
             str(task.get("difficulty", "—")), str(task.get("owner", "claude")),
             display_deps(task)]
    return "| " + " | ".join(esc(c) for c in cells) + " |"


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
        if task.get("phase_name"):
            entry["names"][task["phase_name"]] += 1
    for task in active:
        if task.get("phase_name"):
            phases[phase_key_of(task)]["names"][task["phase_name"]] += 1
    for entry in phases.values():
        if entry["names"]:
            top = max(entry["names"].values())
            entry["name"] = sorted(n for n, c in entry["names"].items() if c == top)[0]
        else:
            entry["name"] = None
    return phases


def phase_header(key, name):
    if key == "?":
        return "### Unphased"
    return f"### Phase {key} — {name}" if name else f"### Phase {key}"


def phase_counts(entry):
    """(done, total, archived_other) — On Hold excluded from done, in total;
    Absorbed excluded from both; archived Finished included in both."""
    non_absorbed = [t for t in entry["active"] if t.get("status") != "Absorbed"]
    done = sum(1 for t in non_absorbed if t.get("status") == "Finished") + entry["arch_finished"]
    total = len(non_absorbed) + entry["arch_finished"]
    return done, total, entry["arch_other"]


# ----------------------------------------------------------- Tasks section

def phase_blockers(blocked_tasks, finished_ids, prev_phase):
    blockers = set()
    for task in blocked_tasks:
        blockers.update(str(d) for d in task.get("decision_dependencies", []))
        for dep in task.get("dependencies", []):
            if str(dep) not in finished_ids:
                blockers.add(f"task-{dep}")
    ordered = sorted(blockers, key=numeric_key)
    if not ordered:
        return f"awaiting Phase {prev_phase}" if prev_phase else "awaiting upstream work"
    shown = ", ".join(f"blocked by {b}" for b in ordered[:2])
    if len(ordered) > 2:
        shown += f" and {len(ordered) - 2} others"
    return shown


def qualifier_line(active_tasks):
    counts = []
    for status in STATUS_ORDER:
        n = sum(1 for t in active_tasks if t.get("status") == status)
        if n:
            counts.append(f"{n} {status.lower()}")
    return ", ".join(counts)


def render_phase(key, entry, finished_ids, prev_phase):
    tasks = entry["active"]
    non_absorbed = [t for t in tasks if t.get("status") != "Absorbed"]
    finished = [t for t in non_absorbed if t.get("status") == "Finished"]
    open_tasks = [t for t in non_absorbed if t.get("status") != "Finished"]
    done, total, arch_other = phase_counts(entry)
    note = f" (+{arch_other} archived non-finished)" if arch_other else ""
    lines = [phase_header(key, entry["name"]), ""]

    # Completed phase collapsing: every countable task Finished (archive-aware).
    if total and not open_tasks:
        lines.append(f"✅ {done} tasks finished{note}")
        lines.append("")
        return lines, done, total

    # Archived-other-only phase (nothing countable, nothing open): note line.
    if not total and not open_tasks:
        lines.append(f"({arch_other} archived non-finished)" if arch_other else "(no tasks)")
        lines.append("")
        return lines, 0, 0

    # Blocked phase collapsing: zero actionable, >5 non-actionable.
    non_actionable = [t for t in open_tasks if t.get("status") in {"Blocked", "Broken Down"}]
    if open_tasks and not any(t.get("status") in ACTIONABLE for t in open_tasks) and len(non_actionable) > 5:
        summary = phase_blockers(non_actionable, finished_ids, prev_phase)
        lines.append(f"⏳ {len(non_actionable)} tasks awaiting upstream — {summary}")
        lines.append("")
        return lines, done, total

    lines.append("| ID | Title | Status | Diff | Owner | Deps |")
    lines.append("|----|-------|--------|------|-------|------|")
    # Summarize the finished portion when >10 finished (display rule) OR when
    # archived finished exist (their rows are gone; counts must not look partial).
    summarize_finished = len(finished) > 10 or entry["arch_finished"] > 0
    rows = [t for t in tasks if t.get("status") != "Finished"] if summarize_finished else tasks
    for task in sorted(rows, key=lambda t: numeric_key(t.get("id"))):
        lines.append(task_row(task))
    lines.append("")
    if summarize_finished and done:
        lines.insert(2, f"✅ {done} tasks finished{note}")
        lines.insert(3, "")
    pct = round(100 * done / total) if total else 0
    qualifier = qualifier_line(open_tasks)
    footer = f"*Phase {key}: {done}/{total} complete ({pct}%)" if key != "?" else \
             f"*Unphased: {done}/{total} complete ({pct}%)"
    footer += f" — {qualifier}*" if qualifier else "*"
    lines.append(footer)
    lines.append("")
    return lines, done, total


def render_tasks_section(active, archived=None):
    archived = archived or []
    phases = build_phases(active, archived)
    out = ["## 📋 Tasks", ""]
    total_done = total_all = 0
    ordered = sorted(phases.keys(), key=lambda k: (k == "?", numeric_key(k)))
    finished_ids = {str(t.get("id")) for t in active if t.get("status") == "Finished"}
    finished_ids |= {str(t.get("id")) for t in archived if t.get("status", "Finished") == "Finished"}
    for idx, key in enumerate(ordered):
        prev_phase = ordered[idx - 1] if idx > 0 else None
        lines, done, total = render_phase(key, phases[key], finished_ids, prev_phase)
        out.extend(lines)
        total_done += done
        total_all += total
    pct = round(100 * total_done / total_all) if total_all else 0
    out.append(f"*{total_done}/{total_all} tasks complete ({pct}%)*")
    out.append("")
    return "\n".join(out)


# -------------------------------------------------------- Progress section

def render_status_summary(active):
    if len(active) <= 20:
        return []
    counts = Counter(t.get("status", "Pending") for t in active)
    lines = ["| Status | Count |", "|--------|-------|"]
    for status in SUMMARY_STATUS_ORDER:
        if counts.get(status):
            lines.append(f"| {status} | {counts[status]} |")
    return lines + [""]


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
                and all(str(d) in resolved for d in t.get("decision_dependencies", []))]
    if eligible:
        ids = ", ".join(str(t.get("id")) for t in sorted(eligible, key=lambda t: numeric_key(t.get("id")))[:3])
        return f"Partially Actionable ({len(eligible)} eligible: {ids})"
    blockers = sorted({str(d) for t in open_tasks for d in t.get("decision_dependencies", [])
                       if str(d) not in resolved}, key=numeric_key)
    if blockers:
        return f"Blocked ({blockers[0]})"
    return "Blocked (awaiting prior phase)"


_GLOBAL_FINISHED = set()  # finished ids (active + archived), set by render_full


def render_phase_table(phases_model, decisions):
    lines = ["| Phase | Done | Total | Status |", "|-------|------|-------|--------|"]
    ordered = sorted(phases_model.keys(), key=lambda k: (k == "?", numeric_key(k)))
    all_complete_so_far = True
    for key in ordered:
        entry = phases_model[key]
        done, total, _ = phase_counts(entry)
        status = phase_status(key, entry, all_complete_so_far, decisions)
        if status != "Complete":
            all_complete_so_far = False
        label = "Unphased" if key == "?" else (f"Phase {key} — {entry['name']}" if entry["name"] else f"Phase {key}")
        lines.append(f"| {esc(label)} | {done} | {total} | {esc(status)} |")
    return lines + [""]


def render_acceptance_criteria(verification_result):
    if not verification_result:
        return []
    criteria = verification_result.get("criteria")
    passed = verification_result.get("criteria_passed")
    failed = verification_result.get("criteria_failed")
    lines = ["### Acceptance Criteria", ""]
    if isinstance(criteria, list) and criteria:
        for c in criteria:
            box = "x" if c.get("status") == "pass" else " "
            note = str(c.get("notes", "")).strip()
            note = f" — *{note[:60]}*" if note else ""
            lines.append(f"- [{box}] {c.get('criterion', '(unnamed)')}{note}")
        p = sum(1 for c in criteria if c.get("status") == "pass")
        lines += ["", f"**{p}/{len(criteria)} criteria passed**", ""]
        return lines
    if passed is not None and failed is not None:
        return lines + [f"**{passed}/{passed + failed} criteria passed**", ""]
    return []


def render_timeline(active, now):
    rows = []
    today = now.date()
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
        return []
    lines = ["### Timeline", "", "| Date | Item | Status | Notes |", "|------|------|--------|-------|"]
    for date_s, item, status, note in sorted(rows, key=lambda r: (r[0], r[1])):
        overdue = False
        try:
            overdue = datetime.strptime(date_s, "%Y-%m-%d").date() < today
        except ValueError:
            pass
        date_cell = f"~~{date_s}~~" if overdue else date_s
        item_cell = f"⚠️ OVERDUE: {item}" if overdue else item
        lines.append(f"| {date_cell} | {esc(item_cell)} | {esc(status)} | {esc(note)} |")
    return lines + [""]


# ------------------------------------------------- critical path + mermaid

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
        for d in t.get("decision_dependencies", []):
            d = str(d)
            if d not in resolved:
                nodes.setdefault(f"D{d}", {"kind": "decision", "id": d})
                edges.setdefault(f"D{d}", set()).add(f"T{tid}")
        for dep in t.get("dependencies", []):
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


def node_label(node_key, nodes):
    info = nodes[node_key]
    if info["kind"] == "decision":
        return f"❗ Resolve {info['id']}"
    t = info["task"]
    return f"{OWNER_EMOJI.get(t.get('owner', 'claude'), '🤖')} {t.get('title', '')}"


def reaches(start, target, edges, limit=2000):
    seen, stack = set(), [start]
    while stack and len(seen) < limit:
        n = stack.pop()
        if n == target:
            return True
        if n in seen:
            continue
        seen.add(n)
        stack.extend(edges.get(n, []))
    return False


def render_critical_path(active, decisions, verification_result):
    nodes, edges = build_graph(active, decisions)
    if not nodes:
        vr_pass = bool(verification_result) and verification_result.get("result") == "pass"
        if vr_pass:
            return "**Critical path:** All tasks complete! ✓"
        return "**Critical path:** 🤖 Phase verification → Done *(1 step)*"
    path = longest_path(nodes, edges)
    if path is None:
        return "**Critical path:** unavailable (dependency cycle detected — run /health-check)"
    if not edges:
        return "**Critical path:** All tasks can start now"
    steps, rendered, i = [], set(), 0
    while i < len(path):
        n = path[i]
        nxt = path[i + 1] if i + 1 < len(path) else None
        branch_heads = []
        if nxt is not None:
            for s in edges.get(n, []):
                if s != nxt and s not in path and reaches(s, nxt, edges):
                    branch_heads.append(s)
        steps.append(node_label(n, nodes))
        rendered.add(n)
        if branch_heads:
            members = [nxt] + branch_heads
            if len(members) > 3:
                steps.append(f"[🤖 {len(members)} parallel tasks]")
            else:
                steps.append("[" + " | ".join(node_label(m, nodes) for m in members) + "]")
            rendered.update(members)
            i += 2
        else:
            i += 1
    count = len(rendered)
    if len(steps) > 5:
        shown = " → ".join(steps[:3])
        return f"**Critical path:** {shown} → ... {len(steps) - 3} more → Done *({count} steps)*"
    if count == 1:
        return f"**Critical path:** {steps[0]} → Done *(1 step)*"
    return f"**Critical path:** {' → '.join(steps)} → Done *({count} steps)*"


def mermaid_id(node_key):
    return re.sub(r"[^A-Za-z0-9_]", "_", node_key)


def render_mermaid(active, archived, decisions, phases_model, sidecar):
    nodes, edges = build_graph(active, decisions)
    task_nodes = [k for k, v in nodes.items() if v["kind"] == "task"]
    if len(task_nodes) < 4:
        return []
    lines = ["### Project Overview", "", "```mermaid", "graph LR"]
    note = None
    if len(task_nodes) > 15:
        path = longest_path(nodes, edges) or []
        keep = set(path)
        for n in path:
            for src, succs in edges.items():
                if n in succs:
                    keep.add(src)
            keep.update(edges.get(n, []))
        omitted = len(task_nodes) - len([k for k in keep if nodes.get(k, {}).get("kind") == "task"])
        nodes = {k: v for k, v in nodes.items() if k in keep}
        edges = {k: [s for s in v if s in keep] for k, v in edges.items() if k in keep}
        note = f"*Showing critical path only — {omitted} additional tasks omitted*"

    ordered = sorted(phases_model.keys(), key=lambda k: (k == "?", numeric_key(k)))
    classes = {"done": [], "active": [], "human": [], "blocked": []}
    emitted = []

    # Completed phases -> single P-nodes, emitted LAZILY: only phases that an
    # edge actually references render (47 disconnected done-nodes is noise —
    # the rules' intent is "keep the diagram focused on remaining work").
    finished_map, phase_labels = {}, {}
    for key in ordered:
        entry = phases_model[key]
        done, total, _ = phase_counts(entry)
        open_tasks = [t for t in entry["active"] if t.get("status") not in {"Finished", "Absorbed"}]
        if total and not open_tasks and key != "?":
            pid = f"P{mermaid_id(key)}"
            phase_labels[pid] = (f"✅ Phase {key} — {entry['name']} ({done}/{total})"
                                 if entry["name"] else f"✅ Phase {key} ({done}/{total})")
            for t in entry["active"]:
                if t.get("status") == "Finished":
                    finished_map[str(t.get("id"))] = pid
    for t in archived:
        if t.get("status", "Finished") == "Finished":
            pid = f"P{mermaid_id(phase_key_of(t))}"
            if pid in phase_labels:
                finished_map[str(t.get("id"))] = pid
    # Finished tasks in ACTIVE phases fold away: map to their predecessors later
    finished_in_active = {str(t.get("id")) for t in active if t.get("status") == "Finished"
                          and str(t.get("id")) not in finished_map}

    def resolve_dep(dep):
        dep = str(dep)
        if f"T{dep}" in nodes:
            return [f"T{dep}"]
        if dep in finished_map:
            return [finished_map[dep]]
        if dep in finished_in_active:
            src_task = next((t for t in active if str(t.get("id")) == dep), None)
            out = []
            for d in (src_task or {}).get("dependencies", []):
                out.extend(resolve_dep(d))
            return out
        return []

    edge_lines, seen_edges = [], set()
    for key, info in sorted(nodes.items(), key=lambda kv: numeric_key(kv[0])):
        mid = mermaid_id(key)
        if info["kind"] == "decision":
            emitted.append(f'    {mid}{{"❓ {info["id"]}"}}')  # diamonds carry no class (golden example)
            continue
        t = info["task"]
        label = f"{OWNER_EMOJI.get(t.get('owner', 'claude'), '🤖')} {t.get('title', '')[:60]}"
        emitted.append(f'    {mid}["{label}"]')
        owner = t.get("owner", "claude")
        if owner == "human":
            classes["human"].append(mid)
        elif t.get("status") == "In Progress":
            classes["active"].append(mid)
        else:
            classes["blocked"].append(mid)
        for dep in t.get("dependencies", []):
            for src in resolve_dep(dep):
                e = f"    {src} --> {mid}"
                if e not in seen_edges:
                    seen_edges.add(e)
                    edge_lines.append(e)
        for d in t.get("decision_dependencies", []):
            d = str(d)
            if f"D{d}" in nodes:
                e = f"    {mermaid_id('D' + d)} --> {mid}"
                if e not in seen_edges:
                    seen_edges.add(e)
                    edge_lines.append(e)

    used_pids = sorted({e.strip().split(" --> ")[0] for e in edge_lines
                        if e.strip().split(" --> ")[0] in phase_labels}, key=numeric_key)
    classes["done"].extend(used_pids)
    emitted = [f'    {pid}["{phase_labels[pid]}"]' for pid in used_pids] + emitted
    lines.extend(emitted)
    lines.extend(edge_lines)
    lines.append("")
    lines.append("    classDef done fill:#c8e6c9,stroke:#2e7d32")
    lines.append("    classDef active fill:#bbdefb,stroke:#1565c0")
    lines.append("    classDef human fill:#fff9c4,stroke:#f57f17")
    lines.append("    classDef blocked fill:#f5f5f5,stroke:#9e9e9e")
    for cls in ["done", "human", "active", "blocked"]:
        members = sorted(set(classes[cls]), key=numeric_key)
        if members:
            lines.append(f"    class {','.join(members)} {cls}")
    lines.append("```")
    if note:
        lines += ["", note]
    return lines + [""]


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


def render_this_week(active, now):
    completed, started, created = week_activity(active, now)
    if not (completed or started or created):
        return []
    return [f"**This week:** {len(completed)} completed · {len(started)} started · {len(created)} created", ""]


def render_recent_activity(active, now):
    completed, started, _ = week_activity(active, now)
    entries = [(d, t, "Finished") for d, t in completed] + [(d, t, "Started") for d, t in started]
    if len(entries) < 3:
        return []
    entries.sort(key=lambda e: (e[0], numeric_key(e[1].get("id"))), reverse=True)
    lines = ["### Recent Activity", ""]
    for d, t, verb in entries[:7]:
        lines.append(f"- **{d.isoformat()}** — Task {t.get('id')} — {verb}: {str(t.get('title', ''))[:60]}")
    return lines + [""]


# -------------------------------------------------------- Decisions section

DECISION_STATUS_DISPLAY = {"approved": "Decided", "implemented": "Decided",
                           "draft": "Pending", "proposed": "Pending",
                           "superseded": "Superseded",
                           "partially_superseded": "Partially Superseded"}


def render_decisions_section(decisions):
    out = ["## 📋 Decisions", ""]
    if not decisions:
        return "\n".join(out + ["*No decisions yet.*", ""])
    out += ["| ID | Decision | Status | Selected |", "|----|----------|--------|----------|"]
    for d in sorted(decisions, key=lambda d: numeric_key(d["id"])):
        display = DECISION_STATUS_DISPLAY.get(d["status"], d["status"].title())
        href = f"support/decisions/{d['file']}"
        text = d["selected"] if (display == "Decided" and d["selected"]) else \
               ("Decided" if display == "Decided" else display)
        out.append(f"| {esc(d['id'])} | {esc(d['title'])} | {display} | [{esc(text)}]({href}) |")
    return "\n".join(out + [""])


# ------------------------------------------------------------- assembly

def canonical_task_hash(active):
    rows = sorted(f"{t.get('id')}:{t.get('status')}:{t.get('difficulty')}:{t.get('owner')}"
                  for t in active)
    return "sha256:" + hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()


def render_meta(active, decisions, spec, version, drift, verification_result, now):
    debt = sum(1 for t in active if t.get("status") == "Finished"
               and (t.get("task_verification") or {}).get("result") != "pass")
    debt += sum(1 for t in active if t.get("status") == "Awaiting Verification")
    counts = Counter(d["status"] for d in decisions)
    drift_count = len(drift.get("deferrals", drift) if isinstance(drift, (dict, list)) else []) if drift else 0
    return "\n".join([
        "<!-- DASHBOARD META",
        f"generated: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"task_count: {len(active)}",
        f"task_hash: {canonical_task_hash(active)}",
        f"spec_version: {spec['version']}",
        f"spec_status: {spec['status']}",
        f"spec_fingerprint: {spec['fingerprint']}",
        f"template_version: {version.get('template_version', '—')}",
        f"verification_debt: {debt}",
        f"drift_deferrals: {drift_count}",
        f"decision_count: {len(decisions)}",
        f"decisions_approved: {counts.get('approved', 0) + counts.get('implemented', 0)}",
        f"decisions_superseded: {counts.get('superseded', 0)}",
        f"decisions_partially_superseded: {counts.get('partially_superseded', 0)}",
        "-->",
    ])


def render_toggles(toggles):
    lines = ["<details><summary><strong>Sections</strong></summary>", "", "<!-- SECTION TOGGLES -->"]
    for key, label in TOGGLE_ORDER:
        box = "x" if toggles.get(key, key != "custom_views") else " "
        lines.append(f"- [{box}] {label}")
    lines += ["<!-- END SECTION TOGGLES -->", "", "</details>"]
    return "\n".join(lines)


def render_header_lines(active, archived, decisions, spec, now):
    title = spec.get("title") or "Project"
    countable = [t for t in active if t.get("status") != "Absorbed"] \
        + [t for t in archived if t.get("status", "Finished") == "Finished"]
    done = sum(1 for t in countable if t.get("status", "Finished") == "Finished")
    total = len(countable)
    if not active and not archived:
        stage = "Spec"
    elif done == total:
        stage = "Complete"
    else:
        stage = "Execute"
    dates = sorted(d for d in (parse_date(t.get("created_date")) for t in active + archived) if d)
    started = f" · Started {dates[0].isoformat()}" if dates else ""
    pct = round(100 * done / total) if total else 0
    return "\n".join([
        f"**{title}** · {stage}{started}",
        "",
        f"**{pct}% complete** — {len(active)} tasks · {len(decisions)} decisions",
        "",
        f"*Updated {now.strftime('%Y-%m-%d %H:%M')} — may not reflect changes made outside `/work`*",
    ])


def render_progress_section(active, archived, decisions, phases_model, verification_result, now, sidecar):
    parts = ["## 📊 Progress", ""]
    parts += render_status_summary(active)
    parts += render_phase_table(phases_model, decisions)
    parts += render_acceptance_criteria(verification_result)
    parts += render_timeline(active, now)
    parts.append(render_critical_path(active, decisions, verification_result))
    parts.append("")
    parts += render_mermaid(active, archived, decisions, phases_model, sidecar)
    parts += render_this_week(active, now)
    parts += render_recent_activity(active, now)
    while parts and parts[-1] == "":
        parts.pop()
    return "\n".join(parts) + "\n"


def render_full(claude_dir: Path, now: datetime):
    global _GLOBAL_FINISHED
    tasks_dir = claude_dir / "tasks"
    active = load_tasks(tasks_dir) if tasks_dir.is_dir() else []
    archived = load_archived(tasks_dir) if tasks_dir.is_dir() else []
    decisions = load_decisions(claude_dir / "support" / "decisions")
    sidecar = load_json_file(claude_dir / "dashboard-state.json") or {}
    version = load_json_file(claude_dir / "version.json") or {}
    verification_result = load_json_file(claude_dir / "verification-result.json")
    drift = load_json_file(claude_dir / "drift-deferrals.json")
    spec = load_spec(claude_dir)
    _GLOBAL_FINISHED = {str(t.get("id")) for t in active if t.get("status") == "Finished"} | \
                       {str(t.get("id")) for t in archived if t.get("status", "Finished") == "Finished"}
    phases_model = build_phases(active, archived)
    toggles = sidecar.get("section_toggles", {})

    blocks = ["# Dashboard", "",
              render_meta(active, decisions, spec, version, drift, verification_result, now), "",
              render_toggles(toggles), "",
              render_header_lines(active, archived, decisions, spec, now), "",
              "---", ""]

    if toggles.get("action_required", True):
        blocks += ["## 🚨 Action Required", "",
                   "<!-- CLAUDE: fill — Action Required per dashboard-regeneration.md"
                   " § Action Item Contract (incl. human-gated coverage) + § Section Display Rules."
                   " Sub-section order: Phase Transitions, Verification Pending, Verification Debt,"
                   " Spec Drift, Audit Findings, Feedback, Decisions, Your Tasks, Reviews."
                   " Omit empty sub-sections. -->", "",
                   "---", ""]
    if toggles.get("progress", True):
        blocks += [render_progress_section(active, archived, decisions, phases_model,
                                           verification_result, now, sidecar), "---", ""]
    if toggles.get("tasks", True):
        blocks += [render_tasks_section(active, archived), "---", ""]
    if toggles.get("decisions", True):
        blocks += [render_decisions_section(decisions), "---", ""]
    if toggles.get("custom_views", False):
        instructions = sidecar.get("custom_views_instructions", "")
        blocks += ["## 👁️ Custom Views", "",
                   "<!-- CUSTOM VIEWS INSTRUCTIONS -->", "",
                   instructions if instructions else "",
                   "", "<!-- END CUSTOM VIEWS INSTRUCTIONS -->", "",
                   "<!-- CLAUDE: fill — render one ### sub-section per bold-labeled instruction above -->",
                   "", "---", ""]
    # Notes: always preserved
    user_notes = sidecar.get("user_notes", "") or "[Your notes here — ideas, questions, reminders]"
    blocks += ["## 💡 Notes", "", "<!-- USER SECTION -->", "", user_notes, "",
               "<!-- END USER SECTION -->", ""]

    debt = sum(1 for t in active if t.get("status") == "Finished"
               and (t.get("task_verification") or {}).get("result") != "pass")
    drift_count = len(drift.get("deferrals", drift) if isinstance(drift, (dict, list)) else []) if drift else 0
    if debt or drift_count:
        indicator = f"⚠️ {drift_count} drift deferrals, {debt} verification debt"
    else:
        indicator = '[Spec aligned](# "0 drift deferrals, 0 verification debt")'
    blocks += ["---", f"*{now.strftime('%Y-%m-%d %H:%M')} UTC · {len(active)} tasks · {indicator}*"]
    return "\n".join(blocks) + "\n"


# ------------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(description="Deterministic dashboard renderer (Family C full port).")
    parser.add_argument("--tasks-section", action="store_true", help="render only the '## 📋 Tasks' section")
    parser.add_argument("--render", action="store_true", help="render the full dashboard markdown")
    parser.add_argument("--task-hash", action="store_true", help="print the canonical META task_hash and exit")
    parser.add_argument("--tasks-dir", default=".claude/tasks", help="task JSON directory (for --tasks-section/--task-hash)")
    parser.add_argument("--claude-dir", default=".claude", help="environment root (for --render)")
    parser.add_argument("--now", default=None, help="ISO timestamp for deterministic output (default: current UTC)")
    args = parser.parse_args(argv)

    modes = sum(bool(m) for m in (args.tasks_section, args.render, args.task_hash))
    if modes != 1:
        parser.print_usage(sys.stderr)
        print("error: exactly one of --tasks-section / --render / --task-hash is required", file=sys.stderr)
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

    if args.tasks_section:
        tasks_dir = Path(args.tasks_dir)
        if not tasks_dir.is_dir():
            print(f"error: tasks dir not found: {tasks_dir}", file=sys.stderr)
            return 2
        print(render_tasks_section(load_tasks(tasks_dir), load_archived(tasks_dir)))
        return 0

    claude_dir = Path(args.claude_dir)
    if not claude_dir.is_dir():
        print(f"error: claude dir not found: {claude_dir}", file=sys.stderr)
        return 2
    print(render_full(claude_dir, now), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
