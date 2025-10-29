from enum import Enum
from typing import Union

from pygit2.config import Config


class Color(Enum):
    """ANSI color codes for terminal text formatting.

    Usage:
    Color.GREEN("Example text"), produces green text.
    Color.GREEN + "Example text" + Color.RESET, is the same as Color.GREEN("Example text")
    """

    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    LIGHT_GRAY = "\033[37m"
    GRAY = "\033[90m"
    LIGHT_RED = "\033[91m"
    LIGHT_GREEN = "\033[92m"
    LIGHT_YELLOW = "\033[93m"
    LIGHT_BLUE = "\033[94m"
    LIGHT_MAGENTA = "\033[95m"
    LIGHT_CYAN = "\033[96m"
    WHITE = "\033[97m"
    RESET = "\033[0m"

    def __call__(self, text):
        return f"{self.value}{text}{Color.RESET.value}"

    def __str__(self):
        return self.value


def print_tree(
    tree: dict[Union[str, tuple[str, str]], Union[dict, None]], indent=4
) -> None:
    """Print a tree like dict to the console."""

    def _tree_to_str(
        item: Union[str, tuple[str, str]],
        tree: Union[dict, None] = None,
        level: int = 0,
        indent: int = 4,
    ) -> str:
        """"""
        description = ""
        if isinstance(item, tuple):
            name, description = item
        else:
            name = item

        if level % 5 == 0:
            name = Color.BLUE(name)
        elif level % 5 == 1:
            name = Color.MAGENTA(name)
        elif level % 5 == 2:
            name = Color.GREEN(name)
        elif level % 5 == 3:
            name = Color.CYAN(name)
        elif level % 5 == 4:
            name = Color.RED(name)

        title = f"{name} {description}".strip()

        lines = [title]
        if tree is None:
            return title
        for index, (subitem, subtree) in enumerate(tree.items()):
            subtree_lines = _tree_to_str(subitem, subtree, level + 1, indent).split(
                "\n"
            )
            last = index == len(tree) - 1

            for line_index, line in enumerate(subtree_lines):
                prefix = " " * indent
                if last:
                    if line_index == 0:
                        prefix = f"└{'─' * (indent - 2)} "
                else:
                    if line_index == 0:
                        prefix = f"├{'─' * (indent - 2)} "
                    else:
                        prefix = f"│{' ' * (indent - 2)} "
                subtree_lines[line_index] = f"{prefix}{line}"
            lines.extend(subtree_lines)
        return "\n".join(lines)

    lines = []
    for subitem, subtree in tree.items():
        lines.append(_tree_to_str(subitem, subtree, 0, indent))
    print("\n".join(lines))


def get_input(
    prompt: str,
    default: Union[str, None] = None,
    optional: bool = False,
    input_type: Union[type] = str,
) -> str | int | float | bool | None:
    """
    Helper function to get input from the user with a prompt.
    If default is provided, it will be used if the user just presses Enter.
    If optional is False, the user must provide an input.
    """
    parenthetical = f" [{Color.BLUE(default)}]" if default is not None else ""
    if optional and default is not None:
        parenthetical = f" [{Color.BLUE(default)}, {Color.MAGENTA('n to skip')}]"

    if input_type is bool:
        parenthetical = f"{parenthetical} {Color.MAGENTA('(y/n)')}"

    while True:
        user_input = input(f"{Color.GREEN(prompt)}{parenthetical}: ")
        if not user_input:
            if default is not None:
                user_input = default
            elif optional:
                return None
            else:
                print("This field is required. Please provide a value.")
                continue
        try:
            if user_input == "n" and optional:
                return None
            if input_type in [int, float, str]:
                return input_type(user_input)
            elif input_type is bool:
                true_input = user_input.lower() in ["true", "1", "yes", "y"]
                false_input = user_input.lower() in ["false", "0", "no", "n"]
                if true_input:
                    return True
                elif false_input:
                    return False
                raise ValueError(f"Invalid input for boolean: {user_input}")
            return input_type(user_input)
        except ValueError:
            print(
                f"{Color.RED}Invalid input. Please enter a valid {input_type.__name__}.{Color.RESET}"
            )


def git_global_config() -> dict[str, str]:
    """
    Fetches the global git configuration.
    """
    config = Config.get_global_config()
    return {value.name: value.value for value in config}


def arg(*argnames, **kwargs):
    """Helper for defining arguments on subcommands"""
    return argnames, kwargs
