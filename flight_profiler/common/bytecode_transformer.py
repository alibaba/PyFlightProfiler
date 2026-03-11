"""
bytecode transformer methods
"""

import gc
import importlib
import re
import sys
import types
from copy import deepcopy
from types import CellType, CodeType, FunctionType
from typing import Any, Dict, List, Optional

import opcode

from flight_profiler.common.code_wrapper_entity import NestedCodeWrapperResult


def _execute_bytecode_transform_intern(
    fn: FunctionType,
    wrapper_generator: FunctionType,
    wrapper_arg,
    global_module: List[str],
    global_attr: Dict[str, List[str]] = None,
) -> CodeType:
    """
    replace fn.__code__ with wrapper func __code__, where wrapper_generator has single arg

    1. replace LOAD_DEREF with LOAD_CONST, for closure num should be same to nfree,
        so put cell variable to const variable to avoid this rule
    2. copy fn to avoid infinite recursion
    3. add global_module to global space, which module is used byte LOAD_GLOBAL

    :param fn: original function
    :param wrapper_generator: original function wrapper generator
    :param wrapper_arg: generator arg
    :param global_module: LOAD_GLOBAL MODULE
    :param global_attr: module attribute, kv mappings for module_name: List[attr_name]
    :return: null
    """
    wrap_function: FunctionType = wrapper_generator(wrapper_arg)(fn)
    wrap_code: CodeType = wrap_function.__code__

    const_var_len = len(wrap_code.co_consts)
    alt_wrapper_arg = bytes([opcode.opmap["LOAD_CONST"], const_var_len])
    alt_func = bytes([opcode.opmap["LOAD_CONST"], const_var_len + 1])

    # cell: [func, watch_setting]
    closure_shift = 0
    if sys.version_info >= (3, 11):
        closure_shift = len(wrap_function.__code__.co_varnames)
    deref_wrapper_arg: bytes = bytes([opcode.opmap["LOAD_DEREF"], closure_shift + 1])
    deref_func = bytes([opcode.opmap["LOAD_DEREF"], closure_shift])
    deref_pattern = (
        bytes([opcode.opmap["LOAD_DEREF"]]) + r"[\s\S]".encode()
    )  # match space&non-space character
    matches = [
        (match.start(), match.group())
        for match in re.finditer(deref_pattern, wrap_code.co_code)
    ]
    alternate_code = deepcopy(wrap_code.co_code)
    for match in matches:
        if match[0] % 2 != 0:
            # if jump to immediate, may coincide with LOAD_DEREF bytecode
            # first argument must be bytecode type
            continue

        if match[1] == deref_wrapper_arg:
            alternate_code = (
                alternate_code[: match[0]]
                + alt_wrapper_arg
                + alternate_code[(match[0] + 2) :]
            )
        elif match[1] == deref_func:
            alternate_code = (
                alternate_code[: match[0]] + alt_func + alternate_code[(match[0] + 2) :]
            )
        else:
            raise ValueError(f"wrap code has invalid LOAD DEREF bytecode: {match[1]}")

    global_space: Dict = fn.__globals__
    for module in global_module:
        if module not in global_space:
            global_space[module] = __import__(module)

    if global_attr is not None:
        for module_name, attr_list in global_attr.items():
            module = importlib.import_module(module_name)
            for attr in attr_list:
                global_space[attr] = getattr(module, attr)

    # avoid infinite recursion
    copy_fn = types.FunctionType(
        fn.__code__, global_space, fn.__name__, fn.__defaults__, fn.__closure__
    )
    copy_fn.__kwdefaults__ = fn.__kwdefaults__
    copy_fn.__annotations__ = fn.__annotations__
    copy_fn.__dict__.update(fn.__dict__)
    copy_fn.__qualname__ = fn.__qualname__

    if sys.version_info >= (3, 11):
        # emit COPY_FREE_VARIABLE
        nop_code = bytes([opcode.opmap["NOP"], opcode.opmap["NOP"]])
        alternate_code = nop_code + alternate_code[2:]
        new_codeobj = types.CodeType(
            wrap_code.co_argcount,
            wrap_code.co_posonlyargcount,
            wrap_code.co_kwonlyargcount,
            wrap_code.co_nlocals,
            wrap_code.co_stacksize,
            wrap_code.co_flags,
            alternate_code,
            wrap_code.co_consts
            + (
                wrapper_arg,
                copy_fn,
            ),
            wrap_code.co_names,
            wrap_code.co_varnames,
            wrap_code.co_filename,
            wrap_code.co_name,
            wrap_code.co_qualname,
            wrap_code.co_firstlineno,
            wrap_code.co_linetable,
            wrap_code.co_exceptiontable,
            fn.__code__.co_freevars,
            wrap_code.co_cellvars,
        )
    else:
        new_codeobj = types.CodeType(
            wrap_code.co_argcount,
            wrap_code.co_posonlyargcount,
            wrap_code.co_kwonlyargcount,
            wrap_code.co_nlocals,
            wrap_code.co_stacksize,
            wrap_code.co_flags,
            alternate_code,
            wrap_code.co_consts
            + (
                wrapper_arg,
                copy_fn,
            ),
            wrap_code.co_names,
            wrap_code.co_varnames,
            wrap_code.co_filename,
            wrap_code.co_name,
            wrap_code.co_firstlineno,
            wrap_code.co_lnotab,
            fn.__code__.co_freevars,
            wrap_code.co_cellvars,
        )
    return new_codeobj

def transform_normal_method_by_aop_wrapper(
    fn: FunctionType,
    wrapper_generator: FunctionType,
    wrapper_arg,
    global_module: List[str],
    global_attr: Dict[str, List[str]] = None,
    is_classmethod: bool = False,
) -> None:
    """ Tranform normal method transform
    """
    new_codeobj: CodeType = _execute_bytecode_transform_intern(
        fn=fn,
        wrapper_generator=wrapper_generator,
        wrapper_arg=wrapper_arg,
        global_module=global_module,
        global_attr=global_attr,
    )

    if is_classmethod:
        # class_method code can't be set directly, follows one indirection
        fn.__func__.__code__ = new_codeobj
    else:
        fn.__code__ = new_codeobj


def _execute_nested_code_const_substitute(
    outer_func: FunctionType,
    nested_code_idx: int,
    wrapped_code_obj: CodeType,
) -> CodeType:
    """ replace outer_func's nestedCodeObj in consts
    """
    outer_func_code: CodeType = outer_func.__code__
    list_co_consts = list(outer_func_code.co_consts)
    list_co_consts[nested_code_idx] = wrapped_code_obj
    refactor_consts = tuple(list_co_consts)
    if sys.version_info >= (3, 11):
        new_codeobj = types.CodeType(
            outer_func_code.co_argcount,
            outer_func_code.co_posonlyargcount,
            outer_func_code.co_kwonlyargcount,
            outer_func_code.co_nlocals,
            outer_func_code.co_stacksize,
            outer_func_code.co_flags,
            outer_func_code.co_code,
            refactor_consts,
            outer_func_code.co_names,
            outer_func_code.co_varnames,
            outer_func_code.co_filename,
            outer_func_code.co_name,
            outer_func_code.co_qualname,
            outer_func_code.co_firstlineno,
            outer_func_code.co_linetable,
            outer_func_code.co_exceptiontable,
            outer_func_code.co_freevars,
            outer_func_code.co_cellvars,
        )
        return new_codeobj
    else:
        new_codeobj = types.CodeType(
            outer_func_code.co_argcount,
            outer_func_code.co_posonlyargcount,
            outer_func_code.co_kwonlyargcount,
            outer_func_code.co_nlocals,
            outer_func_code.co_stacksize,
            outer_func_code.co_flags,
            outer_func_code.co_code,
            refactor_consts,
            outer_func_code.co_names,
            outer_func_code.co_varnames,
            outer_func_code.co_filename,
            outer_func_code.co_name,
            outer_func_code.co_firstlineno,
            outer_func_code.co_lnotab,
            outer_func_code.co_freevars,
            outer_func_code.co_cellvars,
        )
        return new_codeobj


def transform_nested_method_by_aop_wrapper(
    nested_code_obj: CodeType,
    nested_code_idx: int,
    original_func: FunctionType,
    wrapper_generator: FunctionType,
    wrapper_arg,
    global_module: List[str],
    global_attr: Dict[str, List[str]] = None,
    is_classmethod: bool = False,
) -> NestedCodeWrapperResult:
    """ nested method has two sited to fix
    1. current frame call stack, which we need replace LOAD_CONST with our own LOAD_CONST
    2. escaped method, which follows similar change as before transform_normal_method_by_aop_wrapper

    we need to handle CodeType -> FunctionType transformation first
    """
    code_referrers: List[Any] = gc.get_referrers(nested_code_obj)
    nested_func_wrap: Optional[FunctionType] = None
    for item in code_referrers:
        if hasattr(item, "__code__") and item.__code__ == nested_code_obj:
            # find and break
            nested_func_wrap = item
            break

    if nested_func_wrap is not None:
        # escaped
        escaped_func_origin_code = nested_func_wrap.__code__
        new_codeobj: CodeType = _execute_bytecode_transform_intern(
            fn=nested_func_wrap,
            wrapper_generator=wrapper_generator,
            wrapper_arg=wrapper_arg,
            global_module=global_module,
            global_attr=global_attr,
        )
        nested_func_wrap.__code__ = new_codeobj

        outer_func_origin_code : CodeType = original_func.__code__
        outer_func_changed_code_obj = _execute_nested_code_const_substitute(
            outer_func=original_func,
            nested_code_idx=nested_code_idx,
            wrapped_code_obj=new_codeobj,
        )

        if is_classmethod:
            # class_method code can't be set directly, follows one indirection
            original_func.__func__.__code__ = outer_func_changed_code_obj
        else:
            original_func.__code__ = outer_func_changed_code_obj

        return NestedCodeWrapperResult(
            escaped_func=nested_func_wrap,
            escaped_func_origin_code=escaped_func_origin_code,
            outer_func=original_func,
            outer_func_origin_code=outer_func_origin_code
        )
    else:
        # escaped_func is None, we need to construct one
        placeholder_closures = tuple([CellType(None) for _ in range(len(nested_code_obj.co_freevars))])
        constructed_nested_func = types.FunctionType(
            nested_code_obj, original_func.__globals__, nested_code_obj.co_name, (), placeholder_closures
        )
        new_codeobj: CodeType = _execute_bytecode_transform_intern(
            fn=constructed_nested_func,
            wrapper_generator=wrapper_generator,
            wrapper_arg=wrapper_arg,
            global_module=global_module,
            global_attr=global_attr,
        )

        outer_func_origin_code: CodeType = original_func.__code__
        outer_func_changed_code_obj = _execute_nested_code_const_substitute(
            outer_func=original_func,
            nested_code_idx=nested_code_idx,
            wrapped_code_obj=new_codeobj,
        )

        if is_classmethod:
            # class_method code can't be set directly, follows one indirection
            original_func.__func__.__code__ = outer_func_changed_code_obj
        else:
            original_func.__code__ = outer_func_changed_code_obj

        return NestedCodeWrapperResult(
            escaped_func=None,
            escaped_func_origin_code=None,
            outer_func=original_func,
            outer_func_origin_code=outer_func_origin_code,
            need_wrap_nested_inplace=True,
            nested_code_obj=nested_code_obj
        )
