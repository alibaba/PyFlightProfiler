---
name: flight-profiler-gilstat
description: Measure Global Interpreter Lock contention in a running Python process — how long each thread waits to take the GIL and how long it holds it. Use when a multithreaded service is slow but not CPU-bound.
---

# flight-profiler-gilstat

Measure GIL contention: per thread, how many times it took the GIL, how long it waited for it, and how long it held it. This is the command for the case where a service is slow, the CPU is not saturated, and the threads are apparently "doing nothing".

> **Prerequisites:** Read the **flight-profiler-attach** skill first for platform requirements, installation, permissions, and connection details.

## When to Use

- A multithreaded service has high latency but low CPU utilisation
- Adding threads or workers made throughput *worse*
- An inference or data-loading service stalls under concurrency
- A C extension is suspected of holding the GIL across a long call
- `stack` shows threads parked in `take_gil` or waiting to run

Use `perf` first if you do not know whether the problem is CPU at all. Use `gilstat` once you suspect threads are waiting on each other.

## Usage

```bash
flight_profiler <pid> --cmd "gilstat on [gil_take] [gil_hold] [interval] [max_threads]" --no-color
flight_profiler <pid> --cmd "gilstat off" --no-color
```

## Arguments

All four are positional and optional, in this order:

- `gil_take` — warn when a thread waits more than this many **milliseconds** to acquire the GIL. Default `10`.
- `gil_hold` — warn when a thread holds the GIL longer than this many **milliseconds**. Default `10`.
- `interval` — seconds between statistics reports. Default `5`.
- `max_threads` — report at most this many threads. Default `500`.

```bash
# Defaults
flight_profiler <pid> --cmd "gilstat on" --no-color

# Warn on 5ms waits and 5ms holds, report every 10s, top 100 threads
flight_profiler <pid> --cmd "gilstat on 5 5 10 100" --no-color
```

## It streams until stopped — stop it correctly

`gilstat on` installs an interceptor on the GIL take/drop path inside the target process and streams reports **forever**. There is no capture limit.

The interceptor is removed when the client is interrupted with **SIGINT** — the same signal Ctrl-C sends. A plain `kill` or `timeout` (which sends SIGTERM) skips that cleanup and **leaves the interceptor installed in production**, adding overhead to every GIL operation indefinitely.

```bash
# Correct: SIGINT after 30s, so the interceptor is removed on the way out
timeout -s INT 30 flight_profiler <pid> --cmd "gilstat on" --no-color

# Then confirm it is off, regardless of how the previous command ended
flight_profiler <pid> --cmd "gilstat off" --no-color
```

On macOS, `timeout` comes from coreutils and may be installed as `gtimeout`. If neither is available, run `gilstat on` in a foreground session you can Ctrl-C, and always follow with `gilstat off`.

**Always run `gilstat off` when you are finished**, even if you believe the previous command exited cleanly. It is idempotent and cheap.

## Output Format

Two reports are emitted. Both are plain fixed-width tables, and **all durations are nanoseconds**.

### Statistics report — every `interval` seconds

```
gil statistics report:
time    thread_id    thread_name    takecnt    hold_all(ns)    holdavg(ns)    take_all(ns)    takeavg(ns)    dropcnt    drop_all(ns)    dropavg(ns)
```

| Column | Meaning |
| --- | --- |
| `time` | when the sample was taken |
| `thread_id` | OS thread id, in hex |
| `thread_name` | thread name if set, otherwise the OS name |
| `takecnt` | times this thread acquired the GIL in the window |
| `hold_all` / `holdavg` | total and average time holding the GIL |
| `take_all` / `takeavg` | total and average time **waiting** to acquire it |
| `dropcnt`, `drop_all` / `dropavg` | times it released the GIL, and the cost of releasing |

### Warning report — as thresholds are exceeded

```
gil warning report:
time    thread_id    thread_name    event    cost(ns)    threshold(ns)    start(ns)    end(ns)
```

`event` is `take_gil` (waited too long to acquire) or `hold_gil` (held it too long).

## How to Read It

- **High `takeavg` across many threads** — contention. Threads spend their time queueing for the GIL rather than working. More threads will not help; the fix is to release the GIL (move work into a C extension that releases it, or into a separate process).
- **One thread with a very high `holdavg`** — that thread is the bottleneck. Find what it runs with `stack`, then `trace` it. A long hold usually means a C extension or a long pure-Python loop that never yields.
- **Many `hold_gil` warnings from one thread name** — the same story, with timestamps you can correlate against request logs.
- **Low `takeavg` everywhere** — the GIL is not your problem. Go back to `perf` or look at I/O waits with `stack -a`.

Watch the units: these are nanoseconds, so `takeavg` of `15000000` is 15 ms of waiting per acquisition, which is severe.

## Examples

### 1. Is the GIL the problem at all?

```bash
timeout -s INT 30 flight_profiler 51234 --cmd "gilstat on" --no-color
flight_profiler 51234 --cmd "gilstat off" --no-color
```

Compare `takeavg` against `holdavg`. Waiting much longer than working means contention.

### 2. Catch the specific offender

```bash
timeout -s INT 60 flight_profiler 51234 --cmd "gilstat on 2 20 5 50" --no-color
flight_profiler 51234 --cmd "gilstat off" --no-color
```

Warn on 2 ms waits and 20 ms holds. The warning report names the thread holding the GIL too long.

## Typical Workflow

```bash
# Step 1: confirm threads are waiting rather than computing
timeout -s INT 30 flight_profiler <pid> --cmd "gilstat on" --no-color
flight_profiler <pid> --cmd "gilstat off" --no-color

# Step 2: find what the offending thread is executing
flight_profiler <pid> --cmd "stack" --no-color

# Step 3: time the call tree of the function it is stuck in
flight_profiler <pid> --cmd "trace <module> <function> -n 1" --no-color
```

## Tips

- Run it under real load. An idle process has no contention to measure.
- The interceptor adds overhead to every GIL operation. Keep sessions short on a production process, and always turn it off.
- Thread names make the report far easier to read. If the service sets them, the `thread_name` column will identify workers directly.
- On CPython 3.13+ with free-threading enabled there is no GIL to contend for, and this command has nothing to report.

## Related Commands

- **flight-profiler-stack** — what each thread is executing, to identify the one holding the GIL
- **flight-profiler-perf** — whole-process CPU profile, when the problem may not be contention
- **flight-profiler-trace** — call tree of the function that holds the GIL too long

## Source Files

- `flight_profiler/plugins/gilstat/cli_plugin_gilstat.py`
- `flight_profiler/plugins/gilstat/server_plugin_gilstat.py`
- `csrc/py_gil_stat.cpp`
