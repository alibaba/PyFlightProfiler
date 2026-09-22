import argparse
import signal
import time
import unittest

from flight_profiler.client import resolve_cmd_timeout
from flight_profiler.utils.timeout_util import TIMEOUT_EXIT_CODE, command_timeout


def build_args(cmd=None, timeout=None):
    return argparse.Namespace(cmd=cmd, timeout=timeout)


def build_parser():
    parser = argparse.ArgumentParser()
    parser.exit_on_error = False
    return parser


class CommandTimeoutTest(unittest.TestCase):

    def test_deadline_interrupts_a_blocked_command(self):
        with command_timeout(0.2) as deadline:
            start = time.time()
            with self.assertRaises(KeyboardInterrupt):
                time.sleep(10)
            elapsed = time.time() - start

        self.assertTrue(deadline.expired)
        self.assertLess(elapsed, 5)

    def test_command_finishing_first_is_left_alone(self):
        with command_timeout(10) as deadline:
            time.sleep(0.01)

        self.assertFalse(deadline.expired)

    def test_no_deadline_runs_unbounded(self):
        for seconds in (None, 0, -1):
            with command_timeout(seconds) as deadline:
                time.sleep(0.01)
            self.assertFalse(deadline.expired)
            self.assertEqual(seconds, deadline.seconds)

    def test_pending_alarm_is_cancelled_on_exit(self):
        # A timer left armed would fire during the plugin cleanup that the
        # KeyboardInterrupt triggers, aborting the un-instrument request.
        with command_timeout(0.2):
            pass
        time.sleep(0.4)

        self.assertEqual(0.0, signal.getitimer(signal.ITIMER_REAL)[0])

    def test_previous_signal_handler_is_restored(self):
        def handler(signum, frame):
            pass

        previous = signal.signal(signal.SIGALRM, handler)
        try:
            with command_timeout(5):
                pass
            self.assertIs(handler, signal.getsignal(signal.SIGALRM))
        finally:
            signal.signal(signal.SIGALRM, previous)

    def test_exit_code_matches_gnu_timeout(self):
        self.assertEqual(124, TIMEOUT_EXIT_CODE)


class ResolveCmdTimeoutTest(unittest.TestCase):

    def test_flag_is_used_when_given(self):
        timeout = resolve_cmd_timeout(build_args(cmd="stack", timeout=2.5), build_parser())

        self.assertEqual(2.5, timeout)

    def test_unbounded_without_flag_or_env(self):
        self.assertIsNone(resolve_cmd_timeout(build_args(cmd="stack"), build_parser()))

    def test_env_is_used_as_fallback(self):
        with EnvVar("PYFLIGHT_CMD_TIMEOUT", "7"):
            timeout = resolve_cmd_timeout(build_args(cmd="stack"), build_parser())

        self.assertEqual(7, timeout)

    def test_flag_wins_over_env(self):
        with EnvVar("PYFLIGHT_CMD_TIMEOUT", "7"):
            timeout = resolve_cmd_timeout(build_args(cmd="stack", timeout=1), build_parser())

        self.assertEqual(1, timeout)

    def test_env_is_ignored_for_an_interactive_session(self):
        # `flight_profiler <pid>` with the env var exported globally must still
        # open a REPL rather than refuse to start.
        with EnvVar("PYFLIGHT_CMD_TIMEOUT", None):
            self.assertIsNone(resolve_cmd_timeout(build_args(), build_parser()))

    def test_flag_without_cmd_is_rejected(self):
        with self.assertRaises(SystemExit):
            resolve_cmd_timeout(build_args(timeout=5), build_parser())

    def test_non_positive_timeout_is_rejected(self):
        for value in (0, -3):
            with self.assertRaises(SystemExit):
                resolve_cmd_timeout(build_args(cmd="stack", timeout=value), build_parser())

    def test_unparsable_env_is_rejected(self):
        with EnvVar("PYFLIGHT_CMD_TIMEOUT", "soon"):
            with self.assertRaises(SystemExit):
                resolve_cmd_timeout(build_args(cmd="stack"), build_parser())


class EnvVar:
    """Set (or clear, with None) an environment variable for one block."""

    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.previous = None

    def __enter__(self):
        import os

        self.previous = os.environ.get(self.name)
        if self.value is None:
            os.environ.pop(self.name, None)
        else:
            os.environ[self.name] = self.value
        return self

    def __exit__(self, *exc_info):
        import os

        if self.previous is None:
            os.environ.pop(self.name, None)
        else:
            os.environ[self.name] = self.previous


if __name__ == "__main__":
    unittest.main()
