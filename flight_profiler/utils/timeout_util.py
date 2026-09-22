"""Bounded execution for one-shot (``--cmd``) profiling runs.

Streaming commands such as ``watch``, ``trace`` and ``tt`` block until their
display limit is reached, which never happens when the observed function is not
invoked. A non-interactive caller (a CI job, a script, an AI coding agent) has
no way to press Ctrl-C, so it either hangs forever or kills the client -- and a
killed client never tells the target process to remove the instrumentation it
installed.

``command_timeout`` bounds the run by raising ``KeyboardInterrupt`` in the main
thread, which is exactly what Ctrl-C does. The existing interrupt path in
``ProfilerCli.do_action`` therefore runs ``BaseCliPlugin.on_interrupted`` and the
target process is left clean.
"""

import signal
from contextlib import contextmanager

# Mirrors GNU coreutils `timeout`, which exits with 124 when the deadline hits.
TIMEOUT_EXIT_CODE = 124

# SIGALRM/setitimer are POSIX-only. PyFlightProfiler supports Linux and macOS,
# but the guard keeps the import harmless anywhere else.
SUPPORTS_TIMEOUT = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")


class TimeoutState:
    """Reports whether the bounded block was cut short by its deadline."""

    __slots__ = ("seconds", "expired")

    def __init__(self, seconds):
        self.seconds = seconds
        self.expired = False


@contextmanager
def command_timeout(seconds):
    """Interrupt the wrapped block after ``seconds``, the way Ctrl-C would.

    Args:
        seconds (float): deadline in seconds. ``None`` or a non-positive value
            runs the block unbounded.

    Yields:
        TimeoutState: ``expired`` is True when the deadline fired.
    """
    state = TimeoutState(seconds)
    if not seconds or seconds <= 0 or not SUPPORTS_TIMEOUT:
        yield state
        return

    def on_deadline(signum, frame):
        state.expired = True
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGALRM, on_deadline)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield state
    finally:
        # One-shot timer: cancel it so a pending alarm cannot land on the
        # plugin cleanup that the KeyboardInterrupt just triggered.
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
