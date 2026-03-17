# Hive

Multi-agent task dispatcher for Claude CLI + OpenAI Codex CLI with a live Rich TUI dashboard.

```
You (plan) --> tasks/*.md --> dispatch.py --> results/*.json --> You (review)
```

## Quick start

```bash
git clone https://github.com/DavidH-Creation/hive.git
cd hive
pip install rich
python dispatch.py        # run all tasks in tasks/
python dispatch.py 3      # limit to 3 concurrent
```

## Task format

Create `.md` files in `tasks/` with optional YAML frontmatter:

```markdown
---
backend: claude
model: sonnet
difficulty: medium
priority: 1
timeout: 300
---
Your prompt here. Be specific — include file paths and context.
```

| Field | Default | Options |
|-------|---------|---------|
| backend | claude | `claude`, `codex` |
| model | (default) | Claude: `haiku`/`sonnet`/`opus` — Codex: `gpt-5.4`/`gpt-5.3-codex` |
| difficulty | - | `low`/`medium`/`high` (shown in dashboard) |
| priority | 99 | Lower = runs first |
| timeout | 600 | Seconds |

See `tasks/examples/` for sample task files.

## Dashboard

```
+----------------------- Hive Dispatch ------------------------+
| Task            | Back  | Model  | Status  | Time  | Cost    |
|-----------------+-------+--------+---------+-------+---------|
| review-code     | claude| sonnet | OK done | 18.0s | $0.0396 |
| write-tests     | claude| haiku  | >> run  |   5s  | -       |
| codex-task      | codex | gpt5.4 | OK done |  8.6s | -       |
+---------------------------------------------------------------+
         2/3 done  |  Claude: $0.0396  |  Total: $0.0396
```

## Use as a Claude Code skill

Copy the `hive/` directory into your Claude Code skills path. The skill triggers when you ask to dispatch parallel tasks, fan out work, or mention "hive". See `SKILL.md` for the full workflow.

## Requirements

- Python 3.10+
- [rich](https://github.com/Textualize/rich) (`pip install rich`)
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) on PATH
- [Codex CLI](https://github.com/openai/codex) on PATH (optional, for Codex backend tasks)

## License

MIT
