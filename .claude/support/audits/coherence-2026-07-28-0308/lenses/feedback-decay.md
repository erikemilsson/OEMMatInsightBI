# Lens: feedback-decay

Findings: 1

## F-fee-01
- **Title:** FB-007 new and untriaged 44 days
- **Severity:** med
- **Source anchor:** .claude/support/feedback/feedback.md (FB-007)
- **Files affected (read-only):** .claude/support/feedback/feedback.md, .claude/support/audits/coherence-2026-07-28-0308/inputs/feedback-status.json
- **Files to touch (potential fix):** .claude/support/feedback/feedback.md
- **Evidence:** `{"id":"FB-007","status":"new","captured":"2026-06-14","title":": dashboard-render.py mermaid edge sources skip mermaid_id() sanitization","age_days":44}` — status is `new`, captured 2026-06-14, today 2026-07-28 (44 days).
- **What:** FB-007 has sat in `new` status for 44 days without a status change, past the 30-day decay threshold.
- **Why:** Untriaged feedback accumulates; a 30+ day `new` entry signals the feedback loop is not draining.
- **Suggested fix:** Triage FB-007 via /feedback review (see feedback.md § FB-007).
- **Suggested kind:** bundle-eligible