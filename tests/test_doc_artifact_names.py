"""Regression guard for the Fabric artifact-rename sweep (audit C-01 / task-021, 2026-06-21).

Three Fabric artifacts were renamed on disk, the spec was corrected each time, but the
surrounding docs kept the OLD names — most visibly the portfolio front door (README) and
the artifacts inventory, which even tagged non-existent artifacts "Active". task-021 swept
them. This test prevents recurrence on the recruiter-facing surfaces.

Renames (old -> new; new is canonical on disk):
  semantic_model_oeminsightbi      -> OEMInsightBI_v2
  clean_columnsAndHeaders.Notebook -> bronze-to-silver.Notebook
  bronze-to-silver.Notebook        -> bronze_to_silver.Notebook   (Phase 5, 2026-08-04)
  silver-to-gold2.Notebook         -> silver_to_gold.Notebook     (Phase 5, 2026-08-04)
  report.Report                    -> report2.Report

Phase 5 batch B (2026-08-05) additionally renamed three bronze lakehouse TABLES:
  bronze_EUSupplyShares            -> bronze_eu_supply_shares
  bronze_GlobalSupplyShares        -> bronze_global_supply_shares
  bronze_WGI                       -> bronze_wgi

`bronze_WGI` is DELIBERATELY NOT GUARDED, unlike the other two. The string is still
legitimately correct in two live contexts, so guarding it would fire on valid text:
  1. Historical ACTIVITY references. The pipeline activity was `bronze_WGI` before Phase 4
     snake-cased it to `bronze_wgi`; point-in-time design records (error_handling_strategy.md's
     2026-04-05 retry table) correctly retain the old activity name.
  2. The retired `WGI_file2table.Dataflow` contains a Power Query query literally named
     `bronze_WGI` (mashup.pq, queryMetadata.json), and incremental_load_strategy.md's
     "Historically the bronze Power Query dataflows (...)" sentence correctly names it.
The two SupplyShares names have no such dual meaning and are safe to guard.

Scope note: this guard only covers surfaces that have NO legitimate historical/example
occurrence of the old names. It deliberately does NOT cover:
  - docs/standards/naming_standards.md   (retains one legitimate
    `semantic_model_oeminsightbi` naming-convention example)
  - docs/architecture/fabric-artifacts-inventory.md           (L64 "Consider renaming" discussion)
  - fabric/archive/**, .claude/tasks/**, .claude/support/{audits,friction.jsonl,feedback/archive.md}
Adding a broad allowlist for those would make the guard fragile; keeping it to clean
surfaces keeps it robust.

FR-003 (resolved 2026-07-20): error_handling_strategy.md and incremental_load_strategy.md
were previously excluded because they used `clean_columnsAndHeaders` as a pipeline ACTIVITY
identifier. Grounding against pipeline-content.json showed no such activity ever existed —
the real one is `bronze_to_silver_cleaning`, referencing notebooks by GUID. Both files
were renamed accordingly and are now clean, so they are covered by this guard.

task-060 (2026-08-06) added a second, CLAIM-SCOPED guard below. See its own section comment
for why the file-scoped approach above cannot cover the performance documents.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# Old names that must never reappear on a clean surface.
# "report.Report" does not match "report2.Report" (the new name) as a substring.
OLD_NAMES = (
    "semantic_model_oeminsightbi",
    "clean_columnsAndHeaders",
    "report.Report",
    "bronze-to-silver",
    # `silver-to-gold` subsumes `silver-to-gold2` by substring; both are listed because
    # the pair documents the two-step rename history (see module docstring).
    "silver-to-gold",
    "silver-to-gold2",
    # Phase 5 batch B (2026-08-05) bronze table renames. `bronze_WGI` is intentionally
    # absent — see the module docstring for the two live contexts that still use it.
    "bronze_EUSupplyShares",
    "bronze_GlobalSupplyShares",
    # Added by task-060 (2026-08-06). Both were missing despite being pre-rename names;
    # probed first — neither fires on any CLEAN_SURFACE, so this is free hardening.
    # `bronze_EPI`/`bronze_WGI` still cannot be added here (legitimate historical
    # activity references on guarded surfaces) — they live in the claim-scoped set below.
    "bronzecopy_",
)

# Recruiter-facing / guide surfaces with no legitimate old-name occurrence.
CLEAN_SURFACES = (
    "README.md",
    "docs/README.md",
    "docs/portfolio/PORTFOLIO_ASSETS_README.md",
    "docs/guides/FAQ.md",
    "docs/setup/TROUBLESHOOTING.md",
    "docs/architecture/data-flow-diagram.md",
    # Cleaned by FR-003 (2026-07-20) — see module docstring.
    "docs/error_handling_strategy.md",
    "docs/incremental_load_strategy.md",
)


def _stale_hits(rel):
    path = REPO / rel
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return [name for name in OLD_NAMES if name in text]


@pytest.mark.parametrize("rel", CLEAN_SURFACES)
def test_no_stale_fabric_artifact_names(rel):
    hits = _stale_hits(rel)
    if hits is None:
        pytest.skip(f"{rel} not present")
    assert not hits, (
        f"{rel} reintroduced pre-rename Fabric artifact name(s): {hits}. "
        "Use OEMInsightBI_v2 / bronze_to_silver.Notebook / silver_to_gold.Notebook / report2.Report "
        "(audit C-01, task-021)."
    )


# ---------------------------------------------------------------------------
# CLAIM-SCOPED GUARD (task-060, 2026-08-06)
# ---------------------------------------------------------------------------
# The file-scoped guard above cannot cover docs/performance_baseline.md or
# docs/performance_optimized.md. Those documents are point-in-time measurement records
# from 2026-08-02/03, so they LEGITIMATELY contain pre-rename activity names in their
# measured rows — rewriting those rows would falsify the measurement. A blanket ban would
# therefore force a choice between a broken guard and a falsified document.
#
# What actually went wrong (the defect this guard exists to catch): performance_baseline.md
# asserted IN THE PRESENT TENSE that "Activity names below match the live pipeline / repo
# definition: silver-to-gold, bronze-to-silver data cleaning, bronze_EPI, bronze_WGI,
# bronzecopy_*". The Phase 5 snake_case rename (2026-08-04/05) renamed 8 of the 10
# activities and invalidated that sentence, while every measured row stayed correct.
#
# So the guard is scoped to the CLAIM, not the file: a sentence may name pre-rename
# activities freely, but not while asserting that those names match the live pipeline.
#
# Scoped to SENTENCES, not lines, deliberately. Markdown hard-wraps prose, so a
# line-scoped check would miss a claim whose stale name wrapped onto the next line —
# which is exactly the shape of the original defect.
#
# Note `bronze_WGI` and `bronze_EPI` ARE included here although `bronze_WGI` is
# deliberately absent from OLD_NAMES (see module docstring). There is no contradiction:
# the file-scoped guard must tolerate legitimate historical activity references and the
# retired dataflow's Power Query name, whereas a sentence claiming CURRENT fidelity is
# wrong no matter which old name it uses.

# Pre-rename pipeline ACTIVITY names -> current live names (verified 2026-08-06 against
# the live getDefinition payload: 10 activities). Substring match, so "silver-to-gold"
# also covers "silver-to-gold2" and "bronze-to-silver" covers
# "bronze-to-silver data cleaning".
STALE_ACTIVITY_NAMES = {
    "bronzecopy_": "bronze_copy_*",
    "bronze-to-silver": "bronze_to_silver_cleaning",
    "silver-to-gold": "silver_to_gold",
    "bronze_EPI": "bronze_epi",
    "bronze_WGI": "bronze_wgi",
}

# Phrases that make a sentence a present-tense fidelity claim about live/repo state.
FIDELITY_CLAIM_MARKERS = (
    "match the live",
    "matches the live",
    "match the repo",
    "matches the repo",
    "match the current",
    "matches the current",
    "no deploy drift",
    "identical to the live",
    "agree with the live",
)

# Phrases that mark a sentence as explicitly historical / dated, so naming a pre-rename
# activity in it is correct rather than stale.
# Kept deliberately NARROW. A bare "rename"/"renamed" was removed by task-060 review:
# it exempted the single most plausible future defect phrasing — "Activity names below
# match the live pipeline after the Phase 5 rename: `silver-to-gold`, ..." carries a
# fidelity marker and three stale names, yet the word "rename" alone would have waved it
# through. Neither marker was load-bearing (removing both yields zero new violations
# across every scanned surface), so the specific "pre-rename" / "predate" forms stay and
# the generic ones are gone. Resist re-adding a broad term here: every entry is a hole.
HISTORICAL_MARKERS = (
    "predate",
    "pre-rename",
    "no longer match",
    "did not match",
    "as measured",
    "as they were",
    "at the time",
    "point-in-time",
    "historical",
    "historically",
    "deliberately not rewritten",
    "was correct",
    "measurement date",
    "measurement time",
)

# Every prose surface that could carry such a claim.
CLAIM_SCOPED_SURFACES = tuple(
    sorted(
        str(p.relative_to(REPO))
        for p in list((REPO / "docs").rglob("*.md")) + [REPO / "README.md"]
        if p.exists() and "/archive/" not in str(p.relative_to(REPO))
    )
)


def _blocks_with_tables(text):
    """Split into prose blocks, each carrying any markdown table that follows it.

    Wrapped lines are joined so a sentence split across lines is evaluated whole.
    List items, headings and blank lines start new blocks so unrelated bullets never merge.

    A following table is ATTACHED to its preceding block rather than discarded, because a
    claim routinely governs the table beneath it rather than naming activities inline.
    That shape is not hypothetical either: the second pre-rename defect in
    performance_baseline.md was the heading "Live pipeline activity set (observed, 10
    activities)" plus "All 10 activities from the repo definition run in the live pipeline
    — no deploy drift.", with every stale name in the table below. A table-skipping
    version of this guard scored 0 violations against that instance.
    """
    blocks, buf, in_fence = [], [], False
    bullet = re.compile(r"^([-*+]|\d+[.)])\s")

    def flush():
        if buf:
            blocks.append([" ".join(buf), ""])
            buf.clear()

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("```"):
            in_fence = not in_fence
            flush()
            i += 1
            continue
        if in_fence:
            i += 1
            continue
        s = s.lstrip(">").strip()          # blockquote markers
        if s.startswith("|"):              # a table: consume it whole, attach to previous
            rows = []
            while i < len(lines):
                row = lines[i].strip().lstrip(">").strip()
                if not row.startswith("|"):
                    break
                rows.append(row)
                i += 1
            flush()                        # close prose BEFORE attaching
            if not blocks:
                blocks.append(["", ""])
            blocks[-1][1] += " " + " ".join(rows)
            continue
        if not s:                          # paragraph break
            flush()
            i += 1
            continue
        if bullet.match(s) or s.startswith("#"):
            flush()
        buf.append(s)
        i += 1
    flush()
    return blocks


def _claim_units(text):
    """Yield (sentence, haystack) — haystack adds the table the sentence's block governs."""
    for block, table in _blocks_with_tables(text):
        # Split on .!? ONLY — deliberately NOT on ':'. A colon introduces the list it
        # governs, so treating it as a terminator severs a claim from the very names it
        # claims about. That is not hypothetical: the original defect read
        # "...match the live pipeline / repo definition: `silver-to-gold`, ..." and a
        # colon-splitting version of this guard scored 0 violations against it.
        for sentence in re.split(r"(?<=[.!?])\s+", block):
            sentence = sentence.strip()
            if sentence:
                yield sentence, (sentence + " " + table)


def _claim_violations(rel):
    path = REPO / rel
    if not path.exists():
        return None
    bad = []
    for sentence, haystack in _claim_units(path.read_text(encoding="utf-8")):
        low = sentence.lower()
        if not any(m in low for m in FIDELITY_CLAIM_MARKERS):
            continue
        if any(m in low for m in HISTORICAL_MARKERS):
            continue
        stale = [old for old in STALE_ACTIVITY_NAMES if old in haystack]
        if stale:
            bad.append((sentence, stale))
    return bad


@pytest.mark.parametrize("rel", CLAIM_SCOPED_SURFACES)
def test_live_fidelity_claims_use_current_names(rel):
    """A sentence claiming names match the live pipeline must use current names.

    Historical occurrences stay legal — this fires only on a present-tense fidelity
    claim, which is what the Phase 5 rename actually invalidated.
    """
    violations = _claim_violations(rel)
    if violations is None:
        pytest.skip(f"{rel} not present")
    assert not violations, "\n".join(
        f"{rel} claims fidelity to the live pipeline while naming pre-rename "
        f"activities {stale} -> use {[STALE_ACTIVITY_NAMES[s] for s in stale]}.\n"
        f"  Sentence: {sentence!r}\n"
        "  If the sentence is a historical/point-in-time record, say so explicitly "
        f"(one of {HISTORICAL_MARKERS[:4]}...) so it reads honestly."
        for sentence, stale in violations
    )


def _fires(text):
    """True if the claim-scoped guard would flag anything in `text`."""
    for sentence, haystack in _claim_units(text):
        low = sentence.lower()
        if not any(m in low for m in FIDELITY_CLAIM_MARKERS):
            continue
        if any(m in low for m in HISTORICAL_MARKERS):
            continue
        if any(old in haystack for old in STALE_ACTIVITY_NAMES):
            return True
    return False


# Both real pre-rename defects, verbatim from the pre-fix docs/performance_baseline.md.
# Grounded in the REAL artifact, not paraphrased: a synthetic positive control passed
# while the guard scored 0 against the actual file (the colon bug), so the committed
# controls are the genuine text.
DEFECT_INLINE = (
    "- **Activity names** below match the live pipeline / repo definition: "
    "`silver-to-gold`, `bronze-to-silver data cleaning`, `bronze_EPI`, "
    "`bronze_WGI`, `bronzecopy_*`."
)
DEFECT_CLAIM_THEN_TABLE = """## Live pipeline activity set (observed, 10 activities)

All 10 activities from the repo definition run in the live pipeline — no deploy
drift. The 6 bronze activities start in parallel; silver and gold are sequential.

| Stage | Activities |
|-------|------------|
| Bronze | `bronzecopy_EUSupplyShares`, `bronze_EPI`, `bronze_WGI` |
| Silver | `bronze-to-silver data cleaning` |
| Gold | `silver-to-gold` |
"""

# A properly dated historical sentence. Note it DOES carry a fidelity marker
# ("no longer match the live") — otherwise the outer gate would reject it before the
# exemption list is ever consulted, and the control would prove nothing.
DATED_HISTORICAL = (
    "These names no longer match the live pipeline: `silver-to-gold`, `bronze_EPI` "
    "and `bronzecopy_*` are the names as they were on 2026-08-02."
)


@pytest.mark.parametrize(
    "label,text",
    [("inline", DEFECT_INLINE), ("claim-then-table", DEFECT_CLAIM_THEN_TABLE)],
)
def test_claim_guard_catches_the_real_defects(label, text):
    """Positive control: must fire on both real pre-rename defects.

    Without this, a guard that silently matched nothing would look identical to a
    passing one — which is exactly how the colon bug survived its first review.
    """
    assert _fires(text), (
        f"claim-scoped guard failed to flag the real {label} defect from "
        "performance_baseline.md — the guard is not actually guarding anything"
    )


def test_claim_guard_allows_dated_historical_naming():
    """Negative control: a dated historical claim with old names must NOT fire."""
    assert not _fires(DATED_HISTORICAL), (
        "guard is too aggressive — flagged a properly dated historical sentence"
    )


def test_negative_control_is_not_vacuous():
    """Mutation check: the negative control must exercise HISTORICAL_MARKERS.

    The first version of test_claim_guard_allows_dated_historical_naming passed even with
    HISTORICAL_MARKERS emptied, because its input carried no fidelity marker — so the
    outer gate, not the exemption, was doing the work. A negative control validated only
    by "it passes" is indistinguishable from one that tests nothing. This asserts the
    exemption is load-bearing: neutralise it and the control must flip to firing.
    """
    global HISTORICAL_MARKERS
    saved = HISTORICAL_MARKERS
    try:
        HISTORICAL_MARKERS = ()
        assert _fires(DATED_HISTORICAL), (
            "negative control is VACUOUS — with HISTORICAL_MARKERS emptied it still does "
            "not fire, so the exemption list is untested. Give DATED_HISTORICAL a "
            "fidelity-claim marker and a stale name so the exemption is what saves it."
        )
    finally:
        HISTORICAL_MARKERS = saved


def test_fidelity_markers_are_load_bearing():
    """Mutation check: emptying FIDELITY_CLAIM_MARKERS must break the positive control."""
    global FIDELITY_CLAIM_MARKERS
    saved = FIDELITY_CLAIM_MARKERS
    try:
        FIDELITY_CLAIM_MARKERS = ()
        assert not _fires(DEFECT_INLINE), (
            "FIDELITY_CLAIM_MARKERS is not load-bearing — the guard fires without it, "
            "so it is not actually claim-scoped"
        )
    finally:
        FIDELITY_CLAIM_MARKERS = saved


if __name__ == "__main__":
    # Standalone runner (no pytest dependency) for quick verification.
    failures = []
    for rel in CLEAN_SURFACES:
        hits = _stale_hits(rel)
        if hits is None:
            print(f"SKIP {rel} (not present)")
        elif hits:
            failures.append((rel, hits))
            print(f"FAIL {rel}: {hits}")
        else:
            print(f"PASS {rel}")
    for rel in CLAIM_SCOPED_SURFACES:
        viol = _claim_violations(rel)
        if viol:
            failures.append((rel, viol))
            print(f"FAIL (claim) {rel}: {[v[1] for v in viol]}")
    print(f"\n{len(CLAIM_SCOPED_SURFACES)} surfaces claim-scanned")
    raise SystemExit(1 if failures else 0)
