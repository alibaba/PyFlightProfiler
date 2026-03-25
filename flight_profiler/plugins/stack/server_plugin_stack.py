import asyncio
import os
import tempfile
import threading
import traceback
from typing import List

from flight_profiler.common.system_logger import logger
from flight_profiler.ext.stack_C import dump_all_threads_stack
from flight_profiler.plugins.server_plugin import Message, ServerPlugin, ServerQueue
from flight_profiler.utils.args_util import split_regex
from flight_profiler.utils.render_util import (
    BANNER_COLOR_CYAN,
    COLOR_BOLD,
    COLOR_END,
    COLOR_FAINT,
    COLOR_GREEN,
    COLOR_ORANGE,
    COLOR_RED,
    COLOR_WHITE_255,
    COLOR_YELLOW,
)
from flight_profiler.utils.shell_util import resolve_symbol_address


class StackServerPlugin(ServerPlugin):
    def __init__(self, cmd: str, out_q: ServerQueue):
        super().__init__(cmd, out_q)

    def add_thread_name(self, contents):
        threads = threading.enumerate()
        thread_map = dict()
        for thread in threads:
            thread_map[thread.ident] = thread.name
        new_contents = ""
        for content in contents:
            if content.startswith("Thread 0x"):
                thread_id = int(split_regex(content)[1][2:], 16)
                if thread_map.__contains__(thread_id):
                    new_contents = (
                        new_contents
                        + "("
                        + thread_map[thread_id]
                        + ")"
                        + content[len("Thread") :]
                    )
                else:
                    new_contents = new_contents + content
            elif content.startswith("Current thread 0x"):
                thread_id = int(split_regex(content[len("Current thread 0x")])[0], 16)
                if thread_map.__contains__(thread_id):
                    new_contents = (
                        new_contents
                        + "("
                        + thread_map[thread_id]
                        + ")"
                        + content[len("Current thread") :]
                    )
                else:
                    new_contents = new_contents + content
            else:
                new_contents = new_contents + content
        return new_contents

    async def do_action(self, param):
        # Check if we need to show async coroutine stacks
        if param == "async":
            await self._dump_coroutine_stacks()
            return

        tmp_fd, tmp_file_path = tempfile.mkstemp()
        try:
            addr = resolve_symbol_address("_Py_DumpTracebackThreads", os.getpid())
            if addr is None:
                await self.out_q.output_msg(
                    Message(True, "symbol _Py_DumpTracebackThreads not found")
                )
                return
            # dump stack to tempfile
            dump_all_threads_stack(tmp_fd, int(addr))
            with open(tmp_file_path, "r") as f:
                contents = f.readlines()
                await self.out_q.output_msg(
                    Message(True, self.add_thread_name(contents))
                )
        except:
            await self.out_q.output_msg(Message(True, traceback.format_exc()))

    async def _dump_coroutine_stacks(self):
        """
        Dump async coroutine/task stacks from all running event loops.
        """
        try:
            output_lines: List[str] = []
            # Title with green
            separator = f"{COLOR_GREEN}{COLOR_BOLD}{'=' * 60}{COLOR_END}"
            output_lines.append(separator)
            output_lines.append(f"{COLOR_GREEN}{COLOR_BOLD}Async Coroutine/Task Stacks{COLOR_END}")
            output_lines.append(separator)
            output_lines.append("")

            # Get all running event loops across threads
            all_tasks = self._get_all_async_tasks()

            # Group tasks by thread and filter out internal threads
            tasks_by_thread = {}
            for task_info in all_tasks:
                thread_id = task_info.get("thread_id", 0)
                thread_name = task_info.get("thread_name", "Unknown")
                # Skip flight_profiler internal threads early
                if self._is_flight_profiler_thread(thread_name):
                    continue
                key = (thread_id, thread_name)
                if key not in tasks_by_thread:
                    tasks_by_thread[key] = []
                tasks_by_thread[key].append(task_info)

            if not tasks_by_thread:
                output_lines.append(f"{COLOR_YELLOW}No active coroutines/async tasks found.{COLOR_END}")
                output_lines.append("")
                output_lines.append(f"{COLOR_FAINT}Note: Coroutines are only visible when an event loop is running.{COLOR_END}")
            else:
                for (thread_id, thread_name), tasks in tasks_by_thread.items():
                    # Thread header in cyan
                    output_lines.append(f"{BANNER_COLOR_CYAN}{COLOR_BOLD}Thread: {thread_name} (tid: 0x{thread_id:x}){COLOR_END}")
                    output_lines.append(f"{COLOR_FAINT}{'-' * 50}{COLOR_END}")

                    for i, task_info in enumerate(tasks):
                        task_name = task_info.get("name", "<unnamed>")
                        task_state = task_info.get("state", "unknown")
                        coro_repr = task_info.get("coro_repr", "<unknown>")

                        output_lines.append("")
                        # Task name in yellow
                        output_lines.append(f"  {COLOR_YELLOW}{COLOR_BOLD}Task #{i + 1}: {task_name}{COLOR_END}")
                        # State with color based on status
                        state_color = self._get_state_color(task_state)
                        output_lines.append(f"    {COLOR_WHITE_255}State:{COLOR_END} {state_color}{task_state}{COLOR_END}")
                        # Coroutine name in orange
                        output_lines.append(f"    {COLOR_WHITE_255}Coroutine:{COLOR_END} {COLOR_ORANGE}{coro_repr}{COLOR_END}")

                        # Print stack frames
                        stack_frames = task_info.get("stack", [])
                        if stack_frames:
                            output_lines.append(f"    {COLOR_WHITE_255}Stack ({len(stack_frames)} frames):{COLOR_END}")
                            for frame in stack_frames:
                                filename = frame.get("filename", "<unknown>")
                                lineno = frame.get("lineno", 0)
                                funcname = frame.get("name", "<unknown>")
                                line = frame.get("line", "")
                                # File path in faint, line number in green, function name in bold
                                output_lines.append(
                                    f'      {COLOR_FAINT}File "{filename}",{COLOR_END} '
                                    f'{COLOR_GREEN}line {lineno}{COLOR_END}, '
                                    f'{COLOR_BOLD}in {funcname}{COLOR_END}'
                                )
                                if line:
                                    output_lines.append(f"        {COLOR_WHITE_255}{line}{COLOR_END}")
                        else:
                            output_lines.append(f"    {COLOR_FAINT}Stack: <no frames available>{COLOR_END}")

                    output_lines.append("")

            output_lines.append(separator)
            result = "\n".join(output_lines)
            await self.out_q.output_msg(Message(True, result))
        except Exception:
            logger.exception("Failed to dump coroutine stacks")
            await self.out_q.output_msg(Message(True, traceback.format_exc()))

    def _get_state_color(self, state: str) -> str:
        """Get color code based on task state."""
        state_colors = {
            "PENDING": COLOR_YELLOW,
            "WAITING": COLOR_GREEN,
            "FINISHED": COLOR_GREEN,
            "CANCELLED": COLOR_FAINT,
            "FAILED": COLOR_RED,
            "UNKNOWN": COLOR_FAINT,
        }
        return state_colors.get(state, COLOR_WHITE_255)

    def _get_all_async_tasks(self) -> List[dict]:
        """
        Get all async tasks from all running event loops across all threads.
        Returns a list of task info dictionaries.

        Supports multiple Python versions:
        - Python 3.7-3.11: uses asyncio.tasks._all_tasks (WeakSet of all tasks)
        - Python 3.12+: uses asyncio.tasks._scheduled_tasks (WeakSet of pending tasks)
        """
        all_tasks_info = []
        seen_task_ids = set()

        # Directly access asyncio's global task tracking WeakSet
        # This contains tasks from ALL event loops, not just current loop
        try:
            import asyncio.tasks as asyncio_tasks
            all_tasks_weak = None

            # Python 3.7-3.11: _all_tasks contains all tasks (pending + done)
            if hasattr(asyncio_tasks, '_all_tasks'):
                all_tasks_weak = asyncio_tasks._all_tasks
            elif hasattr(asyncio, '_all_tasks'):
                all_tasks_weak = asyncio._all_tasks
            # Python 3.12+: _scheduled_tasks contains pending tasks
            elif hasattr(asyncio_tasks, '_scheduled_tasks'):
                all_tasks_weak = asyncio_tasks._scheduled_tasks

            if all_tasks_weak is not None:
                # Safe iteration over WeakSet (may need retry due to concurrent modification)
                for attempt in range(10):
                    try:
                        tasks_snapshot = list(all_tasks_weak)
                        break
                    except RuntimeError:
                        continue
                else:
                    tasks_snapshot = []

                for task in tasks_snapshot:
                    if task is None or id(task) in seen_task_ids:
                        continue
                    # Skip done tasks
                    try:
                        if task.done():
                            continue
                    except Exception:
                        pass
                    # Skip flight_profiler internal tasks
                    if self._is_flight_profiler_task(task):
                        continue
                    seen_task_ids.add(id(task))

                    # Find the thread running this task's loop
                    thread_id, thread_name = self._find_thread_for_task(task)

                    task_info = {
                        "task_id": id(task),
                        "thread_id": thread_id,
                        "thread_name": thread_name,
                        "name": self._get_task_name(task),
                        "state": self._get_task_state(task),
                        "coro_repr": self._get_coro_repr(task),
                        "stack": self._get_task_stack(task),
                    }
                    all_tasks_info.append(task_info)
        except Exception:
            logger.exception("Failed to get all async tasks")

        return all_tasks_info

    def _find_thread_for_task(self, task: asyncio.Task) -> tuple:
        """
        Find which thread is running the event loop for this task.
        Returns (thread_id, thread_name) tuple.
        """
        try:
            loop = getattr(task, '_loop', None)
            if loop is None:
                return (0, "Unknown")

            # Try to get thread_id directly from loop (set when loop is running)
            loop_thread_id = getattr(loop, '_thread_id', None)
            if loop_thread_id is not None and loop_thread_id != 0:
                # Found the thread id, now get the name
                thread_name = "Unknown"
                for t in threading.enumerate():
                    if t.ident == loop_thread_id:
                        thread_name = t.name
                        break
                return (loop_thread_id, thread_name)

            # Fallback: try to find by scanning current frames
            import sys
            for thread_id, frame in sys._current_frames().items():
                current_frame = frame
                while current_frame is not None:
                    local_vars = current_frame.f_locals
                    for var_name in ['self', 'loop', '_loop', 'event_loop']:
                        if var_name in local_vars:
                            val = local_vars[var_name]
                            if val is loop or (hasattr(val, '_loop') and val._loop is loop):
                                thread_name = "Unknown"
                                for t in threading.enumerate():
                                    if t.ident == thread_id:
                                        thread_name = t.name
                                        break
                                return (thread_id, thread_name)
                    current_frame = current_frame.f_back
        except Exception:
            logger.exception("Failed to find thread for task")
        return (0, "Unknown")

    def _scan_frame_for_loops(
        self, frame, thread_id: int, seen_loops: set,
        seen_task_ids: set, all_tasks_info: List[dict]
    ):
        """
        Recursively scan a frame and its parents for event loops.
        """
        try:
            current_frame = frame
            while current_frame is not None:
                local_vars = current_frame.f_locals
                for var_name, var_value in local_vars.items():
                    if isinstance(var_value, asyncio.AbstractEventLoop):
                        if id(var_value) not in seen_loops:
                            seen_loops.add(id(var_value))
                            # Get thread name
                            thread_name = "Unknown"
                            for t in threading.enumerate():
                                if t.ident == thread_id:
                                    thread_name = t.name
                                    break
                            tasks_info = self._extract_tasks_from_loop(
                                var_value, thread_id, thread_name, seen_task_ids
                            )
                            all_tasks_info.extend(tasks_info)
                current_frame = current_frame.f_back
        except Exception:
            pass

    def _extract_tasks_from_loop(
        self, loop: asyncio.AbstractEventLoop, thread_id: int, thread_name: str,
        seen_task_ids: set = None
    ) -> List[dict]:
        """
        Extract task information from a given event loop.
        """
        tasks_info = []
        if seen_task_ids is None:
            seen_task_ids = set()

        try:
            # Get all tasks from this loop
            try:
                tasks = asyncio.all_tasks(loop)
            except RuntimeError:
                # Loop might not be running
                return tasks_info

            for task in tasks:
                # Skip already seen tasks
                if id(task) in seen_task_ids:
                    continue
                # Skip flight_profiler internal tasks
                if self._is_flight_profiler_task(task):
                    continue
                seen_task_ids.add(id(task))
                task_info = {
                    "task_id": id(task),
                    "thread_id": thread_id,
                    "thread_name": thread_name,
                    "name": self._get_task_name(task),
                    "state": self._get_task_state(task),
                    "coro_repr": self._get_coro_repr(task),
                    "stack": self._get_task_stack(task),
                }
                tasks_info.append(task_info)
        except Exception:
            pass

        return tasks_info

    def _is_flight_profiler_thread(self, thread_name: str) -> bool:
        """
        Check if a thread belongs to flight_profiler itself.
        We filter these out to avoid showing internal tool threads.
        """
        if not thread_name:
            return False
        name_lower = thread_name.lower()
        return "flight-profiler" in name_lower or "flight_profiler" in name_lower

    def _is_flight_profiler_task(self, task: asyncio.Task) -> bool:
        """
        Check if a task belongs to flight_profiler itself.
        We filter these out to avoid showing internal tool tasks.
        """
        try:
            # Check coroutine name
            coro = task.get_coro()
            if coro is not None:
                coro_name = getattr(coro, "__qualname__", "") or getattr(coro, "__name__", "")
                if "flight_profiler" in coro_name.lower():
                    return True
                # Check coroutine's module
                coro_module = getattr(coro, "__module__", "") or ""
                if "flight_profiler" in coro_module:
                    return True
                # Check cr_code for file path
                cr_code = getattr(coro, "cr_code", None)
                if cr_code is not None:
                    filename = getattr(cr_code, "co_filename", "")
                    if "flight_profiler" in filename:
                        return True

            # Check stack frames for flight_profiler paths
            frames = task.get_stack()
            if frames:
                for frame in frames:
                    filename = frame.f_code.co_filename
                    if "flight_profiler" in filename:
                        return True
        except Exception:
            pass
        return False

    def _get_task_name(self, task: asyncio.Task) -> str:
        """
        Get the name of an asyncio task.
        """
        try:
            # Python 3.8+ has task.get_name()
            if hasattr(task, "get_name"):
                return task.get_name()
            return repr(task)
        except Exception:
            return "<unknown>"

    def _get_task_state(self, task: asyncio.Task) -> str:
        """
        Get the state of an asyncio task.
        """
        try:
            if task.done():
                if task.cancelled():
                    return "CANCELLED"
                try:
                    if task.exception() is not None:
                        return "FAILED"
                except (asyncio.CancelledError, asyncio.InvalidStateError):
                    pass
                return "FINISHED"
            # Check if task is waiting (has a waiter)
            if hasattr(task, "_fut_waiter") and task._fut_waiter is not None:
                return "WAITING"
            return "PENDING"
        except Exception:
            return "UNKNOWN"

    def _get_coro_repr(self, task: asyncio.Task) -> str:
        """
        Get a string representation of the coroutine.
        """
        try:
            coro = task.get_coro()
            if coro is not None:
                # Get coroutine name and qualified name
                coro_name = getattr(coro, "__qualname__", None) or getattr(
                    coro, "__name__", repr(coro)
                )
                return coro_name
            return "<no coroutine>"
        except Exception:
            return "<unknown>"

    def _get_task_stack(self, task: asyncio.Task) -> List[dict]:
        """
        Get the full coroutine call chain for an asyncio task.
        This follows the cr_await chain to show nested coroutine calls.
        """
        stack_info = []
        try:
            # Start with the task's coroutine
            coro = task.get_coro()
            if coro is None:
                return stack_info

            # Follow the cr_await chain to build full coroutine stack
            self._collect_coro_frames(coro, stack_info)

        except Exception as e:
            logger.exception("Failed to get task stack")
        return stack_info

    def _collect_coro_frames(self, coro, stack_info: List[dict], depth: int = 0):
        """
        Recursively collect frames from coroutine and its awaited coroutines.
        """
        if coro is None or depth > 100:  # Prevent infinite recursion
            return

        try:
            # Get the current frame of this coroutine
            cr_frame = getattr(coro, 'cr_frame', None)
            if cr_frame is not None:
                frame_info = {
                    "filename": cr_frame.f_code.co_filename,
                    "lineno": cr_frame.f_lineno,
                    "name": cr_frame.f_code.co_name,
                    "line": self._get_line_from_frame(cr_frame),
                }
                stack_info.append(frame_info)

            # Follow cr_await to get the awaited coroutine/awaitable
            cr_await = getattr(coro, 'cr_await', None)
            if cr_await is not None:
                # cr_await could be another coroutine, a Future, or other awaitable
                if hasattr(cr_await, 'cr_frame'):
                    # It's a coroutine
                    self._collect_coro_frames(cr_await, stack_info, depth + 1)
                elif hasattr(cr_await, 'gi_frame'):
                    # It's a generator-based coroutine
                    gi_frame = cr_await.gi_frame
                    if gi_frame is not None:
                        frame_info = {
                            "filename": gi_frame.f_code.co_filename,
                            "lineno": gi_frame.f_lineno,
                            "name": gi_frame.f_code.co_name,
                            "line": self._get_line_from_frame(gi_frame),
                        }
                        stack_info.append(frame_info)
                    # Continue following gi_yieldfrom if present
                    gi_yieldfrom = getattr(cr_await, 'gi_yieldfrom', None)
                    if gi_yieldfrom is not None:
                        self._collect_coro_frames(gi_yieldfrom, stack_info, depth + 1)
                elif hasattr(cr_await, '__self__') and hasattr(cr_await, 'cr_await'):
                    # Some wrapped awaitable
                    self._collect_coro_frames(cr_await, stack_info, depth + 1)
        except Exception as e:
            logger.exception("Failed to collect coroutine frames at depth %d", depth)

    def _get_line_from_frame(self, frame) -> str:
        """
        Get the source code line from a frame object.
        """
        try:
            import linecache

            filename = frame.f_code.co_filename
            lineno = frame.f_lineno
            line = linecache.getline(filename, lineno).strip()
            return line
        except Exception:
            return ""


def get_instance(cmd: str, out_q: ServerQueue):
    return StackServerPlugin(cmd, out_q)
