from typing import Dict, List

from flight_profiler.help_descriptions import (
    CLS_COMMAND_DESCRIPTION,
    CONSOLE_COMMAND_DESCRIPTION,
    GETGLOBAL_COMMAND_DESCRIPTION,
    GILSTAT_COMMAND_DESCRIPTION,
    HELP_COMMAND_DESCRIPTION,
    HISTORY_COMMAND_DESCRIPTION,
    MEM_COMMAND_DESCRIPTION,
    MODULE_COMMAND_DESCRIPTION,
    PERF_COMMAND_DESCRIPTION,
    RELOAD_COMMAND_DESCRIPTION,
    STACK_COMMAND_DESCRIPTION,
    TIME_TUNNEL_COMMAND_DESCRIPTION,
    TORCH_COMMAND_DESCRIPTION,
    TRACE_COMMAND_DESCRIPTION,
    VMTOOL_COMMAND_DESCRIPTION,
    WATCH_COMMAND_DESCRIPTION,
    CommandDescription,
)
from flight_profiler.utils.env_util import py_higher_than_314, readline_enable
from flight_profiler.utils.render_util import (
    COLOR_BOLD,
    COLOR_BRIGHT_GREEN,
    COLOR_END,
    COLOR_WHITE_255,
    align_prefix,
)

HELP_COMMANDS_DESCRIPTIONS: List[CommandDescription] = [
    CLS_COMMAND_DESCRIPTION,
    CONSOLE_COMMAND_DESCRIPTION,
    GETGLOBAL_COMMAND_DESCRIPTION,
    GILSTAT_COMMAND_DESCRIPTION,
    HELP_COMMAND_DESCRIPTION,
    HISTORY_COMMAND_DESCRIPTION,
    MEM_COMMAND_DESCRIPTION,
    MODULE_COMMAND_DESCRIPTION,
    PERF_COMMAND_DESCRIPTION,
    RELOAD_COMMAND_DESCRIPTION,
    STACK_COMMAND_DESCRIPTION,
    TRACE_COMMAND_DESCRIPTION,
    TORCH_COMMAND_DESCRIPTION,
    TIME_TUNNEL_COMMAND_DESCRIPTION,
    VMTOOL_COMMAND_DESCRIPTION,
    WATCH_COMMAND_DESCRIPTION,
]
HELP_COMMANDS_NAMES: List[str] = [
    "cls",
    "console",
    "getglobal",
    "gilstat",
    "help",
    "history",
    "mem",
    "module",
    "perf",
    "reload",
    "stack",
    "trace",
    "torch",
    "tt",
    "vmtool",
    "watch",
]

if py_higher_than_314():
    HELP_COMMANDS_DESCRIPTIONS.remove(PERF_COMMAND_DESCRIPTION)
    HELP_COMMANDS_NAMES.remove("perf")

if not readline_enable():
    HELP_COMMANDS_DESCRIPTIONS.remove(HISTORY_COMMAND_DESCRIPTION)
    HELP_COMMANDS_NAMES.remove("history")



class HelpAgent:

    def __init__(self):
        self.name_to_description: Dict[str, CommandDescription] = {}
        for idx in range(len(HELP_COMMANDS_NAMES)):
            self.name_to_description[HELP_COMMANDS_NAMES[idx]] = (
                HELP_COMMANDS_DESCRIPTIONS[idx]
            )

    def display_all_commands(self):
        """
        help default show all command
        """
        display_msg = ""
        display_msg += f"{COLOR_WHITE_255}{COLOR_BOLD}{'NAME':<15}{align_prefix(15, 'DESCRIPTION')}{COLOR_END}\n"
        for c_idx in range(len(HELP_COMMANDS_NAMES)):
            display_msg += f"{COLOR_BRIGHT_GREEN}{HELP_COMMANDS_NAMES[c_idx]:<15}{COLOR_END}{align_prefix(15, HELP_COMMANDS_DESCRIPTIONS[c_idx].summary)}\n"
        return display_msg

    def get_command_description(self, command_name: str) -> str:
        """
        get target command description
        """
        command_name = command_name.strip()
        if command_name not in self.name_to_description:
            return self.hint()
        else:
            return self.name_to_description[command_name].help_hint()

    def hint(self):
        """
        wrong input hint
        """
        return (
            f"{COLOR_WHITE_255}Usage: help {'|'.join(HELP_COMMANDS_NAMES)}{COLOR_END}"
        )


global_help_agent = HelpAgent()
