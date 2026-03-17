# Hive

Multi-agent task dispatcher for Claude CLI + OpenAI Codex CLI with a live Rich TUI dashboard.

```
Desktop (plan) --> tasks/*.md --> dispatch.py --> results/*.json --> Desktop (review)
```

## What it does

- Break complex work into independent subtasks as `.md` files
- Dispatch them in parallel across Claude and Codex CLI backends
- Monitor progress with a live terminal dashboard (status, time, cost)
- Collect structured JSON results for review

## Quick start

```bash
pip install rich
cd hive
python dispatch.py        # run all tasks
python dispatch.py 3      # limit to 3 concurrent
```

## Task format

```markdown
---
backend: claude
model: sonnet
difficulty: medium
priority: 1
timeout: 300
---
Your prompt here. Be specific.
```

| Field | Default | Options |
|-------|---------|---------|
| backend | claude | `claude`, `codex` |
| model | (default) | Claude: `haiku`/`sonnet`/`opus` — Codex: `gpt-5.4`/`gpt-5.3-codex` |
| difficulty | - | `low`/`medium`/`high` |
| priority | 99 | Lower = runs first |
| timeout | 600 | Seconds |

## Dashboard

```
+------------------ Claude + Codex Dispatch -------------------+
| Task            | Back  | Model  | Status  | Time  | Cost    |
|-----------------+-------+--------+---------+-------+---------|
| review-code     | claude| sonnet | OK done | 18.0s | $0.0396 |
| write-tests     | claude| haiku  | >> run  |   5s  | -       |
| codex-task      | codex | gpt5.4 | OK done |  8.6s | -       |
+---------------------------------------------------------------+
         2/3 done  |  Claude: $0.0396  |  Total: $0.0396
```

## As a Claude Code skill

Copy the `hive/` directory into your skills path and it becomes available as a skill. See `SKILL.md` for the full workflow.

## Requirements

- Python 3.10+
- `rich` (`pip install rich`)
- `claude` CLI on PATH
- `codex` CLI on PATH (optional, for Codex tasks)
