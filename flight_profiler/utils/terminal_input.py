import re
import shutil
import sys
from contextlib import contextmanager

from flight_profiler.utils.render_util import BOX_HORIZONTAL, COLOR_END, COLOR_FAINT

# Optional platform-specific imports
try:
    import readline
    READLINE_AVAILABLE = readline is not None
except ImportError:
    READLINE_AVAILABLE = False

try:
    import termios
    import tty
    TERMIOS_AVAILABLE = True
except ImportError:
    TERMIOS_AVAILABLE = False

try:
    import select as _select_mod
    SELECT_AVAILABLE = True
except ImportError:
    SELECT_AVAILABLE = False


def _find_word_boundary_left(line, pos):
    if pos <= 0:
        return 0
    i = pos - 1
    while i > 0 and line[i] == ' ':
        i -= 1
    while i > 0 and line[i - 1] != ' ':
        i -= 1
    return i


def _find_word_boundary_right(line, pos):
    n = len(line)
    if pos >= n:
        return n
    i = pos
    while i < n and line[i] != ' ':
        i += 1
    while i < n and line[i] == ' ':
        i += 1
    return i


def _get_cursor_position() -> int:
    """Get current cursor row position in terminal (1-based). Returns -1 if unable to detect."""
    if not TERMIOS_AVAILABLE:
        return -1
    try:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            sys.stdout.write('\033[6n')
            sys.stdout.flush()
            response = ''
            while True:
                ch = sys.stdin.read(1)
                response += ch
                if ch == 'R':
                    break
            match = re.search(r'\[(\d+);(\d+)R', response)
            if match:
                return int(match.group(1))
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        pass
    return -1


def _ensure_space_from_bottom(min_lines: int = 3) -> None:
    """Ensure there's enough space from the bottom of terminal."""
    try:
        terminal_height = shutil.get_terminal_size().lines
        cursor_row = _get_cursor_position()
        if cursor_row > 0:
            lines_from_bottom = terminal_height - cursor_row
            if lines_from_bottom < min_lines:
                scroll_lines = min_lines - lines_from_bottom
                print('\n' * scroll_lines, end='')
                sys.stdout.write(f'\033[{scroll_lines}A')
                sys.stdout.flush()
    except Exception:
        pass


class BoxLineEditor:
    """Single-line input editor with box-frame UI and readline-style keybindings."""

    def __init__(self, completions=None):
        """
        Args:
            completions: list of command names for tab completion
        """
        self._completions = completions or []
        # Editing state (reset each read_input call)
        self._line = ''
        self._cursor_pos = 0
        self._prompt = ''
        self._prompt_len = 2  # ❯ + space

    # ── Public API ───────────────────────────────────────────────

    def read_input(self, prompt_active: str, prompt_gray: str,
                   show_placeholder: bool = False) -> str:
        """Read a line with box-frame UI. Raises EOFError / KeyboardInterrupt."""
        _ensure_space_from_bottom(5)

        terminal_width = shutil.get_terminal_size().columns
        separator = f"{COLOR_FAINT}{BOX_HORIZONTAL * terminal_width}{COLOR_END}"
        placeholder = "help"

        if not TERMIOS_AVAILABLE:
            print(separator)
            result = input(prompt_active).strip()
            print(separator)
            return result

        # Draw box frame
        print(separator)
        sys.stdout.write(prompt_active)
        if show_placeholder:
            sys.stdout.write(f'{COLOR_FAINT}{placeholder}{COLOR_END}')
        sys.stdout.write('\n')
        print(separator)

        # Position cursor on input line
        sys.stdout.write('\033[2A')
        sys.stdout.write(f'\033[{self._prompt_len + 1}G')
        sys.stdout.flush()

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        # Reset editing state
        self._line = ''
        self._cursor_pos = 0
        self._prompt = prompt_active
        ctrl_d_pressed = False
        ctrl_c_pressed = False
        placeholder_visible = show_placeholder

        # History navigation
        history_index = -1
        saved_line = ''

        try:
            new_settings = termios.tcgetattr(fd)
            new_settings[3] = new_settings[3] & ~termios.ECHO & ~termios.ICANON & ~termios.ISIG
            new_settings[6][termios.VMIN] = 1
            new_settings[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)

            # Application cursor keys: real arrows → \033O{A,B,C,D}, mouse wheel stays \033[A/B
            sys.stdout.write('\033[?1h')
            sys.stdout.flush()

            while True:
                ch = sys.stdin.read(1)

                if ch == '\x04':  # Ctrl-D
                    if not self._line.strip():
                        if ctrl_d_pressed:
                            sys.stdout.write('\033[1B')
                            sys.stdout.write('\n\033[2K')
                            sys.stdout.write('\n')
                            sys.stdout.flush()
                            raise EOFError()
                        else:
                            ctrl_d_pressed = True
                            sys.stdout.write('\033[1B')
                            sys.stdout.write('\n')
                            sys.stdout.write(f'{COLOR_FAINT}Press Ctrl-D again to exit{COLOR_END}')
                            sys.stdout.write('\033[2A')
                            sys.stdout.write(f'\033[{self._prompt_len + self._cursor_pos + 1}G')
                            sys.stdout.flush()
                    else:
                        self._cleanup_box(prompt_gray)
                        return self._line.strip()

                elif ch == '\x03':  # Ctrl-C
                    if ctrl_c_pressed:
                        sys.stdout.write('\r\033[2K')
                        sys.stdout.write('\033[1B')
                        sys.stdout.write('\n\033[2K')
                        sys.stdout.write('\n')
                        sys.stdout.flush()
                        raise KeyboardInterrupt
                    else:
                        ctrl_c_pressed = True
                        sys.stdout.write('\r\033[2K')
                        sys.stdout.write(self._prompt)
                        self._line = ''
                        self._cursor_pos = 0
                        if ctrl_d_pressed:
                            ctrl_d_pressed = False
                        sys.stdout.write('\033[1B')
                        sys.stdout.write('\n')
                        sys.stdout.write(f'{COLOR_FAINT}Press Ctrl-C again to exit{COLOR_END}')
                        sys.stdout.write('\033[2A')
                        sys.stdout.write(f'\033[{self._prompt_len + 1}G')
                        sys.stdout.flush()

                elif ch == '\n' or ch == '\r':  # Enter
                    if self._line.strip():
                        self._cleanup_box(prompt_gray)
                        return self._line.strip()

                elif ch == '\x7f' or ch == '\x08':  # Backspace
                    if self._cursor_pos > 0:
                        self._line = self._line[:self._cursor_pos - 1] + self._line[self._cursor_pos:]
                        self._cursor_pos -= 1
                        sys.stdout.write('\b')
                        self._redraw_from_cursor()

                elif ch == '\x01':  # Ctrl+A
                    self._move_cursor_to(0)

                elif ch == '\x05':  # Ctrl+E
                    self._move_cursor_to(len(self._line))

                elif ch == '\x15':  # Ctrl+U
                    if self._cursor_pos > 0:
                        self._delete_range(0, self._cursor_pos)

                elif ch == '\x0b':  # Ctrl+K
                    if self._cursor_pos < len(self._line):
                        self._line = self._line[:self._cursor_pos]
                        sys.stdout.write('\033[K')
                        sys.stdout.flush()

                elif ch == '\x17':  # Ctrl+W
                    if self._cursor_pos > 0:
                        new_pos = _find_word_boundary_left(self._line, self._cursor_pos)
                        self._delete_range(new_pos, self._cursor_pos)

                elif ch == '\033':  # Escape sequence
                    seq1 = sys.stdin.read(1)
                    if seq1 == 'O':
                        seq2 = sys.stdin.read(1)
                        if seq2 == 'D':  # Left
                            if self._cursor_pos > 0:
                                self._cursor_pos -= 1
                                sys.stdout.write('\033[D')
                                sys.stdout.flush()
                        elif seq2 == 'C':  # Right
                            if self._cursor_pos < len(self._line):
                                self._cursor_pos += 1
                                sys.stdout.write('\033[C')
                                sys.stdout.flush()
                        elif seq2 == 'A':  # Up - previous history
                            history_len = self._get_history_length()
                            if history_len > 0:
                                if placeholder_visible:
                                    placeholder_visible = False
                                    self._clear_and_rewrite_prompt()
                                if history_index == -1:
                                    saved_line = self._line
                                if history_index < history_len - 1:
                                    history_index += 1
                                    hist_item = self._get_history_item(history_len - history_index)
                                    if hist_item:
                                        self._replace_line(hist_item)
                        elif seq2 == 'B':  # Down - next history
                            if history_index > -1:
                                if placeholder_visible:
                                    placeholder_visible = False
                                    self._clear_and_rewrite_prompt()
                                history_index -= 1
                                if history_index == -1:
                                    self._replace_line(saved_line)
                                else:
                                    history_len = self._get_history_length()
                                    hist_item = self._get_history_item(history_len - history_index)
                                    if hist_item:
                                        self._replace_line(hist_item)
                        elif seq2 == 'H':  # Home
                            self._move_cursor_to(0)
                        elif seq2 == 'F':  # End
                            self._move_cursor_to(len(self._line))
                    elif seq1 == '[':
                        seq2 = sys.stdin.read(1)
                        if seq2 == 'H':
                            self._move_cursor_to(0)
                        elif seq2 == 'F':
                            self._move_cursor_to(len(self._line))
                        elif seq2 == '3':  # Delete key
                            seq3 = sys.stdin.read(1)
                            if seq3 == '~' and self._cursor_pos < len(self._line):
                                self._line = self._line[:self._cursor_pos] + self._line[self._cursor_pos + 1:]
                                self._redraw_from_cursor()
                        elif seq2 == '1':  # Modifier: \033[1;{mod}{dir}
                            seq3 = sys.stdin.read(1)
                            if seq3 == ';':
                                _mod = sys.stdin.read(1)
                                direction = sys.stdin.read(1)
                                if direction == 'D':
                                    self._move_cursor_to(_find_word_boundary_left(self._line, self._cursor_pos))
                                elif direction == 'C':
                                    self._move_cursor_to(_find_word_boundary_right(self._line, self._cursor_pos))
                        elif seq2 in ('A', 'B', 'C', 'D'):
                            pass  # Mouse wheel / stray CSI arrow — ignore
                    elif seq1 in ('b', 'B'):  # Alt+B
                        self._move_cursor_to(_find_word_boundary_left(self._line, self._cursor_pos))
                    elif seq1 in ('f', 'F'):  # Alt+F
                        self._move_cursor_to(_find_word_boundary_right(self._line, self._cursor_pos))
                    elif seq1 == '\x7f':  # Alt+Backspace
                        if self._cursor_pos > 0:
                            new_pos = _find_word_boundary_left(self._line, self._cursor_pos)
                            self._delete_range(new_pos, self._cursor_pos)
                    elif seq1 in ('d', 'D'):  # Alt+D
                        if self._cursor_pos < len(self._line):
                            new_pos = _find_word_boundary_right(self._line, self._cursor_pos)
                            self._delete_range(self._cursor_pos, new_pos)

                elif ch == '\t':  # Tab completion
                    words = self._line.strip().split()
                    if len(words) <= 1 and (len(self._line) == 0 or not self._line.endswith(' ')):
                        prefix = words[0] if words else ''
                        matches = [n for n in self._completions if n.startswith(prefix)]
                        if len(matches) == 1:
                            completion = matches[0] + ' '
                            sys.stdout.write('\b' * self._cursor_pos)
                            sys.stdout.write(' ' * len(self._line))
                            sys.stdout.write('\b' * len(self._line))
                            sys.stdout.write(completion)
                            sys.stdout.flush()
                            self._line = completion
                            self._cursor_pos = len(self._line)
                        elif len(matches) > 1:
                            sys.stdout.write('\n')
                            sys.stdout.write(f"{COLOR_FAINT}  {' '.join(matches)}{COLOR_END}")
                            sys.stdout.write('\033[1A')
                            sys.stdout.write(f'\033[{self._prompt_len + self._cursor_pos + 1}G')
                            sys.stdout.flush()

                elif ' ' <= ch <= '~':  # Printable character
                    if placeholder_visible:
                        placeholder_visible = False
                        sys.stdout.write('\033[2K')
                        sys.stdout.write('\r')
                        sys.stdout.write(self._prompt)
                        sys.stdout.flush()
                    if ctrl_d_pressed or ctrl_c_pressed:
                        ctrl_d_pressed = False
                        ctrl_c_pressed = False
                        sys.stdout.write('\033[1B')
                        sys.stdout.write('\n\033[2K')
                        sys.stdout.write('\033[2A')
                        sys.stdout.write(f'\033[{self._prompt_len + self._cursor_pos + 1}G')
                    self._line = self._line[:self._cursor_pos] + ch + self._line[self._cursor_pos:]
                    self._cursor_pos += 1
                    sys.stdout.write(ch)
                    rest = self._line[self._cursor_pos:]
                    if rest:
                        sys.stdout.write(rest)
                        sys.stdout.write('\b' * len(rest))
                    sys.stdout.flush()

        finally:
            sys.stdout.write('\033[?1l')
            sys.stdout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    @contextmanager
    def suppress_input(self):
        """Context manager: suppress echo and drain stray input during command execution."""
        if not TERMIOS_AVAILABLE:
            yield
            return
        fd = None
        old_settings = None
        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            new_settings = termios.tcgetattr(fd)
            new_settings[3] = new_settings[3] & ~termios.ECHO & ~termios.ICANON
            new_settings[6][termios.VMIN] = 0
            new_settings[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)
        except Exception:
            fd = None
        try:
            yield
        finally:
            if fd is not None and old_settings is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                if SELECT_AVAILABLE:
                    try:
                        while _select_mod.select([sys.stdin], [], [], 0)[0]:
                            sys.stdin.read(1)
                    except Exception:
                        pass

    # ── Private helpers ──────────────────────────────────────────

    def _redraw_from_cursor(self):
        rest = self._line[self._cursor_pos:]
        sys.stdout.write(rest)
        sys.stdout.write('\033[K')
        if rest:
            sys.stdout.write(f'\033[{len(rest)}D')
        sys.stdout.flush()

    def _move_cursor_to(self, new_pos):
        if new_pos == self._cursor_pos:
            return
        if new_pos < self._cursor_pos:
            sys.stdout.write(f'\033[{self._cursor_pos - new_pos}D')
        else:
            sys.stdout.write(f'\033[{new_pos - self._cursor_pos}C')
        self._cursor_pos = new_pos
        sys.stdout.flush()

    def _delete_range(self, start, end):
        if start == end:
            return
        self._line = self._line[:start] + self._line[end:]
        if self._cursor_pos != start:
            self._move_cursor_to(start)
        self._cursor_pos = start
        self._redraw_from_cursor()

    def _replace_line(self, new_text):
        sys.stdout.write('\r')
        sys.stdout.write(self._prompt)
        sys.stdout.write(' ' * len(self._line))
        sys.stdout.write('\r')
        sys.stdout.write(self._prompt)
        sys.stdout.write(new_text)
        sys.stdout.flush()
        self._line = new_text
        self._cursor_pos = len(self._line)

    def _cleanup_box(self, prompt_gray):
        sys.stdout.write('\r\033[1A')
        sys.stdout.write('\033[2K')
        sys.stdout.write(f'{prompt_gray}{self._line}')
        sys.stdout.write('\n\033[J')
        sys.stdout.flush()

    def _clear_and_rewrite_prompt(self):
        sys.stdout.write('\033[2K')
        sys.stdout.write('\r')
        sys.stdout.write(self._prompt)
        sys.stdout.flush()

    @staticmethod
    def _get_history_length():
        if READLINE_AVAILABLE:
            return readline.get_current_history_length()
        return 0

    @staticmethod
    def _get_history_item(index):
        if READLINE_AVAILABLE and index > 0:
            return readline.get_history_item(index)
        return None
