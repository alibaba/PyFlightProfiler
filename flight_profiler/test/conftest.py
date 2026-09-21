"""Let `pytest flight_profiler/test` run in a checkout that has not been built.

Part of this suite needs artefacts that only `make build` produces: the C
extensions under ``flight_profiler/ext`` and the injectable agent library under
``flight_profiler/lib``. Without them those modules fail at *import* time, and a
collection error aborts the whole run -- so in a fresh clone nothing runs at
all, including the many tests that need no build.

Rather than make contributors remember a list of ``--ignore`` flags, this
conftest probes for the artefacts and deselects exactly what cannot work.
A full build still runs the full suite; the header line says what was left out.
"""

import os
import sys

_TEST_ROOT = os.path.dirname(os.path.abspath(__file__))
_PACKAGE_ROOT = os.path.dirname(_TEST_ROOT)

# Test modules whose import chain reaches a compiled extension. Kept explicit
# rather than discovered: a new extension-backed test that is not listed here
# fails collection loudly, which is the right signal.
_EXTENSION_BACKED_TESTS = {
    os.path.join("plugins", "stack", "server_plugin_stack_test.py"):
        "flight_profiler.ext.stack_C",
    os.path.join("plugins", "trace", "trace_agent_test.py"):
        "flight_profiler.ext.trace_profile_C",
    os.path.join("plugins", "trace", "trace_parser_test.py"):
        "flight_profiler.ext.trace_profile_C",
}

# Integration tests spawn a target process and attach to it, which needs the
# injectable agent library. They are found by their use of the harness rather
# than by filename: the naming is not consistent -- perf_server_test.py is one
# of them -- and a new integration test should be recognised whatever it is
# called.
_INTEGRATION_HARNESS = "ProfileIntegration"


def _extension_available(module_name):
    import importlib

    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True


def _agent_library_built():
    suffix = "dylib" if sys.platform == "darwin" else "so"
    library = os.path.join(_PACKAGE_ROOT, "lib", f"flight_profiler_agent.{suffix}")
    return os.path.isfile(library)


def _integration_tests():
    """Paths, relative to this directory, of tests that attach to a process."""
    found = []
    for directory, _subdirectories, filenames in os.walk(_TEST_ROOT):
        for filename in filenames:
            if not filename.endswith("_test.py"):
                continue
            path = os.path.join(directory, filename)
            try:
                with open(path, encoding="utf-8") as handle:
                    source = handle.read()
            except OSError:
                continue
            if _INTEGRATION_HARNESS in source:
                found.append(os.path.relpath(path, _TEST_ROOT))
    return sorted(found)


_missing_extensions = [
    path
    for path, extension in sorted(_EXTENSION_BACKED_TESTS.items())
    if not _extension_available(extension)
]
_missing_agent = [] if _agent_library_built() else _integration_tests()

collect_ignore = _missing_extensions + _missing_agent


def pytest_report_header(config):
    """Say what was deselected, so a short run is never mistaken for a full one."""
    missing = []
    if _missing_extensions:
        missing.append("C extensions (flight_profiler/ext)")
    if _missing_agent:
        missing.append("agent library (flight_profiler/lib)")
    if not missing:
        return None
    return (
        "flight_profiler: {} not built -- skipping {} test module(s) that need them. "
        "Run `make test` for the full suite.".format(
            " and ".join(missing), len(collect_ignore)
        )
    )
