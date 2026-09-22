---
name: flight-profiler-trace
description: Trace execution time of Python method invocations in a live process with call stack visualization. Use this to see a hierarchical call tree showing which sub-calls are slow and where time is spent within a function.
---

# flight-profiler-trace

Trace the execution time of a specified method invocation, displaying a call tree with timing. Unlike `watch` which shows individual invocations, `trace` reveals the full call hierarchy underneath a function — making it ideal for finding which sub-call is the bottleneck.

> **Prerequisites:** Read the **flight-profiler-attach** skill first for platform requirements, installation, permissions, and connection details.

## When to Use

- You want to find which sub-call inside a function is slow
- You need a hierarchical view of function execution with timing at each level
- You want to filter out fast calls and only see slow ones (via `-i` interval threshold)
- You need to understand the call chain depth of a specific function

## Usage

```
flight_profiler <pid> --cmd "trace module [class] method [options]" --no-color --timeout <seconds>
```

`-n` bounds how many invocations are captured; `--timeout` bounds how long to
wait for them. Always pass both — without a deadline the command blocks forever
when the target function is never called. Exit code `124` means the window
elapsed with no invocation observed, which is a result, not an error.

## Positional Arguments

- `module` — the module name as it would be imported in the target process. For example, if the target code does `from myapp.utils import helper`, then module is `myapp.utils`. PyFlightProfiler locates the module via `importlib.import_module`. If you're unsure of the module name, run a separate command to resolve it first: `flight_profiler <pid> --cmd "module /absolute/path/to/file.py" --no-color`, then use the returned module name here.
- `class` (optional) — class name, omit if module-level function
- `method` — target method name

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `-i, --interval <value>` | Only display sub-calls costing more than N milliseconds. Calls below this threshold are hidden from the tree. | `0.1` |
| `-et, --entrance_time <value>` | Only display invocations where the entrance (top-level) cost exceeds N milliseconds. Invocations below this threshold are silently skipped. | `0` |
| `-d, --depth <value>` | Limit call tree display depth. `-d 2` shows only direct children of the traced method. When set, ignores `-i` interval. | `-1` (unlimited) |
| `-nm, --nested-method <value>` | Trace a nested (inner) function defined inside the target method. Depth is restricted to 1. | none |
| `-n, --limits <value>` | Maximum number of invocations to capture before stopping | `10` |
| `-f, --filter_expr <value>` | Filter expression on `(target, *args, **kwargs)`. Only invocations where the expression is truthy are traced. For class methods, `args[0]` is `self`. | none |

## Output Format

Each captured invocation produces a block:

```
────────────────────────────────────────────────────────────
🔍 2026-04-19 11:35:38:953 thread=MainThread tid=8722965056 daemon=False cost=90.003ms
[90.003ms] process_order    trace_demo_script.py:6
├─ [5.574ms] validate    trace_demo_script.py:13
│  └─ [5.52ms]  sleep    <built-in>
├─ [31.402ms] compute_price    trace_demo_script.py:16
│  ├─ [21.285ms]  sleep    <built-in>
│  └─ [10.074ms] apply_discount    trace_demo_script.py:20
│     └─ [10.049ms]  sleep    <built-in>
└─ [52.99ms] save_to_db    trace_demo_script.py:23
   └─ [52.949ms]  sleep    <built-in>
```

**Title line fields:**

| Field | Description |
|-------|-------------|
| `🔍` | trace command icon |
| Timestamp | When the entrance method was called |
| `thread` | Thread name that executed the method |
| `tid` | Thread ID |
| `daemon` | Whether the thread is a daemon thread |
| `cost` | Total execution time of the entrance method (milliseconds) |

**Call tree fields (each line):**

| Field | Description |
|-------|-------------|
| `[Nms]` | Execution time of that specific call. Color-coded in terminal: >50% of parent = red, >20% = yellow, >5% = green, else faint green |
| Method name | Function name. `[await]` prefix indicates an async await point |
| Location | `filename:lineno` for Python methods, `<built-in>` for C extension methods |

**Tree structure:** `├─` / `└─` show child calls, `│` connects sibling levels.

## Examples

### 1. Class method — full call tree

Shows the complete hierarchy with all sub-calls and their timing:

```bash
flight_profiler <pid> --cmd "trace __main__ OrderService process_order -n 1" --no-color
```

```
🔍 2026-04-19 11:35:38:953 thread=MainThread tid=8722965056 daemon=False cost=90.003ms
[90.003ms] process_order    trace_demo_script.py:6
├─ [5.574ms] validate    trace_demo_script.py:13
│  └─ [5.52ms]  sleep    <built-in>
├─ [31.402ms] compute_price    trace_demo_script.py:16
│  ├─ [21.285ms]  sleep    <built-in>
│  └─ [10.074ms] apply_discount    trace_demo_script.py:20
│     └─ [10.049ms]  sleep    <built-in>
└─ [52.99ms] save_to_db    trace_demo_script.py:23
   └─ [52.949ms]  sleep    <built-in>
```

Reading: `save_to_db` takes 52.99ms (59% of total) — the dominant bottleneck. `compute_price` takes 31.4ms including its child `apply_discount`.

### 2. Module-level function

```bash
flight_profiler <pid> --cmd "trace __main__ compute -n 1" --no-color
```

```
🔍 2026-04-19 11:35:42:462 thread=MainThread tid=8722965056 daemon=False cost=21.672ms
[21.672ms] compute    trace_demo_script.py:43
├─ [10.104ms]  sleep    <built-in>
├─ [6.298ms] helper    trace_demo_script.py:48
│  └─ [6.269ms]  sleep    <built-in>
└─ [5.217ms] helper    trace_demo_script.py:48
   └─ [5.184ms]  sleep    <built-in>
```

### 3. Limit depth with `-d`

`-d 2` shows only the entrance method and its direct children — hides deeper calls:

```bash
flight_profiler <pid> --cmd "trace __main__ OrderService process_order -d 2 -n 1" --no-color
```

```
🔍 2026-04-19 11:35:51:448 thread=MainThread tid=8722965056 daemon=False cost=90.374ms
[90.374ms] process_order    trace_demo_script.py:6
├─ [6.282ms] validate    trace_demo_script.py:13
├─ [31.704ms] compute_price    trace_demo_script.py:16
└─ [52.336ms] save_to_db    trace_demo_script.py:23
```

Useful for getting an overview of the top-level breakdown without noise from deeper calls.

### 4. Interval threshold with `-i`

`-i 10` hides sub-calls costing less than 10ms. `validate` (5ms) is hidden:

```bash
flight_profiler <pid> --cmd "trace __main__ OrderService process_order -i 10 -n 1" --no-color
```

```
🔍 2026-04-19 11:35:52:586 thread=MainThread tid=8722965056 daemon=False cost=92.380ms
[92.38ms] process_order    trace_demo_script.py:6
├─ [35.176ms] compute_price    trace_demo_script.py:16
│  ├─ [22.783ms]  sleep    <built-in>
│  └─ [12.343ms] apply_discount    trace_demo_script.py:20
│     └─ [12.313ms]  sleep    <built-in>
└─ [50.889ms] save_to_db    trace_demo_script.py:23
   └─ [50.844ms]  sleep    <built-in>
```

### 5. Entrance time threshold with `-et`

`-et 50` silently skips entire invocations where total cost < 50ms. Only invocations costing >= 50ms are captured. Unlike `-i` which filters sub-calls within a tree, `-et` filters the entire invocation.

```bash
flight_profiler <pid> --cmd "trace __main__ OrderService process_order -et 50 -n 1" --no-color
```

If the method typically takes 90ms, output appears normally. If an invocation only takes 30ms, it is silently dropped and does not count toward `-n`.

### 6. Nested method with `-nm`

Traces an inner function defined inside the target method. Depth is restricted to 1:

```bash
flight_profiler <pid> --cmd "trace __main__ OrderService nested_outer -nm inner_work -n 1" --no-color
```

```
🔍 2026-04-19 11:36:04:093 thread=MainThread tid=8722965056 daemon=False cost=12.526ms
[12.526ms] inner_work    trace_demo_script.py:27
└─ [12.511ms]  sleep    <built-in>
```

Note: the spy message shows `nested_outer.inner_work`, confirming the nested method was found.

### 7. Deep call chain

Automatically follows the full call chain depth:

```bash
flight_profiler <pid> --cmd "trace __main__ OrderService deep_call_a -n 1" --no-color
```

```
🔍 2026-04-19 11:36:05:247 thread=MainThread tid=8722965056 daemon=False cost=6.294ms
[6.294ms] deep_call_a    trace_demo_script.py:32
└─ [6.291ms] deep_call_b    trace_demo_script.py:35
   └─ [6.287ms] deep_call_c    trace_demo_script.py:38
      └─ [6.268ms]  sleep    <built-in>
```

### 8. Filter with `-f`

Only trace invocations matching the filter expression. For module-level functions, `args[0]` is the first argument:

```bash
flight_profiler <pid> --cmd "trace __main__ compute -f 'args[0]>=1' -n 1" --no-color
```

```
🔍 2026-04-19 11:37:42:600 thread=MainThread tid=8722965056 daemon=False cost=24.215ms
[24.215ms] compute    trace_demo_script.py:43
├─ [12.534ms]  sleep    <built-in>
├─ [6.314ms] helper    trace_demo_script.py:48
│  └─ [6.286ms]  sleep    <built-in>
└─ [5.321ms] helper    trace_demo_script.py:48
   └─ [5.303ms]  sleep    <built-in>
```

For class methods, `args[0]` is `self`, so use `args[1]` for the first real argument.

## `-i` / `-et` / `-d` Guide

These three options control what appears in the output at different levels:

| Option | What it filters | Effect |
|--------|----------------|--------|
| `-i` (interval) | Individual sub-calls in the tree | Hides branches where the call cost < N ms. The invocation is still captured, just with fewer branches shown. |
| `-et` (entrance_time) | Entire invocations | Silently skips invocations where the total entrance cost < N ms. Does not count toward `-n`. |
| `-d` (depth) | Tree depth | Truncates the tree at N levels. When set, `-i` is ignored. |

**Common combinations:**

```bash
# Show only slow invocations, then only their expensive sub-calls
trace __main__ MyClass method -et 100 -i 10 -n 3

# Quick overview: just the top-level breakdown
trace __main__ MyClass method -d 2 -n 1

# Catch everything (debug mode)
trace __main__ MyClass method -i 0 -n 1
```

## Troubleshooting: No Output

If trace produces no output:

1. **Method not being called** — make sure the code path is actually being triggered
2. **Wrong module name** — use `flight_profiler <pid> --cmd "module /path/to/file.py" --no-color` to verify
3. **`-et` too high** — invocations below the threshold are silently skipped (try `-et 0`)
4. **`-i` too high** — sub-calls below the threshold are hidden (try `-i 0`)

## Handling Command Output

- **Long output**: trace call trees can be very deep. If the output is too long to display inline, redirect it to a file for the user to review later:
  ```bash
  flight_profiler <pid> --cmd "trace __main__ handle_request -n 1" --no-color > /tmp/trace_output.txt
  ```
- **Short output**: if the output is brief (e.g., `-n 1 -d 2` capturing a shallow tree), display the full result directly to the user. If multiple traces were captured, showing just one representative case is sufficient.

## Tips

- Start with `-d 2 -n 1` for a quick overview, then remove `-d` to see the full tree
- Use `-i 10` to focus on sub-calls taking > 10ms, lowering as needed to zoom in
- Combine with `watch` to first identify a slow function, then `trace` to find the bottleneck inside it
- Use `-et` to skip uninteresting fast invocations when the method is called frequently

## Related Commands

- **watch** — observe individual function calls (args/return/cost), without call tree
- **reload** — hot-patch a function after editing its source file, without restarting the process. Use trace to inspect call tree timing before/after reload when you need to verify performance improvements that aren't visible from normal program output
- **perf** — generate flamegraph for broader performance overview via sampling

## Source Files

- CLI plugin: `flight_profiler/plugins/trace/cli_plugin_trace.py`
- Parser: `flight_profiler/plugins/trace/trace_parser.py`
- Server plugin: `flight_profiler/plugins/trace/server_plugin_trace.py`
