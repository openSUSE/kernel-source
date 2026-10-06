import shlex


def get_printable_cmd(cmd, indent_spaces=2):
    r"""Safely quotes and formats a command list into a multiline string.
    Example:
        >>> cmd = ["qemu-system-aarch64", "-cpu", "max", "-m", "4096"]
        >>> print(f"[INFO] QEMU command: {get_printable_cmd(cmd)}")
        [INFO] QEMU command:
          qemu-system-aarch64 \
            -cpu \
            max \
            -m \
            4096
    """
    if not cmd:
        return ""
    executable = str(cmd[0])
    args = [shlex.quote(str(arg)) for arg in cmd[1:]]

    indent = " " * indent_spaces
    args_indent = indent * 2

    formatted_args = f" \\\n{args_indent}".join(args)

    if formatted_args:
        return f"\n{indent}{executable} \\\n{args_indent}{formatted_args}"
    return f"\n{indent}{executable}"
