import os
import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover - Python 2 style fallback, never hit here
    import mock

from flight_profiler.mcp import target as target_module
from flight_profiler.mcp.target import list_python_processes, resolve_target

VENV_PYTHON = "/opt/envs/serving/bin/python3.11"
VENV_SCRIPT = "/opt/envs/serving/bin/flight_profiler"


def patch_resolution(python_executable, console_script_exists=False, importable=False):
    """Pin the three facts resolve_target looks up about a process."""
    return [
        mock.patch.object(target_module, "get_py_bin_path",
                          return_value=python_executable),
        mock.patch.object(target_module, "_is_executable",
                          return_value=console_script_exists),
        mock.patch.object(target_module, "_package_importable",
                          return_value=importable),
    ]


class ResolveTargetTest(unittest.TestCase):

    def resolve(self, pid=4242, **kwargs):
        patches = patch_resolution(**kwargs)
        for patcher in patches:
            patcher.start()
        self.addCleanup(lambda: [patcher.stop() for patcher in patches])
        return resolve_target(pid)

    def test_the_console_script_beside_the_interpreter_wins(self):
        # The point of the whole module: use the target environment's own
        # flight_profiler, not whichever one happens to be on PATH.
        target = self.resolve(python_executable=VENV_PYTHON, console_script_exists=True)

        self.assertTrue(target.usable)
        self.assertEqual([VENV_SCRIPT], target.argv_prefix)
        self.assertEqual(VENV_PYTHON, target.python_executable)

    def test_an_importable_package_is_run_as_a_module(self):
        target = self.resolve(python_executable=VENV_PYTHON, importable=True)

        self.assertTrue(target.usable)
        self.assertEqual([VENV_PYTHON, "-m", "flight_profiler.client"],
                         target.argv_prefix)

    def test_a_missing_package_yields_the_install_command_for_that_env(self):
        target = self.resolve(python_executable=VENV_PYTHON)

        self.assertFalse(target.usable)
        self.assertIn("not installed", target.problem)
        self.assertEqual(f"{VENV_PYTHON} -m pip install flight_profiler",
                         target.install_command)

    def test_a_process_with_no_interpreter_is_not_usable(self):
        target = self.resolve(python_executable="")

        self.assertFalse(target.usable)
        self.assertIn("no Python interpreter", target.problem)

    def test_a_failure_while_inspecting_is_reported_not_raised(self):
        # get_py_bin_path shells out; a tool call must not die because of it.
        with mock.patch.object(target_module, "get_py_bin_path",
                               side_effect=OSError("lsof missing")):
            target = resolve_target(4242)

        self.assertFalse(target.usable)
        self.assertIn("lsof missing", target.problem)

    def test_describe_states_readiness(self):
        description = self.resolve(python_executable=VENV_PYTHON,
                                   console_script_exists=True).describe()

        self.assertIn("pid: 4242", description)
        self.assertIn("ready to attach", description)

    def test_describe_states_the_problem_and_the_fix(self):
        description = self.resolve(python_executable=VENV_PYTHON).describe()

        self.assertIn("cannot attach", description)
        self.assertIn("pip install flight_profiler", description)


PS_OUTPUT = """
  101 root     /bin/zsh -c python3 /srv/start.py
  202 app      /opt/envs/serving/bin/python3.11 -m uvicorn app:api
  303 app      /usr/bin/java -jar service.jar
  404 app      /opt/envs/serving/bin/gunicorn --workers 4 python_app:wsgi
"""


class ListPythonProcessesTest(unittest.TestCase):

    def list(self, name_filter=None, stdout=PS_OUTPUT):
        completed = mock.Mock(stdout=stdout)
        with mock.patch.object(target_module.subprocess, "run", return_value=completed):
            return list_python_processes(name_filter)

    def test_non_python_processes_are_excluded(self):
        pids = [entry["pid"] for entry in self.list()]

        self.assertNotIn(303, pids)

    def test_processes_running_an_interpreter_sort_first(self):
        # A shell wrapping a python command matches the same substring, so the
        # real interpreter has to lead or the model picks the wrapper.
        entries = self.list()

        self.assertEqual(202, entries[0]["pid"])
        self.assertTrue(entries[0]["runs_interpreter"])
        self.assertFalse(entries[-1]["runs_interpreter"])

    def test_a_console_script_launching_python_is_still_listed(self):
        # gunicorn never names the interpreter in argv[0], so the heuristic has
        # to stay broad enough to catch it.
        pids = [entry["pid"] for entry in self.list()]

        self.assertIn(404, pids)

    def test_the_name_filter_matches_the_command_line(self):
        entries = self.list("uvicorn")

        self.assertEqual([202], [entry["pid"] for entry in entries])

    def test_the_name_filter_ignores_case(self):
        self.assertEqual(1, len(self.list("UVICORN")))

    def test_the_server_does_not_list_itself(self):
        own = f"  {os.getpid()} app      /usr/bin/python3 -m flight_profiler.mcp\n"
        pids = [entry["pid"] for entry in self.list(stdout=PS_OUTPUT + own)]

        self.assertNotIn(os.getpid(), pids)

    def test_unparsable_lines_are_skipped(self):
        entries = self.list(stdout="garbage\n\n  \n" + PS_OUTPUT)

        self.assertEqual(3, len(entries))

    def test_a_failure_to_list_is_raised_with_context(self):
        with mock.patch.object(target_module.subprocess, "run",
                               side_effect=OSError("no ps")):
            with self.assertRaises(RuntimeError) as caught:
                list_python_processes()

        self.assertIn("no ps", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
