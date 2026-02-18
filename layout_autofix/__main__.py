from __future__ import annotations

import argparse
import logging
import os
import signal
import sys

from layout_autofix.app import AutoLayoutFixer
from layout_autofix.logging_setup import DEFAULT_LOG_FILE, configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Tracks EN/RUS input-source changes and converts selected text "
            "to the new layout."
        )
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="How often to poll current input source (seconds).",
    )
    parser.add_argument(
        "--settle-delay",
        type=float,
        default=0.02,
        help="Delay around copy/paste to let clipboard and app settle (seconds).",
    )
    parser.add_argument(
        "--layout-switch-settle-delay",
        type=float,
        default=0.12,
        help="Delay after layout switch before attempting to copy selection (seconds).",
    )
    parser.add_argument(
        "--copy-wait-timeout",
        type=float,
        default=0.35,
        help="How long to wait for clipboard update after Cmd+C (seconds).",
    )
    parser.add_argument(
        "--copy-poll-interval",
        type=float,
        default=0.03,
        help="Polling interval while waiting for clipboard update after Cmd+C (seconds).",
    )
    parser.add_argument(
        "--paste-restore-delay",
        type=float,
        default=0.2,
        help="Delay before restoring clipboard after paste (seconds).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console log level.",
    )
    parser.add_argument(
        "--log-file",
        default=str(DEFAULT_LOG_FILE),
        help="Path to persistent log file.",
    )
    parser.add_argument(
        "--debug-events",
        action="store_true",
        help="Enable detailed event logs for polling, layout detection and clipboard operations.",
    )
    args = parser.parse_args()

    log_path = configure_logging(
        log_level=args.log_level,
        log_file=args.log_file,
        debug_events=args.debug_events,
        enable_console=True,
    )
    logger = logging.getLogger(__name__)
    logger.info("event=cli_app_start pid=%s log_file=%s", os.getpid(), log_path)
    logger.info(
        "event=cli_app_config poll_interval=%s settle_delay=%s layout_switch_settle_delay=%s "
        "copy_wait_timeout=%s copy_poll_interval=%s paste_restore_delay=%s debug_events=%s",
        args.poll_interval,
        args.settle_delay,
        args.layout_switch_settle_delay,
        args.copy_wait_timeout,
        args.copy_poll_interval,
        args.paste_restore_delay,
        args.debug_events,
    )

    fixer = AutoLayoutFixer(
        layout_poll_interval_seconds=args.poll_interval,
        settle_delay_seconds=args.settle_delay,
        layout_switch_settle_delay_seconds=args.layout_switch_settle_delay,
        selection_copy_wait_timeout_seconds=args.copy_wait_timeout,
        selection_copy_poll_interval_seconds=args.copy_poll_interval,
        paste_restore_delay_seconds=args.paste_restore_delay,
        debug_event_logging=args.debug_events,
    )

    def _stop(_sig: int, _frame: object) -> None:
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    fixer.run_forever()


if __name__ == "__main__":
    main()
