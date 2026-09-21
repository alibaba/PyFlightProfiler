"""Entry point for `python -m flight_profiler.mcp`."""

import sys

from flight_profiler.mcp.server import main

if __name__ == "__main__":
    sys.exit(main())
