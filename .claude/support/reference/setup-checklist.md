# Setup Checklist

> **Read during decomposition.** `/work` runs these checks as the first step when decomposing a spec into tasks. Runs every decomposition but is most useful on the first one — subsequent decompositions (e.g., after a spec version bump) will typically pass all checks. Advisory only — warnings do not block decomposition.

## Checks

### 1. `.claude/CLAUDE.md` Customization

Look for unfilled template placeholders:
- `[bracketed text]` — unfilled placeholders (e.g., `[Brief description]`, `[Your license here]`)
- `<!-- DELETE EVERYTHING` — template markers
- `## Maintaining This Template` — template-specific section

✓ Pass: No placeholders found
⚠ Warn: Placeholders remain — list which ones

### 2. `version.json` Configuration

Check that `.claude/version.json` exists and has a `template_repo` field pointing to the upstream template repository:
```json
{
  "template_repo": "https://github.com/TEMPLATE-OWNER/TEMPLATE-REPO"
}
```

This is the source repo for template sync (`/health-check` Part 5). It should point to the template origin, not the user's project repo.

✓ Pass: File exists with a `template_repo` value
⚠ Warn: File missing or `template_repo` is empty

## Output

Report results inline during decomposition as a brief summary block:

```
Setup check:
  ✓ CLAUDE.md customized
  ⚠ version.json — file missing
```

Continue with decomposition regardless of warnings.
