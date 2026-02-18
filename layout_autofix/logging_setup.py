from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


DEFAULT_LOG_FILE = Path.home() / "Library" / "Logs" / "LayoutAutofix" / "layout-autofix.log"


def configure_logging(
    *,
    log_level: str,
    log_file: str | None = None,
    debug_events: bool = False,
    enable_console: bool = True,
) -> Path:
    effective_level = _effective_log_level(log_level, debug_events=debug_events)
    resolved_log_file = _resolve_log_file(log_file)
    resolved_log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handlers: list[logging.Handler] = []

    file_handler = RotatingFileHandler(
        resolved_log_file,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)

    if enable_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    logging.basicConfig(
        level=effective_level,
        handlers=handlers,
        force=True,
    )

    logging.getLogger(__name__).info(
        "event=logging_initialized level=%s debug_events=%s log_file=%s",
        logging.getLevelName(effective_level),
        debug_events,
        resolved_log_file,
    )
    return resolved_log_file


def _resolve_log_file(log_file: str | None) -> Path:
    if not log_file:
        return DEFAULT_LOG_FILE
    return Path(log_file).expanduser().resolve()


def _effective_log_level(log_level: str, *, debug_events: bool) -> int:
    base_level = getattr(logging, log_level.upper(), logging.INFO)
    if debug_events:
        return min(base_level, logging.DEBUG)
    return base_level
