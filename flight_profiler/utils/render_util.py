import os
import shutil
from importlib.metadata import version
from typing import List, Optional, Tuple

from flight_profiler.common.expression_result import ExpressionResult

""" Colors
"""
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_BOLD = "\033[1m"
COLOR_FAINT = "\033[2m"
COLOR_BG_DARK_BLUE_255 = "\033[48;5;24m"
COLOR_WHITE_255 = "\033[38;5;255m"
COLOR_FUNCTION = COLOR_BG_DARK_BLUE_255 + COLOR_WHITE_255
COLOR_BG_DARK_BROWN_255 = "\033[48;5;94m"
COLOR_AWAIT = COLOR_BG_DARK_BROWN_255 + COLOR_WHITE_255
COLOR_BRIGHT_GREEN = "\033[92m"
COLOR_END = "\033[0m"
COLOR_ORANGE = "\033[38;5;214m"
BANNER_COLOR_RED = "\033[38;5;196m"
BANNER_COLOR_GREEN = "\033[38;5;46m"
BANNER_COLOR_YELLOW = "\033[38;5;226m"
BANNER_COLOR_BLUE = "\033[38;5;39m"
BANNER_COLOR_ORANGE = "\033[38;5;208m"
BANNER_COLOR_PURPLE = "\033[38;5;141m"
BANNER_COLOR_PINK = "\033[38;5;207m"
BANNER_COLOR_CYAN = "\033[38;5;87m"
BANNER_COLOR_LIST = [
    BANNER_COLOR_RED,
    BANNER_COLOR_YELLOW,
    BANNER_COLOR_GREEN,
    BANNER_COLOR_CYAN,
    BANNER_COLOR_PINK,
    BANNER_COLOR_ORANGE,
    BANNER_COLOR_BLUE,
    BANNER_COLOR_PURPLE
]


def make_clickable_link(url: str, text: str = None) -> str:
    """
    Create a clickable hyperlink for terminal using OSC 8 escape sequence.
    Works in modern terminals like iTerm2, GNOME Terminal, Windows Terminal, etc.
    Falls back to plain URL for unsupported terminals (e.g., Mac Terminal.app).
    
    Args:
        url: The URL to link to
        text: Display text (defaults to URL if not provided)
    
    Returns:
        Terminal escape sequence for clickable link, or plain URL if unsupported
    """
    if text is None:
        text = url
    
    # Check if terminal supports OSC 8 hyperlinks
    term_program = os.environ.get('TERM_PROGRAM', '')
    term = os.environ.get('TERM', '')
    
    # Known terminals that support OSC 8
    supported_terminals = ['iTerm.app', 'vscode', 'WezTerm', 'Hyper']
    supported_terms = ['xterm-256color', 'screen-256color']
    
    # Check for iTerm2, VSCode, or other known supporting terminals
    is_supported = (
        term_program in supported_terminals or
        'ITERM_SESSION_ID' in os.environ or  # iTerm2
        'WT_SESSION' in os.environ or  # Windows Terminal
        'KONSOLE_VERSION' in os.environ or  # Konsole
        'GNOME_TERMINAL_SCREEN' in os.environ  # GNOME Terminal
    )
    
    if is_supported:
        # OSC 8 format: \033]8;;URL\007TEXT\033]8;;\007
        return f"\033]8;;{url}\007{text}\033]8;;\007"
    else:
        # Plain URL for unsupported terminals (most terminals auto-detect URLs)
        return text

import unicodedata

""" Status Icons
"""
ICON_SUCCESS = "✓"
ICON_FAILED = "✗"
ICON_WARNING = "⚠"
ICON_INFO = "ℹ"
ICON_ARROW = "➜"
ICON_DOT = "●"

""" Command Icons - used for command title headers
"""
CMD_ICON_HELP = "❓"
CMD_ICON_STACK = "📚"
CMD_ICON_MEM = "💾"
CMD_ICON_WATCH = "👀"
CMD_ICON_TRACE = "🔍"
CMD_ICON_PERF = "📊"
CMD_ICON_TT = "🕐"
CMD_ICON_VMTOOL = "🔧"
CMD_ICON_GETGLOBAL = "🌐"
CMD_ICON_MODULE = "📦"
CMD_ICON_RELOAD = "🔄"
CMD_ICON_GILSTAT = "🔒"
CMD_ICON_TORCH = "🔥"
CMD_ICON_CONSOLE = "💻"
CMD_ICON_HISTORY = "📜"
CMD_ICON_TEST = "🧪"
CMD_ICON_CLS = "🧹"
CMD_ICON_DEFAULT = "▸"

""" Box Drawing Characters
"""
BOX_HORIZONTAL = "─"
BOX_VERTICAL = "│"
BOX_TOP_LEFT = "┌"
BOX_TOP_RIGHT = "┐"
BOX_BOTTOM_LEFT = "└"
BOX_BOTTOM_RIGHT = "┘"
BOX_T_DOWN = "┬"
BOX_T_UP = "┴"
BOX_T_RIGHT = "├"
BOX_T_LEFT = "┤"
BOX_CROSS = "┼"
BOX_DOUBLE_HORIZONTAL = "═"
BOX_LIGHT_HORIZONTAL = "╌"
# Rounded corners
BOX_ROUND_TOP_LEFT = "╭"
BOX_ROUND_TOP_RIGHT = "╮"
BOX_ROUND_BOTTOM_LEFT = "╰"
BOX_ROUND_BOTTOM_RIGHT = "╯"


ENTRANCE_HINTS = [
    ("wiki", "https://github.com/alibaba/PyFlightProfiler/blob/main/docs/WIKI.md"),
    ("version", version("flight_profiler")),
]

EXIT_CODE_HINTS = [
    "SUCCESS",
    "ATTACH_FAILED",
    "GET_REGISTERS_AFTER_ATTACH_FAILED",
    "SET_INJECTED_SHELLCODE_REGISTERS_FAILED",
    "READ_TARGET_MEMORY_FAILED",
    "WRITE_SHELLCODE_TO_TARGET_MEMORY_FAILED",
    "ERROR_IN_EXECUTE_MALLOC",
    "GET_MALLOC_REGISTERS_FAILED",
    "MALLOC_RETURN_ZERO",
    "WRITE_LIBRARY_STR_TO_TARGET_MEMORY_FAILED",
    "ERROR_IN_EXECUTE_DLOPEN",
    "GET_DLOPEN_REGISTERS_FAILED",
    "DLOPEN_RETURN_ZERO",
    "ERROR_IN_EXECUTE_FREE",
    "ERROR_IN_RECOVER_INJECTION",
    "ERROR_IN_VERIFY_SO_LOCATION",
    "ERROR_FLIGHT_SERVER_NO_RESPONSE"
]


def char_display_width(char: str) -> int:
    """
    Get the display width of a single character in terminal.
    Wide characters (CJK, emoji) take 2 columns, others take 1.
    """
    if len(char) != 1:
        return sum(char_display_width(c) for c in char)
    # Check East Asian Width
    width_type = unicodedata.east_asian_width(char)
    if width_type in ('W', 'F'):  # Wide or Fullwidth
        return 2
    # Check for emoji and symbols that typically display as 2 columns
    code = ord(char)
    # Emoji ranges - only include ranges that are consistently 2-width across terminals
    if (
        code >= 0x1F300 or  # Emoji (Miscellaneous Symbols and Pictographs onwards)
        0x2600 <= code <= 0x26FF or  # Miscellaneous Symbols
        0x2700 <= code <= 0x27BF     # Dingbats
    ):
        return 2
    return 1


def str_display_width(text: str) -> int:
    """
    Get the total display width of a string in terminal.
    """
    return sum(char_display_width(c) for c in text)


def ljust_display(text: str, width: int, fillchar: str = ' ') -> str:
    """
    Left-justify string to given display width, accounting for wide characters.
    """
    current_width = str_display_width(text)
    if current_width >= width:
        return text
    return text + fillchar * (width - current_width)


def align_prefix(prefix_width: int, source: str, first_line_prefix=None) -> str:
    """
    Transform source string with a constant prefix width from second line.

    Args:
        prefix_width (int): Width of the prefix for alignment
        source (str): Source string to align
        first_line_prefix (Optional[int]): Prefix width for the first line, defaults to prefix_width

    Returns:
        str: Aligned string with proper prefix width
    """
    if first_line_prefix is None:
        first_line_prefix = prefix_width
    terminal_width = shutil.get_terminal_size().columns
    max_length = max(20, terminal_width - prefix_width)
    first_line_max_length = max(20, terminal_width - first_line_prefix)
    space_prefix = " " * prefix_width
    line_source = ""
    pos = 0
    is_first_line = True
    while pos < len(source):
        if is_first_line:
            line_source += source[pos : pos + first_line_max_length]
            pos += first_line_max_length
            is_first_line = False
        else:
            line_source += "\n" + space_prefix + source[pos : pos + max_length]
            pos += max_length
    return line_source


def align_json_lines(
    prefix_width: int,
    source: str,
    is_exp_stack: bool = False,
    split_internal_line: bool = True,
) -> str:
    """
    Split multiple lines source and shift all lines with fixed offset.

    Args:
        prefix_width (int): Width of the prefix for alignment
        source (str): Source string to align
        is_exp_stack (bool): Whether the source is an exception stack trace
        split_internal_line (bool): Whether to split internal lines

    Returns:
        str: Aligned string with proper line breaks and prefixes
    """
    lines = source.splitlines()
    terminal_width = shutil.get_terminal_size().columns
    ret = ""
    space_prefix = " " * prefix_width
    for idx, line in enumerate(lines):
        if idx == 0:
            if split_internal_line:
                ret += align_prefix(prefix_width, line)
            else:
                ret += line
        else:
            shift = 0
            while shift < len(line) - 1 and line[shift].isspace():
                shift += 1
            if is_exp_stack:
                ret += f"{' ' * (max(0, min(prefix_width + shift, terminal_width - 20)))}{align_prefix(prefix_width, line[shift:], prefix_width + shift)}"
            else:
                if split_internal_line:
                    ret += f"{' ' * (max(0, min(prefix_width + shift, terminal_width - 20)))}{align_prefix(prefix_width + shift, line[shift:])}"
                else:
                    ret += space_prefix + line
        if idx != len(lines) - 1:
            ret += "\n"
    return ret


def build_long_spy_command_hint(
    module_name: str, class_name: Optional[str], method_name: str, nested_method: Optional[str] = None
) -> str:
    """
    Build a spy command hint message for long-running operations.

    Args:
        module_name (str): Name of the module being spied on
        class_name (Optional[str]): Name of the class being spied on
        method_name (str): Name of the method being spied on
        nested_method (Optional[str]): Name of the nested method being spied on

    Returns:
        str: Formatted spy command hint message
    """
    if class_name is None:
        return (
            f"{COLOR_GREEN}{ICON_SUCCESS}{COLOR_END} "
            f"{COLOR_WHITE_255}Spy was successfully added on "
            f"{COLOR_FAINT}[MODULE]{COLOR_END} {module_name} "
            f"{COLOR_FAINT}[METHOD]{COLOR_END} {method_name}, "
            f"{COLOR_FAINT}press Ctrl-C to stop.{COLOR_END}"
        )
    else:
        if nested_method is None:
            method_id = f"{method_name}"
        else:
            method_id = f"{method_name}.{nested_method}"
        return (
            f"{COLOR_GREEN}{ICON_SUCCESS}{COLOR_END} "
            f"{COLOR_WHITE_255}Spy was successfully added on "
            f"{COLOR_FAINT}[MODULE]{COLOR_END} {module_name} "
            f"{COLOR_FAINT}[CLASS]{COLOR_END} {class_name} "
            f"{COLOR_FAINT}[METHOD]{COLOR_END} {method_id}, "
            f"{COLOR_FAINT}press Ctrl-C to stop.{COLOR_END}"
        )


def build_error_message(error_text: str) -> str:
    """
    Build a formatted error message with error icon.

    Args:
        error_text: The error message or traceback text

    Returns:
        str: Formatted error message with icon and color
    """
    return f"{COLOR_RED}{ICON_FAILED}{COLOR_END} {error_text}"


def build_colorful_banners() -> None:
    """
    Build and display colorful banners from the banner description file.

    Reads the banner.desc file and renders it with colorful formatting
    using the BANNER_COLOR_LIST colors.
    """
    file_path = os.path.abspath(__file__)
    dir_path = os.path.dirname(os.path.dirname(file_path))
    with open(os.path.join(dir_path, "banner.desc"), "r") as f:
        desc = f.read()
    lines = desc.splitlines()
    space_indices = [0]
    for idx in range(1, len(lines[0])):
        all_space: bool = True
        for j in range(0, len(lines)):
            if idx < len(lines[j]) and lines[j][idx] != " ":
                all_space = False
                break
        if all_space:
            space_indices.append(idx)

    final_rendered_results = []
    for line in lines:
        rendered_display_line = ""
        for idx in range(len(space_indices)):
            if space_indices[idx] >= len(line):
                continue
            if idx < len(space_indices) - 1:
                rendered_display_line += f"{BANNER_COLOR_LIST[idx]}{COLOR_BOLD}{line[space_indices[idx]:space_indices[idx + 1]]}{COLOR_END}"
            else:
                rendered_display_line += f"{BANNER_COLOR_LIST[idx]}{COLOR_BOLD}{line[space_indices[idx]:]}{COLOR_END}"
        final_rendered_results.append(rendered_display_line)
    for line in final_rendered_results:
        print(line)
    print()

def build_title_hints(additional_hints: List[Tuple[str, str]] = None) -> None:
    """
    Build and display title hints with proper alignment.

    Args:
        additional_hints (List[Tuple[str, str]], optional): Additional hints to display
    """
    hints = ENTRANCE_HINTS
    if additional_hints is not None:
        hints.extend(additional_hints)
    max_key_le = 0
    for hint in hints:
        max_key_le = max(max_key_le, len(hint[0]))
    for hint in hints:
        needed_space_cnt = max_key_le - len(hint[0])
        print(f"{COLOR_WHITE_255}{hint[0]}:{' ' * needed_space_cnt} {hint[1]}{COLOR_END}")
    print()


def build_welcome_box(pid: str, py_executable: str) -> None:
    """
    Build and display a Claude Code style welcome box.

    Args:
        pid: Target process ID
        py_executable: Path to Python executable
    """
    ver = version("flight_profiler")
    terminal_width = shutil.get_terminal_size().columns
    box_width = min(80, terminal_width - 2)

    # Read banner
    file_path = os.path.abspath(__file__)
    dir_path = os.path.dirname(os.path.dirname(file_path))
    with open(os.path.join(dir_path, "banner.desc"), "r") as f:
        banner_lines = f.read().splitlines()

    # Border color - use faint/gray for a subtle look
    border_color = COLOR_FAINT

    # Build the box - title with white highlight and gray version number
    title = "PyFlightProfiler"
    version_str = f"v{ver}"
    # Title: white bold (need COLOR_END first to clear FAINT attribute), version: gray
    title_part = f"{COLOR_END}{COLOR_WHITE_255}{COLOR_BOLD}{title}{COLOR_END}"
    version_part = f"{border_color}{version_str}"
    title_display_len = len(f" {title} {version_str} ")
    left_padding = 3
    right_padding = box_width - 2 - left_padding - title_display_len
    top_line = f"{border_color}{BOX_ROUND_TOP_LEFT}{BOX_HORIZONTAL * left_padding} {title_part} {version_part} {BOX_HORIZONTAL * right_padding}{BOX_ROUND_TOP_RIGHT}{COLOR_END}"

    print()  # Empty line before welcome box
    print(top_line)

    # Helper function to print a boxed line
    def print_box_line(content: str, content_display_len: int):
        padding = box_width - 2 - content_display_len
        print(f"{border_color}{BOX_VERTICAL}{COLOR_END}{content}{' ' * max(0, padding)}{border_color}{BOX_VERTICAL}{COLOR_END}")

    # Empty line
    print_box_line("", 0)

    # Banner lines with colors
    space_indices = [0]
    if banner_lines:
        for idx in range(1, len(banner_lines[0])):
            all_space = True
            for j in range(len(banner_lines)):
                if idx < len(banner_lines[j]) and banner_lines[j][idx] != " ":
                    all_space = False
                    break
            if all_space:
                space_indices.append(idx)

    for line in banner_lines:
        rendered_line = "  "
        for idx in range(len(space_indices)):
            if space_indices[idx] >= len(line):
                continue
            if idx < len(space_indices) - 1:
                rendered_line += f"{BANNER_COLOR_LIST[idx]}{COLOR_BOLD}{line[space_indices[idx]:space_indices[idx + 1]]}{COLOR_END}"
            else:
                rendered_line += f"{BANNER_COLOR_LIST[idx]}{COLOR_BOLD}{line[space_indices[idx]:]}{COLOR_END}"
        display_len = str_display_width(line) + 2
        print_box_line(rendered_line, display_len)

    # Empty line
    print_box_line("", 0)

    # Info section - each item on separate line
    wiki_url = "https://github.com/alibaba/PyFlightProfiler/wiki"
    clickable_wiki = make_clickable_link(wiki_url)
    info_items = [
        ("pid", pid),
        ("wiki", clickable_wiki),
        ("python", py_executable),
    ]

    for key, value in info_items:
        line = f"  {COLOR_FAINT}{key}:{COLOR_END} {COLOR_WHITE_255}{value}{COLOR_END}"
        display_len = len(f"  {key}: {value}")
        print_box_line(line, display_len)

    # Empty line
    print_box_line("", 0)

    # Bottom line
    bottom_line = f"{border_color}{BOX_ROUND_BOTTOM_LEFT}{BOX_HORIZONTAL * (box_width - 2)}{BOX_ROUND_BOTTOM_RIGHT}{COLOR_END}"
    print(bottom_line)
    print()


def build_prompt_separator() -> str:
    """
    Build a full-width separator line for the command prompt.

    Returns:
        str: A separator line that spans terminal width
    """
    terminal_width = shutil.get_terminal_size().columns
    return f"{COLOR_FAINT}{BOX_HORIZONTAL * terminal_width}{COLOR_END}"


def render_expression_result(result: ExpressionResult) -> str:
    left_offset: int = 20

    if result.failed:
        value_str = (
            f"{COLOR_WHITE_255}  {'EXPR:'.ljust(left_offset)}{align_prefix(left_offset + 2, result.expr)}{COLOR_END}\n"
            f"{COLOR_WHITE_255}  {'FAILED_REASON:'.ljust(left_offset)}{COLOR_END}"
            f"{COLOR_RED}{align_json_lines(left_offset + 2, result.failed_reason, True)}{COLOR_END}"
        )
        return value_str

    value = result.value
    left_offset: int = 12
    value_str = (
        f"{COLOR_WHITE_255}  {'EXPR:'.ljust(left_offset)}{align_prefix(left_offset + 2, result.expr)}{COLOR_END}\n"
        f"{COLOR_WHITE_255}  {'TYPE:'.ljust(left_offset)}{align_prefix(left_offset + 2, result.type)}{COLOR_END}\n"
        f"{COLOR_WHITE_255}  {'VALUE:'.ljust(left_offset)}"
        f"{align_json_lines(left_offset + 2, value, split_internal_line=False)}{COLOR_END}"
    )
    return value_str


def build_separator(char: str = BOX_HORIZONTAL, width: int = None, color: str = COLOR_FAINT) -> str:
    """
    Build a horizontal separator line.

    Args:
        char (str): Character to use for the separator line
        width (int): Width of the separator, defaults to terminal width
        color (str): Color for the separator line

    Returns:
        str: Formatted separator line
    """
    if width is None:
        width = shutil.get_terminal_size().columns
    return f"{color}{char * width}{COLOR_END}"


def build_command_header(
    cmd_name: str,
    icon: str = CMD_ICON_DEFAULT,
    color: str = BANNER_COLOR_CYAN,
    show_separator: bool = True
) -> str:
    """
    Build a command header with icon and optional separator.

    Args:
        cmd_name (str): Name of the command
        icon (str): Icon to display before the command name
        color (str): Color for the header text
        show_separator (bool): Whether to show separator line below

    Returns:
        str: Formatted command header
    """
    header = f"{color}{COLOR_BOLD}{icon} [{cmd_name.upper()}]{COLOR_END}"
    if show_separator:
        sep_width = len(cmd_name) + 5  # icon + brackets + spaces
        header += f"\n{COLOR_FAINT}{BOX_HORIZONTAL * sep_width}{COLOR_END}"
    return header


def build_status_message(
    message: str,
    status: str = "info",
    prefix_newline: bool = False
) -> str:
    """
    Build a status message with appropriate icon and color.

    Args:
        message (str): The message to display
        status (str): Status type - 'success', 'error', 'warning', or 'info'
        prefix_newline (bool): Whether to add a newline before the message

    Returns:
        str: Formatted status message with icon and color
    """
    status_config = {
        "success": (ICON_SUCCESS, COLOR_GREEN),
        "error": (ICON_FAILED, COLOR_RED),
        "warning": (ICON_WARNING, COLOR_YELLOW),
        "info": (ICON_INFO, COLOR_WHITE_255),
    }
    icon, color = status_config.get(status, (ICON_INFO, COLOR_WHITE_255))
    prefix = "\n" if prefix_newline else ""
    return f"{prefix}{color}{icon} {message}{COLOR_END}"


def build_key_value_line(
    key: str,
    value: str,
    key_width: int = 15,
    key_color: str = COLOR_FAINT,
    value_color: str = COLOR_WHITE_255,
    bullet: str = None
) -> str:
    """
    Build a formatted key-value line.

    Args:
        key (str): The key/label
        value (str): The value
        key_width (int): Width for the key column
        key_color (str): Color for the key
        value_color (str): Color for the value
        bullet (str): Optional bullet character before the line

    Returns:
        str: Formatted key-value line
    """
    bullet_str = f"{bullet} " if bullet else "  "
    return f"{bullet_str}{key_color}{key.ljust(key_width)}{COLOR_END}{value_color}{value}{COLOR_END}"


def build_table_header(columns: List[Tuple[str, int]], color: str = COLOR_BOLD) -> str:
    """
    Build a table header with column names.

    Args:
        columns (List[Tuple[str, int]]): List of (column_name, width) tuples
        color (str): Color for the header

    Returns:
        str: Formatted table header with separator line
    """
    header_line = " "
    for col_name, width in columns:
        header_line += col_name.ljust(width)

    total_width = sum(w for _, w in columns) + 1
    separator = BOX_HORIZONTAL * total_width

    return f"{color}{COLOR_WHITE_255}{header_line}{COLOR_END}\n{COLOR_FAINT}{separator}{COLOR_END}"


def build_section_title(title: str, color: str = COLOR_BRIGHT_GREEN) -> str:
    """
    Build a section title with decorative borders.

    Args:
        title (str): The section title
        color (str): Color for the title

    Returns:
        str: Formatted section title
    """
    return f"{color}{COLOR_BOLD}{BOX_T_RIGHT}{BOX_HORIZONTAL} {title} {BOX_HORIZONTAL}{BOX_T_LEFT}{COLOR_END}"


# Command icon mapping for easy lookup
COMMAND_ICONS = {
    "help": CMD_ICON_HELP,
    "stack": CMD_ICON_STACK,
    "mem": CMD_ICON_MEM,
    "watch": CMD_ICON_WATCH,
    "trace": CMD_ICON_TRACE,
    "perf": CMD_ICON_PERF,
    "tt": CMD_ICON_TT,
    "vmtool": CMD_ICON_VMTOOL,
    "getglobal": CMD_ICON_GETGLOBAL,
    "module": CMD_ICON_MODULE,
    "reload": CMD_ICON_RELOAD,
    "gilstat": CMD_ICON_GILSTAT,
    "torch": CMD_ICON_TORCH,
    "console": CMD_ICON_CONSOLE,
    "history": CMD_ICON_HISTORY,
    "test": CMD_ICON_TEST,
    "cls": CMD_ICON_CLS,
}


def get_command_icon(cmd_name: str) -> str:
    """
    Get the icon for a command.

    Args:
        cmd_name (str): Name of the command

    Returns:
        str: Icon for the command, or default icon if not found
    """
    return COMMAND_ICONS.get(cmd_name.lower(), CMD_ICON_DEFAULT)
