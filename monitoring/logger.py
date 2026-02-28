"""
ARUNABHA ALGO BOT - Logger v5.1
================================
WINDOWS FIX:
- UnicodeEncodeError fix: stdout stream UTF-8 encoding forced
- ANSI color codes disabled on Windows (cmd/powershell doesn't support)
- Emoji in log messages stripped on Windows via SafeFormatter
- File logs always UTF-8 (encoding='utf-8' explicit)
- Platform detection: Windows → plain text, Linux/Mac → color
"""

import os
import sys
import platform
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
from typing import Optional

import config

# ── Platform detection ─────────────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"

# Force UTF-8 on Windows stdout to prevent UnicodeEncodeError
if IS_WINDOWS:
    try:
        # Python 3.7+ reconfigure
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _safe_msg(msg: str) -> str:
    """
    Windows-এ emoji encode করতে পারে না।
    সব non-ASCII character replace করে দাও।
    """
    if IS_WINDOWS:
        return msg.encode("ascii", errors="replace").decode("ascii")
    return msg


class SafeFormatter(logging.Formatter):
    """
    Windows-এ emoji/non-ASCII বাদ দেয়।
    Linux/Mac-এ সব ঠিকঠাক থাকে।
    """

    def format(self, record: logging.LogRecord) -> str:
        # record.msg এ emoji থাকতে পারে — safe করো
        if IS_WINDOWS and isinstance(record.msg, str):
            record.msg = _safe_msg(record.msg)
            if record.args:
                try:
                    record.args = tuple(
                        _safe_msg(str(a)) if isinstance(a, str) else a
                        for a in (record.args if isinstance(record.args, tuple) else (record.args,))
                    )
                except Exception:
                    pass
        return super().format(record)


class ColorFormatter(SafeFormatter):
    """
    ANSI color + safe emoji.
    Windows-এ color বন্ধ (cmd/powershell support করে না by default).
    """

    COLORS = {
        "DEBUG":    "\033[36m",   # Cyan
        "INFO":     "\033[32m",   # Green
        "WARNING":  "\033[33m",   # Yellow
        "ERROR":    "\033[31m",   # Red
        "CRITICAL": "\033[35m",   # Magenta
        "RESET":    "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if IS_WINDOWS:
            # No ANSI on Windows — plain text
            return msg
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        return f"{color}{msg}{self.COLORS['RESET']}"


class BotLogger:
    """
    Custom logger:
    - Console: color on Linux/Mac, plain on Windows
    - File: rotating, always UTF-8
    - Error: separate error-only file
    """

    def __init__(self, name: str = "arunabha"):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

        self.logger.handlers.clear()
        self._setup_console_handler()
        self._setup_file_handler()
        self._setup_error_handler()
        self.logger.propagate = False

    def _setup_console_handler(self):
        # Windows: use sys.stdout with errors='replace' wrapper
        if IS_WINDOWS:
            import io
            stream = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            ) if hasattr(sys.stdout, "buffer") else sys.stdout
        else:
            stream = sys.stdout

        handler = logging.StreamHandler(stream)
        handler.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

        fmt = ColorFormatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)
        self.logger.addHandler(handler)

    def _setup_file_handler(self):
        log_file = self.log_dir / f"{self.name}_{datetime.now().strftime('%Y%m')}.log"
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=getattr(config, "LOG_MAX_SIZE", 10 * 1024 * 1024),
            backupCount=getattr(config, "LOG_BACKUP_COUNT", 5),
            encoding="utf-8",     # ← always UTF-8, emoji safe in file
        )
        handler.setLevel(logging.DEBUG)
        fmt = SafeFormatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)
        self.logger.addHandler(handler)

    def _setup_error_handler(self):
        error_file = self.log_dir / f"{self.name}_errors_{datetime.now().strftime('%Y%m')}.log"
        handler = logging.handlers.RotatingFileHandler(
            error_file,
            maxBytes=getattr(config, "LOG_MAX_SIZE", 10 * 1024 * 1024),
            backupCount=getattr(config, "LOG_BACKUP_COUNT", 5),
            encoding="utf-8",
        )
        handler.setLevel(logging.ERROR)
        fmt = SafeFormatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)
        self.logger.addHandler(handler)

    def get_logger(self) -> logging.Logger:
        return self.logger

    @staticmethod
    def log_exception(logger: logging.Logger, exc: Exception, context: str = ""):
        import traceback
        tb = traceback.format_exc()
        if context:
            logger.error(f"Exception in {context}: {exc}")
        else:
            logger.error(f"Exception: {exc}")
        logger.debug(f"Traceback:\n{tb}")


# Global instance
bot_logger = BotLogger().get_logger()
