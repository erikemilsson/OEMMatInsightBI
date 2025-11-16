# Sync From Fabric Workspace

Pull latest changes from Microsoft Fabric workspace to local environment.

## What This Command Does

This command synchronizes Fabric artifacts to your local repository:
- **Notebooks** - Python/PySpark transformation logic
- **Pipelines** - Orchestration definitions
- **Dataflows** - Power Query M code
- **Semantic Model** - TMDL files (tables, relationships, measures)
- **Reports** - Power BI report definitions

**Use Case:** Pull changes made in Fabric UI to local environment for review, backup, or further development.

## Prerequisites

- Git integration configured in Fabric workspace (see project_definition.md lines 88-93)
- Local git repository cloned
- Fabric workspace access
- Git credentials configured

## Current Git Integration Status

Per project_definition.md line 993:
> "Git Status: The project is managed by a single developer. A formal branching strategy (e.g., GitFlow) is not currently implemented. Work is typically committed directly to the main branch synced with the Fabric workspace."

**Note:** Git integration with Fabric workspace needs verification. This command assumes git integration is configured.

## Method 1: Using Fabric Git Integration

If Fabric workspace is connected to Git:

### Step 1: Commit Changes in Fabric

1. Open Fabric workspace in browser
2. Navigate to workspace settings → Git integration
3. Review "Pending Changes" tab
4. See list of modified artifacts since last commit
5. Add commit message
6. Click "Commit" button
7. Changes are pushed to connected Git repository

### Step 2: Pull Changes Locally

```bash
# Navigate to project directory
cd /path/to/OEMMatInsightBI

# Pull latest changes from remote
git pull origin main

# Review changes
git log -5 --oneline
git diff HEAD~1 HEAD

# Check status
git status
```

Expected output:
```
Updating abc1234..def5678
Fast-forward
 fabric/silver-to-gold2.Notebook/notebook-content.py | 45 ++++++++++++++-
 fabric/semantic_model_oeminsightbi.SemanticModel/definition/measures.tmdl | 23 ++++++++
 2 files changed, 68 insertions(+), 5 deletions(-)
```

## Method 2: Manual Export (No Git Integration)

If Git integration not configured, manually export artifacts:

### Export Notebooks

1. Open notebook in Fabric workspace
2. Click "..." menu → "Export" → "Notebook file (.ipynb)"
3. Save to `/fabric/[NotebookName].Notebook/`
4. Convert to `.py` format if needed:
   ```bash
   jupyter nbconvert --to python notebook.ipynb
   mv notebook.py notebook-content.py
   ```

### Export Pipeline Definitions

1. Open pipeline in Fabric workspace
2. Click "..." menu → "View JSON"
3. Copy JSON content
4. Save to `/fabric/[PipelineName].DataPipeline/pipeline-content.json`

### Export Semantic Model (TMDL)

1. Open semantic model in Fabric
2. Use "Save as" feature or external tools (Tabular Editor)
3. Export as TMDL format
4. Save to `/fabric/semantic_model_oeminsightbi.SemanticModel/definition/`

### Commit Manual Changes

```bash
# Stage all fabric changes
git add fabric/

# Create commit
git commit -m "Sync from Fabric workspace - [describe changes]"

# Push to remote
git push origin main
```

## Method 3: Using Claude Code Workflow (Morning Sync)

Per project_definition.md lines 997-1001, the desired workflow:

**Morning (Claude Code):**
1. Pull latest from Git → **This command**
2. Sync Fabric state (read exported metadata)
3. Review tasks
4. Develop locally
5. Push changes to feature branch

**Implementation:**

```bash
#!/bin/bash
# Morning sync script

echo "=== Morning Fabric Sync ==="

# 1. Pull latest from Git
echo "\n[1/4] Pulling latest from Git..."
git pull origin main

# 2. Check for Fabric exports
echo "\n[2/4] Checking for Fabric exports..."
if [ -d "fabric/" ]; then
    echo "✓ Fabric artifacts found: $(ls -1 fabric/ | wc -l) directories"
else
    echo "✗ No fabric/ directory found"
fi

# 3. Review recent changes
echo "\n[3/4] Recent changes:"
git log -3 --oneline --decorate

# 4. Check working directory status
echo "\n[4/4] Working directory status:"
git status --short

echo "\n✓ Sync complete! Ready for development."
```

Save as `.claude/scripts/morning-sync.sh` and run:
```bash
bash .claude/scripts/morning-sync.sh
```

## Verify Sync Success

After sync, verify artifacts are up-to-date:

```bash
# List all Fabric artifacts by last modified time
find fabric/ -name "*.py" -o -name "*.json" -o -name "*.tmdl" | \
  xargs ls -lht | head -20

# Check for uncommitted changes (should be clean after pull)
git status

# View diff of latest changes
git diff HEAD~1 HEAD --stat
```

## Common Issues

**Issue: Merge Conflicts**
- Symptom: Git pull fails with merge conflict
- Cause: Local changes conflict with Fabric changes
- Resolution:
  ```bash
  # View conflicting files
  git status

  # Resolve conflicts manually, then:
  git add <resolved-files>
  git commit -m "Resolve merge conflicts from Fabric sync"
  ```

**Issue: Git Not Configured in Fabric**
- Symptom: No git integration option in Fabric workspace
- Cause: Workspace not connected to Git repo
- Resolution: Follow Fabric documentation to connect workspace to Azure DevOps or GitHub

**Issue: Files Out of Sync**
- Symptom: Local files don't match Fabric workspace
- Cause: Fabric changes not committed to Git
- Resolution: Ask Fabric admin to commit pending changes

**Issue: Large File Sizes**
- Symptom: Git pull is very slow or fails
- Cause: Binary files (Power BI .pbix) in repo
- Resolution: Use Git LFS for large files

## Best Practices

1. **Pull Before Starting Work:** Always sync before making local changes
2. **Review Changes:** Check `git log` to understand what changed
3. **Small Commits:** Commit frequently in Fabric for easier conflict resolution
4. **Branch Strategy:** Use feature branches for major changes (not implemented yet)
5. **Backup:** Git provides automatic backup of all artifacts

## Fabric-Specific Artifacts Synced

When properly configured, these artifacts sync automatically:

| Artifact Type | Location | File Type | Notes |
|---------------|----------|-----------|-------|
| Notebooks | `/fabric/*.Notebook/` | `.py` | PySpark transformation code |
| Pipelines | `/fabric/*.DataPipeline/` | `.json` | Pipeline orchestration |
| Dataflows | `/fabric/*.Dataflow/` | `.pq`, `.json` | Power Query M code |
| Semantic Models | `/fabric/*.SemanticModel/` | `.tmdl` | Table definitions, relationships, DAX |
| Reports | `/fabric/*.Report/` | `.json` | Power BI report layout (not .pbix) |
| Lakehouse | `/fabric/*.Lakehouse/` | `.json` | Metadata only (not data files) |
| Warehouse | `/fabric/*.Warehouse/` | `.sqlproj`, `.json` | Schema definitions |

**Note:** Data files (actual parquet/delta files) are NOT synced via Git - only metadata.

## Next Steps

After syncing from Fabric:
1. Review changes: `git log -5`
2. Test locally if notebooks changed
3. Update documentation if schemas changed
4. Make local changes and push back: `/sync-to-fabric`

## Related Files

- `/.claude/commands/sync-to-fabric.md` - Push local changes to Fabric
- `/project_definition.md` - Lines 979-1014 (Development Workflow)
- `/.claude/context/architecture/fabric_workspace.md`

## Related Tasks

- **Task**: Configure Git integration in Fabric workspace (if not already done)
- **Reference**: Fabric Git integration documentation
- **Desired State**: Automatic bi-directional sync between Fabric and Git
