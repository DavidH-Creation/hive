# Hive

Multi-agent task dispatcher for Claude CLI + OpenAI Codex CLI with live Rich TUI dashboard and web monitoring.

[![CI](https://github.com/DavidH-Creation/hive/actions/workflows/ci.yml/badge.svg)](https://github.com/DavidH-Creation/hive/actions/workflows/ci.yml)

## Overview

Hive breaks complex tasks into parallel subtasks and dispatches them across multiple AI backends (Claude CLI and Codex CLI). Monitor progress through a Rich TUI dashboard or web interface.

Part of the [Forge Platform](https://github.com/DavidH-Creation/forge-platform) ecosystem — complements Cartographer (planning) and Bulwark (execution) for parallel lightweight subtask dispatch.

## Features

- **Multi-backend dispatch**: Claude CLI (haiku/sonnet/opus) + Codex CLI (gpt-5.4/gpt-5.3-codex)
- **Rich TUI dashboard**: Real-time progress, status indicators, and result summaries
- **Web dashboard** (v0.3): Browser-based monitoring at configurable port
- **Dynamic task spawning** (v0.3): Agents can spawn subtasks via `HIVE_SPAWN:` stdout protocol
- **Git worktree isolation** (v0.3): Each task runs in an isolated worktree copy
- **Priority-based batch execution**: Lower priority number = runs first; same priority = parallel
- **YAML frontmatter task format**: Configure backend, model, difficulty, priority, timeout per task
- **JSON result persistence**: All results saved for post-run analysis

## Usage

```bash
python dispatch.py                          # all tasks, full parallelism
python dispatch.py --workers 3              # limit concurrency
python dispatch.py --tasks-dir ./my         # custom task directory
python dispatch.py --results-dir ./out      # custom results directory
python dispatch.py --web                    # enable web dashboard
python dispatch.py --web --port 9090        # custom port
python dispatch.py --worktree              # enable git worktree isolation
```

## Task Format

Tasks are Markdown files in `tasks/` with optional YAML frontmatter:

```markdown
---
backend: claude | codex
model: haiku | sonnet | opus | gpt-5.4 | gpt-5.3-codex
difficulty: low | medium | high
priority: 1          # lower = runs first, same priority = parallel
timeout: 300         # seconds, default 600
worktree: true       # run in isolated git worktree
---
Your prompt here...
```

## Dynamic Task Spawning

Agents can spawn new tasks by printing to stdout:

```
HIVE_SPAWN: {"name": "sub-task", "prompt": "...", "backend": "claude"}
```

## Claude Code Skill

Hive is also available as a Claude Code skill installed at `~/.claude/skills/hive/`.

## License

MIT
