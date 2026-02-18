from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path

from layout_autofix.app import AutoLayoutFixer
from layout_autofix.autostart import LaunchAgentAutostart
from layout_autofix.logging_setup import DEFAULT_LOG_FILE, configure_logging

try:
    import objc
    from AppKit import (
        NSApp,
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSControlStateValueOff,
        NSControlStateValueOn,
        NSEventMaskLeftMouseUp,
        NSEventMaskRightMouseDown,
        NSEventTypeRightMouseDown,
        NSImage,
        NSImageScaleProportionallyDown,
        NSMenu,
        NSMenuItem,
        NSStatusBar,
        NSVariableStatusItemLength,
    )
    from Foundation import NSMakeSize, NSObject
except Exception as exc:  # pragma: no cover - depends on macOS runtime
    objc = None
    _COCOA_IMPORT_ERROR = exc
else:
    _COCOA_IMPORT_ERROR = None


ICON_FILE_NAME = "layout-switcher-icon.icns"


def _resolve_icon_path() -> str | None:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / ICON_FILE_NAME)

    executable = Path(sys.executable).resolve()
    candidates.append(executable.parent / ICON_FILE_NAME)
    candidates.append(executable.parent.parent / "Resources" / ICON_FILE_NAME)

    # Local dev run: project root is one level above the package directory.
    candidates.append(Path(__file__).resolve().parent.parent / ICON_FILE_NAME)
    candidates.append(Path.cwd() / ICON_FILE_NAME)

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


class StatusBarDelegate(NSObject):  # pragma: no cover - GUI integration
    def initWithFixer_autostart_iconPath_(
        self,
        fixer: AutoLayoutFixer,
        autostart: LaunchAgentAutostart,
        icon_path: str | None,
    ):
        self = objc.super(StatusBarDelegate, self).init()
        if self is None:
            return None

        self._fixer = fixer
        self._autostart = autostart
        self._icon_path = icon_path
        self._status_item = None
        self._worker_thread: threading.Thread | None = None
        self._menu = None
        self._autostart_item = None
        self._logger = logging.getLogger(__name__)
        return self

    def applicationDidFinishLaunching_(self, _notification: object) -> None:
        self._setup_status_item()
        self._start_worker()

    def applicationWillTerminate_(self, _notification: object) -> None:
        self._fixer.stop()

    def onStatusItemClick_(self, _sender: object) -> None:
        event = NSApp.currentEvent()
        if event is None:
            return
        if event.type() != NSEventTypeRightMouseDown:
            return

        self._refresh_menu_state()
        NSMenu.popUpContextMenu_withEvent_forView_(self._menu, event, self._status_item.button())

    def toggleAutostart_(self, _sender: object) -> None:
        try:
            if self._autostart.is_enabled():
                self._autostart.disable()
            else:
                self._autostart.enable()
        finally:
            self._refresh_menu_state()

    def quitApp_(self, _sender: object) -> None:
        self._fixer.stop()
        NSApp.terminate_(None)

    def _setup_status_item(self) -> None:
        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)

        button = self._status_item.button()
        button.setTarget_(self)
        button.setAction_("onStatusItemClick:")
        button.sendActionOn_(NSEventMaskLeftMouseUp | NSEventMaskRightMouseDown)

        image = None
        if self._icon_path:
            image = NSImage.alloc().initWithContentsOfFile_(self._icon_path)
        if image is None:
            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_("keyboard", "Layout Autofix")
        if image is not None:
            image.setTemplate_(True)
            self._fit_status_icon(image, button)
            button.setImage_(image)
        else:
            button.setTitle_("⌨")

        self._menu = NSMenu.alloc().init()
        self._autostart_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Launch At Login",
            "toggleAutostart:",
            "",
        )
        self._autostart_item.setTarget_(self)
        self._menu.addItem_(self._autostart_item)
        self._menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "quitApp:", "")
        quit_item.setTarget_(self)
        self._menu.addItem_(quit_item)

        self._refresh_menu_state()

    def _refresh_menu_state(self) -> None:
        if self._autostart_item is None:
            return
        state = NSControlStateValueOn if self._autostart.is_enabled() else NSControlStateValueOff
        self._autostart_item.setState_(state)

    def _start_worker(self) -> None:
        self._worker_thread = threading.Thread(target=self._fixer.run_forever, daemon=True)
        self._worker_thread.start()
        self._logger.info("event=fixer_thread_started")

    @staticmethod
    def _fit_status_icon(image: object, button: object) -> None:
        try:
            bar_height = float(NSStatusBar.systemStatusBar().thickness())
        except Exception:
            bar_height = 22.0

        icon_size = max(14.0, min(22.0, bar_height - 4.0))
        image.setSize_(NSMakeSize(icon_size, icon_size))
        button.setImageScaling_(NSImageScaleProportionallyDown)


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("This app can run only on macOS.")
    if _COCOA_IMPORT_ERROR is not None:
        raise SystemExit(
            "PyObjC is required for macOS app mode. Install dependency "
            "'pyobjc-framework-Cocoa'."
        )

    parser = argparse.ArgumentParser(
        description=(
            "Runs Layout Autofix as a macOS status bar app with right-click menu "
            "and launch-at-login toggle."
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
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Enable detailed event logs for polling, layout detection and clipboard operations. "
            "Enabled by default for .app launches."
        ),
    )
    args = parser.parse_args()

    log_path = configure_logging(
        log_level=args.log_level,
        log_file=args.log_file,
        debug_events=args.debug_events,
        enable_console=False,
    )
    logger = logging.getLogger(__name__)
    logger.info("event=macos_app_start pid=%s log_file=%s", os.getpid(), log_path)

    fixer = AutoLayoutFixer(
        layout_poll_interval_seconds=args.poll_interval,
        settle_delay_seconds=args.settle_delay,
        layout_switch_settle_delay_seconds=args.layout_switch_settle_delay,
        selection_copy_wait_timeout_seconds=args.copy_wait_timeout,
        selection_copy_poll_interval_seconds=args.copy_poll_interval,
        paste_restore_delay_seconds=args.paste_restore_delay,
        debug_event_logging=args.debug_events,
    )
    autostart = LaunchAgentAutostart()
    icon_path = _resolve_icon_path()
    logger.info(
        "event=macos_app_config poll_interval=%s settle_delay=%s layout_switch_settle_delay=%s "
        "copy_wait_timeout=%s copy_poll_interval=%s paste_restore_delay=%s debug_events=%s",
        args.poll_interval,
        args.settle_delay,
        args.layout_switch_settle_delay,
        args.copy_wait_timeout,
        args.copy_poll_interval,
        args.paste_restore_delay,
        args.debug_events,
    )
    logger.info("event=icon_path_resolved icon_path=%s", icon_path)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    if icon_path:
        app_icon = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if app_icon is not None:
            app.setApplicationIconImage_(app_icon)
    delegate = StatusBarDelegate.alloc().initWithFixer_autostart_iconPath_(fixer, autostart, icon_path)
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
