# Documents

User-provided reference files for the project.

## Purpose

Store external documents that the project references: PDFs, contracts, vendor quotes, design mockups, permits, research papers, or any file the user wants Claude to access during work.

## Convention

- Claude manages file placement — tell Claude where a file is (e.g., "check my Downloads for permit.pdf") and it will move it here with a descriptive filename
- Use descriptive filenames: `building-permit-application.pdf`, not `doc1.pdf`
- Subdirectories are fine for organization: `vendor/`, `legal/`, `research/`

## What Goes Here

| Type | Examples |
|------|----------|
| Reference docs | PDFs, contracts, technical specs |
| External deliverables | Permits, applications, forms |
| Research material | Papers, articles, vendor catalogs |
| Design assets | Mockups, wireframes, diagrams |

## What Doesn't Go Here

- Claude's working documents → `.claude/support/workspace/`
- Decision research → `.claude/support/decisions/.archive/`
- Vision documents → `.claude/vision/`
