---
name: flight-profiler-watch
description: Display input/output args, return object and cost time of a Python method invocation in a live process. Use this to observe function behavior at runtime — see what arguments go in, what comes back, and how long it takes. This is the most frequently used diagnostic command.
---

# flight-profiler-watch

Display the input/output args, return object and cost time of method invocation. This is the most commonly used command for understanding runtime behavior of a specific function.

> **Prerequisites:** Read the **flight-profiler-attach** skill first for platform requirements, installation, permissions, and connection details.

## When to Use

- You want to see what arguments a function receives and what it returns
- You need to measure how long a specific function call takes
- You want to filter calls by argument values or return values
- You need to catch only exception-throwing invocations
- You want to observe a method's behavior without modifying its source code

## Usage

```
flight_profiler <pid> --cmd "watch module [class] method [options]" --no-color --timeout <seconds>
```

`-n` bounds how many invocations are captured; `--timeout` bounds how long to
wait for them. Always pass both — without a deadline the command blocks forever
when the target function is never called. Exit code `124` means the window
elapsed with no invocation observed, which is a result, not an error.

## Positional Arguments

- `module` — the module name as it would be imported in the target process. For example, if the target code does `from myapp.utils import helper`, then module is `myapp.utils`. PyFlightProfiler locates the module via `importlib.import_module`. If you're unsure of the module name, run a separate command to resolve it first: `flight_profiler <pid> --cmd "module /absolute/path/to/file.py" --no-color`, then use the returned module name here.
- `class` (optional) — class name, omit if the method is a module-level function
- `method` — target method name

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `--expr <value>` | Watch expression. Available variables: `target`, `return_obj`, `*args`, `**kwargs` (note: `cost` is NOT available in expr, only in filter) | `args,kwargs` |
| `-x, --expand <value>` | Object tree expand level (1-4, or -1 for infinity) | `1` |
| `-e, --exception` | Only record when method throws exception | off |
| `-nm, --nested-method <value>` | Watch nested method with depth restrict to 1 | none |
| `-r, --raw` | Use `__str__` (equivalent to `print(obj)`) instead of default JSON serialization | off |
| `-v, --verbose` | Display all nested items in target list or dict (no truncation) | off |
| `-n, --limits <value>` | Max display count, auto-stops after reaching limit | `10` |
| `-f, --filter <value>` | Filter expression. Available variables: `target`, `return_obj`, `cost`, `args`, `kwargs` | none |

## Choosing the Right `--expr`

`--expr` directly controls what you see in the output. **Always match the user's intent to the right expression** — the default `args,kwargs` only shows inputs, not outputs.

| User intent | `--expr` value |
|------------|----------------|
| See input arguments | `args,kwargs` (default) |
| See return value / output | `return_obj` |
| See both input and output | `args,kwargs,return_obj` |
| See input, output, and the object itself | `target,args,kwargs,return_obj` |
| See a specific return field | `return_obj['field_name']` |
| See the class instance (self) | `target` |
| See everything | `target,args,kwargs,return_obj` |

When the user says "input/output", "args and return", "what goes in and comes back", or similar — always use `--expr args,kwargs,return_obj`, never just the default.

## Output Format

Each captured invocation produces output in this format:

```
────────────────────────────────────────────────────────────
✓ 2026-04-19 10:33:36:520 method=__main__.compute cost=2.380133ms is_exp=False result={
  EXPR:   args,kwargs
  TYPE:   <class 'tuple'>
  VALUE:  (
            (25, 26),
            {}
          )
}
```

### Output Fields

| Field | Description |
|-------|-------------|
| `✓` / `✗` | Success or exception indicator |
| Timestamp | When the method was called (yyyy-MM-dd HH:mm:ss:SSS) |
| `method` | Fully qualified method name: `module.method` or `module.class.method` |
| `cost` | Execution time in milliseconds (precision to microseconds) |
| `is_exp` | `True` if the method threw an exception, `False` otherwise |
| `EXPR` | The expression used to extract the displayed value |
| `TYPE` | Python type of the expression result |
| `VALUE` | The expression result, formatted as JSON (or `__str__` if `-r`) |
| `EXCEPTION` | (only when is_exp=True) Full traceback of the exception |

## Examples

### Watch a module-level function (default args,kwargs)

```bash
flight_profiler <pid> --cmd "watch __main__ compute -n 1" --no-color
```

Output:
```
────────────────────────────────────────────────────────────
✓ 2026-04-19 10:33:36:520 method=__main__.compute cost=2.380133ms is_exp=False result={
  EXPR:   args,kwargs
  TYPE:   <class 'tuple'>
  VALUE:  (
            (
              25,
              26
            ),
            {}
          )
}
```

### Watch a module-level function — only return value

```bash
flight_profiler <pid> --cmd "watch __main__ compute --expr return_obj -n 1" --no-color
```

Output:
```
────────────────────────────────────────────────────────────
✓ ... method=__main__.compute cost=2.561092ms is_exp=False result={
  EXPR:   return_obj
  TYPE:   <class 'int'>
  VALUE:  89
}
```

### Watch a function with kwargs

```bash
flight_profiler <pid> --cmd "watch __main__ fetch_data -n 1" --no-color
```

Output — `args` contains positional args, `kwargs` contains keyword args:
```
────────────────────────────────────────────────────────────
✓ ... method=__main__.fetch_data cost=0.010014ms is_exp=False result={
  EXPR:   args,kwargs
  TYPE:   <class 'tuple'>
  VALUE:  (
            (
              "SELECT *"
            ),
            {
              "limit": 5,
              "timeout": 30
            }
          )
}
```

### Watch a class instance method

```bash
flight_profiler <pid> --cmd "watch __main__ UserService get_user -n 1" --no-color
```

Output — for class methods, `self` is automatically stripped from args:
```
────────────────────────────────────────────────────────────
✓ ... method=__main__.UserService.get_user cost=10.342121ms is_exp=False result={
  EXPR:   args,kwargs
  TYPE:   <class 'tuple'>
  VALUE:  (
            (
              46
            ),
            {}
          )
}
```

### Use --expr to see target (self) and return value

```bash
flight_profiler <pid> --cmd "watch __main__ UserService get_user --expr target,return_obj -n 1" --no-color
```

Output — `target` is the class instance (`self`), shown with its attributes:
```
────────────────────────────────────────────────────────────
✓ ... method=__main__.UserService.get_user cost=10.831118ms is_exp=False result={
  EXPR:   target,return_obj
  TYPE:   <class 'tuple'>
  VALUE:  (
            UserService({}),
            {
              "active": True,
              "id": 56,
              "name": "user_56"
            }
          )
}
```

### Use --expr to extract a specific return field

```bash
flight_profiler <pid> --cmd "watch __main__ UserService get_user --expr return_obj['name'] -n 1" --no-color
```

Output:
```
────────────────────────────────────────────────────────────
✓ ... method=__main__.UserService.get_user cost=12.423992ms is_exp=False result={
  EXPR:   return_obj['name']
  TYPE:   <class 'str'>
  VALUE:  "user_68"
}
```

### Watch class method with expanded output

```bash
flight_profiler <pid> --cmd "watch __main__ UserService get_user --expr return_obj -x 2 -n 1" --no-color
```

Output:
```
────────────────────────────────────────────────────────────
✓ ... method=__main__.UserService.get_user cost=12.030125ms is_exp=False result={
  EXPR:   return_obj
  TYPE:   <class 'dict'>
  VALUE:  {
            "active": True,
            "id": 81,
            "name": "user_81"
          }
}
```

### Capture exceptions with -e

```bash
flight_profiler <pid> --cmd "watch __main__ UserService delete_user -e -n 1" --no-color
```

Output — note `✗`, `is_exp=True`, and the `EXCEPTION` field:
```
────────────────────────────────────────────────────────────
✗ ... method=__main__.UserService.delete_user cost=0.024080ms is_exp=True result={
  EXPR:       args,kwargs
  TYPE:       <class 'tuple'>
  VALUE:      (
                (
                  58
                ),
                {}
              )
  EXCEPTION:  Traceback (most recent call last):
                ...
                File "watch_demo_script.py", line 11, in delete_user
                  raise ValueError(f"Cannot delete user {user_id}")
              ValueError: Cannot delete user 58
}
```

### Watch with filter — only slow calls

```bash
flight_profiler <pid> --cmd "watch __main__ compute -f cost>10 -n 3" --no-color
```

### Watch with filter — by argument value

```bash
flight_profiler <pid> --cmd "watch __main__ compute -f args[0]>2 -n 1" --no-color
```

### Watch nested inner function with -nm

```bash
flight_profiler <pid> --cmd "watch __main__ UserService nested_outer -nm inner_calc -n 1" --no-color
```

Output — method shows the full path including nested function name:
```
────────────────────────────────────────────────────────────
✓ ... method=__main__.UserService.nested_outer.inner_calc cost=0.071049ms is_exp=False result={
  EXPR:   args,kwargs
  TYPE:   <class 'tuple'>
  VALUE:  (
            (),
            {}
          )
}
```

### Raw mode -r (use `__str__` instead of JSON serialization)

```bash
flight_profiler <pid> --cmd "watch __main__ compute -r -n 1" --no-color
```

Output — VALUE uses `__str__` (like `print(obj)`) instead of default JSON serialization:
```
────────────────────────────────────────────────────────────
✓ ... method=__main__.compute cost=2.539158ms is_exp=False result={
  EXPR:   args,kwargs
  TYPE:   <class 'tuple'>
  VALUE:  ((82, 83), {})
}
```

## `--expr` Expression Guide

The `--expr` option controls **what data is displayed** for each invocation. It accepts any valid Python expression.

**Available variables:**
- `target` — the class instance (`self`) for class methods; `None` for module-level functions
- `return_obj` — the method's return value (`None` if exception was thrown)
- `*args` — positional arguments (for class methods, `self` is already stripped)
- `**kwargs` — keyword arguments

**Note:** `cost` is NOT available in `--expr`. Use `-f` filter to filter by cost.

**Common patterns:**
```bash
# Default: see all args and kwargs
--expr args,kwargs

# See only return value
--expr return_obj

# See args and return value together
--expr args,return_obj

# Extract a specific field from return value
--expr return_obj['key']

# Extract nested field
--expr return_obj['data']['items']

# See the class instance (self)
--expr target

# Combine target and return
--expr target,return_obj

# Use Python expressions
--expr len(args[0])
--expr type(return_obj)
```

## `-f` Filter Guide

The `-f` option controls **which invocations are displayed**. Only invocations where the filter expression evaluates to `True` are shown.

**Available variables:**
- `target` — the class instance (or `None`)
- `return_obj` — the return value
- `cost` — execution time in **milliseconds**
- `args` — positional arguments tuple
- `kwargs` — keyword arguments dict

**Common patterns:**
```bash
# Filter by execution time (cost in ms)
-f cost>10
-f cost>100

# Filter by argument value
-f args[0]>100
-f args[0]=="hello"
-f args[0]["query"]=="SELECT *"

# Filter by return value
-f return_obj is not None
-f return_obj['success']==True
-f len(return_obj)>0

# Filter by kwargs
-f kwargs.get('debug')==True

# Combine conditions
-f cost>10 and args[0]>0
-f return_obj is not None and cost<5
```

## Troubleshooting: No Output

If watch produces no output, the most likely reason is **the target method is not being called** during the observation window. Before concluding there's a problem:

1. **Confirm the method is on the active call path** — make sure the code path that invokes the target method is actually being triggered (e.g., send a request, trigger the workflow)
2. **Check the module name** — use the `module` command to verify the correct module name if unsure
3. **Check for filter issues** — if using `-f`, the filter might be too restrictive. Try without `-f` first
4. **Check `-n` limits** — if limits was reached in a previous watch, the method may already be unwatched

## Handling Command Output

- **Long output**: if the output is too long to display inline, redirect it to a file for the user to review later:
  ```bash
  flight_profiler <pid> --cmd "watch __main__ compute -n 5" --no-color > /tmp/watch_output.txt
  ```
- **Short output**: if the output is brief (e.g., `-n 1` capturing a single invocation), display the full result directly to the user so they can see the most relevant information immediately. If multiple invocations were captured, showing just one representative case is sufficient.

## Handling Large Objects

When an object is too large to serialize or the output is truncated/incomplete:

1. **Prefer minimal extraction** — use `--expr` to extract only the fields you need, instead of the entire object:
   ```bash
   # Instead of serializing the entire return object:
   --expr return_obj
   # Extract only the field you care about:
   --expr return_obj['status']
   --expr return_obj['data']['id']
   --expr type(return_obj),len(return_obj)
   ```

2. **Use `-v` (verbose)** — if you do need the full object, add `-v` to disable truncation so all nested items in lists/dicts are shown completely.

## Tips

- The `-f` filter runs inside the target process so it can reference live objects
- The `--expr` option controls what gets printed; the `-f` option controls which invocations get printed
- `cost` is only available in `-f` filter, not in `--expr`
- For class methods, `self` is automatically stripped from `args` — use `target` to access the instance
- Use `-x 2` or `-x 3` to expand nested objects in the output (max 4, or -1 for infinity)
- `-r` (raw) uses `__str__` (like `print(obj)`) instead of JSON serialization — useful when objects have custom `__str__` or you want the native Python representation
- `-v` (verbose) shows all items in lists/dicts without truncation

## Related Commands

- **trace** — shows full call tree with timing (drill into sub-calls)
- **reload** — hot-patch a function after editing its source file, without restarting the process. Use watch to inspect internal behavior before/after reload when you need to observe arguments, return values, or timing changes that aren't visible from normal program output
- **getglobal** — inspect a specific global/static field value without watching calls

## Source Files

- CLI plugin: `flight_profiler/plugins/watch/cli_plugin_watch.py`
- Parser: `flight_profiler/plugins/watch/watch_parser.py`
- Server plugin: `flight_profiler/plugins/watch/server_plugin_watch.py`
