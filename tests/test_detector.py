import pytest

from layout_autofix.detector import switch_layout


def test_switch_layout_en_to_ru_word() -> None:
    assert switch_layout("ghbdtn", to_layout="RUS") == "привет"


def test_switch_layout_ru_to_en_word() -> None:
    assert switch_layout("руддщ", to_layout="EN") == "hello"


def test_switch_layout_keeps_letter_case() -> None:
    assert switch_layout("Ghbdtn", to_layout="RUS") == "Привет"


def test_switch_layout_raises_for_unknown_target_layout() -> None:
    with pytest.raises(ValueError, match="to_layout must be EN or RUS"):
        switch_layout("hello", to_layout="DE")
