import importlib
import inspect
from types import CodeType, FunctionType, ModuleType
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from flight_profiler.common.bytecode_transformer import (
    transform_nested_method_by_aop_wrapper,
    transform_normal_method_by_aop_wrapper,
)
from flight_profiler.common.code_wrapper_entity import (
    CodeWrapperResult,
    NestedCodeWrapperResult,
)
from flight_profiler.common.system_logger import logger
from flight_profiler.utils.render_util import COLOR_END, COLOR_ORANGE, COLOR_RED

BUILT_IN_METHOD_TYPE = type(len)


def find_class_function(cls, method_name):
    for name, m in inspect.getmembers(
        cls
    ):
        if inspect.isfunction(m):
            if name == method_name:
                return name, m, False
        elif inspect.ismethod(m):
            if name == method_name:
                return name, m, True

    m = getattr(cls, method_name, None)
    if m is not None:
        if type(m) is BUILT_IN_METHOD_TYPE:
            return method_name, m, False
    return None, None, False

def find_local_method_in_frame(method: CodeType, nested_method: str) -> Tuple[Optional[CodeType], int]:
    """ Find nested method in outer frame's const variable
    """

    if hasattr(method, "co_consts"):
        for idx, con in enumerate(method.co_consts):
            if hasattr(con, "co_code") and hasattr(con, "co_name") and con.co_name == nested_method:
                return con, idx
        return None, 0
    else:
        return None, 0

def find_module_function(module: ModuleType, method_name: str) -> Tuple[Optional[FunctionType], bool]:
    """
    return target_method, is_built_in_method
    """
    for name, m in inspect.getmembers(
        module, lambda x: inspect.isfunction(x) or inspect.ismethod(x)
    ):
        if name == method_name:
            return m, False

    m = getattr(module, method_name, None)
    if m is not None:
        if type(m) is BUILT_IN_METHOD_TYPE:
            return m, True
    return None, False


def find_method_by_mod_cls(module_name: str, cls_name: Optional[str], method_name: str) -> Tuple[
    Optional[FunctionType], bool, Optional[ModuleType]]:
    """ Find target method in module or class

    Returns:
        Tuple[Optional[FunctionType], bool]:
            1. Method
            2. is_builtin if specified module method, otherwise class method
            3. Module

    """
    module = importlib.import_module(module_name)
    if cls_name is None:
        method, is_builtin = find_module_function(module, method_name)
        return method, is_builtin, module
    else:
        cls = getattr(module, cls_name, None)
        if cls is not None:
            name, method, is_class_method = find_class_function(cls, method_name)
            return method, is_class_method, module
        return None, False, None


def add_cls_func_wrapper(
    module: ModuleType,
    class_name: str,
    func_name: str,
    wrapper_generator: callable,
    wrapper_arg: Any,
    global_module: List[Any],
    global_attr: Dict[str, List[str]] = None,
    module_name: str = None,
    nested_method: str = None,
) -> CodeWrapperResult:
    cls = getattr(module, class_name, None)
    if cls is not None:
        name, m, is_class_method = find_class_function(cls, func_name)
        if m is None:
            logger.warning(
                f"module {module.__name__} class {class_name} "
                f"function {func_name} "
                f"not found, will skip add wrapper"
            )
            return CodeWrapperResult(
                None, True,  f"No method named {COLOR_ORANGE}{func_name}{COLOR_END}{COLOR_RED}"
                                              f" is found in class {class_name}!"
                    )
        else:
            if nested_method is not None:
                nested_code_obj, nested_idx = find_local_method_in_frame(m.__code__, nested_method)
                if nested_code_obj is None:
                    return CodeWrapperResult(
                        None,
                        True,
                        f"Nested method {COLOR_ORANGE}{nested_method}{COLOR_END}{COLOR_RED} is not found in module: {module_name} method: {func_name}!"
                    )
                else:
                    # do replace
                    nested_result: NestedCodeWrapperResult = transform_nested_method_by_aop_wrapper(
                        nested_code_obj=nested_code_obj,
                        nested_code_idx=nested_idx,
                        original_func=m,
                        wrapper_generator=wrapper_generator,
                        wrapper_arg=wrapper_arg,
                        global_module=global_module,
                        global_attr=global_attr,
                        is_classmethod=is_class_method
                    )
                    return CodeWrapperResult(
                        nested_result,
                    )
            else:
                old_code_obj = m.__code__
                transform_normal_method_by_aop_wrapper(
                    m, wrapper_generator, wrapper_arg, global_module, global_attr,
                    is_classmethod=is_class_method
                )
                logger.info(
                    f"module {module.__name__} class {class_name} "
                    f"function {func_name} "
                    f"add wrapper successfully"
                )
                return CodeWrapperResult(old_code_obj)
    else:
        return CodeWrapperResult(
            None,
            True,
            (
                f"No class named {COLOR_ORANGE}{class_name}{COLOR_END}{COLOR_RED}"
                f" is found in module {module_name}!"
            )
        )


def add_module_func_wrapper(
    module: ModuleType,
    func_name: str,
    wrapper_generator: callable,
    wrapper_arg: Any,
    global_module: List[str],
    global_attr: Dict[str, List[str]],
    module_name: str = None,
    nested_method: str = None
) -> CodeWrapperResult:
    m, is_builtin = find_module_function(module, func_name)

    if is_builtin and nested_method is not None:
        return CodeWrapperResult(
            None,
            True,
            f"Cannot find nested method {COLOR_ORANGE}{nested_method}{COLOR_END}{COLOR_RED}"
            f" in builtin method {COLOR_ORANGE}{func_name}{COLOR_END}{COLOR_RED}!"
        )

    if m is None:
        logger.warning(
            f"module {module.__name__} function {func_name} "
            f"not found, will skip add wrapper"
        )
        return CodeWrapperResult(
            None,
            True,
            (
                f"No method named {COLOR_ORANGE}{func_name}{COLOR_END}{COLOR_RED}"
                f" is found in module {module_name}!"
            )
        )
    else:
        if nested_method is None:
            if not is_builtin:
                old_code_obj = m.__code__
                transform_normal_method_by_aop_wrapper(
                    m, wrapper_generator, wrapper_arg, global_module, global_attr
                )
                logger.info(
                    f"module {module.__name__} function {func_name} "
                    f"add wrapper successfully"
                )
                return CodeWrapperResult(old_code_obj)
            else:
                # builtin method only change in
                wrapper_func = wrapper_generator(wrapper_arg)(m)
                setattr(module, func_name, wrapper_func)
                logger.info(
                    f"module {module.__name__} builtin function {func_name} "
                    f"add wrapper successfully"
                )
                return CodeWrapperResult(m)
        elif is_builtin:
            return CodeWrapperResult(
                None,
                True,
                f"Cannot find nested method {COLOR_ORANGE}{nested_method}{COLOR_END}{COLOR_RED}"
                f" in builtin method {COLOR_ORANGE}{func_name}{COLOR_END}{COLOR_RED}!"
            )
        else:
            # not builtin method and has nested method
            nested_code_obj, nested_idx = find_local_method_in_frame(m.__code__, nested_method)
            if nested_code_obj is None:
                return CodeWrapperResult(
                    None,
                    True,
                    f"Nested method {COLOR_ORANGE}{nested_method}{COLOR_END}{COLOR_RED} is not found in module: {module_name} method: {func_name}!"
                )
            else:
                # do replace
                nested_result: NestedCodeWrapperResult = transform_nested_method_by_aop_wrapper(
                    nested_code_obj=nested_code_obj,
                    nested_code_idx=nested_idx,
                    original_func=m,
                    wrapper_generator=wrapper_generator,
                    wrapper_arg=wrapper_arg,
                    global_module=global_module,
                    global_attr=global_attr,
                    is_classmethod=False
                )
                return CodeWrapperResult(
                    nested_result,
                    False,
                    None
                )


def add_func_wrapper(
    module: ModuleType,
    class_name: str,
    func_name: str,
    wrapper_func: Callable,
    wrapper_arg: Any,
    global_module: List[str],
    global_attr: Dict[str, List[str]] = None,
    nested_method: str = None,
    module_name: str = None,
) -> CodeWrapperResult:
    if class_name is not None:
        return add_cls_func_wrapper(
            module,
            class_name,
            func_name,
            wrapper_func,
            wrapper_arg,
            global_module,
            global_attr,
            module_name=module_name,
            nested_method=nested_method
        )
    else:
        return add_module_func_wrapper(
            module, func_name, wrapper_func, wrapper_arg, global_module, global_attr,
            module_name=module_name,
            nested_method=nested_method
        )

def clear_cls_func_wrapper(module, class_name, func_name, origin_func):
    cls = getattr(module, class_name, None)
    if cls is not None:
        name, m, is_class_method = find_class_function(cls, func_name)
        if m is None:
            logger.warning(
                f"module {module.__name__} class {class_name} "
                f"function {func_name} "
                f"not found, will skip clear wrapper"
            )
            return None
        elif type(origin_func) is NestedCodeWrapperResult:
            if origin_func.escaped_func is not None:
                origin_func.escaped_func.__code__ = origin_func.escaped_func_origin_code
            if origin_func.outer_func is not None:
                if not is_class_method:
                    origin_func.outer_func.__code__ = origin_func.outer_func_origin_code
                else:
                    origin_func.outer_func.__func__.__code__ = origin_func.outer_func_origin_code
        else:
            if not is_class_method:
                m.__code__ = origin_func
            else:
                m.__func__.__code__ = origin_func
            logger.info(
                f"module {module.__name__} class {class_name} "
                f"function {func_name} "
                f"clear wrapper successfully"
            )
    return None


def clear_module_func_wrapper(
    module, func_name, origin_func: Union[CodeType, FunctionType, NestedCodeWrapperResult]
):
    # if builtin method is wrapped, current must be a non-builtin method, so can't use is_builtin to recover
    m, is_builtin = find_module_function(module, func_name)
    if m is None:
        logger.warning(
            f"module {module.__name__} function {func_name} "
            f"not found, will skip clear wrapper"
        )
        return None
    else:
        if type(origin_func) is CodeType:
            m.__code__ = origin_func
            logger.info(
                f"module {module.__name__} function {func_name} "
                f"clear wrapper successfully"
            )
            return m
        elif type(origin_func) is NestedCodeWrapperResult:
            if origin_func.escaped_func is not None:
                origin_func.escaped_func.__code__ = origin_func.escaped_func_origin_code
            if origin_func.outer_func is not None:
                origin_func.outer_func.__code__ = origin_func.outer_func_origin_code
        else:
            setattr(module, func_name, origin_func)
            logger.info(
                f"module {module.__name__} builtin function {func_name} "
                f"clear wrapper successfully"
            )
            return m


def clear_func_wrapper(module: ModuleType, class_name: str, func_name: str, origin_func: Union[CodeType, NestedCodeWrapperResult]):
    if class_name is not None:
        return clear_cls_func_wrapper(module, class_name, func_name, origin_func)
    else:
        return clear_module_func_wrapper(module, func_name, origin_func)
