---
name: flight-profiler-attach
description: Prerequisites and connection details for attaching to a live Python process with PyFlightProfiler. Read this skill first before using any other PyFlightProfiler command (watch, trace, stack, perf, etc.).
---

# flight-profiler-attach — PyFlightProfiler Connection Guide

All PyFlightProfiler commands require attaching to a running Python process. This skill covers the prerequisites, how to connect, and how to troubleshoot failures.

## Core Concept: Static Analysis + Runtime Inspection

PyFlightProfiler skills are designed for **live process diagnostics**. When using these skills, you should combine two sources of information:

1. **Static file analysis** — when the user provides a file path or project directory, read the source code first to understand the code structure: locate target modules, classes, methods, and call relationships. This helps you construct the right command arguments (module name, class name, method name).
2. **Runtime inspection** — attach to the running process and use commands like `stack`, `watch`, `trace` to observe actual runtime behavior: what threads are active, what methods are being called, what arguments are passed, and how long they take.

Always leverage both: read the code to know *what to look for*, then use PyFlightProfiler to see *what's actually happening* at runtime.

## Prerequisites Checklist

Before using any PyFlightProfiler command, verify these conditions in order. If any check fails, PyFlightProfiler cannot be used — report the failure reason to the user.

### 1. Platform

- **Linux** (glibc >= 2.17) or **macOS** only
- Check: `uname -s` should return `Linux` or `Darwin`
- On Linux, verify glibc: `ldd --version | head -1`

### 2. ptrace / LLDB availability

- **Linux**: ptrace must be enabled. Check `cat /proc/sys/kernel/yama/ptrace_scope` — value should be `0` (or the process must be run as root). On CPython >= 3.14, `sys.remote_exec` is used instead of ptrace.
- **macOS**: LLDB is used for injection (comes with Xcode Command Line Tools). On CPython >= 3.14, `sys.remote_exec` is used instead.

### 3. Installation location — same Python environment

`flight_profiler` must be installed in the **exact same Python/pip environment** as the target process. This means the `flight_profiler` CLI and the target process must share the same Python interpreter and site-packages. After injection, the agent runs inside the target process and imports `flight_profiler` modules — if the package isn't in the target's `sys.path`, the import will fail.

**Example:** if the target process runs under `/Users/zy/miniforge3/envs/py310/bin/python`, then:
- **Install** flight_profiler with that environment's pip: `/Users/zy/miniforge3/envs/py310/bin/pip3 install flight_profiler`
- **Run** flight_profiler with that environment's binary: `/Users/zy/miniforge3/envs/py310/bin/flight_profiler <pid>`

Using a `flight_profiler` from a different environment (e.g., system Python or another conda env) will cause the injection to fail because the target process cannot find the `flight_profiler` package in its own `sys.path`.

```bash
# Step 1: Find the target process's Python executable
ls -l /proc/<pid>/exe        # Linux
ps -p <pid> -o command=      # macOS

# Step 2: Check if flight_profiler is already installed in that environment
/path/to/target/python -m pip show flight_profiler

# Step 3: If not installed, install it using the target's pip
/path/to/target/python -m pip install flight_profiler

# Step 4: Run flight_profiler using the same environment's binary
/path/to/target/bin/flight_profiler <pid>
```

**Common scenario — conda / virtualenv:**

```bash
# If the target runs under /Users/zy/miniforge3/envs/py310
# Option A: activate the environment, then install and run
conda activate py310
pip3 install flight_profiler
flight_profiler <pid>

# Option B: use the full path directly (no activation needed)
/Users/zy/miniforge3/envs/py310/bin/pip3 install flight_profiler
/Users/zy/miniforge3/envs/py310/bin/flight_profiler <pid>
```

### 4. Permissions

The `flight_profiler` process must have permission to attach to the target:

- If the target runs as **root**, you must use `sudo flight_profiler <pid> ...`
- If the target runs as a different user, you need root privileges or the same UID
- On Linux, `CAP_SYS_PTRACE` capability can substitute for root

```bash
# Check target process owner
ps -p <pid> -o user=

# If target is root-owned
sudo flight_profiler <pid> --cmd "stack" --no-color
```

### 5. If all checks fail

If the above prerequisites cannot be satisfied, print the specific failure reason and inform the user that PyFlightProfiler skills cannot be used for this target process. Common failure messages:

- "Target process is on an unsupported platform (Windows/other)"
- "glibc version X.XX is below the minimum 2.17"
- "ptrace_scope is set to 2/3, ptrace is disabled"
- "flight_profiler is not installed in the target process's Python environment"
- "Permission denied: target process runs as root, use sudo"

## How to Connect — Locating the Target PID

### Priority 1: User provides PID directly

If the user gives a PID number, use it directly — this is the most straightforward case. Skip to "Run a command" below.

### Priority 2: Search by file path or process name

If the user provides a file path, script name, or process name, search for matching Python processes:

```bash
# Search by script name or file path
pgrep -af "my_script.py"
pgrep -af "myapp"

# List all Python processes with full command lines
ps aux | grep python

# Search by a keyword in the command line
ps aux | grep -E "gunicorn|uvicorn|celery|your_app"
```

Filter out processes that are obviously in a different Python/pip environment (e.g., different conda env, different virtualenv path) — they won't work with `flight_profiler` even if found.

### Priority 3: Multi-process architecture — pick the right PID

Many Python applications use multi-process architectures (e.g., `multiprocessing`, `gunicorn` workers, ML inference frameworks like vLLM/TGI with separate launcher and worker processes). The method you want to observe typically runs in a **child worker process**, not the launcher/master process.

```bash
# List the process tree to see parent-child relationships
pstree -p <launcher_pid>

# Or find all child processes
ps --ppid <launcher_pid> -o pid,cmd    # Linux
ps -o pid,ppid,command | grep <launcher_pid>  # macOS
```

**How to decide which PID to use:**
- If you want to observe request handling, model inference, or business logic — attach to the **worker/child process**
- If you want to observe scheduling, routing, or process management — attach to the **master/launcher process**

### Priority 4: Use `stack` to identify the right process

When multiple Python processes exist and you cannot determine which one contains the target code, use the `stack` command to inspect candidate processes. Look for common file path prefixes or recognizable module names in the stack frames:

```bash
# Check what each candidate process is running
flight_profiler <pid_1> --cmd "stack" --no-color
flight_profiler <pid_2> --cmd "stack" --no-color
```

The stack output lists all active Python files and functions per thread. Compare the file paths against the user's project directory or the file they mentioned — the process whose stack frames reference the same codebase is the target.

**Tip:** if the user mentioned a specific file (e.g., `app/handlers/user.py`), look for that path or its module equivalent in the stack output to confirm the process.

### Run a command

All commands use this format:

```bash
flight_profiler <pid> --cmd "<command>" --no-color --timeout <seconds>
```

- `<pid>` — target process PID
- `--cmd` — single-shot mode (run one command and exit, no interactive REPL)
- `--no-color` — disable ANSI colors for clean text output
- `--timeout` — stop after N seconds and exit with code 124

### Always pass `--timeout` for streaming commands

`watch`, `trace`, `tt` and `gilstat` print a record each time the observed code
runs, and they only return once their display limit (`-n`) is reached. If the
function is never called — wrong module, idle service, wrong worker process —
the command blocks forever and your session hangs.

Pass a deadline that matches how often you expect the code to run:

```bash
# A busy request handler: a few seconds is plenty
flight_profiler <pid> --cmd "watch --pkg app.api --func handle -n 3" --no-color --timeout 15

# A background job that runs every minute
flight_profiler <pid> --cmd "watch --pkg app.jobs --func sync -n 1" --no-color --timeout 90
```

Exit code `124` means the deadline was reached. That is a normal outcome, not a
crash: it tells you the function was not called during the window. When you see
it, report that no invocation was observed and consider whether you targeted the
right process (see "Multi-process architecture" above) or the right module.

**Never kill the client to escape a hanging command.** `watch` and `trace`
install instrumentation inside the target process, and the client removes it on
exit. `--timeout` and Ctrl-C both take that clean path; `kill -9` leaves the
instrumentation running in production.

Point-in-time commands (`stack`, `getglobal`, `module`, `vmtool`) return
immediately, so a deadline is optional there — though a small one is still good
practice in case the target process is stuck holding the GIL.

### What happens on first connect

1. `flight_profiler` checks if the agent server is already injected (scans ports 16000-16500)
2. If not injected: injects `profiler_agent.py` into the target process via ptrace/LLDB/sys.remote_exec
3. The agent starts an async TCP server inside the target process
4. Subsequent `--cmd` calls **reuse the existing agent** — no re-injection, fast (< 1s)

### Port configuration (optional)

```bash
# Custom port range
PYFLIGHT_INJECT_START_PORT=20000 PYFLIGHT_INJECT_END_PORT=20500 flight_profiler <pid> --cmd "stack" --no-color

# Custom timeout
PYFLIGHT_INJECT_TIMEOUT=10 flight_profiler <pid> --cmd "stack" --no-color
```

## Debugging connection issues

Add `--debug` to see detailed diagnostic output:

```bash
flight_profiler <pid> --cmd "stack" --no-color --debug
```

This prints:
- Platform and architecture
- Python executable paths (client vs target)
- Whether they share the same Python executable
- Directory write permissions
- UID comparison between client and target process
