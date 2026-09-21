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

import importlib
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
# injectable agent library. They are named consistently, so a glob is enough.
_INTEGRATION_TEST_GLOB = "**/*_plugin_test.py"


def _extension_available(module_name):
    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True


def _agent_library_built():
    suffix = "dylib" if sys.platform == "darwin" else "so"
    library = os.path.join(_PACKAGE_ROOT, "lib", f"flight_profiler_agent.{suffix}")
    return os.path.isfile(library)


collect_ignore = [
    path
    for path, extension in sorted(_EXTENSION_BACKED_TESTS.items())
    if not _extension_available(extension)
]
collect_ignore_glob = [] if _agent_library_built() else [_INTEGRATION_TEST_GLOB]


def pytest_report_header(config):
    """Say what was deselected, so a short run is never mistaken for a full one."""
    missing = []
    if collect_ignore:
        missing.append("C extensions (flight_profiler/ext)")
    if collect_ignore_glob:
        missing.append("agent library (flight_profiler/lib)")
    if not missing:
        return None
    return (
        "flight_profiler: {} not built -- skipping the tests that need them. "
        "Run `make test` for the full suite.".format(" and ".join(missing))
    )
