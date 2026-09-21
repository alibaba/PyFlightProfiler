"""The tool catalogue exposed over MCP.

Each entry declares its JSON Schema once and builds the matching PyFlightProfiler
command from validated arguments, so an MCP client gets typed parameters instead
of having to compose a command line from prose.

Two properties of the catalogue are deliberate.

*Naming is normalised.* The CLI spells the module argument ``--pkg`` for `watch`
and ``--mod`` for `trace`, `getglobal` and `reload`. Every tool here takes
``module``, and each builds whichever flag its command actually wants.

*Mutating tools are separated.* `reload` rewrites a live function, `vmtool` can
invoke methods on live instances, and the raw escape hatch can run anything.
An agent calling tools on its own should not reach those by default, so the
server only advertises them when explicitly started with ``--allow-mutating``.
"""

import re

from flight_profiler.mcp.target import list_python_processes, resolve_target

# The command tokenizer in flight_profiler.utils.args_util splits on whitespace
# and has no notion of shell quoting, so a value containing a space would be
# silently torn into two arguments. Reject it here with a clear message instead.
_WHITESPACE = re.compile(r"\s")
_MODULE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_OUTPUT_CHARS = 20000


class ToolError(Exception):
    """An argument the tool cannot turn into a valid command."""


def _require(arguments, name):
    value = arguments.get(name)
    if value is None or value == "":
        raise ToolError(f"{name} is required")
    return value


def _check_module(value, name="module"):
    if not _MODULE_NAME.match(str(value)):
        raise ToolError(
            f"{name} must be an importable module path such as 'app.services.order' "
            f"or '__main__', got {value!r}. Use the `module` tool to turn a file "
            f"path into a module name."
        )
    return value


def _check_identifier(value, name):
    if not _IDENTIFIER.match(str(value)):
        raise ToolError(f"{name} must be a Python identifier, got {value!r}")
    return value


def _check_expression(value, name):
    if _WHITESPACE.search(str(value)):
        raise ToolError(
            f"{name} cannot contain spaces -- PyFlightProfiler splits command "
            f"arguments on whitespace. Write {value!r} without spaces."
        )
    return value


def _append(parts, flag, value):
    if value is not None:
        parts.extend([flag, str(value)])


def _append_switch(parts, flag, value):
    if value:
        parts.append(flag)


class Tool:
    """A tool answered locally by the server, without attaching to anything."""

    mutating = False

    def __init__(self, name, description, properties, required, handler):
        self.name = name
        self.description = description
        self.properties = properties
        self.required = required
        self.handler = handler

    def schema(self):
        return {
            "type": "object",
            "properties": dict(self.properties),
            "required": list(self.required),
        }

    def run(self, arguments, execute):
        return self.handler(arguments)


class ProfilerTool(Tool):
    """A tool that attaches to a target process and runs one command."""

    def __init__(self, name, description, properties, required, build_command,
                 mutating=False):
        super().__init__(name, description, properties, required, handler=None)
        self.build_command = build_command
        self.mutating = mutating

    def schema(self):
        properties = {
            "pid": {
                "type": "integer",
                "description": "PID of the target Python process.",
            },
        }
        properties.update(self.properties)
        properties["timeout_seconds"] = {
            "type": "number",
            "description": (
                "Stop after this many seconds. Streaming commands only return once "
                "their capture limit is reached, so a deadline is what prevents an "
                "idle target from blocking the call."
            ),
            "default": DEFAULT_TIMEOUT_SECONDS,
            "minimum": 1,
        }
        properties["max_output_chars"] = {
            "type": "integer",
            "description": "Trim output longer than this, keeping head and tail.",
            "default": DEFAULT_MAX_OUTPUT_CHARS,
            "minimum": 0,
        }
        return {
            "type": "object",
            "properties": properties,
            "required": ["pid"] + list(self.required),
        }

    def run(self, arguments, execute):
        pid = arguments.get("pid")
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            raise ToolError(f"pid must be a positive integer, got {pid!r}")
        return execute(
            pid=pid,
            command=self.build_command(arguments),
            timeout_seconds=arguments.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            max_output_chars=arguments.get("max_output_chars", DEFAULT_MAX_OUTPUT_CHARS),
        )


# --------------------------------------------------------------------------
# Local tools
# --------------------------------------------------------------------------


def _handle_list_processes(arguments):
    processes = list_python_processes(arguments.get("name_filter"))
    if not processes:
        return "No matching Python processes found."
    lines = [f"{len(processes)} Python process(es):", ""]
    for entry in processes:
        note = "" if entry["runs_interpreter"] else "  (matched on its arguments only)"
        lines.append(f"pid {entry['pid']}  user {entry['user']}{note}")
        lines.append(f"  {entry['command']}")
    lines.append("")
    lines.append(
        "Frameworks that fork workers (gunicorn, uvicorn, celery, vLLM) run request "
        "handling in a child process, so the launcher is usually the wrong target. "
        "Confirm a candidate with check_attach_target before running diagnostics."
    )
    return "\n".join(lines)


def _handle_check_target(arguments):
    pid = _require(arguments, "pid")
    return resolve_target(pid).describe()


# --------------------------------------------------------------------------
# Command builders
# --------------------------------------------------------------------------


def _build_stack(arguments):
    parts = ["stack"]
    _append_switch(parts, "-a", arguments.get("async_stacks"))
    _append_switch(parts, "--native", arguments.get("native"))
    return " ".join(parts)


def _build_watch(arguments):
    parts = ["watch", "--pkg", _check_module(_require(arguments, "module"))]
    if arguments.get("class_name"):
        _append(parts, "--cls", _check_identifier(arguments["class_name"], "class_name"))
    _append(parts, "--func", _check_identifier(_require(arguments, "function"), "function"))
    if arguments.get("nested_method"):
        _append(parts, "-nm", _check_identifier(arguments["nested_method"], "nested_method"))
    if arguments.get("expression"):
        _append(parts, "--expr", _check_expression(arguments["expression"], "expression"))
    if arguments.get("filter_expression"):
        _append(parts, "-f", _check_expression(arguments["filter_expression"], "filter_expression"))
    _append(parts, "-n", arguments.get("limit", 1))
    _append(parts, "-x", arguments.get("expand_level"))
    _append_switch(parts, "-e", arguments.get("only_on_exception"))
    _append_switch(parts, "-v", arguments.get("verbose"))
    return " ".join(parts)


def _build_trace(arguments):
    parts = ["trace", "--mod", _check_module(_require(arguments, "module"))]
    if arguments.get("class_name"):
        _append(parts, "--cls", _check_identifier(arguments["class_name"], "class_name"))
    _append(parts, "--func", _check_identifier(_require(arguments, "function"), "function"))
    if arguments.get("nested_method"):
        _append(parts, "-nm", _check_identifier(arguments["nested_method"], "nested_method"))
    _append(parts, "-n", arguments.get("limit", 1))
    _append(parts, "-d", arguments.get("depth"))
    _append(parts, "-i", arguments.get("min_cost_ms"))
    _append(parts, "-et", arguments.get("min_entrance_ms"))
    if arguments.get("filter_expression"):
        _append(parts, "-f", _check_expression(arguments["filter_expression"], "filter_expression"))
    return " ".join(parts)


def _build_getglobal(arguments):
    parts = ["getglobal", "--mod", _check_module(_require(arguments, "module"))]
    if arguments.get("class_name"):
        _append(parts, "--cls", _check_identifier(arguments["class_name"], "class_name"))
    _append(parts, "--var", _check_identifier(_require(arguments, "variable"), "variable"))
    if arguments.get("expression"):
        _append(parts, "-e", _check_expression(arguments["expression"], "expression"))
    _append(parts, "-x", arguments.get("expand_level"))
    _append_switch(parts, "-v", arguments.get("verbose"))
    return " ".join(parts)


def _build_module(arguments):
    path = _require(arguments, "file_path")
    if _WHITESPACE.search(str(path)):
        raise ToolError(f"file_path cannot contain spaces, got {path!r}")
    return f"module {path}"


def _build_vmtool(arguments):
    parts = ["vmtool", "-a", _check_identifier(_require(arguments, "action"), "action")]
    if arguments.get("class_name"):
        _append(parts, "-c", _check_expression(arguments["class_name"], "class_name"))
    if arguments.get("expression"):
        _append(parts, "-e", _check_expression(arguments["expression"], "expression"))
    _append(parts, "-n", arguments.get("limit"))
    _append(parts, "-x", arguments.get("expand_level"))
    return " ".join(parts)


def _build_reload(arguments):
    parts = ["reload", "--mod", _check_module(_require(arguments, "module"))]
    if arguments.get("class_name"):
        _append(parts, "--cls", _check_identifier(arguments["class_name"], "class_name"))
    _append(parts, "--func", _check_identifier(_require(arguments, "function"), "function"))
    _append_switch(parts, "-v", arguments.get("verbose"))
    return " ".join(parts)


def _build_raw(arguments):
    command = _require(arguments, "command")
    if "\n" in str(command):
        raise ToolError("command must be a single line")
    return str(command)


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------

_MODULE_PROPERTY = {
    "type": "string",
    "description": (
        "Module path as the target process would import it, e.g. 'app.services.order' "
        "or '__main__'. Use the `module` tool to convert a file path."
    ),
}
_CLASS_PROPERTY = {
    "type": "string",
    "description": "Class name. Omit for a module-level function.",
}
_LIMIT_PROPERTY = {
    "type": "integer",
    "description": "Stop after this many captured invocations.",
    "default": 1,
    "minimum": 1,
}


def build_catalogue():
    """Return every tool the server knows about, mutating ones included."""
    return [
        Tool(
            name="list_python_processes",
            description=(
                "List the Python processes running on this machine, with their PID, "
                "owner and full command line. Start here when the user names a service "
                "or script rather than a PID."
            ),
            properties={
                "name_filter": {
                    "type": "string",
                    "description": "Case-insensitive substring of the command line.",
                }
            },
            required=[],
            handler=_handle_list_processes,
        ),
        Tool(
            name="check_attach_target",
            description=(
                "Check whether PyFlightProfiler can attach to a PID: resolves the "
                "process's Python interpreter and confirms flight_profiler is "
                "installed in that same environment. Run this before the first "
                "diagnostic command against an unfamiliar process -- a mismatched "
                "environment is the most common cause of attach failures, and this "
                "returns the exact install command to fix it."
            ),
            properties={"pid": {"type": "integer", "description": "PID to check."}},
            required=["pid"],
            handler=_handle_check_target,
        ),
        ProfilerTool(
            name="stack",
            description=(
                "Show the Python stack of every thread in the process, optionally with "
                "native frames and async task stacks. The fastest way to see what a "
                "process is doing right now, and the tool of choice for hangs, "
                "deadlocks and stuck coroutines. Also useful for confirming you picked "
                "the right process: the frames name the files the process is running."
            ),
            properties={
                "async_stacks": {
                    "type": "boolean",
                    "description": "Include async coroutine and task stacks.",
                    "default": False,
                },
                "native": {
                    "type": "boolean",
                    "description": "Include native C frames. Linux only.",
                    "default": False,
                },
            },
            required=[],
            build_command=_build_stack,
        ),
        ProfilerTool(
            name="watch",
            description=(
                "Observe a function at runtime: its arguments, return value, exception "
                "and wall time, captured the next time it is called. Use when you need "
                "to know what data a function actually sees in production. Returns once "
                "`limit` invocations are captured or the deadline passes -- a deadline "
                "with no capture means the function was not called."
            ),
            properties={
                "module": _MODULE_PROPERTY,
                "class_name": _CLASS_PROPERTY,
                "function": {"type": "string", "description": "Function or method name."},
                "expression": {
                    "type": "string",
                    "description": (
                        "What to capture, e.g. 'args,kwargs', 'return_obj', "
                        "'target.state'. Defaults to arguments. Cannot contain spaces."
                    ),
                },
                "filter_expression": {
                    "type": "string",
                    "description": (
                        "Only capture invocations matching this expression, e.g. "
                        "\"args[0]=='abc'\". Cannot contain spaces."
                    ),
                },
                "nested_method": {
                    "type": "string",
                    "description": "Watch a method nested inside the target function.",
                },
                "limit": _LIMIT_PROPERTY,
                "expand_level": {
                    "type": "integer",
                    "description": "Object tree depth to render, 1-4.",
                    "minimum": 1,
                    "maximum": 4,
                },
                "only_on_exception": {
                    "type": "boolean",
                    "description": "Only capture invocations that raise.",
                    "default": False,
                },
                "verbose": {
                    "type": "boolean",
                    "description": "Expand every nested item in lists and dicts.",
                    "default": False,
                },
            },
            required=["module", "function"],
            build_command=_build_watch,
        ),
        ProfilerTool(
            name="trace",
            description=(
                "Trace a function's internal call tree with per-call timings, to find "
                "which sub-call inside a slow function is responsible. Use after `watch` "
                "has shown that a function is slow but not why."
            ),
            properties={
                "module": _MODULE_PROPERTY,
                "class_name": _CLASS_PROPERTY,
                "function": {"type": "string", "description": "Function or method name."},
                "limit": _LIMIT_PROPERTY,
                "depth": {
                    "type": "integer",
                    "description": "Only show calls this many levels deep or less.",
                    "minimum": 1,
                },
                "min_cost_ms": {
                    "type": "number",
                    "description": "Hide calls faster than this, in milliseconds.",
                    "minimum": 0,
                },
                "min_entrance_ms": {
                    "type": "number",
                    "description": "Only trace when the outer call exceeds this, in ms.",
                    "minimum": 0,
                },
                "nested_method": {
                    "type": "string",
                    "description": "Trace a method nested inside the target function.",
                },
                "filter_expression": {
                    "type": "string",
                    "description": "Only trace invocations matching this expression.",
                },
            },
            required=["module", "function"],
            build_command=_build_trace,
        ),
        ProfilerTool(
            name="getglobal",
            description=(
                "Read a module-level global or a class static attribute from the live "
                "process. Read-only, so it is the safe way to check what configuration, "
                "feature flags or cached state a running service actually holds -- which "
                "is often not what the config file on disk says."
            ),
            properties={
                "module": _MODULE_PROPERTY,
                "class_name": {
                    "type": "string",
                    "description": "Class name, for a static attribute.",
                },
                "variable": {"type": "string", "description": "Variable name."},
                "expression": {
                    "type": "string",
                    "description": "Sub-expression on the value, e.g. \"target['key']\".",
                },
                "expand_level": {
                    "type": "integer",
                    "description": "Object tree depth to render, 1-6.",
                    "minimum": 1,
                    "maximum": 6,
                },
                "verbose": {
                    "type": "boolean",
                    "description": "Expand every nested item in lists and dicts.",
                    "default": False,
                },
            },
            required=["module", "variable"],
            build_command=_build_getglobal,
        ),
        ProfilerTool(
            name="module",
            description=(
                "Resolve a source file path to the module name the target process "
                "imports it as. Every other tool takes a module name, so use this "
                "whenever you have a path from the user or from a stack frame."
            ),
            properties={
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to a .py file.",
                }
            },
            required=["file_path"],
            build_command=_build_module,
        ),
        ProfilerTool(
            name="vmtool",
            description=(
                "Find live instances of a class and inspect their attributes, or invoke "
                "a method on them. Invoking runs code inside the target process, so "
                "this tool can change program state."
            ),
            properties={
                "action": {
                    "type": "string",
                    "description": "Action to run, e.g. 'getInstances', 'forceGc'.",
                },
                "class_name": {
                    "type": "string",
                    "description": "Fully qualified class, e.g. 'app.models.User'.",
                },
                "expression": {
                    "type": "string",
                    "description": "Expression over the found instances.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum instances to show, -1 for all.",
                },
                "expand_level": {
                    "type": "integer",
                    "description": "Object tree depth to render, 1-6.",
                    "minimum": 1,
                    "maximum": 6,
                },
            },
            required=["action"],
            build_command=_build_vmtool,
            mutating=True,
        ),
        ProfilerTool(
            name="reload",
            description=(
                "Hot-reload one function in the live process from its updated source on "
                "disk, without a restart. This changes the behaviour of a running "
                "process -- confirm with the user before applying it to anything in "
                "production."
            ),
            properties={
                "module": _MODULE_PROPERTY,
                "class_name": _CLASS_PROPERTY,
                "function": {"type": "string", "description": "Function or method name."},
                "verbose": {
                    "type": "boolean",
                    "description": "Show the reloaded source.",
                    "default": False,
                },
            },
            required=["module", "function"],
            build_command=_build_reload,
            mutating=True,
        ),
        ProfilerTool(
            name="run_profiler_command",
            description=(
                "Run an arbitrary PyFlightProfiler command verbatim, for the commands "
                "without a dedicated tool: perf, mem, gilstat, tt, torch, console, cls. "
                "Run `help` through this tool to list them. Because the command is "
                "unrestricted it can execute code inside the target process."
            ),
            properties={
                "command": {
                    "type": "string",
                    "description": "Command line as typed at the profiler prompt, "
                                   "e.g. 'perf -d 10' or 'mem summary'.",
                }
            },
            required=["command"],
            build_command=_build_raw,
            mutating=True,
        ),
    ]
