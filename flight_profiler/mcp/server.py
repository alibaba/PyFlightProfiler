"""An MCP server exposing PyFlightProfiler to any Model Context Protocol client.

The SKILL.md files added in #29 teach three specific agents to compose
PyFlightProfiler command lines. MCP is the transport the rest of the ecosystem
speaks -- Claude Desktop, Cursor, Windsurf, Cline, Zed, Continue and anything
built on an MCP SDK -- and it carries typed parameter schemas rather than prose,
so a client gets argument validation instead of guessing flag names.

The server speaks JSON-RPC 2.0 over newline-delimited stdio and depends on
nothing outside the standard library, so it runs wherever PyFlightProfiler
already runs.

It shells out to the ``flight_profiler`` CLI rather than importing the plugin
stack, because the CLI has to run from the *target's* Python environment (see
``flight_profiler.mcp.target``). One server can therefore drive processes across
several environments, and every attach, injection and rendering path stays
shared with the interactive client.
"""

import argparse
import json
import sys
import traceback

from flight_profiler.mcp.runner import run_profiler_command
from flight_profiler.mcp.target import resolve_target
from flight_profiler.mcp.tools import ToolError, build_catalogue

SERVER_NAME = "pyflightprofiler"

# Revisions this server implements. The newest is offered when a client asks for
# something unknown, which the spec allows.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _server_version():
    try:
        from importlib.metadata import version

        return version("flight_profiler")
    except Exception:
        return "unknown"


class MCPServer:
    """Dispatches MCP requests onto the PyFlightProfiler tool catalogue."""

    def __init__(self, allow_mutating=False, stdin=None, stdout=None):
        self.allow_mutating = allow_mutating
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout
        self.tools = {tool.name: tool for tool in build_catalogue()}

    # -- tool surface ------------------------------------------------------

    def available_tools(self):
        """Tools this server advertises, honouring the mutating-tool gate."""
        return [
            tool
            for tool in self.tools.values()
            if self.allow_mutating or not tool.mutating
        ]

    def execute_profiler_command(self, pid, command, timeout_seconds, max_output_chars):
        """Run one PyFlightProfiler command against ``pid`` and render the result."""
        target = resolve_target(pid)
        if not target.usable:
            raise ToolError(target.describe())

        argv = target.argv_prefix + [str(pid), "--cmd", command, "--no-color"]
        result = run_profiler_command(argv, timeout_seconds, max_output_chars)

        # Showing the exact command line lets the user reproduce the run by hand
        # and lets the model see which flags its arguments turned into.
        header = f"$ {' '.join(target.argv_prefix)} {pid} --cmd {command!r} --no-color"
        body = result.output.strip() or "(no output)"

        if result.timed_out:
            return (
                f"{header}\n\n{body}\n\n"
                f"[timed out after {timeout_seconds}s] The command stopped before "
                f"capturing everything it was asked for, and any instrumentation it "
                f"installed has been removed. For watch and trace this usually means "
                f"the function was not called during the window -- check that you "
                f"targeted the right process and module, or retry with a longer "
                f"timeout_seconds."
            )
        if result.failed:
            raise ToolError(f"{header}\n\n{body}\n\n[exit code {result.exit_code}]")
        return f"{header}\n\n{body}"

    def call_tool(self, name, arguments):
        tool = self.tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool {name!r}")
        if tool.mutating and not self.allow_mutating:
            raise ToolError(
                f"{name} can change the state of the target process and is disabled. "
                f"Start the server with --allow-mutating to enable it."
            )
        if not isinstance(arguments, dict):
            raise ToolError("arguments must be an object")
        return tool.run(arguments, self.execute_profiler_command)

    # -- protocol ----------------------------------------------------------

    def handle_initialize(self, params):
        requested = (params or {}).get("protocolVersion")
        version = (
            requested
            if requested in SUPPORTED_PROTOCOL_VERSIONS
            else SUPPORTED_PROTOCOL_VERSIONS[0]
        )
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": _server_version()},
            "instructions": (
                "Diagnose live Python processes without restarting them. Resolve the "
                "target first with list_python_processes and check_attach_target, then "
                "use stack to see what the process is doing, watch to capture a "
                "function's arguments and timing, and trace to break a slow call into "
                "its sub-calls. Every command runs against a production process, so "
                "prefer small capture limits and always pass timeout_seconds."
            ),
        }

    def handle_tools_list(self, params):
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.schema(),
                }
                for tool in self.available_tools()
            ]
        }

    def handle_tools_call(self, params):
        params = params or {}
        name = params.get("name")
        if not name:
            raise ToolError("name is required")
        try:
            text = self.call_tool(name, params.get("arguments") or {})
        except ToolError as error:
            return {"content": [{"type": "text", "text": str(error)}], "isError": True}
        except Exception:
            return {
                "content": [{"type": "text", "text": traceback.format_exc()}],
                "isError": True,
            }
        return {"content": [{"type": "text", "text": text}], "isError": False}

    def dispatch(self, message):
        """
        Handle one decoded JSON-RPC message.

        Args:
            message (dict): the decoded request or notification.

        Returns:
            dict: the response to write back, or None for a notification.
        """
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._error(None, INVALID_REQUEST, "expected a JSON-RPC 2.0 message")

        method = message.get("method")
        message_id = message.get("id")
        if not isinstance(method, str):
            return self._error(message_id, INVALID_REQUEST, "method must be a string")

        # Notifications carry no id and must never be answered.
        if message_id is None:
            return None

        handlers = {
            "initialize": self.handle_initialize,
            "tools/list": self.handle_tools_list,
            "tools/call": self.handle_tools_call,
            "ping": lambda params: {},
        }
        handler = handlers.get(method)
        if handler is None:
            return self._error(message_id, METHOD_NOT_FOUND, f"unknown method {method!r}")

        try:
            result = handler(message.get("params"))
        except ToolError as error:
            return self._error(message_id, INVALID_PARAMS, str(error))
        except Exception as error:
            return self._error(message_id, INTERNAL_ERROR, f"{type(error).__name__}: {error}")
        return {"jsonrpc": "2.0", "id": message_id, "result": result}

    @staticmethod
    def _error(message_id, code, message):
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {"code": code, "message": message},
        }

    # -- transport ---------------------------------------------------------

    def _write(self, payload):
        self.stdout.write(json.dumps(payload) + "\n")
        self.stdout.flush()

    def serve_forever(self):
        """Read newline-delimited JSON-RPC from stdin until it closes."""
        for line in self.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError as error:
                self._write(self._error(None, PARSE_ERROR, f"invalid JSON: {error}"))
                continue
            response = self.dispatch(message)
            if response is not None:
                self._write(response)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="flight_profiler mcp",
        description="Expose PyFlightProfiler to MCP clients over stdio.",
    )
    parser.add_argument(
        "--allow-mutating",
        action="store_true",
        default=False,
        help=(
            "also expose tools that can change the target process: reload, vmtool "
            "and run_profiler_command. Off by default so an agent calling tools on "
            "its own is limited to read-only diagnostics."
        ),
    )
    args = parser.parse_args(argv)

    # stdout is the protocol channel: anything else printed there corrupts it.
    server = MCPServer(allow_mutating=args.allow_mutating)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
