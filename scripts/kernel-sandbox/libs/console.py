import logging
import sys

LOGGER_NAME = "kernel_sandbox"
DEFAULT_LOG_FORMAT = "[%(levelname)s] %(message)s"


class LogLevelFilter(logging.Filter):
    """Rejects any record at or above max_level.

    Used to keep the stdout handler from also emitting WARNING/ERROR
    records once the separate stderr handler has claimed them.
    """

    def __init__(self, max_level):
        super().__init__()
        self.max_level = max_level

    def filter(self, record):
        return record.levelno < self.max_level


def print_phase_header(phase_title, details=None, width=70, character="=", indent_spaces=2):
    r"""Prints a structured banner for build pipeline phases.
    Example:
        >>> print_phase_header("Boot Test", ["Arch: arm64", "Timeout: 30s"])
        ======================================================================
          Boot Test
            - Arch: arm64
            - Timeout: 30s
        ======================================================================
    """
    details = details or []
    divider = character * width
    indent = " " * indent_spaces

    print(f"\n{divider}")
    print(f"{indent}{phase_title}")
    for line in details:
        print(f"{indent}  - {line}")
    print(f"{divider}\n")


def configure_logging(logger_name=LOGGER_NAME, level=logging.INFO, log_format=DEFAULT_LOG_FORMAT):
    """
    Configures dual-stream logging (stdout for INFO/DEBUG, stderr for WARNING/ERROR/CRITICAL).
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(log_format)

    # stdout handler: INFO and DEBUG
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(LogLevelFilter(logging.WARNING))
    logger.addHandler(stdout_handler)

    # stderr handler: WARNING, ERROR, CRITICAL
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.WARNING)
    logger.addHandler(stderr_handler)

    return logger


def get_logger(name=None, base_name=LOGGER_NAME):
    """
    Retrieves a logger nested under base_name (ex: get_logger(__name__) inside
    libs/storage_manager.py resolves to "kernel_sandbox.libs.storage_manager"),
    auto-configuring base_name's handlers on first use if none exist yet.
    """
    base_logger = logging.getLogger(base_name)

    if not base_logger.hasHandlers():
        configure_logging(logger_name=base_name)

    return base_logger.getChild(name) if name else base_logger
