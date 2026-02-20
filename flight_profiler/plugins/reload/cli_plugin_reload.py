from flight_profiler.help_descriptions import RELOAD_COMMAND_DESCRIPTION
from flight_profiler.plugins.cli_plugin import BaseCliPlugin
from flight_profiler.plugins.reload.reload_parser import ReloadParser
from flight_profiler.utils.cli_util import (
    common_plugin_execute_routine,
    show_normal_info,
)


class ReloadCliPlugin(BaseCliPlugin):
    def __init__(self, port, server_pid):
        super().__init__(port, server_pid)

    def get_help(self):
        return RELOAD_COMMAND_DESCRIPTION.help_hint()

    def do_action(self, cmd):
        try:
            ReloadParser().parse_reload_params(cmd)
        except:
            show_normal_info(self.get_help())
            return

        common_plugin_execute_routine(
            cmd="reload",
            param=cmd,
            port=self.port,
            raw_text=True
        )

    def on_interrupted(self):
        pass


def get_instance(port: str, server_pid: int):
    return ReloadCliPlugin(port, server_pid)
