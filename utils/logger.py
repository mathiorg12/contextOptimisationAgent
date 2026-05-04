"""
Structured logger for the Context Optimisation Agent.

Writes to:
  - Console: colored output via 'rich' (falls back to plain if unavailable)
  - File:    agent_run.log in the project root (always)

Usage:
    from utils.logger import get_logger
    log = get_logger(__name__)
    log.info("something happened")
    log.debug("tool called: %s args=%s", tool_name, args)
    log.error("API error", exc_info=True)
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

# ── Log file location ────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_FILE = os.path.join(_PROJECT_ROOT, "agent_run.log")

# ── Rich handler (optional) ───────────────────────────────────────────────────
try:
    from rich.logging import RichHandler
    _CONSOLE_HANDLER = RichHandler(
        show_time=True,
        show_level=True,
        show_path=True,
        rich_tracebacks=True,
        markup=True,
    )
    _CONSOLE_HANDLER.setLevel(logging.DEBUG)
    _USE_RICH = True
except ImportError:
    _CONSOLE_HANDLER = logging.StreamHandler(sys.stdout)
    _CONSOLE_HANDLER.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)-8s] %(name)s — %(message)s", datefmt="%H:%M:%S")
    )
    _USE_RICH = False

# ── File handler (always plain text so it's grep-friendly) ───────────────────
_FILE_HANDLER = RotatingFileHandler(
    _LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=3,
    encoding="utf-8",
)
_FILE_HANDLER.setFormatter(
    logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
)
_FILE_HANDLER.setLevel(logging.DEBUG)

# ── Root config ───────────────────────────────────────────────────────────────
def _configure_root():
    root = logging.getLogger()
    if root.handlers:
        return  # already configured
    root.setLevel(logging.DEBUG)
    root.addHandler(_CONSOLE_HANDLER)
    root.addHandler(_FILE_HANDLER)
    # Suppress overly verbose third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "google", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

_configure_root()


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Always call this instead of logging.getLogger() directly."""
    return logging.getLogger(name)


def get_log_file_path() -> str:
    return _LOG_FILE


def read_recent_logs(n_lines: int = 200) -> str:
    """Read the last n_lines from the log file (used by /logs endpoint)."""
    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[-n_lines:])
    except FileNotFoundError:
        return "(no log file yet)"
    except Exception as e:
        return f"(error reading log: {e})"
