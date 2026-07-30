---
id: DEC-007
title: Push-to-main Fabric deploy is dry-run by default; real publish gated behind workflow_dispatch + task-046
status: approved
category: process
created: 2026-07-30
decided: 2026-07-30
decided_by: implement-agent
recommended_by: implement-agent
recommendation_date: 2026-07-30
related:
  tasks: [task-045, task-046]
  decisions: []
implementation_anchors:
  - .github/workflows/deploy-fabric.yml
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# Push-to-main Fabric deploy is dry-run by default; real publish gated behind workflow_dispatch + task-046

## Select an Option

- [x] Option A: push-to-main dry-run by default; workflow_dispatch opts in to publish
- [ ] Option B: push-to-main publishes automatically
- [ ] Option C: workflow_dispatch only, no push trigger

## Background

task-045 authors the GitHub Actions workflow that deploys `fabric/` artifacts to the live Fabric workspace via `fabric-cicd`. That workspace (`99e4cc6d-…`) is the same one Erik edits continuously via the Fabric UI. The spec (§ Next Steps & Priorities → Phase 4) calls for "Deployment triggered on merge to main," and acceptance criterion 1 requires the workflow to "trigger on push to main and support manual dispatch." Criterion 4 additionally requires a dry-run mode that resolves and reports what would deploy without publishing. task-046 (owner: both) owns "the first live run" end-to-end validation. The task's own hazard note states the dry-run mode exists "so the first execution cannot clobber in-flight UI work."

The choice is what the push-to-main trigger actually does: publish immediately, dry-run, or not exist.

## Options Comparison

| Criteria | A: dry-run on push | B: publish on push | C: dispatch-only |
|----------|--------------------|--------------------|------------------|
| Satisfies "triggers on push to main" | Yes | Yes | No (fails criterion 1) |
| Protects Erik's in-flight UI edits | Yes | No — races UI work | Yes |
| Dry-run mode available | Yes (the push default) | Yes (separate input) | Yes |
| First live run stays human-gated (task-046) | Yes | No | Yes |
| Overall | Selected | Rejected | Rejected |

## Option Details

### Option A: push-to-main dry-run by default; workflow_dispatch opts in to publish

**Description:** `on.push.branches: [main]` always runs in dry-run (resolve + report, no publish). `workflow_dispatch` exposes `dry_run` and `publish` boolean inputs; only `publish: true` performs a real `fabric-cicd` publish. Flipping push-to-main to real publish is a one-line `EFFECTIVE_DRY_RUN` default change deferred to task-046.

**Strengths:**
- Satisfies acceptance criteria 1 and 4 literally.
- The automated pusher cannot clobber in-flight Fabric UI work before task-046 validates the deploy end-to-end.
- Real publish remains reachable without code change (manual dispatch).

**Weaknesses:**
- The spec's "Deployment triggered on merge to main" is met in staged form, not literally — merge triggers a dry-run, not a publish, until task-046 flips the default.
- Relies on a future one-line change to reach the spec's end state.

### Option B: push-to-main publishes automatically

**Description:** `on.push.branches: [main]` calls `publish_all_items` directly.

**Strengths:**
- Literally matches "deploys on merge to main."

**Weaknesses:**
- An automated pusher races Erik's concurrent Fabric UI edits — the hazard the task note explicitly calls out.
- Bypasses task-046's ownership of the first live run.

### Option C: workflow_dispatch only, no push trigger

**Description:** No `on.push`; deploys only via manual dispatch.

**Strengths:**
- Maximally safe.

**Weaknesses:**
- Fails acceptance criterion 1 ("triggers on push to main").

## Decision

**Selected:** Option A — push-to-main dry-run by default; workflow_dispatch opts in to publish.

**Rationale:**
The task's hazard note and task-046's ownership of the first live run make a safety gate mandatory. Criterion 1 requires a push trigger but does not require push to publish; criterion 4 requires a dry-run mode. Option A satisfies both while protecting the live workspace. The spec's "deployment on merge" end state is reached via a staged one-line default flip after task-046 validates, preserving the spec goal without exposing in-flight UI work to an automated clobber.

## Trade-offs

**Gaining:**
- A safe validation gate on every merge (resolve + report) that catches drift before any publish.
- Human-in-the-loop control of the first live publish.

**Giving Up:**
- True continuous deployment on merge until task-046 flips the default (an intentional, temporary trade).

## Impact

**Implementation Notes:**
Gating is enforced via `EFFECTIVE_DRY_RUN = (github.event_name == 'workflow_dispatch' && inputs.publish == true) ? false : true` in `deploy-fabric.yml`. The workflow header comment documents the Fabric → local → Update commit-ordering convention and the one-line change deferred to task-046.

**Affected Areas:**
- `.github/workflows/deploy-fabric.yml`
- Related tasks: task-045 (workflow), task-046 (first live run + secret config)

**Risks:**
- The spec line "Deployment triggered on merge to main" (§ Next Steps & Priorities) and the Phase 4 row "deploys Fabric artifacts on merge to main" now describe a staged target rather than the shipped interim behavior. If Erik wants the spec wording to reflect the staged gate explicitly, that is an `/iterate` follow-up — not a correctness defect, since the task acceptance criteria are met.