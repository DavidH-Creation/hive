---
name: hive
description: Orchestrate parallel task execution across Claude CLI and OpenAI Codex CLI with a live Rich TUI dashboard. Use this skill whenever the user wants to break a complex task into subtasks and dispatch them to multiple CLI agents in parallel, monitor progress with a live dashboard, run tasks across both Claude and Codex backends, or coordinate a Desktop-plans-CLI-executes workflow. Also use when the user mentions "hive", "dispatch", "parallel tasks", "fan out", or wants to use multiple AI models on different parts of a problem simultaneously.
---

# Hive -- Multi-Agent Task Dispatcher

Break complex work into independent subtasks, dispatch them in parallel across Claude CLI and OpenAI Codex CLI, monitor via live terminal dashboard or web UI, review and re-dispatch failures.

## Workflow

```
1. PLAN    -- Analyze request, decompose into independent subtasks
2. WRITE   -- Create tasks/*.md files with frontmatter (backend, model, priority)
3. RUN     -- python dispatch.py [--web] [--worktree]
4. REVIEW  -- Read results/*.json, grade PASS/FAIL
5. RETRY   -- Re-dispatch failures with clearer prompts
6. CLEAN   -- Remove completed tasks from tasks/ before next run
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
worktree: true
---
Your prompt here. Must be fully self-contained -- the CLI agent
has no conversation history. Include file paths, context, and
expected output format.
```

All frontmatter fields are optional. Defaults: `backend=claude`, `priority=99`, `timeout=600`, `worktree=false`.

## Model Selection

Pick based on task complexity -- lighter models save quota and run faster:

| Difficulty | Claude | Codex | Typical tasks |
|-----------|--------|-------|---------------|
| low | haiku | gpt-5.3-codex-spark* | Simple queries, format conversion |
| medium | sonnet | gpt-5.3-codex | Code gen, refactoring, tests |
| high | opus | gpt-5.4 | Architecture, complex debug |

*gpt-5.3-codex-spark may not be available on all accounts -- fall back to gpt-5.4.

## Writing Good Task Prompts

Each CLI agent runs in complete isolation. The prompt is all it gets. Make it count:

- Include absolute file paths (the agent doesn't know your working directory)
- Provide enough context that a stranger could execute the task
- Specify the expected output format ("return JSON", "write to file X", etc.)
- If the task operates on a specific directory, state it explicitly
- For Codex tasks that need file access, the `--skip-git-repo-check` flag is already set

## Dynamic Task Spawning

Agents can spawn new tasks at runtime by printing to stdout:

```
HIVE_SPAWN: {"name": "sub-task-name", "prompt": "do something", "backend": "claude"}
```

All fields from frontmatter are supported: `name`, `prompt`, `backend`, `model`, `difficulty`, `priority`, `timeout`, `worktree`. Only `prompt` is required.

Spawned tasks run after the current batch completes, grouped by priority like static tasks. They appear in the dashboard with a `>` prefix indicating their parent.

## Git Worktree Isolation

When agents write code to the same repo, enable worktree isolation to prevent conflicts:

```bash
python dispatch.py --worktree          # enable for all tasks
```

Or per-task via frontmatter: `worktree: true`

Each task gets its own git worktree under `.hive/worktrees/<task-name>` with a dedicated branch `hive/<task-name>`. Worktrees are cleaned up after task completion.

Requires: CWD must be inside a git repo. If not, worktree is silently disabled.

## Web Dashboard

```bash
python dispatch.py --web               # open dashboard at localhost:8686
python dispatch.py --web --port 9090   # custom port
```

The web dashboard provides:
- Real-time task status via Server-Sent Events (SSE)
- Summary cards (total, running, done, failed, cost)
- Progress bar with completion percentage
- Per-task table with backend, model, status, elapsed time, cost
- Spawned tasks shown with parent indicator
- Auto-reconnect on connection loss

The Rich TUI dashboard still runs in the terminal simultaneously.

## Running

```bash
cd <hive-directory>
python dispatch.py                     # all tasks, full parallelism
python dispatch.py --workers 3         # max 3 concurrent
python dispatch.py --web               # with web dashboard
python dispatch.py --worktree          # with git worktree isolation
python dispatch.py --web --worktree -w 4   # all features
```

## Reviewing Results

Each `results/<task-name>.json` contains:
- `status`: `ok`, `error`, `timeout`, or `exception`
- `parsed_output`: the CLI output (Claude returns structured JSON with `total_cost_usd`)
- `elapsed_s`, `cost_usd`, `backend`, `model`
- `spawned_by`: parent task name (for dynamically spawned tasks)
- `worktree`: worktree path used (if worktree was enabled)

After review, remove or archive completed task files from `tasks/` before the next dispatch run -- otherwise they'll re-execute.

## Decomposition Guidelines

When breaking down a user request:

1. **2-8 subtasks** is the sweet spot. Fewer means you're not parallelizing enough; more means the overhead of isolation hurts.
2. **Each task must be independent** -- no shared state between CLI processes. If task B needs task A's output, set priority so A runs first, and have B read from a known file path.
3. **Don't over-split** -- if two things are tightly coupled, keep them in one task. The cost of lost context is higher than the gain from parallelism.
4. **Number your files** for readability: `01-setup.md`, `02-implement.md`, `03-test.md`.
5. **Use worktree** when multiple tasks write code to the same repo to avoid merge conflicts.
6. **Use dynamic spawning** when an agent discovers sub-work at runtime -- e.g., a test runner finds failures and spawns fix tasks.
