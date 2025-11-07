"""Простой модуль версионности и релизных объявлений для бота Мира."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class ReleaseAnnouncement:
    """Описание релиза и текста, который нужно отправить пользователю."""

    version: str
    message: str
    is_active: bool = True


def _version_tuple(value: Optional[str]) -> tuple[int, ...]:
    """Преобразует строковое представление версии в кортеж чисел."""

    if not value:
        return ()

    parts: List[int] = []
    for raw_part in value.split("."):
        part = raw_part.strip()
        if not part:
            continue
        try:
            parts.append(int(part))
        except ValueError as exc:  # pragma: no cover - защитный fallback
            raise ValueError(f"Некорректный формат версии: '{value}'") from exc
    return tuple(parts)


def sort_releases(releases: Iterable[ReleaseAnnouncement]) -> List[ReleaseAnnouncement]:
    """Возвращает релизы, отсортированные по версии."""

    return sorted(releases, key=lambda rel: _version_tuple(rel.version))


RELEASES: List[ReleaseAnnouncement] = sort_releases(
    [
        ReleaseAnnouncement(
            version="2025.11.07.0",
            message=(
                "🚀 Обновление: умные напоминания\n\n"
                "Теперь я умею делать умные напоминания. Просто скажи слово «Напомни», "
                "и я пришлю напоминание в нужное время!\n"
                "☝️ Например:\n"
                "• 'Напомни мне сходить к парикмахеру завтра в 10:00'\n"
                "• 'Напомни мне выключить кастрюлю через 20 минут\n"
            ),
        ),
    ]
)


CURRENT_VERSION: str = RELEASES[-1].version if RELEASES else "0.0.0"


def get_pending_releases(last_seen_version: Optional[str]) -> List[ReleaseAnnouncement]:
    """Вернуть релизы, которые нужно показать пользователю."""

    seen_tuple = _version_tuple(last_seen_version)
    pending: List[ReleaseAnnouncement] = []

    for release in RELEASES:
        if not release.is_active:
            continue
        if _version_tuple(release.version) > seen_tuple:
            pending.append(release)

    return pending

