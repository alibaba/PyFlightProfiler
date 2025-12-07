import argparse
import importlib
import json
import os
import platform
import re
import signal
import socket
import sys
import tempfile
import time
import traceback
from importlib.metadata import version
from pathlib import Path
from subprocess import PIPE, Popen
from typing import Any, Dict

from flight_profiler.common.global_store import (
    FORBIDDEN_COMMANDS_IN_PY314,
    set_history_file_path,
    set_inject_server_pid,
)
from flight_profiler.common.system_logger import logger
from flight_profiler.communication.flight_client import FlightClient
from flight_profiler.plugins.help.help_agent import HELP_COMMANDS_NAMES
from flight_profiler.utils.cli_util import (
    show_error_info,
    show_normal_info,
    verify_exit_code,
)
from flight_profiler.utils.env_util import is_linux, is_mac, py_higher_than_314
from flight_profiler.utils.render_util import (
    COLOR_END,
    COLOR_GREEN,
    COLOR_ORANGE,
    COLOR_RED,
    COLOR_WHITE_255,
    build_colorful_banners,
    build_title_hints,
)
from flight_profiler.utils.shell_util import execute_shell, get_py_bin_path

# Check readline availability, which may not be enabled in some python distribution.
try:
    import readline
    READLINE_AVAILABLE = readline is not None
except ImportError:
    READLINE_AVAILABLE = False

class ProfilerCli(object):

    def __init__(self, port: int,
                 target_executable: str):
        self.port = port
        self.server_pid = None
        self.target_executable = target_executable
        home = str(Path.home())
        output_dir = os.path.join(home, "pyFlightProfiler")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        self.history_file = os.path.join(output_dir, "cli_history")
        set_history_file_path(self.history_file)
        self.current_plugin = None

    def run(self):
        build_colorful_banners()
        build_title_hints([
            ("pid", str(self.server_pid)),
            ("py_executable", self.target_executable)
        ])

        while True:
            try:
                prompt = f"[cmd@{self.server_pid}]$ "
                cmd = input(prompt).strip()
                if len(cmd) == 0:
                    print("", end="")
                    continue
                self.do_action(cmd)
            except EOFError:
                if READLINE_AVAILABLE:
                    readline.write_history_file(self.history_file)
                sys.exit("CTRL+D pressed. Exiting Profiler.")
            except KeyboardInterrupt:
                print("")
                pass

    def check_need_help(self, cmd: str) -> bool:
        return " --help " in cmd or " -h " in cmd or cmd.endswith("-h") or cmd.endswith("--help")

    def do_action(self, cmd: str):
        try:
            cmd = cmd.strip()
            parts = re.split(r"\s", cmd)
            if parts[0] == "quit" or parts[0] == "exit" or parts[0] == "stop":
                if READLINE_AVAILABLE:
                    readline.write_history_file(self.history_file)
                from flight_profiler.plugins.cli_plugin import QuitCliPlugin

                self.current_plugin = QuitCliPlugin(self.port, self.server_pid)
                self.current_plugin.do_action(cmd[cmd.find(parts[0]) + len(parts[0]) :])
            else:
                module_name = (
                    "flight_profiler.plugins." + parts[0] + ".cli_plugin_" + parts[0]
                )
                try:
                    if (py_higher_than_314() and parts[0] in FORBIDDEN_COMMANDS_IN_PY314 or
                        not READLINE_AVAILABLE and parts[0] == "history"):
                        raise ModuleNotFoundError

                    module = importlib.import_module(module_name)
                except ModuleNotFoundError as e:
                    print(
                        f"{COLOR_RED} Unsupported command {parts[0]}, use {COLOR_END}{COLOR_ORANGE}help{COLOR_END}{COLOR_RED} "
                        f"to find available commands!{COLOR_END}"
                    )
                    return
                self.current_plugin = module.get_instance(self.port, self.server_pid)
                if self.check_need_help(cmd):
                    help_msg = self.current_plugin.get_help()
                    if help_msg is not None:
                        show_normal_info(help_msg)
                    else:
                        self.current_plugin.do_action(
                            cmd[cmd.find(parts[0]) + len(parts[0]) :]
                        )
                else:
                    self.current_plugin.do_action(
                        cmd[cmd.find(parts[0]) + len(parts[0]) :]
                    )
        except KeyboardInterrupt:
            if self.current_plugin is not None:
                try:
                    self.current_plugin.on_interrupted()
                    print()  # create new line
                except Exception:
                    show_error_info(traceback.format_exc())
        except Exception:
            show_error_info(traceback.format_exc())

    def check_status(self, timeout=None):
        s = time.time()

        check_preload = False
        if timeout is None:
            timeout = 5
        while time.time() - s < timeout:
            try:
                client = FlightClient("localhost", self.port)
            except:
                time.sleep(0.5)
                continue
            try:
                server_resp: Dict[str, Any] = json.loads(
                    client.request({"target": "status", "is_plugin_calling": False})
                )
                if server_resp["app_type"] != "py_flight_profiler":
                    continue
                self.server_pid = server_resp["pid"]
                set_inject_server_pid(self.server_pid)
                check_preload = True
                client.close()
                break
            except:
                time.sleep(2)
                continue
        return check_preload


def check_server_injected(
    pid: str, start_port: int, end_port: int, timeout: int
) -> int:
    """
    check pid injected or not by request local /status path from start_port to end_port
    not strictly right, useful for most of situations

    :param pid: target pid
    :param start_port: checking start port
    :param end_port: checking end port
    :param timeout: checking timeout, seconds
    :return flight_agent and server connect port, -1 if not injected
    """
    fault_tolerance = 0
    for port in range(start_port, end_port):
        try:
            try:
                client = FlightClient("localhost", port)
            except:
                continue
            try:
                server_resp: Dict[str, Any] = json.loads(
                    client.request({"target": "status", "is_plugin_calling": False})
                )
                if server_resp["app_type"] != "py_flight_profiler":
                    continue
                server_pid = server_resp["pid"]
                if str(server_pid) == pid:
                    return port
            except:
                # maybe the port is used by application
                continue
            finally:
                client.close()
        except:
            # this port is inaccessible, if the server already injected, mostly use this port
            # but if previous injected process is dead, may cause reinjected again, so add fault_tolerance check
            fault_tolerance += 1
            if fault_tolerance >= 3:
                break
    return -1


def completer(text, state):
    """
    complete first command
    """
    if not READLINE_AVAILABLE:
        return None

    import readline
    line_buf = readline.get_line_buffer()
    words = line_buf.strip().split()

    if len(words) <= 1 and (len(line_buf) == 0 or not line_buf[-1].isspace()):
        options = [name for name in HELP_COMMANDS_NAMES if name.startswith(text)]
    else:
        options = []  # only complete first command

    try:
        return options[state]
    except IndexError:
        return None


def find_port_available(start_port: int, end_port: int) -> int:
    """
    find available port for client/server communicate in range[start_port, end_port]
    returns -1 if not find
    """
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except socket.error:
                continue
    return -1

def check_directory_write_permission(directory: str) -> bool:
    """
    Check if the current process has write permission to the specified directory.

    Args
        directory(str): The directory path to check

    Returns:
        True if write permission is available, False otherwise
    """
    try:
        # Try to create a temporary file in the directory
        test_file = os.path.join(directory, ".write_test_tmp")
        with open(test_file, "w") as f:
            f.write("test")
        # If successful, remove the test file
        os.remove(test_file)
        return True
    except (PermissionError, OSError):
        return False
    except Exception:
        return False


def get_base_addr(current_directory: str, server_pid: str, platform: str) -> int:
    base_addr_locate_shell_path = os.path.join(
        current_directory, f"shell/{platform}/py_bin_base_addr_locate.sh"
    )
    base_addr = execute_shell(
        base_addr_locate_shell_path, ["bash", base_addr_locate_shell_path, server_pid, str(sys.executable)]
    )
    if base_addr is None or len(base_addr) == 0:
        show_error_info(
            f"[Error] can't locate python bin base addr, please make sure target python process and flight_profiler is in the same python environment."
        )
        exit(1)
    try:
        base_addr = int(base_addr, 16)
    except:
        show_error_info(f"\n{base_addr}")
        exit(1)
    return base_addr


def do_inject_on_linux(free_port: int, server_pid: str, debug: bool = False) -> int:
    """
    inject by ptrace under linux env
    returns target port if inject successfully, otherwise exit abnormally
    """
    current_directory = os.path.dirname(os.path.abspath(__file__))
    base_addr = get_base_addr(current_directory, server_pid, "linux")

    code_inject_py: str = os.path.join(current_directory, "code_inject.py")
    with open(os.path.join(current_directory, "lib/inject_params.data"), "w") as f:
        f.write(f"{code_inject_py.strip()},{free_port},{base_addr}\n")

    shell_path = os.path.join(current_directory, "lib/inject")
    # Add debug flag to the command if enabled
    cmd_args = [str(shell_path), server_pid]
    if debug:
        cmd_args.append("--debug")

    ps = Popen(
        cmd_args,
        stdin=PIPE,
        stdout=None,
        stderr=None,
        bufsize=1,
        text=True,
    )
    exit_code = ps.wait()
    verify_exit_code(exit_code, server_pid)
    return free_port


def do_inject_on_mac(free_port: int, server_pid: str, debug: bool = False) -> int:
    """
    inject by lldb under mac env
    returns target port if inject successfully, otherwise exit abnormally
    """
    tmp_fd, tmp_file_path = tempfile.mkstemp()
    current_directory = os.path.dirname(os.path.abspath(__file__))
    shell_path = os.path.join(current_directory, "shell/code_inject.sh")

    # Prepare command arguments
    cmd_args = [str(shell_path), str(os.getpid()), server_pid, tmp_file_path, str(free_port)]
    if debug:
        cmd_args.append("--debug")

    ps = Popen(
        cmd_args,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        bufsize=1,
        text=True,
    )
    if debug:
        # Only print output in debug mode
        while True:
            output = ps.stdout.readline()
            if output:
                print(output, end="")
            else:
                break
    ps.wait()
    with open(tmp_file_path, "r") as temp:
        content = temp.read()
        if content is None or len(content) == 0:
            print("PyFlightProfiler attach failed!")
            exit(1)
        return int(content)



def do_inject_with_sys_remote_exec(free_port: int, server_pid: str, debug: bool = False):
    current_directory = os.path.dirname(os.path.abspath(__file__))
    code_inject_py: str = os.path.join(current_directory, "code_inject.py")
    inject_code_file_path: str = os.path.join(current_directory, f"code_inject_{server_pid}_{int(time.time())}.py")
    shared_lib_suffix = "so" if is_linux() else "dylib"
    inject_agent_so_path: str = os.path.join(current_directory, "lib", f"flight_profiler_agent.{shared_lib_suffix}")

    if is_linux():
        nm_symbol_offset= get_base_addr(current_directory, server_pid, "linux")
    else:
        nm_symbol_offset = get_base_addr(current_directory, server_pid, "mac")

    with open(code_inject_py, 'r', encoding='utf-8') as f:
        content = f.read()
    modified_content = content.replace("${listen_port}", str(free_port))
    modified_content = modified_content.replace("${current_file_abspath}", inject_code_file_path)
    modified_content = modified_content.replace("${flight_profiler_agent_so_path}", inject_agent_so_path)
    modified_content = modified_content.replace("${nm_symbol_offset}", str(nm_symbol_offset))
    with open(inject_code_file_path, 'w', encoding='utf-8') as f:
        f.write(modified_content)

    try:
        sys.remote_exec(int(server_pid), inject_code_file_path)
    except PermissionError as e:
        show_error_info(f"\n[ERROR] Higher Permission required! This error id caused by {e}")
        show_normal_info(f"[{COLOR_GREEN}Solution{COLOR_END}{COLOR_WHITE_255}] Try run flight_profiler $pid as {COLOR_RED}root{COLOR_END}{COLOR_WHITE_255}!")
        exit(1)
    except:
        logger.exception(f"Attach via sys.remote_exec failed!")
        exit(1)
    return free_port


def show_pre_attach_info(server_pid: str, debug: bool = False):
    from flight_profiler.utils.env_util import (
        get_current_process_uids,
        get_process_uids,
    )

    current_directory = os.path.dirname(os.path.abspath(__file__))
    server_executable: str = get_py_bin_path(server_pid)
    client_executable: str = get_py_bin_path(os.getpid())
    same: bool = server_executable == client_executable

    # Get process UIDs for permission comparison
    server_uids = get_process_uids(server_pid)
    client_uids = get_current_process_uids()

    # Print executable information
    print(f"PyFlightProfiler version: {version('flight_profiler')}")
    print(f"[INFO] Platform system: {platform.system()}. Architecture: {platform.machine()}")
    print(f"[INFO] Installation directory: {current_directory}.")
    if debug:
        print(f"[DEBUG] Server Python Executable: {server_executable}")
        print(f"[DEBUG] Client Python Executable: {client_executable}")
    print(f"[INFO] Verify pyFlightProfiler and target are using the same python executable: {'🌟' if same else '❌'}")

    # Check directory write permissions
    directory_write_permission = check_directory_write_permission(current_directory)
    permission_status = "🌟" if directory_write_permission else "❌"
    print(f"[INFO] Verify pyFlightProfiler has write permission to installation directory: {permission_status}")
    if not directory_write_permission:
        print(f"[WARN] PyFlightProfiler needs write permission to {current_directory} to function properly. "
              f"Please try run {COLOR_RED}flight_profiler with appropriate permissions{COLOR_END}.")

    # Print permission information
    if server_uids and client_uids:
        server_real_uid, server_effective_uid, server_saved_uid, server_filesystem_uid = server_uids
        client_real_uid, client_effective_uid, client_saved_uid, client_filesystem_uid = client_uids

        if debug:
            print(f"[INFO] Server Process - Real UID: {server_real_uid}, Effective UID: {server_effective_uid}")
            print(f"[INFO] Client Process - Real UID: {client_real_uid}, Effective UID: {client_effective_uid}")

        # Check if client has sufficient privileges
        has_sufficient_privileges = (
            client_effective_uid == 0 or  # Client is root
            client_effective_uid == server_real_uid or  # Client is same user as server owner
            client_effective_uid == server_effective_uid  # Client has same effective UID as server
        )

        privilege_status = "🌟" if has_sufficient_privileges else "❌"
        print(f"[INFO] Verify pyFlightProfiler has user permission to attach target: {privilege_status}")

        # Additional check for root privileges
        if server_real_uid == 0 and client_effective_uid != 0:
            print(f"[WARN] Target process is running as root, elevated privileges may be required.")
        elif client_effective_uid != 0 and server_real_uid != client_real_uid:
            print(f"[WARN] Target process is owned by a different user, permission issues may occur.")
    else:
        print(f"[INFO] Permission information not available on this platform.")

def run():
    parser = argparse.ArgumentParser(
        usage="%(prog)s <pid> \n\ndescription: A realtime analysis tool used for profiling python program!  \n"
              " "
    )
    parser.add_argument(
        "pid",
        type=int,
        help="python process id to analyze."
    )
    parser.add_argument("--cmd", required=False, type=str, help="One-time profile, primarily used for unit testing.")
    parser.add_argument("--debug", required=False, action="store_true", help="enable debug logging for attachment.")
    try:
        args = parser.parse_args()
    except:
        exit(1)
    server_pid = str(args.pid)
    inject_start_port = int(os.getenv("PYFLIGHT_INJECT_START_PORT", 16000))
    inject_end_port = int(os.getenv("PYFLIGHT_INJECT_END_PORT", 16500))
    inject_timeout = int(os.getenv("PYFLIGHT_INJECT_TIMEOUT", 5))
    show_pre_attach_info(server_pid, args.debug)

    connect_port: int = check_server_injected(
        server_pid, inject_start_port, inject_end_port, inject_timeout
    )
    if connect_port < 0:
        free_port: int = find_port_available(inject_start_port, inject_end_port)
        if free_port < 0:
            print(
                f"No available debug port between range: {inject_start_port} {inject_end_port}"
            )
        if sys.version_info >= (3, 14):
            if not is_linux() and not is_mac():
                print(f"flight profiler is not enabled on platform: {platform.system()}.")
                exit(1)
            # sys.remote_exec is provided in CPython 3.14, we can just use it to inject agent code
            connect_port = do_inject_with_sys_remote_exec(free_port, server_pid, args.debug)
        else:
            if is_linux():
                connect_port = do_inject_on_linux(free_port, server_pid, args.debug)
            elif is_mac():
                connect_port = do_inject_on_mac(free_port, server_pid, args.debug)
            else:
                print(f"flight profiler is not enabled on platform: {platform.system()}.")
                exit(1)
    else:
        print(
            f"[INFO] Process {server_pid} was attached through port {connect_port} already, so keep reusing the same port."
        )

    # add tab complete
    if READLINE_AVAILABLE:
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
    cli = ProfilerCli(port=connect_port, target_executable=get_py_bin_path(server_pid))
    check_preload = cli.check_status(timeout=5)
    if check_preload:
        print(f"\nPyFlightProfiler: 🌟 attach target process {server_pid} successfully!")
    else:
        # here the injection routine is done successfully, but server has no chance to respond
        verify_exit_code(16, server_pid)

    # load history cmd
    if os.path.exists(cli.history_file) and READLINE_AVAILABLE:
        readline.read_history_file(cli.history_file)

    # run cmd once and exit
    if hasattr(args, "cmd") and getattr(args, "cmd") is not None:
        cmd_args = getattr(args, "cmd")
        if READLINE_AVAILABLE:
            readline.add_history(cmd_args)
        cli.do_action(cmd_args)
        if READLINE_AVAILABLE:
            readline.write_history_file(cli.history_file)
        exit(0)

    def handler(signum, frame):
        if READLINE_AVAILABLE:
            readline.write_history_file(cli.history_file)
        sys.exit("CTRL+Z pressed. Exiting Profiler.")

    signal.signal(signal.SIGTSTP, handler)
    cli.run()


if __name__ == "__main__":
    run()
