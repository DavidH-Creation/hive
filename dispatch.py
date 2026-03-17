"""
Hive — Multi-Agent Task Dispatcher

Task file format (.md) with optional YAML frontmatter:
  ---
  backend: claude | codex
  model: haiku | sonnet | opus | gpt-5.4 | gpt-5.3-codex
  difficulty: low | medium | high
  priority: 1          (lower = runs first, same priority = parallel)
  timeout: 300         (seconds, default 600)
  ---
  Your prompt here...

Usage:
  python dispatch.py                     # all tasks, full parallelism
  python dispatch.py --workers 3         # limit concurrency
  python dispatch.py --tasks-dir ./my    # custom task directory
"""

import argparse
import itertools
import os
import json
import re
import shutil
import subprocess
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Fix Windows encoding
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    os.system("")  # enable VT100 escape sequences

from rich.live import Live
from rich.table import Table
from rich.console import Console
from rich.text import Text
from rich.panel import Panel

DEFAULT_TIMEOUT = 600
VALID_BACKENDS = {"claude", "codex"}

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


# ── Preflight ─────────────────────────────────────────────────

def preflight(tasks: list[dict]) -> list[str]:
    """Check that required CLI tools are on PATH. Returns list of errors."""
    needed = {t["backend"] for t in tasks}
    errors = []
    for backend in needed:
        if backend == "claude":
            if not shutil.which("claude"):
                errors.append("'claude' CLI not found on PATH")
        elif backend == "codex":
            bin_name = "codex.cmd" if sys.platform == "win32" else "codex"
            if not shutil.which(bin_name):
                errors.append(f"'{bin_name}' CLI not found on PATH")
    return errors


# ── Task parsing ──────────────────────────────────────────────

def parse_task(task_file: Path) -> dict:
    """Parse .md with simple key: value frontmatter. Returns task config dict."""
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

    # Validate backend
    backend = meta.get("backend", "claude").lower()
    if backend not in VALID_BACKENDS:
        raise ValueError(f"{task_file.name}: invalid backend '{backend}' (must be one of {VALID_BACKENDS})")

    # Validate numeric fields
    try:
        priority = int(meta.get("priority", 99))
    except ValueError:
        raise ValueError(f"{task_file.name}: priority must be an integer, got '{meta['priority']}'")
    try:
        timeout = int(meta.get("timeout", DEFAULT_TIMEOUT))
    except ValueError:
        raise ValueError(f"{task_file.name}: timeout must be an integer, got '{meta['timeout']}'")

    return {
        "name": task_file.stem,
        "file": task_file,
        "backend": backend,
        "model": meta.get("model", ""),
        "difficulty": meta.get("difficulty", ""),
        "priority": priority,
        "timeout": timeout,
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


# ── CLI runners (Popen-based for proper timeout + kill) ───────

def run_process(cmd: list[str], timeout: int) -> dict:
    """Run a command with Popen. Returns dict with stdout, stderr, returncode."""
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
        return {
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
            "returncode": proc.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return {
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "timed_out": True,
        }


def build_claude_cmd(prompt: str, model: str) -> list[str]:
    cmd = ["claude", "-p", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)
    return cmd


def build_codex_cmd(prompt: str, model: str) -> list[str]:
    codex_bin = "codex.cmd" if sys.platform == "win32" else "codex"
    cmd = [codex_bin, "exec", "--json", "--skip-git-repo-check"]
    if model:
        cmd += ["-m", model]
    cmd.append(prompt)
    return cmd


# ── Output parsing ────────────────────────────────────────────

def parse_claude_output(stdout: str) -> dict:
    """Claude --output-format json returns a single JSON object."""
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"raw_output": stdout}


def parse_codex_output(stdout: str) -> dict:
    """Codex --json returns JSONL (one JSON object per line).
    We collect all events and extract the final agent message."""
    events = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not events:
        return {"raw_output": stdout}

    # Extract the final agent message and usage from events
    result = {"events": events}
    for event in events:
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                result["message"] = item.get("text", "")
        elif event.get("type") == "turn.completed":
            result["usage"] = event.get("usage", {})

    return result


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
            cmd = build_codex_cmd(prompt, model)
        else:
            cmd = build_claude_cmd(prompt, model)

        proc_result = run_process(cmd, timeout)
        elapsed = round(time.time() - start, 1)

        # Base result with full stdout/stderr preserved
        result = {
            "task": name,
            "backend": backend,
            "model": model,
            "elapsed_s": elapsed,
            "exit_code": proc_result["returncode"],
            "stdout": proc_result["stdout"],
            "stderr": proc_result["stderr"],
        }

        if proc_result["timed_out"]:
            add_cost(backend, 0, failed=True)
            update_state(name, status="timeout", elapsed_s=timeout)
            result["status"] = "timeout"
            result["elapsed_s"] = timeout
            return result

        # Parse output based on backend
        if backend == "codex":
            parsed = parse_codex_output(proc_result["stdout"])
        else:
            parsed = parse_claude_output(proc_result["stdout"])

        result["parsed_output"] = parsed

        if proc_result["returncode"] == 0:
            cost = 0.0
            if backend == "claude" and isinstance(parsed, dict):
                cost = parsed.get("total_cost_usd", 0) or 0
            add_cost(backend, cost)
            update_state(name, status="ok", elapsed_s=elapsed, cost_usd=cost)
            result["status"] = "ok"
            result["cost_usd"] = cost
        else:
            add_cost(backend, 0, failed=True)
            update_state(name, status="error", elapsed_s=elapsed)
            result["status"] = "error"

        return result

    except Exception as e:
        elapsed = round(time.time() - start, 1)
        add_cost(backend, 0, failed=True)
        update_state(name, status="exception", elapsed_s=elapsed)
        return {
            "task": name, "backend": backend, "model": model,
            "status": "exception", "elapsed_s": elapsed,
            "exit_code": -1, "stdout": "", "stderr": "",
            "error": str(e),
        }


# ── Priority batch execution ─────────────────────────────────

def run_batch(batch: list[dict], max_workers: int, console: Console, live: Live):
    """Run a batch of same-priority tasks in parallel."""
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(run_task, t): t["name"] for t in batch}
        while any(not f.done() for f in futures):
            live.update(build_dashboard())
            time.sleep(0.5)
        live.update(build_dashboard())
        return [f.result() for f in futures]


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hive — Multi-Agent Task Dispatcher")
    parser.add_argument("--workers", "-w", type=int, default=0,
                        help="Max concurrent tasks (default: all)")
    parser.add_argument("--tasks-dir", "-t", type=Path, default=None,
                        help="Tasks directory (default: ./tasks)")
    parser.add_argument("--results-dir", "-r", type=Path, default=None,
                        help="Results directory (default: ./results)")
    args = parser.parse_args()

    root = Path(__file__).parent
    tasks_dir = args.tasks_dir or (root / "tasks")
    results_dir = args.results_dir or (root / "results")
    results_dir.mkdir(exist_ok=True)

    task_files = sorted(tasks_dir.glob("*.md"))
    if not task_files:
        print(f"No .md task files found in {tasks_dir}")
        sys.exit(1)

    # Parse all tasks (exits on validation error)
    tasks = [parse_task(f) for f in task_files]

    # Preflight: check CLIs are available
    errors = preflight(tasks)
    if errors:
        for e in errors:
            print(f"Error: {e}")
        sys.exit(1)

    # Group by priority for batch execution
    tasks.sort(key=lambda t: t["priority"])
    batches = []
    for _, group in itertools.groupby(tasks, key=lambda t: t["priority"]):
        batches.append(list(group))

    max_workers = args.workers or len(tasks)

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
    n_batches = len(batches)
    batch_info = f" in {n_batches} priority batch{'es' if n_batches > 1 else ''}" if n_batches > 1 else ""
    console.print(f"\n[bold]Dispatching {len(tasks)} tasks{batch_info} (max {max_workers} parallel)[/bold]\n")

    all_results = []
    with Live(build_dashboard(), console=console, refresh_per_second=2) as live:
        for batch in batches:
            results = run_batch(batch, max_workers, console, live)
            all_results.extend(results)

    # Save results
    for result in all_results:
        out_path = results_dir / f"{result['task']}.json"
        out_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # Exit code: 0 if all ok, 1 if any failures
    has_failures = any(r["status"] != "ok" for r in all_results)
    console.print(f"\n[bold green]Done.[/bold green] Results saved to {results_dir}/\n")
    sys.exit(1 if has_failures else 0)


if __name__ == "__main__":
    main()
