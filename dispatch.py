"""
Hive — Multi-Agent Task Dispatcher

Task file format (.md) with optional YAML frontmatter:
  ---
  backend: claude | codex
  model: haiku | sonnet | opus | gpt-5.4 | gpt-5.3-codex
  difficulty: low | medium | high
  priority: 1          (lower = runs first)
  timeout: 300         (seconds, default 600)
  ---
  Your prompt here...

Usage:
  python dispatch.py           # run all, full parallelism
  python dispatch.py 3         # limit to 3 concurrent
"""

import os
import subprocess
import json
import re
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Fix Windows encoding: force UTF-8 for subprocess and console
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    os.system("")  # enable VT100 escape sequences on Windows

from rich.live import Live
from rich.table import Table
from rich.console import Console
from rich.text import Text
from rich.panel import Panel

ROOT = Path(__file__).parent
TASKS_DIR = ROOT / "tasks"
RESULTS_DIR = ROOT / "results"
DEFAULT_TIMEOUT = 600

# Shared state
lock = threading.Lock()
task_states: dict[str, dict] = {}
cost_tracker = {"claude": 0.0, "codex": 0.0, "tasks_done": 0, "tasks_failed": 0, "tasks_total": 0}


def update_state(name: str, **kwargs):
    with lock:
        task_states[name].update(kwargs)


def add_cost(backend: str, cost: float, failed: bool = False):
    with lock:
        cost_tracker[backend] += cost
        cost_tracker["tasks_done"] += 1
        if failed:
            cost_tracker["tasks_failed"] += 1


# ── Task parsing ──────────────────────────────────────────────

def parse_task(task_file: Path) -> dict:
    """Parse .md with optional YAML frontmatter. Returns task config dict."""
    text = task_file.read_text(encoding="utf-8").strip()
    meta = {}
    prompt = text

    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if m:
        for line in m.group(1).strip().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        prompt = m.group(2).strip()

    return {
        "name": task_file.stem,
        "file": task_file,
        "backend": meta.get("backend", "claude").lower(),
        "model": meta.get("model", ""),
        "difficulty": meta.get("difficulty", ""),
        "priority": int(meta.get("priority", 99)),
        "timeout": int(meta.get("timeout", DEFAULT_TIMEOUT)),
        "prompt": prompt,
    }


# ── Dashboard ─────────────────────────────────────────────────

def build_dashboard() -> Panel:
    with lock:
        states = dict(task_states)
        costs = dict(cost_tracker)

    table = Table(show_header=True, expand=True, border_style="bright_blue")
    table.add_column("Task", style="bold", ratio=3)
    table.add_column("Backend", justify="center", ratio=1)
    table.add_column("Model", justify="center", ratio=1)
    table.add_column("Status", justify="center", ratio=1)
    table.add_column("Time", justify="right", ratio=1)
    table.add_column("Cost", justify="right", ratio=1)

    for name, s in states.items():
        status = s.get("status", "queued")
        backend = s.get("backend", "?")
        model = s.get("model", "-")
        start = s.get("start_time")
        cost = s.get("cost_usd", 0)
        diff = s.get("difficulty", "")
        diff_style = {"low": "green", "medium": "yellow", "high": "red"}.get(diff, "dim")

        backend_txt = Text(backend, style="cyan" if backend == "claude" else "magenta")
        model_txt = Text(model or "-", style=diff_style)

        if status == "queued":
            badge = Text(".. queued", style="dim")
            elapsed_txt = Text("-", style="dim")
        elif status == "running":
            badge = Text(">> running", style="bold yellow")
            elapsed_txt = Text(f"{time.time() - start:.0f}s", style="yellow")
        elif status == "ok":
            badge = Text("OK done", style="bold green")
            elapsed_txt = Text(f"{s.get('elapsed_s', 0):.1f}s", style="green")
        elif status == "error":
            badge = Text("XX error", style="bold red")
            elapsed_txt = Text(f"{s.get('elapsed_s', 0):.1f}s", style="red")
        elif status == "timeout":
            badge = Text("!! timeout", style="bold red")
            elapsed_txt = Text(f"{s.get('timeout', DEFAULT_TIMEOUT)}s", style="red")
        else:
            badge = Text(status, style="bold magenta")
            elapsed_txt = Text("-")

        cost_txt = Text(f"${cost:.4f}" if cost else "-", style="dim" if not cost else "")
        table.add_row(name, backend_txt, model_txt, badge, elapsed_txt, cost_txt)

    # Summary
    done = costs["tasks_done"]
    failed = costs["tasks_failed"]
    total = costs["tasks_total"]
    claude_cost = costs["claude"]
    codex_cost = costs["codex"]
    total_cost = claude_cost + codex_cost

    parts = [f"[bold]{done}/{total}[/bold] done"]
    if failed:
        parts.append(f"[red]{failed} failed[/red]")
    if claude_cost:
        parts.append(f"Claude: [cyan]${claude_cost:.4f}[/cyan]")
    if codex_cost:
        parts.append(f"Codex: [magenta]${codex_cost:.4f}[/magenta]")
    if total_cost:
        parts.append(f"Total: [bold]${total_cost:.4f}[/bold]")

    return Panel(table, title="Hive Dispatch", subtitle="  |  ".join(parts),
                 border_style="bright_blue")


# ── CLI runners ───────────────────────────────────────────────

def run_claude(prompt: str, model: str, timeout: int) -> subprocess.CompletedProcess:
    cmd = ["claude", "-p", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)
    return subprocess.run(cmd, capture_output=True, timeout=timeout, encoding="utf-8", errors="replace")


def run_codex(prompt: str, model: str, timeout: int) -> subprocess.CompletedProcess:
    codex_bin = "codex.cmd" if sys.platform == "win32" else "codex"
    cmd = [codex_bin, "exec", "--json", "--skip-git-repo-check"]
    if model:
        cmd += ["-m", model]
    cmd.append(prompt)
    return subprocess.run(cmd, capture_output=True, timeout=timeout, encoding="utf-8", errors="replace")


# ── Task execution ────────────────────────────────────────────

def run_task(task: dict) -> dict:
    name = task["name"]
    backend = task["backend"]
    model = task["model"]
    prompt = task["prompt"]
    timeout = task["timeout"]
    start = time.time()

    update_state(name, status="running", start_time=start)

    try:
        if backend == "codex":
            result = run_codex(prompt, model, timeout)
        else:
            result = run_claude(prompt, model, timeout)

        elapsed = round(time.time() - start, 1)

        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                data = {"raw_output": result.stdout}

            cost = 0.0
            if backend == "claude" and isinstance(data, dict):
                cost = data.get("total_cost_usd", 0) or 0

            add_cost(backend, cost)
            update_state(name, status="ok", elapsed_s=elapsed, cost_usd=cost)
            return {"task": name, "backend": backend, "model": model,
                    "status": "ok", "elapsed_s": elapsed, "cost_usd": cost, "result": data}
        else:
            add_cost(backend, 0, failed=True)
            update_state(name, status="error", elapsed_s=elapsed)
            return {"task": name, "backend": backend, "model": model,
                    "status": "error", "elapsed_s": elapsed, "stderr": result.stderr}

    except subprocess.TimeoutExpired as e:
        # Kill the hanging process on timeout
        if e.cmd and hasattr(e, 'args'):
            try:
                import signal
                os.killpg(os.getpgid(e.cmd.pid), signal.SIGTERM)
            except Exception:
                pass
        add_cost(backend, 0, failed=True)
        update_state(name, status="timeout", elapsed_s=timeout)
        return {"task": name, "backend": backend, "model": model,
                "status": "timeout", "elapsed_s": timeout}
    except Exception as e:
        add_cost(backend, 0, failed=True)
        update_state(name, status="exception",
                     elapsed_s=round(time.time() - start, 1))
        return {"task": name, "backend": backend, "model": model,
                "status": "exception", "error": str(e)}


# ── Main ──────────────────────────────────────────────────────

def main():
    RESULTS_DIR.mkdir(exist_ok=True)

    task_files = sorted(TASKS_DIR.glob("*.md"))
    if not task_files:
        print("No .md task files found in tasks/")
        sys.exit(1)

    # Parse and sort by priority
    tasks = [parse_task(f) for f in task_files]
    tasks.sort(key=lambda t: t["priority"])

    max_workers = int(sys.argv[1]) if len(sys.argv) > 1 else len(tasks)

    # Init dashboard state
    for t in tasks:
        task_states[t["name"]] = {
            "status": "queued",
            "backend": t["backend"],
            "model": t["model"],
            "difficulty": t["difficulty"],
        }
    cost_tracker["tasks_total"] = len(tasks)

    console = Console()
    console.print(f"\n[bold]Dispatching {len(tasks)} tasks (max {max_workers} parallel)[/bold]\n")

    with Live(build_dashboard(), console=console, refresh_per_second=2) as live:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(run_task, t): t["name"] for t in tasks}

            while any(not f.done() for f in futures):
                live.update(build_dashboard())
                time.sleep(0.5)

            live.update(build_dashboard())

            for future in futures:
                result = future.result()
                out_path = RESULTS_DIR / f"{result['task']}.json"
                out_path.write_text(
                    json.dumps(result, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

    console.print("\n[bold green]Done.[/bold green] Results saved to results/\n")


if __name__ == "__main__":
    main()
