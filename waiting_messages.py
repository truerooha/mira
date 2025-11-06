import random
from pathlib import Path
from typing import List


_DEFAULT_FALLBACK_MESSAGES: List[str] = [
    "Думаю…",
    "Секундочку…",
]


def _load_messages_file() -> List[str]:
    base_dir = Path(__file__).parent
    file_path = base_dir / "data" / "waiting_messages.txt"

    if not file_path.exists():
        return list(_DEFAULT_FALLBACK_MESSAGES)

    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return list(_DEFAULT_FALLBACK_MESSAGES)

    seen = set()
    messages: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in seen:
            continue
        seen.add(line)
        messages.append(line)

    return messages or list(_DEFAULT_FALLBACK_MESSAGES)


_CACHED_MESSAGES: List[str] = _load_messages_file()


def get_waiting_message() -> str:
    """Возвращает случайную фразу ожидания.

    Если файл с фразами недоступен, возвращает одну из запасных фраз.
    """
    return random.choice(_CACHED_MESSAGES)


def get_all_waiting_messages() -> List[str]:
    """Возвращает полный список доступных фраз ожидания."""
    return list(_CACHED_MESSAGES)


