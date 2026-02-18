from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from pynput import keyboard

from layout_autofix.detector import switch_layout

try:  # pragma: no cover - optional runtime dependency
    import Quartz
except Exception:  # pragma: no cover
    Quartz = None

try:  # pragma: no cover - optional runtime dependency
    import HIServices
except Exception:  # pragma: no cover
    HIServices = None


@dataclass
class AutoLayoutFixer:
    layout_poll_interval_seconds: float = 0.1
    settle_delay_seconds: float = 0.02
    layout_switch_settle_delay_seconds: float = 0.12
    selection_copy_wait_timeout_seconds: float = 0.35
    selection_copy_poll_interval_seconds: float = 0.03
    paste_restore_delay_seconds: float = 0.2
    debug_event_logging: bool = False
    _controller: keyboard.Controller = field(default_factory=keyboard.Controller, init=False)
    _conversion_active: threading.Event = field(default_factory=threading.Event, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _ax_warning_logged: bool = field(default=False, init=False)
    _logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__), init=False)

    def run_forever(self) -> None:
        previous_layout = self._get_current_layout()
        self._logger.info(
            "event=watcher_started initial_layout=%s poll_interval=%s settle_delay=%s "
            "layout_switch_settle_delay=%s selection_copy_wait_timeout=%s "
            "selection_copy_poll_interval=%s paste_restore_delay=%s debug_events=%s",
            previous_layout,
            self.layout_poll_interval_seconds,
            self.settle_delay_seconds,
            self.layout_switch_settle_delay_seconds,
            self.selection_copy_wait_timeout_seconds,
            self.selection_copy_poll_interval_seconds,
            self.paste_restore_delay_seconds,
            self.debug_event_logging,
        )
        self._check_ax_permission(prompt=True)

        while not self._stop_event.is_set():
            time.sleep(self.layout_poll_interval_seconds)
            try:
                previous_layout = self._poll_layout_once(previous_layout)
            except Exception:
                self._logger.exception("event=poll_iteration_exception")

        self._logger.info("event=watcher_stopped")

    def stop(self) -> None:
        self._stop_event.set()
        self._logger.info("event=watcher_stop_requested")

    def _poll_layout_once(self, previous_layout: str | None) -> str | None:
        current_layout = self._get_current_layout()
        if current_layout is None:
            return previous_layout

        if previous_layout is not None and current_layout != previous_layout:
            self._logger.info(
                "event=layout_changed from_layout=%s to_layout=%s",
                previous_layout,
                current_layout,
            )
            self._schedule_selection_conversion(current_layout)

        return current_layout

    def _schedule_selection_conversion(self, target_layout: str) -> None:
        with self._lock:
            if self._conversion_active.is_set():
                if self.debug_event_logging:
                    self._logger.debug(
                        "event=selection_convert_skipped reason=already_active target_layout=%s",
                        target_layout,
                    )
                return
            self._conversion_active.set()
            if self.debug_event_logging:
                self._logger.debug("event=selection_convert_scheduled target_layout=%s", target_layout)

        thread = threading.Thread(
            target=self._convert_selected_text_after_switch,
            args=(target_layout,),
            daemon=True,
        )
        thread.start()

    def _convert_selected_text_after_switch(self, target_layout: str) -> None:
        previous_clipboard: str | None = None
        try:
            if self.debug_event_logging:
                self._logger.debug("event=selection_convert_started target_layout=%s", target_layout)
                self._logger.debug(
                    "event=selection_convert_wait_before_capture seconds=%s",
                    self.layout_switch_settle_delay_seconds,
                )
            time.sleep(self.layout_switch_settle_delay_seconds)
            selected_text, previous_clipboard = self._capture_selected_text()
            if not selected_text:
                self._logger.info("event=no_selection")
                return

            if self.debug_event_logging:
                self._logger.debug(
                    "event=selection_captured text_len=%s text_preview=%r",
                    len(selected_text),
                    self._text_preview(selected_text),
                )
            converted = switch_layout(selected_text, to_layout=target_layout)
            if converted == selected_text:
                self._logger.info("event=selection_unchanged text=%r", selected_text)
                return

            replaced = self._replace_selected_text(converted)
            self._logger.info(
                "event=selection_converted target_layout=%s success=%s original=%r converted=%r",
                target_layout,
                replaced,
                selected_text,
                converted,
            )
        except Exception:
            self._logger.exception("event=selection_convert_exception target_layout=%s", target_layout)
        finally:
            if previous_clipboard is not None:
                self._write_clipboard(previous_clipboard)
                if self.debug_event_logging:
                    self._logger.debug(
                        "event=clipboard_restored restored_len=%s restored_preview=%r",
                        len(previous_clipboard),
                        self._text_preview(previous_clipboard),
                    )
            self._conversion_active.clear()
            if self.debug_event_logging:
                self._logger.debug("event=selection_convert_finished target_layout=%s", target_layout)

    def _capture_selected_text(self) -> tuple[str | None, str | None]:
        selected_via_ax = self._read_selected_text_ax()
        if selected_via_ax:
            if self.debug_event_logging:
                self._logger.debug(
                    "event=selection_capture_success method=ax selected_len=%s selected_preview=%r",
                    len(selected_via_ax),
                    self._text_preview(selected_via_ax),
                )
            return selected_via_ax, None

        previous_clipboard = self._read_clipboard()
        marker = f"__layout_autofix_marker_{time.monotonic_ns()}__"
        if self.debug_event_logging:
            self._logger.debug(
                "event=selection_capture_started previous_clipboard_len=%s marker=%s",
                None if previous_clipboard is None else len(previous_clipboard),
                marker,
            )

        if not self._write_clipboard(marker):
            if self.debug_event_logging:
                self._logger.debug("event=selection_capture_failed reason=write_marker_failed")
            return None, previous_clipboard

        time.sleep(self.settle_delay_seconds)
        copied = self._copy_selected_text_to_clipboard(marker)
        if copied is None:
            if self.debug_event_logging:
                self._logger.debug("event=selection_capture_empty reason=clipboard_not_updated")
            return None, previous_clipboard

        if self.debug_event_logging:
            self._logger.debug(
                "event=selection_capture_success copied_len=%s copied_preview=%r",
                len(copied),
                self._text_preview(copied),
            )
        return copied, previous_clipboard

    def _replace_selected_text(self, text: str) -> bool:
        replaced_via_ax = self._replace_selected_text_ax(text)
        if replaced_via_ax:
            if self.debug_event_logging:
                self._logger.debug("event=selection_replace_done method=ax")
            return True

        if self.debug_event_logging:
            self._logger.debug(
                "event=selection_replace_started text_len=%s text_preview=%r",
                len(text),
                self._text_preview(text),
            )
        if not self._write_clipboard(text):
            if self.debug_event_logging:
                self._logger.debug("event=selection_replace_failed reason=write_clipboard_failed")
            return False

        time.sleep(self.settle_delay_seconds)
        self._send_shortcut(keyboard.Key.cmd, "v")
        # Do not restore clipboard too early; target app may paste asynchronously.
        time.sleep(self.paste_restore_delay_seconds)
        if self.debug_event_logging:
            self._logger.debug("event=selection_replace_done")
        return True

    def _read_selected_text_ax(self) -> str | None:
        if HIServices is None:
            return None
        try:
            system = HIServices.AXUIElementCreateSystemWide()
            err, focused = HIServices.AXUIElementCopyAttributeValue(
                system,
                HIServices.kAXFocusedUIElementAttribute,
                None,
            )
            if err != HIServices.kAXErrorSuccess or focused is None:
                if self.debug_event_logging:
                    self._logger.debug("event=ax_focused_element_failed error=%s", err)
                if err == HIServices.kAXErrorAPIDisabled:
                    self._check_ax_permission(prompt=True)
                return None

            err, selected = HIServices.AXUIElementCopyAttributeValue(
                focused,
                HIServices.kAXSelectedTextAttribute,
                None,
            )
            if err != HIServices.kAXErrorSuccess:
                if self.debug_event_logging:
                    self._logger.debug("event=ax_selected_text_failed error=%s", err)
                return None
            if selected is None:
                return None

            selected_text = str(selected)
            if selected_text == "":
                return None
            return selected_text
        except Exception as exc:
            if self.debug_event_logging:
                self._logger.debug("event=ax_selected_text_exception error=%r", exc)
            return None

    def _check_ax_permission(self, *, prompt: bool) -> bool:
        if HIServices is None:
            return False

        trusted = False
        try:
            trusted = bool(HIServices.AXIsProcessTrusted())
        except Exception as exc:
            if self.debug_event_logging:
                self._logger.debug("event=ax_trust_check_failed error=%r", exc)

        if trusted:
            if self.debug_event_logging:
                self._logger.debug("event=ax_trusted")
            return True

        if not self._ax_warning_logged:
            self._logger.warning(
                "event=ax_not_trusted reason=accessibility_disabled "
                "hint='System Settings -> Privacy & Security -> Accessibility: add/enable LayoutAutofix.app'"
            )
            self._ax_warning_logged = True

        if prompt and hasattr(HIServices, "AXIsProcessTrustedWithOptions"):
            try:
                HIServices.AXIsProcessTrustedWithOptions(
                    {HIServices.kAXTrustedCheckOptionPrompt: True}
                )
            except Exception as exc:
                if self.debug_event_logging:
                    self._logger.debug("event=ax_prompt_failed error=%r", exc)
        return False

    def _replace_selected_text_ax(self, text: str) -> bool:
        if HIServices is None:
            return False
        try:
            system = HIServices.AXUIElementCreateSystemWide()
            err, focused = HIServices.AXUIElementCopyAttributeValue(
                system,
                HIServices.kAXFocusedUIElementAttribute,
                None,
            )
            if err != HIServices.kAXErrorSuccess or focused is None:
                if self.debug_event_logging:
                    self._logger.debug("event=ax_replace_focus_failed error=%s", err)
                return False

            err = HIServices.AXUIElementSetAttributeValue(
                focused,
                HIServices.kAXSelectedTextAttribute,
                text,
            )
            if err != HIServices.kAXErrorSuccess:
                if self.debug_event_logging:
                    self._logger.debug("event=ax_replace_failed error=%s", err)
                return False
            return True
        except Exception as exc:
            if self.debug_event_logging:
                self._logger.debug("event=ax_replace_exception error=%r", exc)
            return False

    def _read_clipboard(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["pbpaste"],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            if self.debug_event_logging:
                self._logger.debug("event=clipboard_read_exception error=%r", exc)
            return None

        if result.returncode != 0:
            if self.debug_event_logging:
                self._logger.debug(
                    "event=clipboard_read_failed returncode=%s stderr=%r",
                    result.returncode,
                    result.stderr,
                )
            return None
        if self.debug_event_logging:
            self._logger.debug(
                "event=clipboard_read_ok text_len=%s text_preview=%r",
                len(result.stdout),
                self._text_preview(result.stdout),
            )
        return result.stdout

    def _write_clipboard(self, text: str) -> bool:
        try:
            result = subprocess.run(
                ["pbcopy"],
                check=False,
                input=text,
                text=True,
            )
        except Exception as exc:
            if self.debug_event_logging:
                self._logger.debug("event=clipboard_write_exception error=%r", exc)
            return False

        if result.returncode != 0:
            if self.debug_event_logging:
                self._logger.debug(
                    "event=clipboard_write_failed returncode=%s stderr=%r",
                    result.returncode,
                    result.stderr,
                )
            return False
        if self.debug_event_logging:
            self._logger.debug(
                "event=clipboard_write_ok text_len=%s text_preview=%r",
                len(text),
                self._text_preview(text),
            )
        return True

    def _copy_selected_text_to_clipboard(self, marker: str) -> str | None:
        self._send_shortcut(keyboard.Key.cmd, "c")
        copied = self._wait_for_clipboard_change(marker)
        if copied is not None:
            if self.debug_event_logging:
                self._logger.debug("event=copy_shortcut_success method=pynput")
            return copied

        if self.debug_event_logging:
            self._logger.debug("event=copy_shortcut_fallback method=quartz reason=pynput_no_clipboard_update")
        if not self._send_command_shortcut_quartz("c"):
            if self.debug_event_logging:
                self._logger.debug("event=copy_shortcut_fallback_unavailable method=quartz")
            return None

        copied = self._wait_for_clipboard_change(marker)
        if copied is not None and self.debug_event_logging:
            self._logger.debug("event=copy_shortcut_success method=quartz")
        return copied

    def _wait_for_clipboard_change(self, marker: str) -> str | None:
        deadline = time.monotonic() + self.selection_copy_wait_timeout_seconds
        attempts = 0
        last_value: str | None = None
        while time.monotonic() < deadline:
            attempts += 1
            time.sleep(self.selection_copy_poll_interval_seconds)
            copied = self._read_clipboard()
            if copied is None:
                continue
            last_value = copied
            if copied != marker:
                if self.debug_event_logging:
                    self._logger.debug(
                        "event=clipboard_copy_detected attempts=%s copied_len=%s copied_preview=%r",
                        attempts,
                        len(copied),
                        self._text_preview(copied),
                    )
                return copied

        if self.debug_event_logging:
            self._logger.debug(
                "event=clipboard_copy_timeout attempts=%s last_value_is_marker=%s last_value_preview=%r",
                attempts,
                last_value == marker,
                None if last_value is None else self._text_preview(last_value),
            )
        return None

    def _send_command_shortcut_quartz(self, key: str) -> bool:
        if Quartz is None:
            return False

        keycodes = {
            "c": 8,
            "v": 9,
        }
        keycode = keycodes.get(key.lower())
        if keycode is None:
            return False

        try:
            source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
            if source is None:
                return False

            key_down = Quartz.CGEventCreateKeyboardEvent(source, keycode, True)
            key_up = Quartz.CGEventCreateKeyboardEvent(source, keycode, False)
            if key_down is None or key_up is None:
                return False

            flags = Quartz.kCGEventFlagMaskCommand
            Quartz.CGEventSetFlags(key_down, flags)
            Quartz.CGEventSetFlags(key_up, flags)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)
            return True
        except Exception as exc:
            if self.debug_event_logging:
                self._logger.debug("event=quartz_shortcut_failed key=%s error=%r", key, exc)
            return False

    def _send_shortcut(self, modifier: keyboard.Key, key: str) -> None:
        if self.debug_event_logging:
            self._logger.debug("event=send_shortcut modifier=%s key=%s", modifier, key)
        self._controller.press(modifier)
        self._controller.press(key)
        self._controller.release(key)
        self._controller.release(modifier)

    def _get_current_layout(self) -> str | None:
        try:
            output = subprocess.check_output(
                ["defaults", "read", "com.apple.HIToolbox", "AppleSelectedInputSources"],
                text=True,
            )
        except Exception as exc:
            if self.debug_event_logging:
                self._logger.debug("event=layout_read_failed error=%r", exc)
            return None

        layout_names = re.findall(r'"KeyboardLayout Name"\s*=\s*([^;]+);', output)
        if not layout_names:
            if self.debug_event_logging:
                self._logger.debug("event=layout_parse_failed reason=no_layout_names")
            return None

        current_name = layout_names[-1].strip().strip('"').lower()
        if "russian" in current_name or "рус" in current_name:
            return "RUS"
        if "abc" in current_name or "u.s." in current_name or "english" in current_name:
            return "EN"
        if self.debug_event_logging:
            self._logger.debug("event=layout_unknown current_layout_name=%r", current_name)
        return None

    @staticmethod
    def _text_preview(text: str, *, limit: int = 120) -> str:
        compact = text.replace("\n", "\\n")
        if len(compact) <= limit:
            return compact
        return compact[:limit] + "..."
