# Spec Readiness Guide

Defines "complete enough" for a specification to move to task decomposition.

## Core Questions

A spec is ready when you can answer these confidently:

| Question | Why It Matters |
|----------|----------------|
| What does this do and for whom? | Without this, you're building blind |
| What are the main components/parts? | Needed to break into tasks |
| What key decisions have been made? | Undecided architecture blocks work |
| How will you know it works? | No acceptance criteria = no definition of done |
| What's explicitly out of scope? | Prevents scope creep during implementation |

## Readiness Levels

### Not Ready
- Can't explain what it does in 2 minutes
- Major technical decisions unmade ("what database?" still open)
- No way to verify if it works
- Scope is fuzzy ("make it good")

### Ready for Work
- Problem and users are clear
- Core architecture decided
- Has testable acceptance criteria
- Remaining questions are implementation details

### Well-Defined
- All of the above, plus:
- Non-functional requirements have measurable targets
- Constraints and dependencies documented
- Acceptance criteria map to clear verification steps

## Calibrating to Project Seriousness

Not every project needs the same rigor:

| Project Type | Minimum Bar |
|--------------|-------------|
| Quick prototype | Problem clear, basic approach outlined |
| MVP / proof of concept | Above + key decisions made, basic acceptance criteria |
| Production system | Full "Ready for Work" criteria |
| Critical infrastructure | "Well-Defined" level |

The `/iterate` command asks about project seriousness early and calibrates accordingly.

## Red Flags

Watch for these regardless of project type:

- Placeholder text still present (`[TBD]`, `[describe here]`)
- Vague statements ("make it better", "should be fast")
- Requirements that are really tasks ("add login button")
- Decisions without rationale
- Acceptance criteria requiring subjective judgment ("looks good")

