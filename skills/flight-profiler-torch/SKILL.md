---
name: flight-profiler-torch
description: Profile PyTorch operator time on CPU/CUDA and capture CUDA memory snapshots for a function in a running process. Use for inference latency and GPU out-of-memory investigations without restarting the service.
---

# flight-profiler-torch

Profile a PyTorch function in a **running** process: per-operator CPU and CUDA time, or CUDA memory allocation behaviour. Both write files you load in PyTorch's own viewers.

The point of doing this live is that inference services are expensive and slow to restart, and the behaviour you want to measure — a cold cache, a specific batch shape, a memory fragmentation pattern — often does not reproduce in a fresh process.

> **Prerequisites:** Read the **flight-profiler-attach** skill first for platform requirements, installation, permissions, and connection details.

## When to Use

- An inference endpoint's latency is too high and you need the operator breakdown
- You need to know whether time goes to compute, to H2D/D2H copies, or to Python overhead
- The process hits CUDA OOM and you need to see what is holding memory
- You want to compare GPU behaviour between two batch shapes on a live service

Use `trace` instead for pure-Python call trees. `torch` is for what happens *inside* the operators.

## Usage

Two subcommands.

```bash
# Operator profile -> Chrome trace JSON
flight_profiler <pid> --cmd "torch profile module [class] method [-nm nested] [-f out.json]" --no-color

# CUDA memory -> pickle snapshot
flight_profiler <pid> --cmd "torch memory -s [-f out.pickle]" --no-color
flight_profiler <pid> --cmd "torch memory -r module [class] method [-nm nested] [-f out.pickle]" --no-color
```

## `torch profile`

Wraps the target function and records a PyTorch profile of the next invocation.

- `module` — module name as the target imports it. Use the `module` command to resolve a file path.
- `class` (optional) — omit for a module-level function.
- `method` — function to profile.
- `-nm, --nested-method` — profile a method nested inside the target, depth 1.
- `-f, --filepath` — output path. **Must end in `.json`.** Defaults to `trace.json`.

`torch.cuda.synchronize()` is inserted automatically before and after the call, so CUDA times are real rather than the time taken to enqueue kernels. That synchronisation is also why the measured wall time is slightly higher than in production — read the operator breakdown, not the total.

On success:

```
torch profile info has been written to /tmp/infer.json successfully.
```

### Reading the result

The file is a Chrome trace. It is large and not worth reading as text — report the path and tell the user to open it in one of:

- `chrome://tracing` or [ui.perfetto.dev](https://ui.perfetto.dev)
- TensorBoard with the PyTorch profiler plugin

What to look for: operators sorted by CUDA time, gaps between kernels (Python or H2D/D2H overhead), and `aten::copy_` entries that indicate avoidable transfers.

## `torch memory`

Two modes, and they answer different questions.

### `-s, --snapshot` — what is allocated right now

```bash
flight_profiler <pid> --cmd "torch memory -s -f /tmp/snapshot.pickle" --no-color
```

Dumps the current CUDA caching-allocator state. Use it when the process is already near OOM and you want to see what is resident.

### `-r, --record` — what a function allocates

```bash
flight_profiler <pid> --cmd "torch memory -r module [class] method -f /tmp/during.pickle" --no-color
```

Records allocator activity across one invocation of the named function. Use it to attribute a spike to a specific call.

`-f/--filepath` **must end in `.pickle`**; it defaults to `snapshot.pickle`.

### Recording history must be enabled first

The CUDA allocator only keeps the allocation history these snapshots need if the target process enabled it. If the snapshot comes back empty or the command reports that history is unavailable, the process needs:

```python
from torch.cuda.memory import _record_memory_history
_record_memory_history()
```

That call has to happen **inside the target process**. It cannot be enabled from outside, so either the service already calls it, or you add it and restart — which is the one case where this command cannot avoid a restart.

### Reading the result

Upload the pickle to [pytorch.org/memory_viz](https://pytorch.org/memory_viz), which renders the allocation timeline and the stacks that allocated each block.

## Examples

### 1. Where does inference latency go?

```bash
flight_profiler 51234 --cmd "module /srv/app/model.py" --no-color
# -> app.model

flight_profiler 51234 --cmd "torch profile app.model Predictor forward -f /tmp/forward.json" --no-color
```

### 2. Profile a nested step inside the forward pass

```bash
flight_profiler 51234 --cmd "torch profile app.model Predictor forward -nm encode -f /tmp/encode.json" --no-color
```

### 3. What is holding GPU memory right now?

```bash
flight_profiler 51234 --cmd "torch memory -s -f /tmp/resident.pickle" --no-color
```

### 4. Which call causes the spike?

```bash
flight_profiler 51234 --cmd "torch memory -r app.model Predictor forward -f /tmp/spike.pickle" --no-color
```

## Typical Workflow

```bash
# Step 1: confirm the function is the slow one and see its real inputs
flight_profiler <pid> --cmd "watch <module> <class> forward -n 3" --no-color

# Step 2: get the operator breakdown
flight_profiler <pid> --cmd "torch profile <module> <class> forward -f /tmp/forward.json" --no-color

# Step 3: for an OOM, attribute the allocations
flight_profiler <pid> --cmd "torch memory -r <module> <class> forward -f /tmp/mem.pickle" --no-color

# Step 4: report both paths to the user with what to open them in
```

## Tips

- Both subcommands wait for the **next** invocation of the target function. On an idle service nothing will be written — drive traffic at it, or pick a function that actually runs.
- Write to absolute paths under `/tmp`. Relative paths resolve inside the target process's working directory, which is often not where you expect.
- Profiling adds real overhead and synchronises the device. Do one invocation at a time on a production service.
- The file extensions are enforced: `.json` for `profile`, `.pickle` for `memory`. A wrong extension is rejected before anything is instrumented.
- If the process has no CUDA device, `profile` still reports CPU operator times, which is useful on its own.

## Related Commands

- **flight-profiler-watch** — the function's arguments and wall time, to confirm you picked the right one
- **flight-profiler-trace** — Python-level call tree around the model call
- **flight-profiler-perf** — whole-process flame graph when the bottleneck may not be in PyTorch at all

## Source Files

- `flight_profiler/plugins/torch/cli_plugin_torch.py`
- `flight_profiler/plugins/torch/torch_parser.py`
- `flight_profiler/plugins/torch/torch_agent.py`
