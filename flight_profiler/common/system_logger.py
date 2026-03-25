import logging
import os


def setup_logger(level=None):
    """
    Set up logger for flight profiler.

    Args:
        level: Logging level. If None, determined by FLIGHT_PROFILER_DEBUG environment variable.

    Returns:
        logging.Logger: Configured logger instance
    """
    _logger = logging.getLogger("flight_profiler_logger")

    # Prevent duplicate handlers when module is imported multiple times
    if _logger.handlers:
        return _logger

    if level is None:
        if os.getenv("FLIGHT_PROFILER_DEBUG", "0").strip().lower() in ("1", "true"):
            level = logging.DEBUG
        else:
            level = logging.INFO

    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [PyFlightProfiler] %(levelname)s %(message)s")
    handler.setFormatter(formatter)

    _logger.setLevel(level)
    _logger.addHandler(handler)
    # Prevent propagation to root logger to avoid duplicate output
    _logger.propagate = False
    return _logger


logger = setup_logger()
