# Git Workflow - OEMMatInsightBI

## Current Workflow

**Status:** Single developer, direct commits to main branch

**Process:**
1. Make changes locally or in Fabric workspace
2. Commit to main branch with descriptive message
3. Push to remote repository
4. Fabric workspace syncs from Git (manual trigger)

## Branching Strategy

### Current (Simplified)
```
main (production)
  └─ Direct commits
```

### Recommended (Future - with team)
```
main (production)
  ├─ develop (integration branch)
  │   ├─ feature/task-01-dq-dashboard
  │   ├─ feature/task-02-dax-measures
  │   └─ bugfix/fix-unit-conversion
  └─ hotfix/critical-bug
```

## Commit Message Standards

### Format
```
<type>: <subject> (max 50 chars)

[Optional body with more details]

[Optional footer: references, breaking changes]
```

### Types
- **feat:** New feature
- **fix:** Bug fix
- **docs:** Documentation changes
- **refactor:** Code restructuring (no behavior change)
- **test:** Add or update tests
- **chore:** Maintenance (dependencies, config)
- **perf:** Performance improvements

### Examples

**Good:**
```
feat: Add incremental load to procurement dataflow

- Implements @p_from_date parameter filtering
- Updates notebook to merge instead of overwrite
- Addresses Task 06: Implement Incremental Load

Closes #6
```

**Bad:**
```
updated files
```

## Commit Frequency

**Recommended:**
- **After each logical change** (preferred)
- **At end of work session** (minimum)
- **Before switching tasks** (good practice)

**Avoid:**
- Massive commits with many unrelated changes
- Committing broken/non-functional code
- Committing sensitive data (passwords, keys)

## What to Commit

### ✓ Always Commit
```
.claude/                    # Claude Code configuration
fabric/                     # Fabric artifact definitions
azure/                      # SQL setup scripts
project_definition.md       # Project documentation
README.md                   # Setup instructions
.gitignore                  # Git exclusions
```

### ✗ Never Commit
```
.venv/                      # Python virtual environment
.DS_Store                   # macOS system files
*.pyc, __pycache__/         # Python compiled files
.env                        # Environment variables with secrets
*.log                       # Log files
data/                       # Data files (use .gitignore)
```

## Git Commands Reference

### Daily Workflow
```bash
# Morning: Pull latest
git pull origin main

# Make changes...

# Stage changes
git add .claude/tasks/01_enhance_data_quality.md
git add fabric/silver-to-gold2.Notebook/

# Commit with message
git commit -m "feat: Add country alias for Turkey encoding variants"

# Push to remote
git push origin main
```

### Viewing History
```bash
# View recent commits
git log --oneline -10

# View changes in last commit
git show HEAD

# View file history
git log --follow fabric/silver-to-gold2.Notebook/notebook-content.py
```

### Undoing Changes
```bash
# Unstage file (before commit)
git restore --staged <file>

# Discard local changes
git restore <file>

# Revert last commit (creates new commit)
git revert HEAD

# Amend last commit (only if not pushed!)
git commit --amend -m "Updated message"
```

### Branching (for future)
```bash
# Create and switch to new branch
git checkout -b feature/task-01-dq-dashboard

# List branches
git branch -a

# Switch branches
git checkout main

# Merge branch
git merge feature/task-01-dq-dashboard

# Delete branch
git branch -d feature/task-01-dq-dashboard
```

## Fabric Workspace Sync

### Fabric → Git (Export from Fabric)
1. Make changes in Fabric workspace
2. Navigate to: Workspace → Git integration
3. Review pending changes
4. Add commit message
5. Click "Commit" → Pushes to Git

### Git → Fabric (Import to Fabric)
1. Push changes to Git locally
2. Navigate to Fabric workspace
3. Workspace → Git integration
4. Click "Update from Git" or "Pull"
5. Review changes, click "Apply"

## Conflict Resolution

### When Conflicts Occur
```bash
# Pull with conflict
git pull origin main
# Error: Conflict in fabric/silver-to-gold2.Notebook/

# View conflicting files
git status

# Open file, resolve conflicts manually
# Look for markers: <<<<<<<, =======, >>>>>>>

# After resolving
git add fabric/silver-to-gold2.Notebook/
git commit -m "fix: Resolve merge conflict in silver-to-gold"
git push origin main
```

### Preventing Conflicts
- Pull before starting work
- Commit frequently
- Communicate with team (if applicable)
- Use separate branches for major changes

## .gitignore Best Practices

### Current .gitignore
```
# Python
.venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/settings.json
.idea/

# Data files (large)
data/*.csv
data/*.parquet
*.log

# Secrets
.env
credentials.json
```

## Pre-Commit Checklist

Before committing, verify:
- [ ] Code works (tested locally or in Fabric)
- [ ] No sensitive data (passwords, API keys)
- [ ] Commit message is descriptive
- [ ] Changes are related (not mixing features)
- [ ] Documentation updated if needed
- [ ] No large files (>10MB) unless necessary

## Tagging Releases

### Creating Tags
```bash
# Create annotated tag
git tag -a v1.0.0 -m "Release 1.0: Initial portfolio version"

# Push tag to remote
git push origin v1.0.0

# List tags
git tag -l
```

### Semantic Versioning
```
v1.0.0
│ │ │
│ │ └─ Patch (bug fixes)
│ └─── Minor (new features, backward compatible)
└───── Major (breaking changes)
```

## Troubleshooting

### Large File Rejected
```bash
# If file > 100MB
# Use Git LFS (Large File Storage)
git lfs install
git lfs track "*.pbix"
git add .gitattributes
git commit -m "chore: Enable Git LFS for Power BI files"
```

### Accidentally Committed Secret
```bash
# Remove from history (use with caution!)
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch path/to/secret-file' \
  --prune-empty --tag-name-filter cat -- --all

# Force push (dangerous!)
git push origin --force --all
```

### Diverged Branches
```bash
# If local and remote diverged
git fetch origin
git rebase origin/main
# Or merge instead
git merge origin/main
```

## Git Aliases (Optional)

Add to `~/.gitconfig`:
```ini
[alias]
    st = status
    co = checkout
    br = branch
    ci = commit
    unstage = restore --staged
    last = log -1 HEAD
    visual = log --graph --oneline --all
```

Usage:
```bash
git st        # Instead of git status
git co main   # Instead of git checkout main
git visual    # Pretty log graph
```

## Related Files
- `.gitignore` - File exclusion rules
- `/.claude/commands/sync-from-fabric.md` - Pull from Fabric
- `/.claude/commands/sync-to-fabric.md` - Push to Fabric
- `/project_definition.md` - Lines 979-1014 (Development Workflow)
