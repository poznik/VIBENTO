from layout_autofix.app import AutoLayoutFixer


class PollProbeFixer(AutoLayoutFixer):
    def __init__(self, layouts: list[str | None]) -> None:
        super().__init__()
        self.layouts = layouts
        self._index = 0
        self.scheduled: list[str] = []

    def _get_current_layout(self) -> str | None:
        if not self.layouts:
            return None
        if self._index >= len(self.layouts):
            return self.layouts[-1]

        layout = self.layouts[self._index]
        self._index += 1
        return layout

    def _schedule_selection_conversion(self, target_layout: str) -> None:
        self.scheduled.append(target_layout)


class ConversionProbeFixer(AutoLayoutFixer):
    def __init__(self, selected_text: str | None) -> None:
        super().__init__(layout_poll_interval_seconds=0, settle_delay_seconds=0, paste_restore_delay_seconds=0)
        self.selected_text = selected_text
        self.replaced_texts: list[str] = []
        self.restored_clipboards: list[str] = []

    def _capture_selected_text(self) -> tuple[str | None, str | None]:
        return self.selected_text, "saved-clipboard"

    def _replace_selected_text(self, text: str) -> bool:
        self.replaced_texts.append(text)
        return True

    def _write_clipboard(self, text: str) -> bool:
        self.restored_clipboards.append(text)
        return True


class ClipboardProbeFixer(AutoLayoutFixer):
    def __init__(
        self,
        clipboard_values: list[str | None],
        *,
        wait_timeout: float = 0.05,
        poll_interval: float = 0.0,
    ) -> None:
        super().__init__(
            selection_copy_wait_timeout_seconds=wait_timeout,
            selection_copy_poll_interval_seconds=poll_interval,
        )
        self._clipboard_values = clipboard_values
        self._clipboard_index = 0

    def _read_clipboard(self) -> str | None:
        if self._clipboard_index >= len(self._clipboard_values):
            return self._clipboard_values[-1]

        value = self._clipboard_values[self._clipboard_index]
        self._clipboard_index += 1
        return value


def test_poll_detects_layout_switch() -> None:
    fixer = PollProbeFixer(layouts=["RUS"])

    new_layout = fixer._poll_layout_once(previous_layout="EN")

    assert new_layout == "RUS"
    assert fixer.scheduled == ["RUS"]


def test_poll_without_layout_change_does_not_schedule_conversion() -> None:
    fixer = PollProbeFixer(layouts=["EN"])

    new_layout = fixer._poll_layout_once(previous_layout="EN")

    assert new_layout == "EN"
    assert fixer.scheduled == []


def test_poll_with_unknown_current_layout_keeps_previous() -> None:
    fixer = PollProbeFixer(layouts=[None])

    new_layout = fixer._poll_layout_once(previous_layout="EN")

    assert new_layout == "EN"
    assert fixer.scheduled == []


def test_selected_text_is_converted_to_target_layout() -> None:
    fixer = ConversionProbeFixer(selected_text="Ghbdtn")

    fixer._convert_selected_text_after_switch(target_layout="RUS")

    assert fixer.replaced_texts == ["Привет"]
    assert fixer.restored_clipboards == ["saved-clipboard"]


def test_no_selection_skips_replacement() -> None:
    fixer = ConversionProbeFixer(selected_text=None)

    fixer._convert_selected_text_after_switch(target_layout="EN")

    assert fixer.replaced_texts == []
    assert fixer.restored_clipboards == ["saved-clipboard"]


def test_wait_for_clipboard_change_returns_text_when_updated() -> None:
    fixer = ClipboardProbeFixer(["marker", "marker", "copied-text"], wait_timeout=0.1)

    assert fixer._wait_for_clipboard_change("marker") == "copied-text"


def test_wait_for_clipboard_change_times_out_when_marker_stays() -> None:
    fixer = ClipboardProbeFixer(["marker"], wait_timeout=0.02, poll_interval=0.005)

    assert fixer._wait_for_clipboard_change("marker") is None
