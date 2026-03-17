---
name: hive
description: Orchestrate parallel task execution across Claude CLI and OpenAI Codex CLI with a live Rich TUI dashboard. Use this skill whenever the user wants to break a complex task into subtasks and dispatch them to multiple CLI agents in parallel, monitor progress with a live dashboard, run tasks across both Claude and Codex backends, or coordinate a Desktop-plans-CLI-executes workflow. Also use when the user mentions "hive", "dispatch", "parallel tasks", "fan out", or wants to use multiple AI models on different parts of a problem simultaneously.
---

# Hive — Multi-Agent Task Dispatcher

Break complex work into independent subtasks, dispatch them in parallel across Claude CLI and OpenAI Codex CLI, monitor via live terminal dashboard, review and re-dispatch failures.

## Workflow

```
1. PLAN    — Analyze request, decompose into independent subtasks
2. WRITE   — Create tasks/*.md files with frontmatter (backend, model, priority)
3. RUN     — python dispatch.py <N>
4. REVIEW  — Read results/*.json, grade PASS/FAIL
5. RETRY   — Re-dispatch failures with clearer prompts
6. CLEAN   — Remove completed tasks from tasks/ before next run
```

## Task File Format

Each `.md` file in `tasks/` (top-level only, subdirectories are ignored):

```markdown
---
backend: claude
model: sonnet
difficulty: medium
priority: 1
timeout: 300
---
Your prompt here. Must be fully self-contained — the CLI agent
has no conversation history. Include file paths, context, and
expected output format.
```

All frontmatter fields are optional. Defaults: `backend=claude`, `priority=99`, `timeout=600`.

## Model Selection

Pick based on task complexity — lighter models save quota and run faster:

| Difficulty | Claude | Codex | Typical tasks |
|-----------|--------|-------|---------------|
| low | haiku | gpt-5.3-codex-spark* | Simple queries, format conversion |
| medium | sonnet | gpt-5.3-codex | Code gen, refactoring, tests |
| high | opus | gpt-5.4 | Architecture, complex debug |

*gpt-5.3-codex-spark may not be available on all accounts — fall back to gpt-5.4.

## Writing Good Task Prompts

Each CLI agent runs in complete isolation. The prompt is all it gets. Make it count:

- Include absolute file paths (the agent doesn't know your working directory)
- Provide enough context that a stranger could execute the task
- Specify the expected output format ("return JSON", "write to file X", etc.)
- If the task operates on a specific directory, state it explicitly — Claude CLI runs with `-p` in the dispatch directory by default
- For Codex tasks that need file access, the `--skip-git-repo-check` flag is already set

## Running

```bash
cd <hive-directory>
python dispatch.py        # all tasks, full parallelism
python dispatch.py 3      # max 3 concurrent
```

## Reviewing Results

Each `results/<task-name>.json` contains:
- `status`: `ok`, `error`, `timeout`, or `exception`
- `result`: the CLI output (Claude returns structured JSON with `total_cost_usd`)
- `elapsed_s`, `cost_usd`, `backend`, `model`

After review, remove or archive completed task files from `tasks/` before the next dispatch run — otherwise they'll re-execute.

## Decomposition Guidelines

When breaking down a user request:

1. **2-8 subtasks** is the sweet spot. Fewer means you're not parallelizing enough; more means the overhead of isolation hurts.
2. **Each task must be independent** — no shared state between CLI processes. If task B needs task A's output, set priority so A runs first, and have B read from a known file path.
3. **Don't over-split** — if two things are tightly coupled, keep them in one task. The cost of lost context is higher than the gain from parallelism.
4. **Number your files** for readability: `01-setup.md`, `02-implement.md`, `03-test.md`.
