import asyncio
import ctypes
import os
import sys
import threading

from flight_profiler.common.system_logger import logger

PYTHON_VERSION_314: bool = sys.version_info >= (3, 14)
if PYTHON_VERSION_314:
    listen_port = "${listen_port}"
    current_file_abspath = "${current_file_abspath}"
else:
    global_vars_dict = globals()
    listen_port = global_vars_dict["__profile_listen_port__"]
    current_file_abspath = os.path.abspath(__file__)

sys.path.append(os.path.dirname(current_file_abspath))
from flight_profiler.server_flight_profiler import FlightProfilerServer


def load_frida_gum():
    try:
        nm_symbol_offset = int("${nm_symbol_offset}")
        flight_profiler_agent_so_path = "${flight_profiler_agent_so_path}"
        lib = ctypes.CDLL(flight_profiler_agent_so_path)
        lib.init_native_profiler.argtypes = [ctypes.c_ulong]
        lib.init_native_profiler.restype = ctypes.c_int
        if lib.init_native_profiler(nm_symbol_offset) != 0:
            logger.warning("Native profiler init failed, gilstat is disabled!")
    except:
        logger.exception("Native profiler agent load failed!")

if PYTHON_VERSION_314:
    load_frida_gum()

listen_port = int(listen_port)
logger.debug(f"Agent listening on port {listen_port}")


def run_app():
    profiler = FlightProfilerServer("localhost", listen_port)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tasks = [loop.create_task(profiler.run())]
    loop.run_until_complete(asyncio.wait(tasks))


profile_thread = threading.Thread(target=run_app, name="flight-profiler-agent")
profile_thread.start()
logger.debug("Agent thread started")
