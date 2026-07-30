---
id: DEC-008
title: Service Principal auth via azure-identity ClientSecretCredential (fabric-cicd has no own-auth layer)
status: approved
category: technology
created: 2026-07-30
decided: 2026-07-30
decided_by: implement-agent
recommended_by: implement-agent
recommendation_date: 2026-07-30
related:
  tasks: [task-045, task-043]
  decisions: []
implementation_anchors:
  - .github/workflows/deploy-fabric.yml
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# Service Principal auth via azure-identity ClientSecretCredential (fabric-cicd has no own-auth layer)

## Select an Option

- [x] Option A: azure-identity ClientSecretCredential
- [ ] Option B: a fabric-cicd-specific auth helper / env-var convention

## Background

task-045's workflow must authenticate to Fabric as the Service Principal registered in task-043, using GitHub repository secrets (never inline credentials). fabric-cicd 1.2.0 is installed locally, so the auth contract was verified against the actual `FabricWorkspace.__init__` signature and docstring rather than assumed.

## Options Comparison

| Criteria | A: ClientSecretCredential | B: fabric-cicd auth helper |
|----------|---------------------------|---------------------------|
| Matches installed fabric-cicd 1.2.0 API | Yes — `FabricWorkspace` takes `token_credential` | No — fabric-cicd exposes no own-auth layer |
| Uses standard secret convention | Yes (`AZURE_CLIENT_ID/SECRET/TENANT_ID`) | N/A |
| Overall | Selected | Rejected (does not exist) |

## Option Details

### Option A: azure-identity ClientSecretCredential

**Description:** The workflow exports `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` (and `FABRIC_WORKSPACE_ID`) from repository secrets to environment, constructs `azure.identity.ClientSecretCredential(tenant_id, client_id, client_secret)`, and passes it as `FabricWorkspace`'s `token_credential`.

**Strengths:**
- Verified against the installed library — `FabricWorkspace.__init__` documents `ClientSecretCredential` as the SP path.
- Standard `AZURE_*` secret naming; no inline credentials.

**Weaknesses:**
- Adds an `azure-identity` dependency (already a fabric-cicd transitive dep).

### Option B: a fabric-cicd-specific auth helper / env-var convention

**Description:** Use a fabric-cicd-native auth helper or env-var convention.

**Strengths:**
- None identified.

**Weaknesses:**
- fabric-cicd 1.2.0 exposes no such layer — option does not exist.

## Decision

**Selected:** Option A — azure-identity ClientSecretCredential.

**Rationale:**
Verified against the installed fabric-cicd 1.2.0 `FabricWorkspace.__init__` signature and docstring: it takes a `token_credential` and explicitly documents `ClientSecretCredential` as the Service Principal path. fabric-cicd has no own-auth layer, so Option B is not real.

## Trade-offs

**Gaining:**
- API-verified auth wiring; standard secret convention.

**Giving Up:**
- Nothing — Option B does not exist.

## Impact

**Implementation Notes:**
Secret names: `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, `FABRIC_WORKSPACE_ID`. These are configured in task-046 (owner: both). Dry-run still authenticates because resolving `$items.*.$id` requires reading the live workspace.

**Affected Areas:**
- `.github/workflows/deploy-fabric.yml`
- Related tasks: task-045 (workflow), task-043 (SP registration)

**Risks:**
- None beyond the standard secret-rotation hygiene.