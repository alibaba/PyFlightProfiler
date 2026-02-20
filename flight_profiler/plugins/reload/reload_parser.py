import argparse
from argparse import RawTextHelpFormatter
from typing import Optional

from flight_profiler.help_descriptions import RELOAD_COMMAND_DESCRIPTION
from flight_profiler.utils.args_util import rewrite_args


class ReloadParams:

    def __init__(
        self,
        module_name: str,
        class_name: Optional[str],
        func_name: str,
        verbose: bool,
    ):
        self.module_name = module_name
        self.class_name = class_name
        self.func_name = func_name
        self.verbose = verbose

class ReloadParser(argparse.ArgumentParser):

    def __init__(self):
        super(ReloadParser, self).__init__(
            description=RELOAD_COMMAND_DESCRIPTION.help_hint(),
            add_help=True,
            formatter_class=RawTextHelpFormatter,
        )
        if hasattr(self, "exit_on_error"):
            self.exit_on_error = False

        self.add_argument("--mod", required=True, help="module package")
        self.add_argument("--cls", required=False, help="class name")
        self.add_argument("--func", required=True, help="function name")
        self.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            default=False,
            help="display the newest method source without nested.",
        )

    def error(self, message):
        raise Exception(message)

    def parse_reload_params(self, arg_string: str) -> ReloadParams:
        new_args = rewrite_args(
            arg_string, unspec_names=["mod", "cls", "func"], omit_column="cls"
        )
        args = self.parse_args(args=new_args)
        return ReloadParams(
            module_name=getattr(args, "mod"),
            class_name=getattr(args, "cls"),
            func_name=getattr(args, "func"),
            verbose=getattr(args, "verbose")
        )
