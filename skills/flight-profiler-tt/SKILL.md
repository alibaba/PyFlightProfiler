---
name: flight-profiler-tt
description: Time tunnel — record method invocations in a running process, then list, inspect and replay them afterwards. Use for intermittent failures where you cannot be watching at the moment they happen.
---

# flight-profiler-tt

Record invocations of a method into numbered time fragments, then inspect or replay any of them later. Where `watch` shows you a call as it happens, `tt` keeps a history you can come back to.

That difference is the whole point: intermittent bugs do not occur while you are looking. Record with a filter, walk away, then examine the calls that matched.

> **Prerequisites:** Read the **flight-profiler-attach** skill first for platform requirements, installation, permissions, and connection details.

## When to Use

- A failure happens occasionally and you cannot watch for it live
- You want to compare several invocations against each other, not just see one
- You need to re-run a specific past call with its original arguments
- One request in a thousand is slow and you want to catch that one

Use `watch` when the call happens on demand and one sample is enough. Use `tt` when you need history.

## Usage

```bash
# Record
flight_profiler <pid> --cmd "tt -t module [class] method [-n N] [-f <filter>]" --no-color

# Inspect what was recorded
flight_profiler <pid> --cmd "tt -l" --no-color
flight_profiler <pid> --cmd "tt -i <index> [-x N] [-v]" --no-color

# Replay
flight_profiler <pid> --cmd "tt -i <index> -p" --no-color

# Clean up
flight_profiler <pid> --cmd "tt -d <index>" --no-color
flight_profiler <pid> --cmd "tt -da" --no-color
```

## Options

### Recording

- `-t, --time_tunnel module [class] method` — start recording the named method.
- `-n, --limits` — stop after this many invocations. **Default 50.**
- `-f, --filter` — only record matching invocations. The expression sees `target`, `return_obj`, `cost` (ms) and `args`/`kwargs`, e.g. `cost>100` or `return_obj['success']==False`. No spaces.
- `-nm, --nested-method` — also record a method nested inside the target, depth 1.

### Inspecting

- `-l, --list` — list recorded fragments with their indexes.
- `-i, --index` — show one fragment in detail.
- `-x, --expand` — object tree depth, 1–6, default 1.
- `-v, --verbose` — expand every nested item in lists and dicts.
- `-r, --raw` — use `__str__` instead of JSON rendering.

### Managing

- `-p, --play` — replay the fragment at `-i` with its recorded arguments.
- `-d, --delete <index>` — delete one fragment.
- `-da, --delete_all` — delete all fragments.
- `-m, --method` — method locator in `module.class.method` form, with `None` for the class when the method is module-level.

## Recording blocks until the limit is reached

`tt -t` returns once `-n` invocations have been captured. If the method is called rarely — which is usually why you are using `tt` — that wait is long. Always set `-n` explicitly to the smallest number that answers your question, and add a filter so you are not filling the buffer with healthy calls.

Fragments live **inside the target process** and persist between sessions until deleted. Run `tt -da` when you are finished; leaving a large history in a production process wastes memory.

## Replay changes the running process

`-p/--play` actually calls the method again, in the live process, with the recorded arguments. If that method writes to a database, sends a message or mutates shared state, **it will do so again**.

Confirm with the user before replaying anything that is not obviously read-only.

## Examples

### 1. Catch the slow request

```bash
flight_profiler 51234 --cmd "tt -t app.api handle_request -n 5 -f cost>500" --no-color
```

Records only invocations slower than 500 ms, up to five of them.

### 2. Catch the failing one

```bash
flight_profiler 51234 --cmd "tt -t app.api OrderService submit -n 3 -f return_obj['success']==False" --no-color
```

### 3. Review what was captured

```bash
flight_profiler 51234 --cmd "tt -l" --no-color
flight_profiler 51234 --cmd "tt -i 1002 -x 3" --no-color
```

### 4. Replay a captured call

```bash
flight_profiler 51234 --cmd "tt -i 1002 -p" --no-color
```

### 5. Clean up

```bash
flight_profiler 51234 --cmd "tt -da" --no-color
```

## Typical Workflow

```bash
# Step 1: start a filtered recording targeting the symptom
flight_profiler <pid> --cmd "tt -t <module> <method> -n 5 -f cost>500" --no-color

# Step 2: list what was captured
flight_profiler <pid> --cmd "tt -l" --no-color

# Step 3: inspect the interesting fragments and compare their arguments
flight_profiler <pid> --cmd "tt -i <index> -x 3" --no-color

# Step 4: if the cause is clear, fix the source and hot-reload it
flight_profiler <pid> --cmd "reload <module> <method>" --no-color

# Step 5: delete the history
flight_profiler <pid> --cmd "tt -da" --no-color
```

## Tips

- Filter expressions cannot contain spaces — PyFlightProfiler splits arguments on whitespace with no quote handling. Write `cost>500`, not `cost > 500`.
- A filter that never matches means the recording waits for the full `-n` and then returns nothing. If that happens, loosen the filter and check with `watch` that the method is called at all.
- Comparing a failing fragment against a healthy one is usually faster than reading either in isolation.
- Recorded arguments hold references to real objects. A large recording keeps those objects alive — another reason to delete fragments when done.

## Related Commands

- **flight-profiler-watch** — observe a call as it happens, when one live sample is enough
- **flight-profiler-trace** — the call tree inside a slow invocation
- **flight-profiler-reload** — apply the fix once you have found it

## Source Files

- `flight_profiler/plugins/tt/cli_plugin_tt.py`
- `flight_profiler/plugins/tt/time_tunnel_parser.py`
- `flight_profiler/plugins/tt/time_tunnel_agent.py`
