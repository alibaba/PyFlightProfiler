# PyFlightProfiler
![OS Linux](https://img.shields.io/badge/OS-Linux|Mac-blue)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/flight_profiler)
![PyPI - Implementation](https://img.shields.io/pypi/implementation/flight_profiler)
![PyPI](https://img.shields.io/pypi/v/flight_profiler)
![PyPI - Downloads](https://img.shields.io/pypi/dm/flight_profiler)

> A diagnostic toolbox for Python applications that provides non-intrusive, low-overhead capabilities for online analysis.

## Background
The growing demand for AI inference and agent-based applications has led to an increased deployment of Python systems in production environments. Inference services frequently encounter performance bottlenecks, while agent-based services face challenges in troubleshooting complex business logic. Production issues are often difficult to reproduce and debug, and traditional logging-based diagnostics typically result in prolonged investigation cycles with limited efficiency. PyFlightProfiler is designed to help address some of these common pain points.

## What is PyFlightProfiler

PyFlightProfiler is a toolbox that lets you inspect the status of a running Python process. It allows developers to observe method execution, trace call paths, monitor GIL status, and more, without restarting the application.

## What PyFlightProfiler can do

PyFlightProfiler has the following amazing features:

- 🛫 Non-intrusive Online Diagnostics: Analyze running Python processes without restarting or modifying the application code.
- 🎯 Method Execution Observation: Watch method inputs, outputs, and execution time with customizable expressions.
- 🔍 Call Path Tracing: Trace internal method calls and their execution times to identify performance bottlenecks.
- 🧵 Thread Stack Analysis: Display Python stack frames for all threads, including native stack information.
- 🌐 Cross-time Method Observation: Record method calls over time and replay them for detailed analysis.
- 🌍 Global Variable Inspection: View module global variables and class static variables.
- 🧮 Class Instance Management: Get and manipulate live class instances in the process.
- 🔥 Performance Profiling: Generate flame graphs for performance hotspot analysis.
- 🐚 Interactive Console: Execute custom scripts within the target process.
- 📦 Memory Analysis: Analyze memory usage, including memory diffs and object summaries.
- 🧠 PyTorch Profiling: Profile PyTorch function execution times and GPU memory allocation behavior.
- 🔒 GIL Status Monitoring: Observe the Global Interpreter Lock (GIL) status, including lock acquisition and release times.

## What platforms are supported

PyFlightProfiler currently supports Linux x86_64 (glibc ≥ 2.17) and macOS (arm64), and requires Python 3.8 or later.

## Installation

To install PyFlightProfiler, simply use pip:

```shell
pip3 install flight_profiler
```

## Documentation

You can find the full documentation [here](docs/WIKI.md).

## Usage

For a Python process to be profiled, PyFlightProfiler must reside in the same Python environment. Only then can the process correctly reference the flight_profiler library once attached.
PyFlightProfiler follows a two-stage attach-then-profile workflow. After attaching to a target process, you can use various subcommands to inspect and debug your Python program in real time.

### Attaching to a Running Process

The first step for attachment is to use the `flight_profiler` command followed by the PID of the process you want to analyze.

```shell
usage: flight_profiler <pid>

description: A realtime analysis tool used for profiling python program!

positional arguments:
  pid         python process id to analyze.

optional arguments:
  -h, --help  show this help message and exit
  --cmd CMD   One-time profile, primarily used for unit testing.
  --debug     enable debug logging for attachment.
```

For CPython 3.14 and above, we utilize sys.remote_exec for remote code execution, a feature introduced by [PEP-0768](https://peps.python.org/pep-0768/). This approach is therefore largely safe.

In CPython 3.13 and earlier versions, the implementation of remote code execution differs between macOS and Linux.
On macOS, we utilize [LLDB](https://lldb.llvm.org/) to inject agent logic into the target process.
On Linux, however, code is dispatched to the remote process via [ptrace](https://man7.org/linux/man-pages/man2/ptrace.2.html).
This approach requires that the Linux distribution supports ptrace and that the SYS_PTRACE capability is enabled in Docker environments.

> [!Note]
>
> It is important to note that this procedure involves certain risks, and its safety cannot be fully guaranteed,
> as it is influenced by CPython's internal mechanisms. For example, if the Global Interpreter Lock (GIL)
> is held indefinitely by another thread, the injected code may never execute.
> We have thoroughly tested PyFlightProfiler with a variety of applications on CentOS systems using
> libc versions 2.17 to 2.32. We welcome further user feedback to help us reduce attachment failures and
> improve reliability.

As a best practice, PyFlightProfiler should be comprehensively validated in a non-production environment to ensure stability and performance before being trusted with live services.

### Watching Method Input and Output

For method location, PyFlightProfiler uses the format `module [class] method`,
where module corresponds to the import path as it appears in the program.
For instance, `__main__` for top-level scripts executed directly, `pkg_a.pkg_b` when the code uses `from pkg_a import pkg_b`,
and `pkg_b` when using `import pkg_b`.
This simple module resolution scheme suffices for most use cases.
If you know the file path of the target code but are unsure of its runtime module name,
you can use the [module](#locating-module-with-filepath) subcommand (described below) to verify whether the module as well as the target method is loaded in the process.
The `[class]` component is optional and should only be included when the method belongs to a class. It is omitted for standalone (non-class) functions.

In addition, PyFlightProfiler provides mechanisms for method filtering (-f) and custom extraction of key properties (--expr).
You can specify a Python expression that operates within a context where the effective function signature is (target, return_obj, cost, *args, **kwargs),
and the expression you provide serves as the body of a return statement.
Here, `target` refers to the class instance if the method is bound (or None for standalone functions),
`return_obj` is the value returned by the method,
`cost` represents the execution time in milliseconds,
and `args` and `kwargs` correspond to the positional and keyword arguments passed to the method, respectively.
For concrete usage patterns, refer to the examples provided in the watch command below.

```text
USAGE:                                                                                                                                                                                               12:01:21 [3/52]
  watch module [class] method [--expr <value>] [-nm <value] [-e] [-r] [-v] [-n <value>] [-x <value>] [-f <value>]

SUMMARY:
  Display the input/output args, return object and cost time of method invocation.

EXAMPLES:
  watch __main__ func -x 2
  watch __main__ func -f args[0]["query"]=='hello'
  watch __main__ func -f return_obj['success']==True
  watch __main__ func --expr return_obj,args -f cost>10
  watch __main__ classA func

OPTIONS:
<module>                           the module that method locates.
<class>                            the class name if method belongs to class.
<method>                           target method name.
--expr <value>                     contents you want to watch,  write python bool statement like input func args is (target, return_obj, cost, *args, **kwargs). default is args,kwargs .
-x, --expand                       object represent tree expand level(default 1), -1 means infinity.
-e, --exception                    short for --exception, only record when method throws exception.
-nm, --nested-method               watch nested method with depth restrict to 1.
-r, --raw                          display raw output without json format.
-v, --verbose                      display all the nested items in target list or dict.
-n, --limits <value>               limit the the upperbound of display watched result, default is 10.
-f, --filter <value>               filter method params&args&return_obj&cost&target, expressions according to --expreg: args[0]=='hello'.
```

### Tracing Method Call Paths

The `trace` subcommand is used to inspect method execution time and its inner method call chain.
It uses the same method location mechanism as described in the [watch](#watching-method-execution-input-and-output) subcommand.
The `-i, --interval` option sets the threshold (in milliseconds) for displaying inner method
calls—only invocations with a cost greater than ${interval} will be shown, with a default
value of 0.1 ms. A higher interval reduces the profiler’s impact on the original program.
In practice, we observe an average runtime overhead of 5%–20%, depending on the chosen interval.

```text
USAGE:
  trace module [class] method [-i <value>] [-nm <value>] [-et <value>] [-d <value>] [-n <value>] [-f <value>]

SUMMARY:
  Trace the execution time of specified method invocation.

EXAMPLES:
  trace __main__ func
  trace __main__ func --interval 1
  trace __main__ func -et 30 -i 1
  trace __main__ classA func

OPTIONS:
<module>                           the module that method locates.
<class>                            the class name if method belongs to class.
<method>                           target method name.
-i, --interval <value>             display function invocation cost more than ${value} milliseconds, default is 0.1ms.
-et, --entrance_time <value>       filter function execute cost more than ${value} milliseconds, but on entrance filter.
-d, --depth <value>                display the method call stack limited to the specified depth ${value}. Particularly useful when combined with '-i 0' for stack inspection.
-nm, --nested-method               trace nested method with depth restrict to 1.
-f, --filter_expr <value>          filter method params expressions, only support filter target&args, write python bool statement like input func args is (target, *args, **kwargs), eg: args[0]=='hello'.
-n, --limits <value>               threshold of trace method times, default is 10.
```

### Locating module with filepath

Use the `module` subcommand to determine the correct module name for a given source file path. This is helpful when you know the file location but are unsure how it was imported.
```text
USAGE:
  module filepath

EXAMPLES:
  module /home/admin/application/compute.py

OPTIONS:
<filepath>          Absolute or relative path to the Python source file.
```

### Other Subcommands

PyFlightProfiler includes several additional tools for advanced diagnostics:

- `help` - Display help for any command.
- `console` - Launch an interactive Python console inside the target process.
- `stack` - Analyze Python thread stacks (based on [pystack](https://github.com/bloomberg/pystack)).
- `tt, timetunnel` - Observe method behavior across time (historical execution context).
- `getglobal` - Inspect global variables in the target process.
- `vmtool` - Inspect live class instances and their attributes.
- `perf` - Sample CPU hotspots and generate flame graphs (based on [py-spy](https://github.com/benfred/py-spy)).
- `torch` - Profile PyTorch operations using the pre-installed PyTorch profiler (based on [pytorch](https://github.com/pytorch/pytorch)).
- `mem` - Report memory usage statistics (based on [pympler](https://github.com/pympler/pympler)).
- `gilstat` - Monitor Python’s Global Interpreter Lock (GIL) contention and performance impact.


## Acknowledgements

PyFlightProfiler is inspired by the design of [Arthas](https://github.com/alibaba/arthas).
The project is developed by Alibaba Group. The code is distributed under the Apache License (Version 2.0). This product contains various third-party components under other open-source licenses. See the `NOTICE` file for more information.

The implementation of the trace subcommand is conceptually inspired by [pyinstrument](https://github.com/joerick/pyinstrument). The process attachment mechanism on Linux was inspired by [linux-inject](https://github.com/gaffe23/linux-inject). Python bytecode transform mechanism is inspired by [Python on-the-fly function update](https://hardenedapple.github.io/stories/computers/python_function_override/).
The following open-source libraries and tools are used in PyFlightProfiler, either in their close-to-original form or as an inspiration:

- [pystack](https://github.com/bloomberg/pystack) - Used for Python stack analysis on Linux
- [frida](https://frida.re/) - Used for GIL lock analysis
- [pympler](https://github.com/pympler/pympler) - Used for memory usage analysis
- [py-spy](https://github.com/benfred/py-spy) - Used for CPU hotspot function analysis
- [pytorch](https://github.com/pytorch/pytorch) - Used for sampling torch timeline via torch.profiler
