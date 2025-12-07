"""
Command descriptions followed by below format
 USAGE:
 SUMMARY:
 EXAMPLES:
 WIKI:
 OPTIONS:
"""

from typing import List, Optional, Tuple

from flight_profiler.utils.env_util import is_linux
from flight_profiler.utils.render_util import (
    COLOR_BOLD,
    COLOR_BRIGHT_GREEN,
    COLOR_END,
    COLOR_WHITE_255,
    align_prefix,
)


class CommandDescription:

    def __init__(
        self,
        usage: List[str],
        summary: str,
        examples: List[str],
        wiki: Optional[str],
        options: Optional[List[Tuple[str, str]]],
        option_offset=20,
    ):
        self._usage = usage
        self._summary = summary
        self._examples = examples
        self._wiki = wiki
        self._options = options
        self._option_offset = option_offset
        self._help = self._build_help_msg()

    @property
    def summary(self) -> str:
        return self._summary

    def help_hint(self) -> str:
        """
        command help should call help_hint to get hint
        """
        return self._help

    def _build_help_msg(self) -> str:
        usage = ""
        for single_usage in self._usage:
            usage += f"  {COLOR_WHITE_255}{single_usage}{COLOR_END}\n"
        examples = ""
        for single_example in self._examples:
            examples += f"  {COLOR_WHITE_255}{single_example}{COLOR_END}\n"
        options = ""
        if self._options is not None:
            for option in self._options:
                options += f"{COLOR_WHITE_255}{option[0].ljust(self._option_offset)}{align_prefix(self._option_offset, option[1])}{COLOR_END}\n"

        wiki_description = ""
        if self._wiki is not None:
            wiki_description = (
                f"{COLOR_BRIGHT_GREEN}{COLOR_BOLD}WIKI:{COLOR_END}\n"
                f"  {COLOR_WHITE_255}{self._wiki}{COLOR_END}\n\n"
            )
        return (
            f"{COLOR_BRIGHT_GREEN}{COLOR_BOLD}USAGE:{COLOR_END}\n"
            f"{usage}\n"
            f"{COLOR_BRIGHT_GREEN}{COLOR_BOLD}SUMMARY:{COLOR_END}\n"
            f"  {COLOR_WHITE_255}{self._summary}{COLOR_END}\n\n"
            f"{COLOR_BRIGHT_GREEN}{COLOR_BOLD}EXAMPLES:{COLOR_END}\n"
            f"{examples}\n"
            f"{wiki_description}"
            f"{COLOR_BRIGHT_GREEN}{COLOR_BOLD}OPTIONS:{COLOR_END}\n"
            f"{options}"
        )


CLS_COMMAND_DESCRIPTION = CommandDescription(
    usage=["cls [-h] "],
    summary="Clear the screen.",
    examples=["cls"],
    wiki=None,
    options=[("-h, --help", "show help.")],
)

GETGLOBAL_COMMAND_DESCRIPTION = CommandDescription(
    usage=["getglobal module [class] field [-x <value>] [-e <value>] [-r] [-v]"],
    summary="Inspect python module global field or class static field value.",
    examples=["getglobal __main__ global_A", "getglobal __main__ classA static_B -x 3"],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[
        ("<module>", "the module that field locates."),
        ("<class>", "class static field if specifies."),
        ("<field>", "field name."),
        ("-r, --raw", "display raw output without json format."),
        ("-v, --verbose", "display all the nested items in target list or dict."),
        (
            "-e, --expr <value>",
            "contents you want to watch, write python statement like input func args is "
            "(target), eg: target.field",
        ),
        (
            "-x, --expand <value>",
            "Object represent tree expand level(default 1), max_value is 6.",
        ),
    ],
    option_offset=35,
)

GILSTAT_COMMAND_DESCRIPTION = CommandDescription(
    usage=["gilstat on [gil_take] [gil_hold] [interval] [max_threads]", "gilstat off"],
    summary="Collect python global interpreter lock statistics, including gil holding,taking,dropping time....",
    examples=["gilstat on", "gilstat on 5 5 10 100", "gilstat off"],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[
        ("on/off", "enable/disable gil statistics display."),
        ("<gil_take>", "print warning if gil take more than #{gil_take}ms."),
        ("<gil_hold>", "print warning if gil hold more than #{gil_hold}ms."),
        ("<interval>", "statistics display intervals."),
        ("<max_threads>", "display at most #{max_threads} threads."),
    ],
)

HELP_COMMAND_DESCRIPTION = CommandDescription(
    usage=["help [cmd]"],
    summary="Show command description.",
    examples=["help", "help getglobal"],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[("<cmd>", "command name")],
)

HISTORY_COMMAND_DESCRIPTION = CommandDescription(
    usage=["history [-c] [-n <value>]"],
    summary="Display command history.",
    examples=["history", "help -c", "history -n 30"],
    wiki=None,
    options=[
        ("-c, --clear", "clear history."),
        ("-n, --limit <value>", "how many history commands to display."),
    ],
)

MEM_COMMAND_DESCRIPTION = CommandDescription(
    usage=[
        "mem summary [--limit <value>] [--order <value>]",
        "mem diff [--interval <value>] [--limit <value>] [--order <value>]",
    ],
    summary="Display python process memory usage.",
    examples=[
        "mem summary",
        "mem summary --limit 100",
        "mem summary --limit 10 --order descending",
        "mem diff",
        "mem diff --interval 10 --limit 100",
        "mem diff --interval 10 --limit 10 --order ascending",
    ],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[
        (
            "<summary>",
            "display object memory size, default top 10 object type memory size.",
        ),
        ("<diff>", "diff memory usage, default differ 15 second."),
        ("--limit <value>", "display top #{value} size object type."),
        ("--interval <value>", "diff every #{value}s interval."),
        (
            "--order [descending|ascending]",
            "Display top/bottom object type memory size.",
        ),
    ],
    option_offset=35,
)

MODULE_COMMAND_DESCRIPTION = CommandDescription(
    usage=["module filepath"],
    summary="Translate filepath to module name in the code.",
    examples=["module /home/admin/application/compute.py"],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[
        ("<filepath>", "Absolute or relative path to the Python source file."),
    ],
)

PERF_COMMAND_DESCRIPTION = CommandDescription(
    usage=["perf [pid] [-f <value>] [-r <value>] [-d <value>]"],
    summary="Dump stack trace information to flamegraph.",
    examples=["perf", "perf -f application.svg"],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[
        (
            "<pid>",
            "perf target process id, default analyze current injected process and support analyze other process in the same container.",
        ),
        ("-f, --filepath", "redirect flamegraph to filepath."),
        ("-r, --rate", "sample rate per second, default is 100."),
        ("-d, --duration", "sample duration in seconds, default is unlimited."),
    ],
)

CONSOLE_COMMAND_DESCRIPTION = CommandDescription(
    usage=["console"],
    summary="Create remote interactive console.",
    examples=["console"],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=None,
)

if is_linux():
    STACK_COMMAND_DESCRIPTION = CommandDescription(
        usage=["stack [pid] [-f <value>] [--native]"],
        summary="Inspect stack frames of current running process.",
        examples=["stack", "stack --native", "stack -f ./stack.log"],
        wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
        options=[
            (
                "<pid>",
                "stack target process id, default analyze current injected process and support analyze other process in the same container.",
            ),
            ("-f, --filepath", "redirect thread stack to filepath."),
            ("--native", "display native stack frames."),
        ],
    )
else:
    STACK_COMMAND_DESCRIPTION = CommandDescription(
        usage=["stack [filepath]"],
        summary="Inspect stack frames of current running process.",
        examples=["stack", "stack ./stack.log"],
        wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
        options=[("<filepath>", "redirect thread stack to filepath.")],
    )

TRACE_COMMAND_DESCRIPTION = CommandDescription(
    usage=[
        "trace module [class] method [-i <value>] [-nm <value>] [-et <value>] [-d <value>] [-n <value>] [-f <value>]"
    ],
    summary="Trace the execution time of specified method invocation.",
    examples=[
        "trace __main__ func",
        "trace __main__ func --interval 1",
        "trace __main__ func -et 30 -i 1",
        "trace __main__ classA func",
    ],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[
        ("<module>", "the module that method locates."),
        ("<class>", "the class name if method belongs to class."),
        ("<method>", "target method name."),
        (
            "-i, --interval <value>",
            "display function invocation cost more than ${value} milliseconds, default is 0.1ms.",
        ),
        (
            "-et, --entrance_time <value>",
            "filter function execute cost more than ${value} milliseconds, but on entrance filter.",
        ),
        (
            "-d, --depth <value>",
            "display the method call stack, limited to the specified depth ${value}. When a depth is specified, "
            "the ${interval} parameter is ignored and its value is constrained to 0.",
        ),
        (
            "-nm, --nested-method",
            "trace nested method with depth restrict to 1."
        ),
        (
            "-f, --filter_expr <value>",
            "filter method params expressions, only support filter target&args, write python bool statement like input func args is"
            " (target, *args, **kwargs), eg: args[0]=='hello'.",
        ),
        ("-n, --limits <value>", "threshold of trace method times, default is 10."),
    ],
    option_offset=35,
)

TIME_TUNNEL_COMMAND_DESCRIPTION = CommandDescription(
    usage=[
        "tt [-t module [class] method] [-n <value>] [-l] [-i <value>] [-d <value>] [-nm <value>] [-da] [-x <value>] [-p] [-f <value>] [-r] [-v]"
        " [-m <value>]"
    ],
    summary="Time tunnel, records contexts of method invocation at different times in execution history.",
    examples=[
        "tt -t __main__ func",
        "tt -t __main__ A func",
        "tt -l",
        "tt -i 1000",
        "tt -i 1000 -x 3",
        "tt -i 1000 -p",
        "tt -t __main__ func -f \"return_obj['success']==True and cost>10\"",
        "tt -t __main__ func -f args[0][\"query\"]=='hello'",
    ],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[
        ("-t, --time_tunnel", "record the method invocation within time fragments."),
        ("    module", "the module that method locates."),
        ("    <class>", "the class name if method belongs to class."),
        ("    method", "target method name."),
        (
            "-nm, --nested-method",
            "record nested method with depth restrict to 1."
        ),
        ("-d,  --delete <value>", "delete time fragment specified by index."),
        ("-da, --delete_all", "delete all the time fragments."),
        ("-n,  --limits <value>", "threshold of execution times, default value 50."),
        ("-l,  --list", "list all the time fragments."),
        ("-r, --raw", "display raw output without json format."),
        ("-v, --verbose", "display all the nested items in target list or dict."),
        (
            "-i,  --index <value>",
            "display the detailed information from specified time fragment.",
        ),
        (
            "-x,  --expand <value>",
            "object represent tree expand level(default 1), max_value is 6.",
        ),
        ("-p,  --play", "replay the time fragment specified by index."),
        (
            "-f, --filter <value>",
            "filter method params&args&return_obj&cost&target, expressions, write python bool statement like input func args is "
            "(target, return_obj, cost, *args, **kwargs), eg: args[0]=='hello'.",
        ),
        (
            "-m, --method <value>",
            "specify method locator, default format is module.class.method, fill in None if method belongs to module.",
        ),
    ],
    option_offset=35,
)

TORCH_COMMAND_DESCRIPTION = CommandDescription(
    usage=[
        "torch profile module [class] method [-f <value>]",
        "torch memory [-s] [-r module [class] method] [-nm <value] [-f <value>]",
    ],
    summary="Profile torch function calling on cpu/cuda and memory analysis, will insert torch.cuda.synchronize() automatically before/after method invocation.",
    examples=[
        "torch profile __main__ func_name",
        "torch profile __main__ func_name -f ~/trace.json",
        "torch memory -s -f ~/snapshot.pickle",
        "torch memory -r __main__ call",
        "torch memory -r __main__ classA call -f ~/snapshot.pickle",
    ],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[
        ("<profile>", "sample function stack trace on torch interface."),
        ("<memory>", "anaylze cuda memory used by process"),
        ("module", "the module that method locates."),
        ("<class>", "the class name if method belongs to class."),
        ("method", "target method name."),
        (
            "-nm, --nested-method",
            "record nested method with depth restrict to 1."
        ),
        (
            "-f, --filepath <value>",
            "profile infos dumped filepath, profile/memory subcommand correspond to json/pickle file separately.",
        ),
        ("-s, --snapshot", "dump current memory snapshot to pickle file."),
        (
            "-r, --record",
            "record torch cache allocator cuda memory usage during method execution.",
        ),
    ],
    option_offset=35,
)

VMTOOL_COMMAND_DESCRIPTION = CommandDescription(
    usage=[
        "vmtool -a {forceGc|getInstances} [-c module class] [-e <value>] [-x <value>] [-n <value>] [-v] [-r]"
    ],
    summary="Python VM tool",
    examples=[
        "vmtool -a getInstances -c  __main__ classA",
        "vmtool -a getInstances -c  __main__ classA -e len(instances)",
        "vmtool -a getInstances -c  __main__ classA -e instances[0]",
        "vmtool -a forceGc",
    ],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[
        ("-a, --action", "Action to execute"),
        ("-c, --class", "class locator"),
        ("    module", "the module that class locates."),
        ("    class", "class name."),
        (
            "-e, --expr <value>",
            "expression describe instances that you want to inspect,  default is instances",
        ),
        ("-r, --raw", "display raw output without json format."),
        ("-v, --verbose", "display all the nested items in target list or dict."),
        (
            "-x, --expand <value>",
            "object represent tree expand level(default 1), max_value is 4.",
        ),
        (
            "-n, --limits <value>",
            "limit the the upperbound of display instances, default is 10, -1 means infinity.",
        ),
    ],
    option_offset=35,
)

WATCH_COMMAND_DESCRIPTION = CommandDescription(
    usage=[
        "watch module [class] method [--expr <value>] [-nm <value] [-e] [-r] [-v] [-n <value>] [-x <value>] [-f <value>]"
    ],
    summary="Display the input/output args, return object and cost time of method invocation.",
    examples=[
        "watch __main__ func -x 2",
        "watch __main__ func -f args[0][\"query\"]=='hello'",
        "watch __main__ func -f return_obj['success']==True",
        "watch __main__ func --expr return_obj,args -f cost>10",
        "watch __main__ classA func",
    ],
    wiki="https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md",
    options=[
        ("<module>", "the module that method locates."),
        ("<class>", "the class name if method belongs to class."),
        ("<method>", "target method name."),
        (
            "--expr <value>",
            "contents you want to watch,  write python bool statement like input func args is "
            "(target, return_obj, cost, *args, **kwargs). default is args,kwargs .",
        ),
        (
            "-x, --expand",
            "object represent tree expand level(default 1), -1 means infinity.",
        ),
        (
            "-e, --exception",
            "short for --exception, only record when method throws exception.",
        ),
        (
            "-nm, --nested-method",
            "watch nested method with depth restrict to 1."
        ),
        ("-r, --raw", "display raw output without json format."),
        ("-v, --verbose", "display all the nested items in target list or dict."),
        (
            "-n, --limits <value>",
            "limit the the upperbound of display watched result, default is 10.",
        ),
        (
            "-f, --filter <value>",
            "filter method params&args&return_obj&cost&target, expressions according to --expr"
            "eg: args[0]=='hello'.",
        ),
    ],
    option_offset=35,
)
