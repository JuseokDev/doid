import logging
import os
import sys


def is_docker() -> bool:
    return (
        os.path.exists("/.dockerenv")
        or os.path.isfile("/proc/self/cgroup")
        and any("docker" in line for line in open("/proc/self/cgroup"))
    )


def supports_color() -> bool:
    is_a_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    return is_docker() or (
        is_a_tty
        and (
            sys.platform != "win32"
            or "WT_SESSION" in os.environ
            or os.environ.get("TERM_PROGRAM") == "vscode"
            or "PYCHARM_HOSTED" in os.environ
        )
    )


class Formatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(asctime)s %(levelname)-8s %(name)s %(message)s", "%Y-%m-%d %H:%M:%S")


class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = [
        (logging.DEBUG, "\x1b[32;1m"),
        (logging.INFO, "\x1b[34;1m"),
        (logging.WARNING, "\x1b[33;1m"),
        (logging.ERROR, "\x1b[31;1m"),
        (logging.CRITICAL, "\x1b[30;47;1m"),
    ]

    FORMATS = {
        level: logging.Formatter(
            f"\x1b[30;1m%(asctime)s {color}%(levelname)-8s\x1b[0m \x1b[32m%(name)s\x1b[0m %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
        for level, color in LEVEL_COLORS
    }

    def format(self, record: logging.LogRecord):
        formatter = self.FORMATS.get(record.levelno)
        if formatter is None:
            formatter = self.FORMATS[logging.DEBUG]

        if record.exc_info:
            record.exc_text = f"\x1b[31m{formatter.formatException(record.exc_info)}\x1b[0m"

        output = formatter.format(record)

        record.exc_text = None
        return output


def get_formatter():
    return ColorFormatter() if supports_color() else Formatter()
