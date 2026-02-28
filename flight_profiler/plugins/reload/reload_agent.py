import ast
import inspect
import tokenize
import types
from typing import Optional, Tuple

from flight_profiler.common.aop_decorator import find_method_by_mod_cls
from flight_profiler.utils.render_util import (
    COLOR_BOLD,
    COLOR_END,
    COLOR_GREEN,
    COLOR_ORANGE,
    COLOR_RED,
    COLOR_WHITE_255,
)


def compare_code_objects_equal(co1, co2) -> bool:
    """ Compare the codeObject1 and codeObject2 are equal after bytecode transform.
    """
    if co1.co_code != co2.co_code:
        return False

    if co1.co_consts != co2.co_consts:
        return False

    if co1.co_names != co2.co_names:
        return False

    if co1.co_varnames != co2.co_varnames:
        return False

    if (co1.co_argcount != co2.co_argcount or
        co1.co_posonlyargcount != co2.co_posonlyargcount or
        co1.co_kwonlyargcount != co2.co_kwonlyargcount):
        return False

    if co1.co_cellvars != co2.co_cellvars or co1.co_freevars != co2.co_freevars:
        return False

    return True

def prepare_colored_method_sign(method_name: str, class_name: Optional[str], module_name: str) -> str:
    if class_name is None:
        return f"{COLOR_ORANGE}{method_name}{COLOR_END}{COLOR_WHITE_255} in module {COLOR_RED}{module_name}{COLOR_WHITE_255}"
    else:
        return f"{COLOR_ORANGE}{method_name}{COLOR_END}{COLOR_WHITE_255} in module {COLOR_RED}{module_name}{COLOR_WHITE_255} class {COLOR_RED}{class_name}{COLOR_WHITE_255}"


class ReloadResult:

    def __init__(self, error_reason: Optional[str] = None,
                method_source: Optional[str] = None,
                verbose: bool = False,
                located_file_path: Optional[str] = None,
                start_line_no: Optional[int] = None):
        self.error_reason = error_reason
        self.method_source = method_source
        self.located_file_path =  located_file_path
        self.start_line_no = start_line_no
        self.verbose = verbose

    def _format_method_source(self):
        if self.method_source is None:
            return None
        if self.verbose:
            method_source = self.method_source
        else:
            lines = self.method_source.splitlines()
            total_lines = len(lines)

            if total_lines <= 20:
                method_source = self.method_source
            else:
                head = lines[:10]
                tail = lines[-10:]
                middle_msg = f"\n# ... [{total_lines - 20} lines omitted] ...\n"
                method_source = "\n".join(head) + middle_msg + "\n".join(tail)
        return method_source

    def __str__(self):
        if self.error_reason is not None:
            display_msg = f"{COLOR_BOLD}{COLOR_RED}Error{COLOR_END}{COLOR_WHITE_255}: {self.error_reason}.\n"
            rendered_color = COLOR_RED
        else:
            display_msg = f"{COLOR_WHITE_255}Reload is done {COLOR_GREEN}{COLOR_BOLD}successfully{COLOR_END}{COLOR_WHITE_255}.\n"
            rendered_color = COLOR_GREEN
        if self.located_file_path is not None:
            display_msg += f"{rendered_color}{COLOR_BOLD}Located file path{COLOR_END}{COLOR_WHITE_255}: {self.located_file_path}\n"
        method_source = self._format_method_source()
        if method_source is not None:
            display_msg += f"{rendered_color}{COLOR_BOLD}Extracted method source{COLOR_END}{COLOR_WHITE_255}:\n{self._format_method_source()}{COLOR_END}"
        return display_msg


def find_innermost_func(func: types.FunctionType, target_name: str):
    """ find inner function with decorators
    """
    # Decorators use @wraps
    if hasattr(func, "__wrapped__"):
        return find_innermost_func(func.__wrapped__, target_name)

    # If decorators don't use @wraps, we check __closure__
    if hasattr(func, "__closure__") and func.__closure__:
        for cell in func.__closure__:
            content = cell.cell_contents
            if isinstance(content, (types.FunctionType, types.MethodType)):
                if content.__name__ == target_name:
                    inner = find_innermost_func(content, target_name)
                    return inner if inner else content

                if content.__closure__:
                    res = find_innermost_func(content, target_name)
                    if res: return res

    # maybe function don't use decorators
    return func

class ASTMethodLocator:

    @staticmethod
    def get_node_start_end(node: ast.AST) -> Tuple[int, int, bool]:
        start_line = node.lineno
        has_decorators = False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.decorator_list:
                has_decorators = True

        end_line = getattr(node, "end_lineno", start_line)
        return start_line, end_line, has_decorators

    @staticmethod
    def locate_cls_method_in_file(file_path: str, method_name: str, class_name: Optional[str] = None) -> Tuple[Optional[str],
        Optional[str], bool]:
        """
        Returns:
            Tuple[Optional[str], Optional[str]]:
                class source content, method source content
        """
        try:
            with tokenize.open(file_path) as fp:
                source = fp.read()
                fp.seek(0)
                lines = fp.readlines()
        except Exception:
            return None, None, False

        try:
            tree = ast.parse(source)
        except SyntaxError:
            raise

        target_method_node = None
        target_class_node = None

        if class_name:
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    target_class_node = node
                    for sub_node in node.body:
                        if isinstance(sub_node, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub_node.name == method_name:
                            target_method_node = sub_node
                            break
                    break
        else:
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
                    target_method_node = node
                    break

        if not target_method_node:
            return None, None, False

        class_source = None
        if target_class_node is not None:
            cls_start, cls_end, has_cls_decorator = ASTMethodLocator.get_node_start_end(target_class_node)
            cls_lines = lines[cls_start - 1: cls_end]
            class_source = "".join(cls_lines)

        method_start, method_end, has_method_decorator = ASTMethodLocator.get_node_start_end(target_method_node)
        method_lines = lines[method_start - 1 : method_end]
        method_source = "".join(method_lines)
        return class_source, method_source, has_method_decorator


class ReloadAgent:

    @staticmethod
    def reload_function(module_name: str, class_name: Optional[str], func_name: str, verbose: bool) -> str:
        """
        Reload a function's implementation based on the latest file content.

        Args:
            module_name: Name of the module containing the function
            class_name: Name of the class containing the function (optional)
            func_name: Name of the function to reload
            verbose: control return info verbose

        Returns:
            A message indicating the result of the reload operation
        """
        result = ReloadResult(verbose=verbose)
        try:
            method_target, builtin_or_class_method, module = find_method_by_mod_cls(module_name, class_name, func_name)
            if method_target is None:
                result.error_reason = f"Cannot locate method {prepare_colored_method_sign(func_name, class_name, module_name)}"
                return str(result)

            if not class_name and builtin_or_class_method:
                result.error_reason = f"Reload is not supported on builtin_function_or_method"
                return str(result)

            try:
                method_file_path = inspect.getfile(module)
            except:
                result.error_reason = f"Cannot read filepath of {prepare_colored_method_sign(func_name, class_name, module_name)}"
                return str(result)
            result.located_file_path = method_file_path

            try:
                class_source, method_source, has_decorators = ASTMethodLocator.locate_cls_method_in_file(method_file_path, func_name,
                                                                                     class_name)
                if method_source is None:
                    result.error_reason = f"Could not extract method source from file {method_file_path}"
                    return str(result)
            except Exception as e:
                result.error_reason = f"Could not get source code for function {func_name}, error: {e}"
                return str(result)
            result.method_source = method_source

            # Find Innermost method
            if has_decorators:
                method_target = find_innermost_func(method_target, func_name)

            try:
                original_code = method_target.__code__
            except:
                result.error_reason = f"Cannot locate co_code field in method {prepare_colored_method_sign(func_name, class_name, module_name)}"
                return str(result)

            try:
                # Compile the new source code
                if class_name:
                    # For class methods, we need to compile as part of a class
                    compiled_code = compile(class_source, method_file_path, 'exec')
                else:
                    # For module functions, compile just the function
                    compiled_code = compile(method_source, method_file_path, 'exec')
            except SyntaxError as e:
                result.error_reason = f"Syntax error in new implementation: {str(e)}"
                return str(result)
            except Exception as e:
                result.error_reason =  f"Compilation failed: {str(e)}"
                return str(result)

            try:
                # Execute the compiled code to get the new function object
                namespace = {}
                if class_name:
                    # For class methods
                    exec(compiled_code, namespace)
                    if class_name in namespace:
                        cls = namespace[class_name]
                        if hasattr(cls, func_name):
                            new_func = getattr(cls, func_name)
                            # Replace the code object
                            if compare_code_objects_equal(new_func.__code__, original_code):
                                result.error_reason = f"Method source has not changed"
                                return str(result)
                            else:
                                if not builtin_or_class_method:
                                    if hasattr(new_func, '__defaults__'):
                                        method_target.__defaults__ = new_func.__defaults__
                                    if hasattr(new_func, '__annotations__'):
                                        method_target.__annotations__ = new_func.__annotations__
                                    method_target.__code__ = new_func.__code__
                                else:
                                    if hasattr(new_func, '__defaults__'):
                                        method_target.__func__.__defaults__ = new_func.__defaults__
                                    if hasattr(new_func, '__annotations__'):
                                        method_target.__func__.__annotations__ = new_func.__annotations__
                                    method_target.__func__.__code__ = new_func.__code__
                        else:
                            result.error_reason = f"Function {func_name} not found in compiled class"
                            return str(result)
                    else:
                        result.error_reason = f"Error: Class {class_name} not found in compiled code"
                        return str(result)
                else:
                    # For module functions
                    # Create a temporary module to execute the code
                    temp_module = types.ModuleType('temp_reload_module')
                    exec(compiled_code, temp_module.__dict__)
                    if func_name in temp_module.__dict__:
                        new_func = temp_module.__dict__[func_name]
                        # Replace the code object
                        if compare_code_objects_equal(new_func.__code__, original_code):
                            result.error_reason = f"Method source has not changed"
                            return str(result)
                        else:
                            if hasattr(new_func, '__defaults__'):
                                method_target.__defaults__ = new_func.__defaults__
                            if hasattr(new_func, '__annotations__'):
                                method_target.__annotations__ = new_func.__annotations__
                            method_target.__code__ = new_func.__code__
                    else:
                        result.error_reason = f"Function {func_name} not found in compiled module, temp_module.__dict__: {temp_module.__dict__}"
                        return str(result)
                return str(result)
            except Exception as e:
                result.error_reason = f"Failed to replace function bytecode: {str(e)}"
                return str(result)
        except Exception as e:
            result.error_reason = f"Unexpected error during reload: {str(e)}"
            return str(result)
