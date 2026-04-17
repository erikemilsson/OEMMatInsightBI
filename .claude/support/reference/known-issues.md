# Known Issues and Advisories

Contextual advisories checked by `/work` Step 0 before relevant operations. Each entry describes an issue, when it applies, and the recommended workaround. Only matching entries are surfaced to the user.

---

## KI-001: Turbopack CSS Resolution Failure in Subdirectory Layouts

**Applies when:** Running `next dev` (without `--webpack`) in a Next.js 16+ project where the app lives in a subdirectory of the git repo root.

**Symptoms:** `Error: Can't resolve 'tailwindcss'`, 100% CPU usage, CSS `@import` resolving from wrong directory.

**Root cause:** Turbopack's hot reloader calculates `projectPath` as `path.relative(rootPath, projectPath) || '.'`. In subdirectory layouts, this produces `""` which falls back to `"."`, causing CSS imports to resolve from the parent directory where `node_modules` doesn't exist.

**Tracked in:** vercel/next.js#90307, vercel/next.js#92060 (both auto-closed by bot, not actually fixed).

**Workaround:** Use `next dev --webpack`. Set `"dev": "next dev --webpack"` in `package.json`.

**Note:** This issue only affects subdirectory layouts. Projects using the recommended flat layout (app at repo root, v2.0+) are not affected. If you're on a flat layout, this advisory can be ignored.

**Monitor:** Remove this entry when the Turbopack issues are resolved upstream.
