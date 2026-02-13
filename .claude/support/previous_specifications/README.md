# Previous Specifications

This directory stores spec snapshots taken at task decomposition time.

## Purpose

When `/work` decomposes a specification into tasks, it saves a copy here with the naming convention:

```
spec_v{N}_decomposed.md
```

These snapshots enable:
- **Diff generation** - Show exactly what changed when spec drifts
- **Section comparison** - Compare current sections against decomposition-time sections
- **Audit trail** - Track how the spec evolved over time

## How It's Used

1. **At decomposition**: `/work` copies the current spec here
2. **At drift detection**: `/work` loads the snapshot to generate diffs
3. **In health check**: Validates that referenced snapshots exist

## File Naming

| File | Description |
|------|-------------|
| `spec_v1_decomposed.md` | Snapshot of spec_v1 when tasks were first created |
| `spec_v2_decomposed.md` | Snapshot of spec_v2 when tasks were re-decomposed |

## Cleanup

Old snapshots can be safely deleted if:
- All tasks have been re-decomposed against a newer spec
- You don't need historical diff capability

The system will fall back to full-spec comparison if a snapshot is missing.
