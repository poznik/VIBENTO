from __future__ import annotations


EN_TO_RU: dict[str, str] = {
    "`": "ё",
    "q": "й",
    "w": "ц",
    "e": "у",
    "r": "к",
    "t": "е",
    "y": "н",
    "u": "г",
    "i": "ш",
    "o": "щ",
    "p": "з",
    "[": "х",
    "]": "ъ",
    "a": "ф",
    "s": "ы",
    "d": "в",
    "f": "а",
    "g": "п",
    "h": "р",
    "j": "о",
    "k": "л",
    "l": "д",
    ";": "ж",
    "'": "э",
    "z": "я",
    "x": "ч",
    "c": "с",
    "v": "м",
    "b": "и",
    "n": "т",
    "m": "ь",
    ",": "б",
    ".": "ю",
    "/": ".",
}

RU_TO_EN: dict[str, str] = {value: key for key, value in EN_TO_RU.items()}


def switch_layout(word: str, to_layout: str) -> str:
    if to_layout not in {"EN", "RUS"}:
        raise ValueError("to_layout must be EN or RUS")

    mapping = EN_TO_RU if to_layout == "RUS" else RU_TO_EN
    converted: list[str] = []
    for ch in word:
        base = mapping.get(ch.lower())
        if base is None:
            converted.append(ch)
            continue
        converted.append(base.upper() if ch.isupper() else base)
    return "".join(converted)
