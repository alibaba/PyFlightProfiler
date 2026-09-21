import sys
import time
import unittest

from flight_profiler.mcp.runner import run_profiler_command, trim_output


def python_command(source):
    return [sys.executable, "-c", source]


# Stands in for a client that removes its instrumentation on Ctrl-C, the way
# ProfilerCli.do_action does before exiting.
CLEANS_UP_ON_SIGINT = """
import signal, sys, time

def on_interrupt(signum, frame):
    print("instrumentation removed")
    sys.stdout.flush()
    sys.exit(0)

signal.signal(signal.SIGINT, on_interrupt)
print("watching")
sys.stdout.flush()
time.sleep(60)
"""

IGNORES_SIGINT = """
import signal, sys, time

signal.signal(signal.SIGINT, signal.SIG_IGN)
print("wedged")
sys.stdout.flush()
time.sleep(60)
"""


class TrimOutputTest(unittest.TestCase):

    def test_short_output_is_returned_unchanged(self):
        self.assertEqual("hello", trim_output("hello", 100))

    def test_no_budget_means_no_trimming(self):
        text = "x" * 10000

        self.assertEqual(text, trim_output(text, 0))
        self.assertEqual(text, trim_output(text, None))

    def test_long_output_keeps_the_head_and_the_tail(self):
        text = "HEAD" + ("x" * 5000) + "TAIL"

        trimmed = trim_output(text, 500)

        self.assertTrue(trimmed.startswith("HEAD"))
        self.assertTrue(trimmed.endswith("TAIL"))
        self.assertIn("characters trimmed", trimmed)

    def test_trimmed_output_respects_the_budget(self):
        for budget in (200, 500, 2000):
            trimmed = trim_output("y" * 100000, budget)

            self.assertLessEqual(len(trimmed), budget, budget)

    def test_a_budget_smaller_than_the_marker_still_returns_the_marker(self):
        trimmed = trim_output("z" * 1000, 10)

        self.assertIn("characters trimmed", trimmed)


class RunProfilerCommandTest(unittest.TestCase):

    def test_a_successful_command_returns_its_output(self):
        result = run_profiler_command(python_command("print('stack dump')"), 30)

        self.assertEqual(0, result.exit_code)
        self.assertFalse(result.timed_out)
        self.assertFalse(result.failed)
        self.assertIn("stack dump", result.output)

    def test_stderr_is_folded_into_the_output(self):
        result = run_profiler_command(
            python_command("import sys; sys.stderr.write('attach failed')"), 30
        )

        self.assertIn("attach failed", result.output)

    def test_a_failing_command_reports_its_exit_code(self):
        result = run_profiler_command(python_command("raise SystemExit(3)"), 30)

        self.assertEqual(3, result.exit_code)
        self.assertTrue(result.failed)

    def test_a_missing_executable_does_not_raise(self):
        result = run_profiler_command(["/nonexistent/flight_profiler", "1"], 30)

        self.assertEqual(127, result.exit_code)
        self.assertTrue(result.failed)
        self.assertIn("could not start", result.output)

    def test_the_deadline_lets_the_client_clean_up_before_exiting(self):
        started = time.time()
        result = run_profiler_command(python_command(CLEANS_UP_ON_SIGINT), 0.5)
        elapsed = time.time() - started

        self.assertTrue(result.timed_out)
        # SIGINT, not SIGKILL: the client ran its cleanup and said so.
        self.assertIn("instrumentation removed", result.output)
        self.assertLess(elapsed, 30)

    def test_a_deadline_is_not_treated_as_a_failure(self):
        # Exit 124 means "the observed code did not run in the window", which is
        # a diagnostic answer rather than a fault.
        result = run_profiler_command(python_command(CLEANS_UP_ON_SIGINT), 0.5)

        self.assertEqual(124, result.exit_code)
        self.assertFalse(result.failed)

    def test_a_client_ignoring_sigint_is_killed_and_flagged(self):
        result = run_profiler_command(
            python_command(IGNORES_SIGINT), 0.5, cleanup_grace_seconds=0.5
        )

        self.assertTrue(result.timed_out)
        self.assertIn("was killed", result.output)
        self.assertIn("may still be installed", result.output)

    def test_output_is_capped_on_the_way_back(self):
        result = run_profiler_command(
            python_command("print('n' * 50000)"), 30, max_output_chars=1000
        )

        self.assertLessEqual(len(result.output), 1000)


if __name__ == "__main__":
    unittest.main()
