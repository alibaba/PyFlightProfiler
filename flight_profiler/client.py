import argparse
import importlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import sys
import tempfile
import time
import traceback
from contextlib import nullcontext
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
    COLOR_FAINT,
    COLOR_GREEN,
    COLOR_ORANGE,
    COLOR_RED,
    COLOR_WHITE_255,
    build_welcome_box,
)
from flight_profiler.utils.shell_util import execute_shell, get_py_bin_path
from flight_profiler.utils.terminal_input import BoxLineEditor

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
        self.first_input = True
        self.editor = BoxLineEditor(completions=HELP_COMMANDS_NAMES)

    def run(self):
        build_welcome_box(str(self.server_pid), self.target_executable)

        prompt_active = f"{COLOR_WHITE_255}❯{COLOR_END} "
        prompt_gray = f"{COLOR_FAINT}❯{COLOR_END} "

        while True:
            try:
                cmd = self.editor.read_input(
                    prompt_active, prompt_gray,
                    show_placeholder=self.first_input,
                )

                if len(cmd) == 0:
                    continue

                self.first_input = False

                if READLINE_AVAILABLE:
                    readline.add_history(cmd)

                self.do_action(cmd)
            except EOFError:
                if READLINE_AVAILABLE:
                    readline.write_history_file(self.history_file)
                sys.exit(0)
            except KeyboardInterrupt:
                if READLINE_AVAILABLE:
                    readline.write_history_file(self.history_file)
                sys.exit(0)

    def check_need_help(self, cmd: str) -> bool:
        return " --help " in cmd or " -h " in cmd or cmd.endswith("-h") or cmd.endswith("--help")

    def do_action(self, cmd: str):
        try:
            cmd = cmd.strip()
            parts = re.split(r"\s", cmd)
            if parts[0] == "quit" or parts[0] == "exit" or parts[0] == "stop":
                with self.editor.suppress_input():
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
                        f"to find available commands!{COLOR_END}\n"
                    )
                    return
                self.current_plugin = module.get_instance(self.port, self.server_pid)
                ctx = nullcontext() if self.current_plugin.handles_own_input else self.editor.suppress_input()
                with ctx:
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
            sys.stdout.write('\r\033[2K\n')
            sys.stdout.flush()
            if self.current_plugin is not None:
                try:
                    self.current_plugin.on_interrupted()
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
        options = [name + " " for name in HELP_COMMANDS_NAMES if name.startswith(text)]
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
    # Pass the lsof-resolved client binary path so the script compares the same
    # path representation as it derives from the server pid. On macOS framework
    # Pythons, sys.executable points at bin/pythonX.Y while lsof reports the
    # Python.app/Contents/MacOS/Python launcher — comparing them directly fails.
    client_bin_path = get_py_bin_path(os.getpid())
    base_addr = execute_shell(
        base_addr_locate_shell_path, ["bash", base_addr_locate_shell_path, server_pid, client_bin_path]
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


def do_inject_on_linux(free_port: int, server_pid: str, debug: bool = False, diagnostic_messages: list = None) -> int:
    """
    inject by ptrace under linux env
    returns target port if inject successfully, otherwise exit abnormally
    """
    current_directory = os.path.dirname(os.path.abspath(__file__))
    base_addr = get_base_addr(current_directory, server_pid, "linux")

    profiler_agent_py: str = os.path.join(current_directory, "profiler_agent.py")
    with open(os.path.join(current_directory, "lib/attach_params.data"), "w") as f:
        f.write(f"{profiler_agent_py.strip()},{free_port},{base_addr}\n")

    shell_path = os.path.join(current_directory, "lib/attach")
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
    if exit_code != 0 and not debug and diagnostic_messages:
        for msg in diagnostic_messages:
            print(msg)
    verify_exit_code(exit_code, server_pid)
    return free_port


def do_inject_on_mac(free_port: int, server_pid: str, debug: bool = False, diagnostic_messages: list = None) -> int:
    """
    inject by lldb under mac env
    returns target port if inject successfully, otherwise exit abnormally
    """
    tmp_fd, tmp_file_path = tempfile.mkstemp()
    current_directory = os.path.dirname(os.path.abspath(__file__))
    shell_path = os.path.join(current_directory, "shell/profiler_attach.sh")

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
    stdout_output, stderr_output = ps.communicate()
    if debug and stdout_output:
        print(stdout_output, end="")
    with open(tmp_file_path, "r") as temp:
        content = temp.read()
        if content is None or len(content) == 0:
            # Print diagnostic info on failure (skip if already printed in debug mode)
            if not debug and diagnostic_messages:
                for msg in diagnostic_messages:
                    print(msg)
            # Print process output on failure (contains error details)
            if not debug and stdout_output:
                print(stdout_output, end="" if stdout_output.endswith("\n") else "\n")
            print("PyFlightProfiler attach failed!")
            exit(1)
        return int(content)



def do_inject_with_sys_remote_exec(free_port: int, server_pid: str, debug: bool = False, diagnostic_messages: list = None):
    current_directory = os.path.dirname(os.path.abspath(__file__))
    profiler_agent_py: str = os.path.join(current_directory, "profiler_agent.py")
    inject_code_file_path: str = os.path.join(current_directory, f"profiler_agent_{server_pid}_{int(time.time())}.py")
    shared_lib_suffix = "so" if is_linux() else "dylib"
    inject_agent_so_path: str = os.path.join(current_directory, "lib", f"flight_profiler_agent.{shared_lib_suffix}")

    if is_linux():
        nm_symbol_offset= get_base_addr(current_directory, server_pid, "linux")
    else:
        nm_symbol_offset = get_base_addr(current_directory, server_pid, "mac")

    with open(profiler_agent_py, 'r', encoding='utf-8') as f:
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
        # Print diagnostic info on failure (skip if already printed in debug mode)
        if not debug and diagnostic_messages:
            for msg in diagnostic_messages:
                print(msg)
        show_error_info(f"\n[ERROR] Higher Permission required! This error id caused by {e}")
        show_normal_info(f"[{COLOR_GREEN}Solution{COLOR_END}{COLOR_WHITE_255}] Try run flight_profiler $pid as {COLOR_RED}root{COLOR_END}{COLOR_WHITE_255}!")
        exit(1)
    except:
        # Print diagnostic info on failure (skip if already printed in debug mode)
        if not debug and diagnostic_messages:
            for msg in diagnostic_messages:
                print(msg)
        logger.exception(f"Attach via sys.remote_exec failed!")
        exit(1)
    return free_port


def show_pre_attach_info(server_pid: str, debug: bool = False) -> list:
    """
    Collect pre-attach diagnostic information.
    Returns a list of info messages to be printed only on failure.
    """
    from flight_profiler.utils.env_util import (
        get_current_process_uids,
        get_process_uids,
    )

    messages = []
    current_directory = os.path.dirname(os.path.abspath(__file__))
    server_executable: str = get_py_bin_path(server_pid)
    client_executable: str = get_py_bin_path(os.getpid())
    same: bool = server_executable == client_executable

    # Get process UIDs for permission comparison
    server_uids = get_process_uids(server_pid)
    client_uids = get_current_process_uids()

    # Collect diagnostic information
    messages.append(f"PyFlightProfiler version: {version('flight_profiler')}")
    messages.append(f"[INFO] Platform system: {platform.system()}. Architecture: {platform.machine()}")
    messages.append(f"[INFO] Installation directory: {current_directory}.")
    if debug:
        messages.append(f"[DEBUG] Server Python Executable: {server_executable}")
        messages.append(f"[DEBUG] Client Python Executable: {client_executable}")
    messages.append(f"[INFO] Verify pyFlightProfiler and target are using the same python executable: {'🌟' if same else '❌'}")

    # Check directory write permissions
    directory_write_permission = check_directory_write_permission(current_directory)
    permission_status = "🌟" if directory_write_permission else "❌"
    messages.append(f"[INFO] Verify pyFlightProfiler has write permission to installation directory: {permission_status}")
    if not directory_write_permission:
        messages.append(f"[WARN] PyFlightProfiler needs write permission to {current_directory} to function properly. "
              f"Please try run {COLOR_RED}flight_profiler with appropriate permissions{COLOR_END}.")

    # Collect permission information
    if server_uids and client_uids:
        server_real_uid, server_effective_uid, server_saved_uid, server_filesystem_uid = server_uids
        client_real_uid, client_effective_uid, client_saved_uid, client_filesystem_uid = client_uids

        if debug:
            messages.append(f"[INFO] Server Process - Real UID: {server_real_uid}, Effective UID: {server_effective_uid}")
            messages.append(f"[INFO] Client Process - Real UID: {client_real_uid}, Effective UID: {client_effective_uid}")

        # Check if client has sufficient privileges
        has_sufficient_privileges = (
            client_effective_uid == 0 or  # Client is root
            client_effective_uid == server_real_uid or  # Client is same user as server owner
            client_effective_uid == server_effective_uid  # Client has same effective UID as server
        )

        privilege_status = "🌟" if has_sufficient_privileges else "❌"
        messages.append(f"[INFO] Verify pyFlightProfiler has user permission to attach target: {privilege_status}")

        # Additional check for root privileges
        if server_real_uid == 0 and client_effective_uid != 0:
            messages.append(f"[WARN] Target process is running as root, elevated privileges may be required.")
        elif client_effective_uid != 0 and server_real_uid != client_real_uid:
            messages.append(f"[WARN] Target process is owned by a different user, permission issues may occur.")
    else:
        messages.append(f"[INFO] Permission information not available on this platform.")

    return messages

def _install_skills():
    """Install PyFlightProfiler skills to Claude Code, Gemini CLI, and Codex skill directories."""
    from flight_profiler.utils.render_util import (
        COLOR_END,
        COLOR_FAINT,
        COLOR_GREEN,
        COLOR_RED,
        COLOR_WHITE_255,
        COLOR_YELLOW,
        COLOR_BOLD,
        ICON_SUCCESS,
        ICON_FAILED,
        ICON_WARNING,
        ICON_DOT,
    )

    # Packaged layout: flight_profiler/skills/  |  Dev layout: <project_root>/skills/
    skills_src = Path(__file__).parent / "skills"
    if not skills_src.is_dir():
        skills_src = Path(__file__).parent.parent / "skills"
    if not skills_src.is_dir():
        print(f"{COLOR_RED}{ICON_FAILED} Skills directory not found{COLOR_END}")
        sys.exit(1)

    skill_dirs = sorted([d for d in skills_src.iterdir() if d.is_dir() and d.name.startswith("flight-profiler-") and (d / "SKILL.md").exists()])
    if not skill_dirs:
        print(f"{COLOR_YELLOW}{ICON_WARNING} No skill files found to install.{COLOR_END}")
        return

    skill_names = [d.name for d in skill_dirs]

    # Parse optional --dir argument
    custom_dir = None
    argv = sys.argv[2:]  # skip 'flight_profiler' and 'install-skills'
    if argv and argv[0] == "--dir" and len(argv) >= 2:
        custom_dir = Path(argv[1])

    if custom_dir:
        targets = [(str(custom_dir), custom_dir)]
    else:
        targets = [
            ("Claude Code", Path.home() / ".claude" / "skills"),
            ("Gemini CLI / Codex", Path.home() / ".agent" / "skills"),
        ]

    print(f"\n  {COLOR_GREEN}{COLOR_BOLD}✅ Installing {len(skill_names)} PyFlightProfiler skills{COLOR_END}\n")

    # Extract description from each SKILL.md frontmatter
    skill_descriptions = {}
    for skill_dir in skill_dirs:
        try:
            with open(skill_dir / "SKILL.md", "r") as f:
                for line in f:
                    if line.startswith("description:"):
                        skill_descriptions[skill_dir.name] = line[len("description:"):].strip()
                        break
        except Exception:
            pass

    print(f"  {COLOR_FAINT}Skills:{COLOR_END}")
    for idx, name in enumerate(skill_names):
        if idx > 0:
            print()
        desc = skill_descriptions.get(name, "")
        print(f"    {COLOR_GREEN}{ICON_DOT}{COLOR_END} {COLOR_WHITE_255}{name}{COLOR_END}")
        if desc:
            import textwrap
            term_width = shutil.get_terminal_size().columns
            indent = "      "
            prefix = indent + "Description: "
            wrapped = textwrap.fill(desc, width=min(max(term_width, 40), 120),
                                    initial_indent=prefix, subsequent_indent=indent)
            print(f"{COLOR_FAINT}{wrapped}{COLOR_END}")

    print(f"\n  {COLOR_FAINT}Targets:{COLOR_END}")
    for label, dst_dir in targets:
        for skill_dir in skill_dirs:
            target_skill_dir = dst_dir / skill_dir.name
            target_skill_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skill_dir / "SKILL.md", target_skill_dir / "SKILL.md")
        print(f"    {COLOR_GREEN}{ICON_SUCCESS}{COLOR_END} {COLOR_WHITE_255}{label}{COLOR_END} {COLOR_FAINT}({dst_dir}/){COLOR_END}")

    labels = [label for label, _ in targets]
    print(f"\n  {COLOR_FAINT}✨ Skills are now available in {', '.join(labels)}.{COLOR_END}\n")


def run():
    if len(sys.argv) >= 2 and sys.argv[1] == "install-skills":
        _install_skills()
        return

    parser = argparse.ArgumentParser(
        usage="%(prog)s <pid> [options]\n       %(prog)s install-skills [--dir <path>]"
              "\n\ndescription: A realtime analysis tool used for profiling python program!\n",
        epilog="subcommands:\n"
               "  install-skills          Install Claude Code / Gemini CLI / Codex skills\n"
               "  install-skills --dir D  Install skills to a custom directory\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pid",
        type=int,
        help="python process id to analyze."
    )
    parser.add_argument("--cmd", required=False, type=str, help="One-time profile, primarily used for unit testing.")
    parser.add_argument("--debug", required=False, action="store_true", help="enable debug logging for attachment.")
    parser.add_argument("--no-color", required=False, action="store_true", dest="no_color", help="Disable colored output (also respects NO_COLOR env var).")
    try:
        args = parser.parse_args()
    except:
        exit(1)
    # Disable colors if --no-color flag or NO_COLOR env var is set
    if getattr(args, "no_color", False) or os.getenv("NO_COLOR"):
        from flight_profiler.utils.render_util import _NoColorStream
        sys.stdout = _NoColorStream(sys.stdout)

    server_pid = str(args.pid)
    inject_start_port = int(os.getenv("PYFLIGHT_INJECT_START_PORT", 16000))
    inject_end_port = int(os.getenv("PYFLIGHT_INJECT_END_PORT", 16500))
    inject_timeout = int(os.getenv("PYFLIGHT_INJECT_TIMEOUT", 5))

    # Collect diagnostic info (print immediately if debug mode, otherwise only on failure)
    diagnostic_messages = show_pre_attach_info(server_pid, args.debug)
    if args.debug:
        for msg in diagnostic_messages:
            print(msg)
        print()  # Empty line before welcome box

    connect_port: int = check_server_injected(
        server_pid, inject_start_port, inject_end_port, inject_timeout
    )
    if connect_port < 0:
        free_port: int = find_port_available(inject_start_port, inject_end_port)
        if free_port < 0:
            # Print diagnostic info on failure (skip if already printed in debug mode)
            if not args.debug:
                for msg in diagnostic_messages:
                    print(msg)
            print(
                f"No available debug port between range: {inject_start_port} {inject_end_port}"
            )
            exit(1)
        if sys.version_info >= (3, 14):
            if not is_linux() and not is_mac():
                if not args.debug:
                    for msg in diagnostic_messages:
                        print(msg)
                print(f"flight profiler is not enabled on platform: {platform.system()}.")
                exit(1)
            # sys.remote_exec is provided in CPython 3.14, we can just use it to inject agent code
            connect_port = do_inject_with_sys_remote_exec(free_port, server_pid, args.debug, diagnostic_messages)
        else:
            if is_linux():
                connect_port = do_inject_on_linux(free_port, server_pid, args.debug, diagnostic_messages)
            elif is_mac():
                connect_port = do_inject_on_mac(free_port, server_pid, args.debug, diagnostic_messages)
            else:
                if not args.debug:
                    for msg in diagnostic_messages:
                        print(msg)
                print(f"flight profiler is not enabled on platform: {platform.system()}.")
                exit(1)

    # add tab complete
    if READLINE_AVAILABLE:
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
    cli = ProfilerCli(port=connect_port, target_executable=get_py_bin_path(server_pid))
    check_preload = cli.check_status(timeout=5)
    if not check_preload:
        # Print diagnostic info on failure (skip if already printed in debug mode)
        if not args.debug:
            for msg in diagnostic_messages:
                print(msg)
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
