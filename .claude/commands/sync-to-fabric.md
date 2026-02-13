# Sync To Fabric Workspace

Push local changes from development environment to Microsoft Fabric workspace.

## What This Command Does

This command synchronizes local changes to the Fabric workspace:
- Push updated notebooks to Fabric
- Update pipeline definitions
- Sync dataflow changes (Power Query M code)
- Update semantic model definitions
- Commit changes to Git (which syncs to Fabric)

**Use Case:** Deploy local development work to Fabric workspace for testing with real data or sharing with team.

## Prerequisites

- Git integration configured in Fabric workspace
- Local changes committed to Git
- Fabric workspace access with write permissions
- No pending changes in Fabric (resolve conflicts first)

## Current Git Integration Status

Per project_definition.md line 993:
> "Work is typically committed directly to the main branch synced with the Fabric workspace."

**Workflow:** Commit locally → Push to Git → Fabric automatically syncs

## Method 1: Using Git Integration (Recommended)

### Step 1: Commit Local Changes

```bash
# Navigate to project directory
cd /path/to/OEMMatInsightBI

# Check status of changes
git status

# Stage changes
git add fabric/

# Or stage specific files
git add fabric/silver-to-gold2.Notebook/notebook-content.py
git add fabric/semantic_model_oeminsightbi.SemanticModel/definition/measures.tmdl

# Commit with descriptive message
git commit -m "Update gold transformation logic: add new alias mappings

- Added 10 new country aliases (encoding variants)
- Updated material grouping logic for rare earth elements
- Fixed spend calculation for edge case with null unit prices
"

# View commit
git log -1 --stat
```

### Step 2: Push to Remote Repository

```bash
# Push to main branch (current workflow)
git push origin main

# Or push to feature branch (recommended for larger changes)
git checkout -b feature/new-dax-measures
git push origin feature/new-dax-measures
```

### Step 3: Sync in Fabric Workspace

1. Open Fabric workspace in browser
2. Navigate to workspace settings → Git integration
3. Fabric detects new commits automatically
4. Click "Update from Git" or "Pull" button
5. Review changes to be applied
6. Click "Apply changes"
7. Fabric updates artifacts in workspace

**Sync Timeline:**
- Automatic check: Every 15 minutes (Fabric default)
- Manual trigger: Click "Update from Git" button
- Typical sync time: 30 seconds - 2 minutes

## Method 2: Manual Upload (No Git Integration)

If Git integration not available:

### Upload Notebook

1. Open Fabric workspace
2. Navigate to workspace items
3. Click "Upload" → "Notebook"
4. Select `.ipynb` file from `/fabric/[NotebookName].Notebook/`
5. Overwrite existing notebook

### Update Pipeline

1. Open pipeline in Fabric
2. Click "Edit" button
3. Copy JSON from `/fabric/[PipelineName].DataPipeline/pipeline-content.json`
4. Paste into pipeline JSON editor (if available)
5. Or manually recreate pipeline activities based on JSON
6. Save changes

### Update Semantic Model

1. Open semantic model in Power BI Desktop (connect to Fabric)
2. Update DAX measures from `/fabric/semantic_model_oeminsightbi.SemanticModel/definition/measures.tmdl`
3. Save changes
4. Publish to Fabric workspace

## Method 3: Using Claude Code Workflow (Evening Sync)

Per project_definition.md lines 1009-1013, the desired workflow:

**Evening (Claude Code):**
1. Pull latest (includes DQ reports from Fabric)
2. Sync state, review issues
3. Create tasks for problems
4. Plan next day
5. Push changes → **This command**

**Implementation:**

```bash
#!/bin/bash
# Evening sync script

echo "=== Evening Fabric Sync ==="

# 1. Ensure all changes are committed
echo "\n[1/5] Checking for uncommitted changes..."
if [[ -n $(git status -s) ]]; then
    echo "✗ Uncommitted changes found:"
    git status -s
    echo "\nCommit these changes first:"
    echo "  git add <files>"
    echo "  git commit -m \"<message>\""
    exit 1
else
    echo "✓ Working directory clean"
fi

# 2. Pull latest (in case of Fabric updates during the day)
echo "\n[2/5] Pulling latest from remote..."
git pull origin main

# 3. Push local commits
echo "\n[3/5] Pushing local commits..."
LOCAL_COMMITS=$(git log origin/main..HEAD --oneline | wc -l)
if [ $LOCAL_COMMITS -gt 0 ]; then
    echo "✓ Pushing $LOCAL_COMMITS commit(s)..."
    git push origin main
else
    echo "✓ No new commits to push"
fi

# 4. Wait for Fabric sync (if configured)
echo "\n[4/5] Waiting for Fabric workspace sync..."
echo "  (Check Fabric UI: Workspace → Git integration → Update from Git)"
echo "  Typical sync time: 30-60 seconds"

# 5. Summary
echo "\n[5/5] Sync Summary:"
git log -3 --oneline --decorate

echo "\n✓ Evening sync complete!"
echo "✓ Changes pushed to Git. Don't forget to sync Fabric workspace."
```

Save as `.claude/scripts/evening-sync.sh` and run:
```bash
bash .claude/scripts/evening-sync.sh
```

## Verify Sync Success

After pushing to Git and syncing Fabric:

### Check Git Status

```bash
# Verify push succeeded
git log origin/main --oneline -5

# Confirm local and remote are in sync
git status
# Should show: "Your branch is up to date with 'origin/main'"
```

### Check Fabric Workspace

1. Open Fabric workspace in browser
2. Check artifact "Last Modified" timestamps
3. Open updated artifacts to verify changes applied
4. Run pipeline/notebook to test changes

### Validate Changes in Fabric

```python
# In Fabric notebook, verify changes applied
# Example: Check if new function exists

def validate_deployment():
    """Verify local changes are reflected in Fabric"""
    print("Deployment Validation")
    print("=" * 60)

    # Check notebook version
    try:
        # If you added a new function, try importing it
        from my_new_function import calculate_something
        print("✓ New function deployed successfully")
    except ImportError:
        print("✗ New function not found - check deployment")

    # Check table schema
    try:
        df = spark.table("oem_lh.gold_dim_country")
        if "new_column" in df.columns:
            print("✓ Schema change deployed successfully")
        else:
            print("⚠ Schema change not found - may need to re-run transformation")
    except:
        print("✗ Table not accessible")

validate_deployment()
```

## Common Issues

**Issue: Push Rejected (Non-Fast-Forward)**
- Symptom: `git push` fails with "Updates were rejected"
- Cause: Remote has commits you don't have locally
- Resolution:
  ```bash
  # Pull remote changes first
  git pull origin main --rebase

  # Resolve any conflicts, then push
  git push origin main
  ```

**Issue: Fabric Not Syncing**
- Symptom: Changes pushed to Git but not appearing in Fabric
- Cause: Fabric workspace not pulling from Git
- Resolution:
  1. Open Fabric workspace → Git integration
  2. Click "Update from Git" manually
  3. Check for errors in sync log
  4. Verify branch configuration (main vs master)

**Issue: Merge Conflicts in Fabric**
- Symptom: Fabric shows "Conflicts" when syncing
- Cause: Local changes conflict with Fabric changes
- Resolution:
  1. Download Fabric version of conflicted files
  2. Merge manually in local environment
  3. Commit resolved version
  4. Push and sync again

**Issue: File Size Limits**
- Symptom: Push succeeds but file not synced to Fabric
- Cause: File exceeds Fabric size limits
- Resolution:
  - Notebooks: Max 10MB
  - Dataflows: Max 100MB
  - If exceeded, optimize file or split into multiple artifacts

## Git Commit Best Practices

**Good Commit Messages:**
```bash
# Good: Clear, specific, explains why
git commit -m "Add incremental load logic to procurement dataflow

- Implements @p_from_date parameter filtering
- Updates notebook to merge (not overwrite) silver tables
- Addresses Task 06: Implement Incremental Load"

# Bad: Vague, no context
git commit -m "updated files"
```

**Commit Frequency:**
- **Small commits:** After each logical change (preferred)
- **Medium commits:** At end of feature development
- **Large commits:** Avoid! Hard to review and debug

**What to Commit:**
```bash
# Do commit:
git add fabric/              # Fabric artifact definitions
git add .claude/             # Claude Code configuration
git add project_definition.md  # Project documentation
git add README.md

# Don't commit:
git add .venv/               # Python virtual environment
git add .DS_Store            # OS files
git add *.pyc                # Compiled Python
git add data/                # Local data files (use .gitignore)
```

## Branching Strategy (Future Enhancement)

Current: Direct commits to main
Recommended (for team collaboration):

```bash
# Create feature branch
git checkout -b feature/enhance-dq-dashboard

# Make changes, commit locally
git add .
git commit -m "Add DQ dashboard visualizations"

# Push feature branch
git push origin feature/enhance-dq-dashboard

# In Fabric: Create separate workspace for testing

# After testing, merge to main
git checkout main
git merge feature/enhance-dq-dashboard
git push origin main

# Sync production Fabric workspace from main
```

## Next Steps

After syncing to Fabric:
1. Test changes in Fabric with real data
2. Run pipeline to verify transformations
3. Check Power BI report for updated visuals
4. If issues found, fix locally and repeat sync
5. Document deployment in project_definition.md

## Related Files

- `/.claude/commands/sync-from-fabric.md` - Pull changes from Fabric
- `/project_definition.md` - Lines 979-1014 (Development Workflow)
- `/.gitignore` - Files excluded from Git
- `/.claude/support/documents/architecture/fabric_workspace.md`

## Troubleshooting Checklist

Before syncing:
- [ ] All changes committed locally (`git status` clean)
- [ ] Pulled latest from remote (no conflicts)
- [ ] Commit message is descriptive
- [ ] No sensitive data in commits (passwords, keys)
- [ ] Changes tested locally (if notebooks)

After syncing:
- [ ] Git push succeeded
- [ ] Fabric workspace updated from Git
- [ ] Artifacts showing correct "Last Modified" time
- [ ] Changes tested in Fabric with real data
- [ ] No errors in Fabric execution logs
