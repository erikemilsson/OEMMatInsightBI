# Git Hooks Directory

This directory contains git hook templates for automating task management workflows.

## Available Hooks (Templates)

### pre-commit-task-validation.sh
Validates that:
- Active task is in "In Progress" status
- Commit message references task ID (e.g., "[task-002] Implement core measures")
- No uncommitted task JSON changes

### post-commit-task-update.sh
Automatically:
- Updates task progress based on commit
- Runs `/sync-tasks` if task JSON files changed
- Adds commit to task notes

## Installation

Copy desired hooks to `.git/hooks/` and make executable:
```bash
cp .claude/hooks/pre-commit-task-validation.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Note
These are templates - customize for your workflow. Git hooks are not committed to the repository.
