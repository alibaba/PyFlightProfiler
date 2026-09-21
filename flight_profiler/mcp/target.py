"""Resolve which ``flight_profiler`` executable can attach to a given process.

PyFlightProfiler has to run from the same Python environment as its target: the
injected agent imports ``flight_profiler`` from inside the target process, so
the package must be on *that* process's ``sys.path``. This is the most common
reason an attach fails, and it is invisible from the outside -- the command just
reports an injection error.

An MCP server cannot live in every environment on the machine at once, so rather
than assuming its own interpreter it resolves the target's interpreter per PID
and invokes the ``flight_profiler`` belonging to that environment. One server
process can therefore drive targets across conda envs, virtualenvs and the
system Python.
"""

import os
import subprocess

from flight_profiler.utils.shell_util import get_py_bin_path

# Long enough for a cold interpreter start on a loaded machine, short enough
# that a wedged interpreter does not stall the MCP call.
_PROBE_TIMEOUT_SECONDS = 20


class TargetEnvironment:
    """How (and whether) PyFlightProfiler can be run against one process."""

    __slots__ = ("pid", "python_executable", "argv_prefix", "problem", "install_command")

    def __init__(self, pid, python_executable=None, argv_prefix=None, problem=None,
                 install_command=None):
        self.pid = pid
        self.python_executable = python_executable
        self.argv_prefix = argv_prefix
        self.problem = problem
        self.install_command = install_command

    @property
    def usable(self):
        return self.argv_prefix is not None

    def describe(self):
        """Render the resolution as text for a tool result."""
        lines = [f"pid: {self.pid}"]
        if self.python_executable:
            lines.append(f"python: {self.python_executable}")
        if self.usable:
            lines.append(f"flight_profiler: {' '.join(self.argv_prefix)}")
            lines.append("status: ready to attach")
        else:
            lines.append(f"status: cannot attach -- {self.problem}")
            if self.install_command:
                lines.append(f"fix: {self.install_command}")
        return "\n".join(lines)


def _runs_interpreter(command):
    """Whether the command's own executable is a Python interpreter."""
    executable = command.split()[0] if command.split() else ""
    return os.path.basename(executable).lower().startswith("python")


def _is_executable(path):
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _package_importable(python_executable):
    """Check whether `flight_profiler` is importable by the target's interpreter."""
    try:
        completed = subprocess.run(
            [python_executable, "-c", "import flight_profiler"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def resolve_target(pid):
    """
    Work out how to run PyFlightProfiler against ``pid``.

    Args:
        pid (int): the process to attach to.

    Returns:
        TargetEnvironment: ``usable`` is False when the process is gone, is not
        a Python process, or has no flight_profiler in its environment. In that
        last case ``install_command`` says how to fix it.
    """
    try:
        python_executable = get_py_bin_path(pid)
    except Exception as error:  # the resolver shells out; never fail the tool call
        return TargetEnvironment(pid, problem=f"could not inspect the process ({error})")

    if not python_executable:
        return TargetEnvironment(
            pid,
            problem=(
                "no Python interpreter found for this pid -- the process may have "
                "exited, may not be a Python process, or may belong to another user"
            ),
        )

    # A console script next to the interpreter is by definition the one installed
    # into that environment, so prefer it over anything on PATH.
    console_script = os.path.join(os.path.dirname(python_executable), "flight_profiler")
    if _is_executable(console_script):
        return TargetEnvironment(pid, python_executable, [console_script])

    # No console script, but the package may still be importable -- for instance
    # when the environment was installed with `pip install --no-scripts`, or when
    # the target runs from a source checkout on PYTHONPATH.
    if _package_importable(python_executable):
        return TargetEnvironment(
            pid, python_executable, [python_executable, "-m", "flight_profiler.client"]
        )

    return TargetEnvironment(
        pid,
        python_executable,
        problem="flight_profiler is not installed in this process's Python environment",
        install_command=f"{python_executable} -m pip install flight_profiler",
    )


def list_python_processes(name_filter=None):
    """
    List the Python processes on this machine.

    Matching is a heuristic -- any command line mentioning "python" -- because a
    Python service may be launched through a console script such as `gunicorn`
    that never names the interpreter. Processes whose own executable is an
    interpreter sort first; use ``resolve_target`` to confirm a candidate.

    Args:
        name_filter (str): case-insensitive substring to match against the
            command line, e.g. "gunicorn" or "my_service.py".

    Returns:
        list: dicts with ``pid``, ``user``, ``command`` and ``runs_interpreter``.
    """
    try:
        completed = subprocess.run(
            ["ps", "-A", "-o", "pid=,user=,args="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=_PROBE_TIMEOUT_SECONDS,
            universal_newlines=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"could not list processes: {error}")

    needle = name_filter.lower() if name_filter else None
    own_pid = os.getpid()
    processes = []
    for line in completed.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) < 3:
            continue
        pid_text, user, command = fields
        if not pid_text.isdigit() or int(pid_text) == own_pid:
            continue
        if "python" not in command.lower():
            continue
        if needle and needle not in command.lower():
            continue
        processes.append(
            {
                "pid": int(pid_text),
                "user": user,
                "command": command,
                "runs_interpreter": _runs_interpreter(command),
            }
        )
    # A shell wrapping a python command also matches on "python", so surface the
    # processes actually running an interpreter first.
    processes.sort(key=lambda entry: (not entry["runs_interpreter"], entry["pid"]))
    return processes
