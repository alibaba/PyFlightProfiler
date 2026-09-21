import io
import json
import unittest

from flight_profiler.mcp.server import (
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    SUPPORTED_PROTOCOL_VERSIONS,
    MCPServer,
)


def request(method, params=None, message_id=1):
    message = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


class InitializeTest(unittest.TestCase):

    def test_a_supported_protocol_version_is_echoed_back(self):
        for version in SUPPORTED_PROTOCOL_VERSIONS:
            response = MCPServer().dispatch(
                request("initialize", {"protocolVersion": version})
            )

            self.assertEqual(version, response["result"]["protocolVersion"])

    def test_an_unknown_protocol_version_falls_back_to_the_newest(self):
        response = MCPServer().dispatch(
            request("initialize", {"protocolVersion": "1999-01-01"})
        )

        self.assertEqual(SUPPORTED_PROTOCOL_VERSIONS[0],
                         response["result"]["protocolVersion"])

    def test_the_server_advertises_tools_and_identifies_itself(self):
        result = MCPServer().dispatch(request("initialize", {}))["result"]

        self.assertIn("tools", result["capabilities"])
        self.assertEqual("pyflightprofiler", result["serverInfo"]["name"])
        self.assertTrue(result["instructions"])


class ToolListingTest(unittest.TestCase):

    def listed(self, **kwargs):
        response = MCPServer(**kwargs).dispatch(request("tools/list"))
        return {tool["name"] for tool in response["result"]["tools"]}

    def test_mutating_tools_are_hidden_by_default(self):
        names = self.listed()

        self.assertIn("stack", names)
        self.assertIn("watch", names)
        self.assertNotIn("reload", names)
        self.assertNotIn("vmtool", names)
        self.assertNotIn("run_profiler_command", names)

    def test_mutating_tools_appear_when_explicitly_allowed(self):
        names = self.listed(allow_mutating=True)

        self.assertIn("reload", names)
        self.assertIn("vmtool", names)
        self.assertIn("run_profiler_command", names)

    def test_each_listed_tool_carries_an_input_schema(self):
        response = MCPServer(allow_mutating=True).dispatch(request("tools/list"))

        for tool in response["result"]["tools"]:
            self.assertEqual("object", tool["inputSchema"]["type"], tool["name"])
            self.assertTrue(tool["description"], tool["name"])


class ToolCallTest(unittest.TestCase):

    def call(self, name, arguments, server=None):
        server = server or MCPServer()
        response = server.dispatch(
            request("tools/call", {"name": name, "arguments": arguments})
        )
        return response["result"]

    def test_a_successful_call_returns_text_content(self):
        server = MCPServer()
        server.execute_profiler_command = (
            lambda pid, command, timeout_seconds, max_output_chars: f"ran {command}"
        )

        result = self.call("stack", {"pid": 99}, server)

        self.assertFalse(result["isError"])
        self.assertEqual("ran stack", result["content"][0]["text"])

    def test_a_bad_argument_is_an_error_result_not_a_protocol_error(self):
        # MCP reserves JSON-RPC errors for protocol faults; a tool that cannot
        # run reports isError so the model can read the reason and retry.
        result = self.call("watch", {"pid": 99, "module": "/tmp/a.py", "function": "f"})

        self.assertTrue(result["isError"])
        self.assertIn("module", result["content"][0]["text"])

    def test_calling_a_gated_tool_explains_how_to_enable_it(self):
        result = self.call("reload", {"pid": 99, "module": "app", "function": "f"})

        self.assertTrue(result["isError"])
        self.assertIn("--allow-mutating", result["content"][0]["text"])

    def test_calling_an_unknown_tool_is_an_error_result(self):
        result = self.call("teleport", {})

        self.assertTrue(result["isError"])
        self.assertIn("teleport", result["content"][0]["text"])

    def test_an_unexpected_failure_is_reported_rather_than_crashing_the_server(self):
        server = MCPServer()

        def explode(pid, command, timeout_seconds, max_output_chars):
            raise RuntimeError("boom")

        server.execute_profiler_command = explode

        result = self.call("stack", {"pid": 99}, server)

        self.assertTrue(result["isError"])
        self.assertIn("boom", result["content"][0]["text"])


class ProtocolTest(unittest.TestCase):

    def test_ping_is_answered_with_an_empty_result(self):
        self.assertEqual({}, MCPServer().dispatch(request("ping"))["result"])

    def test_an_unknown_method_is_a_json_rpc_error(self):
        response = MCPServer().dispatch(request("resources/list"))

        self.assertEqual(METHOD_NOT_FOUND, response["error"]["code"])

    def test_a_notification_is_never_answered(self):
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}

        self.assertIsNone(MCPServer().dispatch(notification))

    def test_a_non_json_rpc_message_is_rejected(self):
        response = MCPServer().dispatch({"method": "ping", "id": 1})

        self.assertEqual(INVALID_REQUEST, response["error"]["code"])


class StdioTransportTest(unittest.TestCase):

    def run_session(self, lines, **kwargs):
        stdin = io.StringIO("\n".join(lines) + "\n")
        stdout = io.StringIO()
        MCPServer(stdin=stdin, stdout=stdout, **kwargs).serve_forever()
        return [json.loads(line) for line in stdout.getvalue().splitlines()]

    def test_a_full_handshake_over_stdio(self):
        responses = self.run_session([
            json.dumps(request("initialize", {"protocolVersion": "2025-06-18"}, 1)),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps(request("tools/list", message_id=2)),
        ])

        # Two requests, one notification: exactly two responses, in order.
        self.assertEqual([1, 2], [response["id"] for response in responses])
        self.assertTrue(responses[1]["result"]["tools"])

    def test_blank_lines_are_skipped(self):
        responses = self.run_session(["", json.dumps(request("ping")), ""])

        self.assertEqual(1, len(responses))

    def test_malformed_json_does_not_end_the_session(self):
        responses = self.run_session(
            ["{not json", json.dumps(request("ping", message_id=7))]
        )

        self.assertEqual(PARSE_ERROR, responses[0]["error"]["code"])
        self.assertEqual(7, responses[1]["id"])


if __name__ == "__main__":
    unittest.main()
