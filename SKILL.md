---
name: hive
description: Orchestrate parallel task execution across Claude CLI and OpenAI Codex CLI with a live Rich TUI dashboard. Use this skill whenever the user wants to break a complex task into subtasks and dispatch them to multiple CLI agents in parallel, monitor progress with a live dashboard, run tasks across both Claude and Codex backends, or coordinate a Desktop-plans-CLI-executes workflow. Also use when the user mentions "hive", "dispatch", "parallel tasks", "fan out", or wants to use multiple AI models on different parts of a problem simultaneously.
---

# Hive — Multi-Agent Task Dispatcher

Hive lets you break complex work into independent subtasks, dispatch them in parallel across Claude CLI and OpenAI Codex CLI, and monitor everything through a live terminal dashboard.

## Architecture

```
You (the planner)
  |
  +-- 1. Analyze the user's request
  +-- 2. Break it into independent subtasks
  +-- 3. Assess difficulty, pick backend + model for each
  +-- 4. Write task files to tasks/
  |
  v
dispatch.py (executor + dashboard)
  |
  +-- Reads tasks/*.md
  +-- Launches CLI processes in parallel
  +-- Shows live Rich TUI with status/time/cost
  +-- Writes results to results/*.json
  |
  v
You (the reviewer)
  |
  +-- Read results/*.json
  +-- Grade each: PASS / FAIL / NEEDS_REVISION
  +-- Re-dispatch failures with new task files
```

## Setup

The hive directory lives at the path where this skill is installed. Before first use, ensure `rich` is installed (`pip install rich`). Both `claude` and `codex` CLI must be on PATH.

## How to Generate Task Files

Each task is a `.md` file in the `tasks/` directory with optional YAML frontmatter:

```markdown
---
backend: claude
model: sonnet
difficulty: medium
priority: 1
timeout: 300
---
Your prompt to the CLI agent goes here.
Be specific — include file paths, context, and expected output format.
```

**Frontmatter fields** (all optional):
| Field | Default | Values |
|-------|---------|--------|
| backend | claude | `claude`, `codex` |
| model | (default) | Claude: `haiku`, `sonnet`, `opus` / Codex: `gpt-5.4`, `gpt-5.3-codex` |
| difficulty | - | `low`, `medium`, `high` (informational, shown in dashboard) |
| priority | 99 | Lower number = runs first |
| timeout | 600 | Seconds before the task is killed |

## Model Selection Guide

Pick the model based on task complexity — using a cheaper/faster model for simple work saves quota and time:

| Difficulty | Claude | Codex | When to use |
|-----------|--------|-------|-------------|
| low | haiku | gpt-5.3-codex-spark* | Format conversion, simple queries, doc generation |
| medium | sonnet | gpt-5.3-codex | Code generation, refactoring, test writing |
| high | opus | gpt-5.4 | Architecture design, complex debugging, multi-file changes |

*gpt-5.3-codex-spark may not be available on all account types. Fall back to gpt-5.4 if it errors.

## Running the Dispatcher

```bash
cd <hive-directory>
python dispatch.py        # all tasks, full parallelism
python dispatch.py 3      # limit to 3 concurrent workers
```

The live dashboard shows:
- Task name, backend, model
- Status: queued -> running -> done/error/timeout
- Elapsed time per task
- Cost per task (Claude only, from JSON output)
- Cumulative cost in the footer

## Reviewing Results

After dispatch completes, read each `results/<task-name>.json`. The structure:

```json
{
  "task": "task-name",
  "backend": "claude",
  "model": "sonnet",
  "status": "ok",
  "elapsed_s": 18.0,
  "cost_usd": 0.0396,
  "result": { ... }
}
```

For each result:
1. Check if the output fully addresses the original task prompt
2. Check code quality if applicable
3. Mark as PASS, FAIL, or NEEDS_REVISION
4. For failures: write a new task file with clearer instructions and re-dispatch

## Step-by-Step Workflow

When a user gives you a complex request:

1. **Analyze**: Understand the full scope. Identify parts that can run independently.

2. **Decompose**: Break into 2-8 subtasks. Each should be self-contained — a CLI agent with no conversation history needs to understand it fully from the task file alone. Include file paths, context, and expected output.

3. **Assign models**: Use the model selection guide. Don't use opus/gpt-5.4 for simple tasks — save the heavy models for tasks that genuinely need deep reasoning.

4. **Write task files**: Create `.md` files in `tasks/`. Use numbered prefixes for readability (e.g., `01-setup-db.md`, `02-write-api.md`). Set priority if ordering matters.

5. **Dispatch**: Run `python dispatch.py <N>` where N is a sensible concurrency limit (usually 3-5).

6. **Review**: Read all results. Summarize what passed, what failed, and why. Re-dispatch failures if needed.

7. **Synthesize**: Combine the results into a coherent whole. The individual tasks produce fragments — your job is to integrate them.

## Important Notes

- Each CLI agent runs in isolation with no shared state. Tasks must be fully self-contained.
- Claude CLI tasks return `total_cost_usd` in their JSON output. Codex does not report cost.
- On Windows, the dispatcher uses `codex.cmd` for Codex (npm shim compatibility).
- The `tasks/` directory should be cleared between dispatch runs to avoid re-running old tasks.
- Results are overwritten if a task with the same name runs again.
