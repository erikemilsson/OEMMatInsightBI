# Templates Directory

This directory contains templates for common project artifacts.

## Available Templates

### task-template.json
Template for creating new tasks with all required fields:
- Metadata (id, title, description, priority, difficulty)
- Acceptance criteria
- Dependencies
- Subtasks structure

### pr-template.md
Pull request description template:
- Summary of changes
- Related tasks (with links to JSON files)
- Testing performed
- Screenshots (for UI changes)

### issue-template.md
GitHub issue template for bug reports and feature requests

### adr-template.md
Architecture Decision Record template following ADR format

## Usage

Copy template, fill in details, and save to appropriate location:
```bash
# Create new task
cp .claude/templates/task-template.json .claude/tasks/task-013.json
# Edit task-013.json with task details
```
