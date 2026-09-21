---
name: flight-profiler-mem
description: Summarise Python object memory by type in a running process, or diff it over an interval to find a leak. Use when RSS grows without bound or a process is being OOM-killed.
---

# flight-profiler-mem

Summarise what is on the Python heap of a running process, by type, or diff two snapshots taken an interval apart. `summary` answers "what is holding memory"; `diff` answers "what is *growing*".

> **Prerequisites:** Read the **flight-profiler-attach** skill first for platform requirements, installation, permissions, and connection details.

## When to Use

- RSS climbs steadily and the process is eventually OOM-killed
- Memory grows under load and never comes back down
- You want to know whether growth is in application objects or in a library's caches
- You need evidence for a leak before deciding where to look in the code

For CUDA memory use **flight-profiler-torch**; this command only sees the Python heap.

## Usage

```bash
flight_profiler <pid> --cmd "mem summary [--limit N] [--order descending|ascending]" --no-color
flight_profiler <pid> --cmd "mem diff [--interval S] [--limit N] [--order descending|ascending]" --no-color
```

## Options

- `--limit` — number of type rows to show. Default `10`.
- `--order` — `descending` (largest first, the default) or `ascending`.
- `--interval` — **`diff` only**, seconds between the two snapshots. Default `15`.

## `mem summary` — what is on the heap now

```bash
flight_profiler 51234 --cmd "mem summary --limit 20" --no-color
```

Output is a pympler summary table, sorted by total size:

```
                       types |   # objects |   total size
============================ | =========== | ============
                         str |       89231 |      9.42 MB
                        dict |       21044 |      7.11 MB
        app.models.OrderItem |      140233 |      6.03 MB
                        list |        9822 |      2.18 MB
```

Read it as: type name, how many live instances, and the bytes they account for. An application class high in this table with a surprising object count is the usual signature of a leak.

## `mem diff` — what is growing

```bash
flight_profiler 51234 --cmd "mem diff --interval 30 --limit 20" --no-color
```

Takes a snapshot, waits `--interval` seconds, takes another, and prints the difference in the same table shape. Counts and sizes are **deltas**: positive means growth over the window.

Types near zero are noise. A type that gains thousands of objects in 30 seconds and never releases them is your leak.

### It blocks for the full interval

`diff` sleeps for `--interval` seconds **inside the target process** before the second snapshot, so the command does not return until then. Budget for it: with the default the call takes at least 15 seconds, and `--interval 60` takes at least a minute.

## This command is expensive — use it deliberately

Both subcommands call `muppy.get_objects()`, which walks every object the garbage collector knows about. On a large heap this takes real time and holds the GIL while it runs, so the target process stalls.

- Expect a noticeable pause on a process with a large heap
- Prefer `summary` first; only reach for `diff` once you know growth is happening
- Do not run it in a loop against production
- Run it during a period you can afford a stall, not at peak

## Examples

### 1. First look at a process with growing RSS

```bash
flight_profiler 51234 --cmd "mem summary --limit 25" --no-color
```

### 2. Confirm growth and attribute it

```bash
flight_profiler 51234 --cmd "mem diff --interval 60 --limit 25" --no-color
```

A minute is long enough for a slow leak to show above the noise.

### 3. Look at the smallest contributors

```bash
flight_profiler 51234 --cmd "mem summary --order ascending --limit 20" --no-color
```

Rarely what you want, but useful when you suspect a large number of tiny objects.

## Typical Workflow

```bash
# Step 1: what dominates the heap
flight_profiler <pid> --cmd "mem summary --limit 25" --no-color

# Step 2: what is actually growing
flight_profiler <pid> --cmd "mem diff --interval 60 --limit 25" --no-color

# Step 3: for a suspect application class, look at the live instances
flight_profiler <pid> --cmd "vmtool -a getInstances -c <module>.<Class> -n 5" --no-color

# Step 4: find what keeps creating them
flight_profiler <pid> --cmd "watch <module> <factory_function> -n 5" --no-color
```

## Tips

- `str` and `dict` at the top is normal for any Python process; look past them for an *application* type that should not be there in that quantity.
- A leak that shows as growing `dict` alone often means an unbounded cache — check module globals with `getglobal`.
- If RSS grows but this table does not, the memory is not on the Python heap: look at native allocations, CUDA (`torch memory`), or fragmentation.
- Growth that stops when load stops is usually a cache with no eviction rather than a true leak.

## Related Commands

- **flight-profiler-vmtool** — inspect the live instances of a suspect class
- **flight-profiler-getglobal** — read module-level caches and registries
- **flight-profiler-torch** — CUDA memory, which this command cannot see

## Source Files

- `flight_profiler/plugins/mem/cli_plugin_mem.py`
- `flight_profiler/plugins/mem/server_plugin_mem.py`
- `flight_profiler/plugins/mem/mem_parser.py`
