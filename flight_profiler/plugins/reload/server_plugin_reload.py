import traceback

from flight_profiler.plugins.reload.reload_agent import ReloadAgent
from flight_profiler.plugins.reload.reload_parser import ReloadParams, ReloadParser
from flight_profiler.plugins.server_plugin import Message, ServerPlugin, ServerQueue


class ReloadServerPlugin(ServerPlugin):
    def __init__(self, cmd: str, out_q: ServerQueue):
        super().__init__(cmd, out_q)

    async def do_action(self, param):
        """
        Handle reload command request.

        Args:
            param: Command parameters as a string

        Returns:
            Result message as a string
        """
        try:
            # Parse the parameters
            parser = ReloadParser()
            params: ReloadParams = parser.parse_reload_params(param)

            # Perform the reload operation
            result = ReloadAgent.reload_function(
                module_name=params.module_name,
                class_name=params.class_name,
                func_name=params.func_name,
                verbose=params.verbose
            )

            self.out_q.output_msg_nowait(
                Message(
                    True,
                    result
                )
            )
        except Exception as e:
            self.out_q.output_msg_nowait(
                Message(True, traceback.format_exc())
            )

def get_instance(cmd: str, out_q: ServerQueue):
    return ReloadServerPlugin(cmd, out_q)
