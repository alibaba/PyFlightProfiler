---
name: flight-profiler-perf
description: Sample a running Python process and write a flame graph SVG, to find where CPU time actually goes. Use when a service is slow or CPU-bound and you do not yet know which function to blame.
---

# flight-profiler-perf

Sample the stacks of a running Python process and render them as a flame graph SVG. This is the command to reach for when something is slow and you have **no candidate function yet** — it surveys the whole process instead of instrumenting one method.

> **Prerequisites:** Read the **flight-profiler-attach** skill first for platform requirements, installation, permissions, and connection details.

## When to Use

- A service is slow or pegging a CPU and you do not know which code is responsible
- You want a whole-process picture before narrowing down with `trace`
- You need to show someone where time goes, in a form they can open in a browser
- You suspect the hot path is in a library rather than application code

Use `trace` instead once you know which function is slow and want its internal call tree. Use `perf` to *find* that function.

## Usage

```bash
flight_profiler <pid> --cmd "perf -d <seconds> -f <output.svg>" --no-color
```

### Always pass `-d`

Without `-d/--duration` the sampler runs **until interrupted**, which will hang a non-interactive session. Always give it a duration.

```bash
# Sample for 20 seconds, write to an explicit path
flight_profiler 51234 --cmd "perf -d 20 -f /tmp/ranking.svg" --no-color
```

## Options

- `pid` (optional) — process to sample. Defaults to the attached process. Can name a different process in the same container.
- `-d, --duration` — seconds to sample. **Default is unlimited**; always set this.
- `-f, --filepath` — output path. Defaults to `flamegraph.svg` in the current working directory.
- `-r, --rate` — samples per second, default `100`. Raise it for short-lived spikes, lower it to reduce overhead on a busy box.

## Platform notes

- Backed by [py-spy](https://github.com/benfred/py-spy), which is installed as a dependency.
- **macOS requires root.** The command prepends `sudo` itself, so run the whole thing under a shell that can authenticate, or run `flight_profiler` as root.
- Sampling reads the target's memory from outside; it does not instrument or pause the process.

## Output

On success, a single line naming the file that was written:

```
Flamegraph data has been successfully written to /tmp/ranking.svg!
```

On failure, py-spy's stderr is printed verbatim — usually a permissions problem.

### The output is an SVG, not text

Do not try to read the SVG to answer the user's question; it is a rendered graphic and reading it wastes context for no insight. Instead:

1. Report the absolute path and tell the user to open it in a browser
2. If you need the finding yourself, follow up with `trace` on the functions you suspect, or `stack` sampled a few times

A flame graph's width is time: the widest boxes near the top are where the process actually spends CPU.

## Examples

### 1. Survey an unfamiliar slow service

```bash
flight_profiler 51234 --cmd "perf -d 30 -f /tmp/survey.svg" --no-color
```

Sample for half a minute under real traffic, then open the SVG to see which subtree dominates.

### 2. Higher resolution for a short spike

```bash
flight_profiler 51234 --cmd "perf -d 10 -r 500 -f /tmp/spike.svg" --no-color
```

### 3. Sample a sibling process in the same container

```bash
flight_profiler 51234 --cmd "perf 51240 -d 20 -f /tmp/worker.svg" --no-color
```

Useful when you attached to a launcher but want a worker's profile.

## Typical Workflow

```bash
# Step 1: survey the whole process
flight_profiler <pid> --cmd "perf -d 30 -f /tmp/profile.svg" --no-color

# Step 2: the user opens the SVG and names the hot function, or you infer a
#         candidate from repeated stack samples

# Step 3: drill into that function's call tree
flight_profiler <pid> --cmd "trace <module> <function> -n 1" --no-color

# Step 4: confirm the inputs that make it slow
flight_profiler <pid> --cmd "watch <module> <function> -n 3" --no-color
```

## Tips

- Sample while the process is under the load you care about. A flame graph of an idle service shows the idle loop.
- 20–30 seconds is usually enough. Longer runs mostly add resolution to what is already the widest box.
- If the flame graph is dominated by a wait rather than compute, the problem is not CPU — use `stack` to see what the threads are blocked on, and `gilstat` if you suspect lock contention.
- Write to an absolute path under `/tmp`. The default is relative to the profiler's working directory, which may not be where you expect.

## Related Commands

- **flight-profiler-trace** — call tree with timings for one function, once you know which
- **flight-profiler-stack** — what every thread is doing right now, including blocked ones
- **flight-profiler-gilstat** — GIL contention, when threads are waiting rather than computing

## Source Files

- `flight_profiler/plugins/perf/cli_plugin_perf.py`
- `flight_profiler/plugins/perf/perf_parser.py`
