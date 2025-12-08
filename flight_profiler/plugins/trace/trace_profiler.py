"""
Python version of TraceProfiler, used only for debugging.
"""

import sys
import time
from types import FrameType
from typing import Any, Callable, List

from flight_profiler.plugins.server_plugin import ServerQueue


class FrameNode:

    def __init__(self):
        # stack level prev
        self.prev = None
        self.succ = []
        self.start_ns = 0
        self.offset = 0

        self.frame_desp = None
        # for async function, coroutine will be entered multiple times.
        self.frame_id = None
        self.enter_timestamp = []


class TraceProfiler:

    def __init__(
        self,
        target: Callable[[ServerQueue, List[Any]], Any],
        out_q: ServerQueue,
        interval: int,
        is_async: bool = False,
        depth_limit: int = -1
    ):
        self.target = target
        self.on_sending_frame = []
        self.sf_sz = 0
        self.current_depth = 0
        self.depth_limit = depth_limit
        self.top = FrameNode()
        self.top.offset = -1
        self.out_q = out_q
        self.interval = interval
        self.first = True
        self.is_async = is_async

    def push_frame(self, start_ns: int, f_info: str):
        nd = FrameNode()
        nd.start_ns = start_ns
        nd.offset = self.sf_sz
        nd.prev = self.top
        nd.frame_desp = f_info

        self.sf_sz += 1
        self.top = nd

    def push_frame_with_depth(self, start_ns: int, f_info: str):
        self.push_frame(start_ns, f_info)
        self.current_depth += 1

    def finish_unclosed_async_frame(self) -> None:
        current_top = self.top
        while len(current_top.succ) > 0:
            last_async_node: FrameNode = current_top.succ.pop(-1)
            last_leave_ns = last_async_node.enter_timestamp[-1]
            last_async_start_ns = last_async_node.enter_timestamp[0]
            cost_ns = last_leave_ns - last_async_start_ns
            if cost_ns >= self.interval:
                pid = current_top.offset
                frame_desp = self.build_last_async_frame(
                    last_async_node.frame_desp, last_async_start_ns, cost_ns, pid
                )
                dif = last_async_node.offset + 1 - len(self.on_sending_frame)
                # todo we ignore interval here
                for _ in range(dif):
                    self.on_sending_frame.append(None)
                self.on_sending_frame[last_async_node.offset] = frame_desp
                current_top = last_async_node
            else:
                break

    def finish_unclosed_async_frame_with_depth(self) -> None:

        current_top = self.top
        while len(current_top.succ) > 0:
            last_async_node: FrameNode = current_top.succ.pop(-1)
            last_leave_ns = last_async_node.enter_timestamp[-1]
            last_async_start_ns = last_async_node.enter_timestamp[0]
            cost_ns = last_leave_ns - last_async_start_ns
            if self.current_depth < self.depth_limit:
                pid = current_top.offset
                frame_desp = self.build_last_async_frame(
                    last_async_node.frame_desp, last_async_start_ns, cost_ns, pid
                )
                dif = last_async_node.offset + 1 - len(self.on_sending_frame)
                # todo we ignore interval here
                for _ in range(dif):
                    self.on_sending_frame.append(None)
                self.on_sending_frame[last_async_node.offset] = frame_desp
                current_top = last_async_node
            else:
                break


    def inner_push_async_frame(self, start_ns: int, f_info: str, frame_id: int):
        nd = FrameNode()
        nd.enter_timestamp.append(start_ns)
        nd.frame_id = frame_id
        self.top.succ.append(nd)
        nd.offset = self.sf_sz
        nd.prev = self.top
        nd.frame_desp = f_info

        self.sf_sz += 1
        self.top = nd

    def inner_push_async_frame_with_depth(self, start_ns: int, f_info: str, frame_id: int):
        self.inner_push_async_frame(start_ns, f_info, frame_id)
        self.current_depth += 1

    def push_frame_async(
        self,
        start_ns: int,
        f_info: str,
        is_async_frame: bool = False,
        frame_id: int = None,
    ):
        if not is_async_frame:
            if self.top.offset == -1:
                return
            # non async frame must be poped out
            # and we clear pre enter async frame
            self.finish_unclosed_async_frame()
            self.push_frame(start_ns, f_info)
        else:
            # judge reenter
            if self.top.offset == -1:
                if len(self.top.succ) > 0:
                    if self.top.succ[-1].frame_id == frame_id:
                        self.top = self.top.succ[-1]
                    else:
                        # this is a another coroutine call not belonged to original stack
                        # just skip
                        return
                else:
                    self.inner_push_async_frame(start_ns, f_info, frame_id)
                    return
            if self.top.frame_id == frame_id:
                if len(self.top.succ) == 0:
                    # enter at least twice and there is not succ nodes, means we have a context switch
                    # make a context switch node
                    # like we do a push & pop operation
                    last_leave_ns = self.top.enter_timestamp[-1]
                    cost_ns = start_ns - last_leave_ns
                    if cost_ns >= self.interval:
                        pid = self.top.offset
                        frame_desp = self.build_context_switch_frame(
                            last_leave_ns, cost_ns, pid
                        )
                        dif = self.sf_sz + 1 - len(self.on_sending_frame)
                        # todo we ignore interval here
                        for _ in range(dif):
                            self.on_sending_frame.append(None)
                        self.on_sending_frame[self.sf_sz] = frame_desp
                        self.sf_sz += 1
                        self.top.enter_timestamp.pop(-1)
                else:
                    # move top
                    # todo a little dangerous is there a potential
                    # def a():
                    #     f = future()
                    #     await ff() # normal async function
                    #     await f # switch context
                    self.top = self.top.succ[-1]
            # current the top node is pushed and not root(offset == -1)
            # todo do we need to clear previous undefined
            else:
                self.finish_unclosed_async_frame()
                self.inner_push_async_frame(start_ns, f_info, frame_id)

    def push_frame_async_with_depth(
        self,
        start_ns: int,
        f_info: str,
        is_async_frame: bool = False,
        frame_id: int = None,
    ):
        if not is_async_frame:
            if self.top.offset == -1:
                return
            # non async frame must be poped out
            # and we clear pre enter async frame
            self.finish_unclosed_async_frame_with_depth()
            self.push_frame_with_depth(start_ns, f_info)
        else:
            # judge reenter
            if self.top.offset == -1:
                if len(self.top.succ) > 0:
                    if self.top.succ[-1].frame_id == frame_id:
                        self.top = self.top.succ[-1]
                        self.current_depth += 1
                    else:
                        # this is a another coroutine call not belonged to original stack
                        # just skip
                        return
                else:
                    self.inner_push_async_frame_with_depth(start_ns, f_info, frame_id)
                    return
            if self.top.frame_id == frame_id:
                if len(self.top.succ) == 0:
                    # enter at least twice and there is not succ nodes, means we have a context switch
                    # make a context switch node
                    # like we do a push & pop operation
                    last_leave_ns = self.top.enter_timestamp[-1]
                    cost_ns = start_ns - last_leave_ns
                    if self.current_depth < self.depth_limit:
                        pid = self.top.offset
                        frame_desp = self.build_context_switch_frame(
                            last_leave_ns, cost_ns, pid
                        )
                        dif = self.sf_sz + 1 - len(self.on_sending_frame)
                        # todo we ignore interval here
                        for _ in range(dif):
                            self.on_sending_frame.append(None)
                        self.on_sending_frame[self.sf_sz] = frame_desp
                        self.sf_sz += 1
                        self.top.enter_timestamp.pop(-1)
                else:
                    self.top = self.top.succ[-1]
                    self.current_depth += 1
            # current the top node is pushed and not root(offset == -1)
            # todo do we need to clear previous undefined
            else:
                self.finish_unclosed_async_frame_with_depth()
                self.inner_push_async_frame_with_depth(start_ns, f_info, frame_id)

    def pop_frame(self) -> FrameNode:
        if self.top is None:
            return None
        nd = self.top
        self.top = self.top.prev

        nd.prev = None
        return nd

    def pop_frame_with_depth(self) -> FrameNode:
        if self.top is None:
            return None
        nd = self.top
        self.top = self.top.prev

        nd.prev = None
        self.current_depth -= 1
        return nd

    def pop_frame_async(
        self, is_async_frame: bool = False, end_time: int = None
    ) -> FrameNode:
        # only sync function or async builtin method will pop node really
        if self.top.offset == -1:
            return None
        if not is_async_frame:
            nd = self.top
            self.top = self.top.prev
            nd.prev = None
            return nd
        else:
            nd = self.top
            self.top.enter_timestamp.append(end_time)
            self.top = self.top.prev
            return nd

    def pop_frame_async_with_depth(
        self, is_async_frame: bool = False, end_time: int = None
    ) -> FrameNode:
        # only sync function or async builtin method will pop node really
        if self.top.offset == -1:
            return None
        if not is_async_frame:
            nd = self.top
            self.top = self.top.prev
            nd.prev = None
            self.current_depth -= 1
            return nd
        else:
            nd = self.top
            self.top.enter_timestamp.append(end_time)
            self.top = self.top.prev
            self.current_depth -= 1
            return nd

    def get_frame_info(
        self,
        frame: FrameType,
        start_ns: int,
        cost_ns: int,
        pid: int,
        arg: Any,
        c_frame: int,
    ):
        if c_frame != 0:
            return "%s\x00%s\x00%i\x01%i\x01%i\x01%i" % (
                getattr(arg, "__qualname__", arg.__name__),
                "<built-in>",
                0,
                start_ns,
                cost_ns,
                pid,
            )
        else:
            return "%s\x00%s\x00%i\x01%i\x01%i\x01%i" % (
                frame.f_code.co_name,
                frame.f_code.co_filename,
                frame.f_code.co_firstlineno,
                start_ns,
                cost_ns,
                pid,
            )

    def build_context_switch_frame(self, start_ns: int, cost_ns: int, pid: int) -> str:
        return "%s\x00%s\x00%i\x01%i\x01%i\x01%i" % (
            "[await]",
            "",
            0,
            start_ns,
            cost_ns,
            pid,
        )

    def build_last_async_frame(
        self, frame_desp: str, start_ns: int, cost_ns: int, pid: int
    ) -> str:
        return "%s\x01%i\x01%i\x01%i" % (frame_desp, start_ns, cost_ns, pid)

    def get_header(self, frame, c_frame, arg):
        if c_frame != 0:
            return "%s\x00%s\x00%i" % (
                getattr(arg, "__qualname__", arg.__name__),
                "<built-in>",
                0,
            )
        else:
            return "%s\x00%s\x00%i" % (
                frame.f_code.co_name,
                frame.f_code.co_filename,
                frame.f_code.co_firstlineno,
            )

    def fulfill_async_unfinished_requests(self):
        while self.top is not None:
            if self.top.offset == -1:
                if len(self.top.succ) > 0:
                    self.top = self.top.succ.pop(-1)
                else:
                    return
            else:
                # it means in previous async function, there is no context switch happens
                last_async_node: FrameNode = self.top
                last_leave_ns = last_async_node.enter_timestamp[-1]
                last_async_start_ns = last_async_node.enter_timestamp[0]
                cost_ns = last_leave_ns - last_async_start_ns
                if cost_ns >= self.interval:
                    pid = self.top.prev.offset
                    frame_desp = self.build_last_async_frame(
                        last_async_node.frame_desp, last_async_start_ns, cost_ns, pid
                    )
                    dif = last_async_node.offset + 1 - len(self.on_sending_frame)
                    # todo we ignore interval here
                    for _ in range(dif):
                        self.on_sending_frame.append(None)
                    self.on_sending_frame[last_async_node.offset] = frame_desp
                    if len(self.top.succ) > 0:
                        self.top = self.top.succ.pop(-1)
                    else:
                        self.top = None
                else:
                    self.top = None

    def fulfill_async_unfinished_requests_with_depth(self):
        while self.top is not None:
            if self.top.offset == -1:
                if len(self.top.succ) > 0:
                    self.top = self.top.succ.pop(-1)
                    self.current_depth += 1
                else:
                    return
            else:
                # it means in previous async function, there is no context switch happens
                last_async_node: FrameNode = self.top
                last_leave_ns = last_async_node.enter_timestamp[-1]
                last_async_start_ns = last_async_node.enter_timestamp[0]
                cost_ns = last_leave_ns - last_async_start_ns
                if self.current_depth <= self.depth_limit:
                    pid = self.top.prev.offset
                    frame_desp = self.build_last_async_frame(
                        last_async_node.frame_desp, last_async_start_ns, cost_ns, pid
                    )
                    dif = last_async_node.offset + 1 - len(self.on_sending_frame)
                    # todo we ignore interval here
                    for _ in range(dif):
                        self.on_sending_frame.append(None)
                    self.on_sending_frame[last_async_node.offset] = frame_desp
                    if len(self.top.succ) > 0:
                        self.top = self.top.succ.pop(-1)
                        self.current_depth += 1
                    else:
                        self.top = None
                else:
                    self.top = None

    def profile_func(self, frame: FrameType, event: str, arg: any):
        try:
            if self.first:
                self.first = False
                return
            print(
                f"Is Coroutine: {frame.f_code.co_flags & 0x80}"
                f" time: {time.time() * 1000}"
                f" event: {event} "
                f" frame: {self.get_frame_info(frame, 0, 0, 0, arg, 1 if 'c_' in event else 0)}"
            )

            c_time = time.time_ns()
            if event == "call" or event == "c_call":
                if event == "c_call":
                    c_frame = 1
                else:
                    c_frame = 0
                self.push_frame(c_time, self.get_header(frame, c_frame, arg))
            elif event == "return" or event == "c_return" or event == "c_exception":
                frame_node = self.pop_frame()
                if event == "c_return" or event == "c_exception":
                    c_frame = 1
                else:
                    c_frame = 0
                cost_ns = c_time - frame_node.start_ns
                if cost_ns >= self.interval:
                    info = self.get_frame_info(
                        frame,
                        frame_node.start_ns,
                        cost_ns,
                        self.top.offset,
                        arg,
                        c_frame,
                    )
                    dif = frame_node.offset + 1 - len(self.on_sending_frame)
                    for i in range(dif):
                        self.on_sending_frame.append(None)
                    self.on_sending_frame[frame_node.offset] = info
                else:
                    self.sf_sz -= 1
        except:
            pass
        return 0

    def profile_async_func(self, frame: FrameType, event: str, arg: any):
        try:
            if self.first:
                self.first = False
                return

            print(
                f"Async Path Is Coroutine: {frame.f_code.co_flags & 0x80}"
                f" time: {time.time() * 1000}"
                f" event: {event} "
                f" frame: {self.get_frame_info(frame, 0, 0, 0, arg, 1 if 'c_' in event else 0)},"
                f" frame_id: {id(frame)}"
            )

            is_async_frame = (
                frame.f_code.co_flags & 0x80 > 0
                and event != "c_call"
                and event != "c_return"
                and event != "c_exception"
            )
            c_time = time.time_ns()
            if event == "call" or event == "c_call":
                if event == "c_call":
                    c_frame = 1
                else:
                    c_frame = 0
                self.push_frame_async(
                    c_time,
                    self.get_header(frame, c_frame, arg),
                    is_async_frame,
                    id(frame),
                )
            elif event == "return" or event == "c_return" or event == "c_exception":
                frame_node = self.pop_frame_async(is_async_frame, c_time)
                if not is_async_frame and frame_node is not None:
                    if event == "c_return" or event == "c_exception":
                        c_frame = 1
                    else:
                        c_frame = 0
                    cost_ns = c_time - frame_node.start_ns
                    if cost_ns >= self.interval:
                        info = self.get_frame_info(
                            frame,
                            frame_node.start_ns,
                            cost_ns,
                            self.top.offset,
                            arg,
                            c_frame,
                        )
                        dif = frame_node.offset + 1 - len(self.on_sending_frame)
                        for i in range(dif):
                            self.on_sending_frame.append(None)
                        self.on_sending_frame[frame_node.offset] = info
                    else:
                        self.sf_sz -= 1  # this is parent_id
        except:
            pass
        return 0

    def profile_func_with_depth(self, frame: FrameType, event: str, arg: any):
        try:
            if self.first:
                self.first = False
                return
            print(
                f"Is Coroutine: {frame.f_code.co_flags & 0x80}"
                f" time: {time.time() * 1000}"
                f" event: {event} "
                f" frame: {self.get_frame_info(frame, 0, 0, 0, arg, 1 if 'c_' in event else 0)}"
            )

            c_time = time.time_ns()
            if event == "call" or event == "c_call":
                if event == "c_call":
                    c_frame = 1
                else:
                    c_frame = 0
                self.push_frame_with_depth(c_time, self.get_header(frame, c_frame, arg))
            elif event == "return" or event == "c_return" or event == "c_exception":
                frame_node = self.pop_frame_with_depth()
                if event == "c_return" or event == "c_exception":
                    c_frame = 1
                else:
                    c_frame = 0
                cost_ns = c_time - frame_node.start_ns
                if self.current_depth < self.depth_limit:
                    info = self.get_frame_info(
                        frame,
                        frame_node.start_ns,
                        cost_ns,
                        self.top.offset,
                        arg,
                        c_frame,
                    )
                    dif = frame_node.offset + 1 - len(self.on_sending_frame)
                    for i in range(dif):
                        self.on_sending_frame.append(None)
                    self.on_sending_frame[frame_node.offset] = info
                else:
                    self.sf_sz -= 1
        except:
            pass
        return 0

    def profile_async_func_with_depth(self, frame: FrameType, event: str, arg: any):
        try:
            if self.first:
                self.first = False
                return

            print(
                f"Async Path Is Coroutine: {frame.f_code.co_flags & 0x80}"
                f" time: {time.time() * 1000}"
                f" event: {event} "
                f" frame: {self.get_frame_info(frame, 0, 0, 0, arg, 1 if 'c_' in event else 0)},"
                f" frame_id: {id(frame)}"
            )

            is_async_frame = (
                frame.f_code.co_flags & 0x80 > 0
                and event != "c_call"
                and event != "c_return"
                and event != "c_exception"
            )
            c_time = time.time_ns()
            if event == "call" or event == "c_call":
                if event == "c_call":
                    c_frame = 1
                else:
                    c_frame = 0
                self.push_frame_async_with_depth(
                    c_time,
                    self.get_header(frame, c_frame, arg),
                    is_async_frame,
                    id(frame),
                )
            elif event == "return" or event == "c_return" or event == "c_exception":
                frame_node = self.pop_frame_async_with_depth(is_async_frame, c_time)
                if not is_async_frame and frame_node is not None and self.current_depth < self.depth_limit:
                    if event == "c_return" or event == "c_exception":
                        c_frame = 1
                    else:
                        c_frame = 0
                    cost_ns = c_time - frame_node.start_ns
                    info = self.get_frame_info(
                        frame,
                        frame_node.start_ns,
                        cost_ns,
                        self.top.offset,
                        arg,
                        c_frame,
                    )
                    dif = frame_node.offset + 1 - len(self.on_sending_frame)
                    for i in range(dif):
                        self.on_sending_frame.append(None)
                    self.on_sending_frame[frame_node.offset] = info
        except:
            pass
        return 0

    def send_trace_frames(self):
        if not self.is_async:
            self.target(self.out_q, self.on_sending_frame)
        else:
            if self.depth_limit == -1:
                self.fulfill_async_unfinished_requests()
            else:
                self.fulfill_async_unfinished_requests_with_depth()
            self.target(self.out_q, self.on_sending_frame)


def set_trace_profile(
    target, out_q: ServerQueue, interval, async_func, depth: int
) -> TraceProfiler:
    profiler = TraceProfiler(target, out_q, interval, is_async=async_func, depth_limit=depth)
    if async_func:
        if depth > 0:
            sys.setprofile(profiler.profile_async_func_with_depth)
        else:
            sys.setprofile(profiler.profile_async_func)
    else:
        if depth > 0:
            sys.setprofile(profiler.profile_func_with_depth)
        else:
            sys.setprofile(profiler.profile_func)
    return profiler


def remove_trace_profile(profiler: TraceProfiler) -> None:
    sys.setprofile(None)
    if profiler is not None:
        profiler.send_trace_frames()
