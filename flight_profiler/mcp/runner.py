"""Run a PyFlightProfiler command as a subprocess, bounded and size-capped.

Two things matter when the caller is an autonomous agent rather than a person at
a terminal.

*Deadlines must be graceful.* `watch` and `trace` install AOP instrumentation
inside the target process, and only the client's exit path removes it again.
Killing a stuck client outright leaves a production process instrumented
forever, so the deadline sends SIGINT first -- the same signal Ctrl-C sends, and
the same path `--timeout` uses -- and only escalates if the client ignores it.

*Output must be bounded.* A `stack` dump of a process with hundreds of threads
can run to megabytes. Handing that back verbatim would blow the model's context
for no diagnostic gain, so long output is trimmed from the middle, keeping the
head and tail where the useful signal lives.
"""

import signal
import subprocess

# How long the client gets to remove its instrumentation after SIGINT before
# being killed. Un-instrumenting is a single request to the in-process agent.
_CLEANUP_GRACE_SECONDS = 5


class CommandResult:
    """Outcome of one PyFlightProfiler invocation."""

    __slots__ = ("argv", "output", "exit_code", "timed_out")

    def __init__(self, argv, output, exit_code, timed_out):
        self.argv = argv
        self.output = output
        self.exit_code = exit_code
        self.timed_out = timed_out

    @property
    def failed(self):
        # 124 is the deadline, which is a diagnostic result rather than a fault:
        # it means the observed code did not run during the window.
        return self.exit_code not in (0, 124)


def trim_output(text, max_chars):
    """
    Trim the middle out of ``text`` so it fits in ``max_chars``.

    The head carries the command header and first records; the tail carries the
    summary and any error. The middle is the repetitive part.

    Args:
        text (str): raw command output.
        max_chars (int): budget, or 0/None for no limit.

    Returns:
        str: the original text, or a trimmed copy with a marker in the middle.
    """
    if not max_chars or len(text) <= max_chars:
        return text

    marker_template = "\n\n... [{} characters trimmed; narrow the query or lower -n] ...\n\n"
    # Reserve room for the marker itself before splitting the budget.
    reserve = len(marker_template.format(len(text)))
    keep = max(max_chars - reserve, 0)
    head_chars = keep * 2 // 3
    tail_chars = keep - head_chars
    trimmed_count = len(text) - head_chars - tail_chars
    tail = text[len(text) - tail_chars:] if tail_chars else ""
    return text[:head_chars] + marker_template.format(trimmed_count) + tail


def run_profiler_command(argv, timeout_seconds, max_output_chars=0,
                         cleanup_grace_seconds=_CLEANUP_GRACE_SECONDS):
    """
    Run a PyFlightProfiler client invocation to completion or to its deadline.

    Args:
        argv (list): full command line, already split -- never passed to a shell.
        timeout_seconds (float): deadline, or None to wait indefinitely.
        max_output_chars (int): cap on returned characters, 0 for no cap.
        cleanup_grace_seconds (float): how long the client may take to remove
            its instrumentation after SIGINT before it is killed.

    Returns:
        CommandResult
    """
    try:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
    except OSError as error:
        return CommandResult(argv, f"could not start {argv[0]}: {error}", exit_code=127,
                             timed_out=False)

    timed_out = False
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        # Ctrl-C, not kill: lets the client un-instrument the target first.
        process.send_signal(signal.SIGINT)
        try:
            output, _ = process.communicate(timeout=cleanup_grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
            output = (output or "") + (
                "\n[warning] the client did not stop after SIGINT and was killed. "
                "Instrumentation may still be installed in the target process; "
                "re-attach and run the same command with -n 1 to clear it."
            )

    exit_code = process.returncode
    if timed_out and exit_code in (0, -signal.SIGINT):
        # Normalise a SIGINT-terminated run onto the same code `--timeout` uses.
        exit_code = 124

    return CommandResult(
        argv,
        trim_output(output or "", max_output_chars),
        exit_code=exit_code,
        timed_out=timed_out,
    )
