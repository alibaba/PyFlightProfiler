import unittest

from flight_profiler.mcp.tools import ToolError, build_catalogue


def tool_named(name):
    for tool in build_catalogue():
        if tool.name == name:
            return tool
    raise AssertionError(f"no tool named {name}")


def command_for(name, **arguments):
    """Build the profiler command a tool would run, without running it."""
    captured = {}

    def execute(pid, command, timeout_seconds, max_output_chars):
        captured.update(
            pid=pid,
            command=command,
            timeout_seconds=timeout_seconds,
            max_output_chars=max_output_chars,
        )
        return "ok"

    arguments.setdefault("pid", 4242)
    tool_named(name).run(arguments, execute)
    return captured


class CatalogueTest(unittest.TestCase):

    def test_tool_names_are_unique(self):
        names = [tool.name for tool in build_catalogue()]

        self.assertEqual(len(names), len(set(names)))

    def test_every_tool_declares_a_description_and_schema(self):
        for tool in build_catalogue():
            schema = tool.schema()
            self.assertTrue(tool.description, tool.name)
            self.assertEqual("object", schema["type"], tool.name)
            for required in schema["required"]:
                self.assertIn(required, schema["properties"], f"{tool.name}.{required}")

    def test_state_changing_tools_are_marked_mutating(self):
        mutating = {tool.name for tool in build_catalogue() if tool.mutating}

        self.assertEqual({"reload", "vmtool", "run_profiler_command"}, mutating)

    def test_process_tools_take_a_pid_and_a_deadline(self):
        for tool in build_catalogue():
            if tool.name in ("list_python_processes", "check_attach_target"):
                continue
            schema = tool.schema()
            self.assertIn("pid", schema["required"], tool.name)
            self.assertIn("timeout_seconds", schema["properties"], tool.name)


class CommandBuildingTest(unittest.TestCase):

    def test_watch_builds_a_module_level_function(self):
        captured = command_for("watch", module="app.api", function="handle")

        self.assertEqual("watch --pkg app.api --func handle -n 1", captured["command"])
        self.assertEqual(4242, captured["pid"])

    def test_watch_builds_a_method_with_options(self):
        captured = command_for(
            "watch",
            module="app.api",
            class_name="OrderService",
            function="process",
            expression="return_obj",
            filter_expression="args[0]=='x'",
            limit=3,
            expand_level=2,
            only_on_exception=True,
            verbose=True,
        )

        self.assertEqual(
            "watch --pkg app.api --cls OrderService --func process "
            "--expr return_obj -f args[0]=='x' -n 3 -x 2 -e -v",
            captured["command"],
        )

    def test_trace_uses_its_own_module_flag(self):
        # The CLI spells this --mod for trace and --pkg for watch; the tool
        # surface hides that difference behind one `module` argument.
        captured = command_for("trace", module="app.api", function="handle", depth=2,
                               min_cost_ms=5, limit=2)

        self.assertEqual(
            "trace --mod app.api --func handle -n 2 -d 2 -i 5", captured["command"]
        )

    def test_getglobal_builds_a_class_static(self):
        captured = command_for("getglobal", module="app.config", class_name="Settings",
                               variable="CACHE", expand_level=3)

        self.assertEqual(
            "getglobal --mod app.config --cls Settings --var CACHE -x 3",
            captured["command"],
        )

    def test_stack_switches_are_optional(self):
        self.assertEqual("stack", command_for("stack")["command"])
        self.assertEqual(
            "stack -a --native",
            command_for("stack", async_stacks=True, native=True)["command"],
        )

    def test_module_passes_the_path_through(self):
        captured = command_for("module", file_path="/srv/app/api.py")

        self.assertEqual("module /srv/app/api.py", captured["command"])

    def test_reload_builds_a_method(self):
        captured = command_for("reload", module="app.api", class_name="Svc",
                               function="handle", verbose=True)

        self.assertEqual("reload --mod app.api --cls Svc --func handle -v",
                         captured["command"])

    def test_vmtool_builds_an_action(self):
        captured = command_for("vmtool", action="getInstances", class_name="app.User",
                               limit=5)

        self.assertEqual("vmtool -a getInstances -c app.User -n 5", captured["command"])

    def test_raw_command_is_passed_through_verbatim(self):
        captured = command_for("run_profiler_command", command="perf -d 10")

        self.assertEqual("perf -d 10", captured["command"])

    def test_defaults_bound_time_and_output(self):
        captured = command_for("stack")

        self.assertEqual(30, captured["timeout_seconds"])
        self.assertEqual(20000, captured["max_output_chars"])

    def test_caller_can_override_the_defaults(self):
        captured = command_for("stack", timeout_seconds=5, max_output_chars=100)

        self.assertEqual(5, captured["timeout_seconds"])
        self.assertEqual(100, captured["max_output_chars"])


class ArgumentValidationTest(unittest.TestCase):

    def assert_rejected(self, name, **arguments):
        with self.assertRaises(ToolError):
            command_for(name, **arguments)

    def test_a_file_path_is_not_a_module_name(self):
        # The likeliest model mistake: passing the path it already has.
        self.assert_rejected("watch", module="/srv/app/api.py", function="handle")

    def test_dunder_main_is_a_valid_module(self):
        captured = command_for("watch", module="__main__", function="handle")

        self.assertIn("--pkg __main__", captured["command"])

    def test_identifiers_with_spaces_are_rejected(self):
        # args_util splits on whitespace with no notion of quoting, so a space
        # would silently become an extra argument.
        self.assert_rejected("watch", module="app.api", function="handle order")

    def test_expressions_with_spaces_are_rejected(self):
        self.assert_rejected("watch", module="app.api", function="handle",
                             expression="args[0] + 1")

    def test_missing_required_arguments_are_rejected(self):
        self.assert_rejected("watch", module="app.api")
        self.assert_rejected("getglobal", module="app.config")
        self.assert_rejected("run_profiler_command")

    def test_pid_must_be_a_positive_integer(self):
        for pid in (0, -1, "1234", None, True):
            with self.assertRaises(ToolError):
                command_for("stack", pid=pid)

    def test_multiline_raw_commands_are_rejected(self):
        self.assert_rejected("run_profiler_command", command="stack\nquit")


if __name__ == "__main__":
    unittest.main()
