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

### 2. Project Layout Check

Verify the project uses flat layout (app at repo root, recommended since template v2.0):

- Check for `package.json` (or equivalent project manifest) at the repo root
- Check that no `app/` subdirectory contains a separate `package.json` (subdirectory layout)

✓ Pass: App files at repo root (flat layout)
⚠ Warn: App appears to be in a subdirectory — see `.claude/support/reference/known-issues.md` KI-001 for potential framework tooling issues. The template works in both layouts, but flat layout avoids dev server and build tool friction.

### 3. `version.json` Configuration

Check that `.claude/version.json` exists and has a `template_repo` field pointing to the upstream template repository:
```json
{
  "template_repo": "https://github.com/TEMPLATE-OWNER/TEMPLATE-REPO"
}
```

This is the source repo for template sync (`/health-check` Part 5). It should point to the template origin, not the user's project repo.

✓ Pass: File exists with a `template_repo` value
⚠ Warn: File missing or `template_repo` is empty

### 4. External CLI Tools

Scan the spec and (if present) `./CLAUDE.md` for signals that the project integrates with external services. When a signal matches, check whether the corresponding CLI is on `PATH` — warn if missing.

| Spec signal (keywords, case-insensitive) | Recommended CLI | Install (macOS) | Install (Linux) |
|------------------------------------------|-----------------|-----------------|-----------------|
| `github`, `pull request`, `PR`, `gh issue`, `gh.com` | `gh` | `brew install gh` | `sudo apt install gh` or see cli.github.com |
| `aws`, `s3://`, `lambda`, `ec2`, `cloudformation` | `aws` | `brew install awscli` | `pip install awscli` or AWS installer |
| `gcp`, `google cloud`, `gcs://`, `cloud run`, `bigquery` | `gcloud` | `brew install --cask google-cloud-sdk` | see cloud.google.com/sdk/docs/install |
| `sentry`, `error tracking` (when release tagging is implied) | `sentry-cli` | `brew install getsentry/tools/sentry-cli` | `curl -sL https://sentry.io/get-cli/ \| bash` |
| `vercel deploy`, `vercel env`, `v0.dev` | `vercel` | `npm install -g vercel` | `npm install -g vercel` |
| `netlify deploy`, `netlify build` | `netlify` | `npm install -g netlify-cli` | `npm install -g netlify-cli` |

**How to check presence:** `command -v <cli> >/dev/null 2>&1` (shell-builtin, works in bash/zsh/sh). If the check returns non-zero for a matched signal, emit a warning row.

**Signal detection scope:** Read the spec's stated integrations, dependencies, and acceptance criteria. Do NOT infer from generic mentions — a spec that says "authenticate with GitHub OAuth" is a `gh` signal only if PR/issue/release operations are also in scope. When ambiguous, emit the warning anyway — a false positive here is cheaper than a mid-implementation friction.

✓ Pass: No external-service signals detected, OR all matched signals have their CLI on `PATH`
⚠ Warn: One or more matched signals missing a CLI — list each with the install command

**Why this check exists:** Authenticated CLI tools return structured data with fewer rate-limit issues than unauthenticated API calls. When spec work depends on (for example) reading GitHub issues or uploading to S3, having the CLI installed and authenticated at decomposition time prevents mid-implementation context loss from repeated unauthenticated failures.

## Output

Report results inline during decomposition as a brief summary block:

```
Setup check:
  ✓ CLAUDE.md customized
  ✓ Flat layout
  ⚠ version.json — file missing
  ⚠ CLI tools — `gh` missing (spec mentions GitHub PRs); install: brew install gh
```

CLI-tool warnings are advisory — decomposition proceeds. The user installs flagged tools when convenient.

Continue with decomposition regardless of warnings.

## Optional Hooks

Hooks let you enforce structural rules at the harness level — running before or after every tool call. They live in `.claude/settings.local.json` (user-owned, gitignored) under the `hooks` key, so they're opt-in per project. The template does not ship hooks; the recipe below is documentation for users who want a copy-paste starting point.

### Block dev-server starts (frontend projects)

Long-running dev servers (`next dev`, `npm run dev`, etc.) are easy to start accidentally inside an agent loop and hard to terminate cleanly afterwards. A `PreToolUse` hook can hard-block them so you start the dev server yourself in a separate terminal.

Add to `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "jq -r '.tool_input.command // \"\"' | grep -qE '(npm|pnpm|yarn|bun)( run)? dev|next dev|vite( |$)' && { echo 'Dev server start blocked by PreToolUse hook in settings.local.json. Start it yourself in another terminal if needed.' >&2; exit 2; } || exit 0"
          }
        ]
      }
    ]
  }
}
```

**How it works:**
- `PreToolUse` fires before every Bash invocation; the JSON tool envelope (including `tool_input.command`) is piped to the hook on stdin.
- `jq` extracts the command string; `grep -qE` returns 0 if any dev-server pattern matches.
- On match: print to stderr and exit 2 — Claude Code treats exit 2 as a hard block and surfaces the message to the model. On no match: exit 0 and the Bash call proceeds.
- Requires `jq` on `PATH` (preinstalled on most Linux distros; `brew install jq` on macOS).

**Composition with `permissions.allow` and auto mode:**
- Hooks run **after** rule lookup and classifier evaluation — they're the final gate before execution. A `PreToolUse` hook can hard-block a command that `permissions.allow` or `--permission-mode auto` would otherwise approve.
- A `permissions.deny` rule short-circuits before the hook ever runs. Use `deny` for static blocks; use a hook when the decision needs runtime logic (parsing the actual command string, checking env vars, inspecting working-directory state).

**Customizing:**
- Adjust the regex to cover the package manager / framework / script names your project uses.
- For multi-pattern logic or several projects, lift the inline command into a script file (e.g., `scripts/hooks/block-dev-server.sh`) and reference its path in the `command` field — keeps `settings.local.json` readable.
- Other useful matchers: `Write` / `Edit` (guard specific paths), `WebFetch` (block external endpoints), or `*` (run for every tool).

See Claude Code's hooks documentation for the full event list (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, etc.) and matcher syntax.
