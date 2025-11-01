"""
Умный форматтер дат для человечных ответов
Проект "Второй мозг" - персональный голосовой интеллект
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class SmartDateFormatter:
    """Умный форматтер дат для создания человечных временных выражений"""
    
    def __init__(self):
        # Маппинг месяцев
        self.month_names = {
            1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
            5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
            9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
        }
        
        # Маппинг дней недели (именительный падеж)
        self.weekday_names = {
            0: 'понедельник', 1: 'вторник', 2: 'среда', 3: 'четверг',
            4: 'пятница', 5: 'суббота', 6: 'воскресенье'
        }
        
        # Маппинг дней недели (винительный падеж с предлогом "в")
        self.weekday_names_accusative = {
            0: 'понедельник', 1: 'вторник', 2: 'среду', 3: 'четверг',
            4: 'пятницу', 5: 'субботу', 6: 'воскресенье'
        }
    
    def format_entry_date(self, entry: Dict, reference_date: datetime = None) -> str:
        """
        Форматирует дату записи в человечном формате относительно текущей даты
        
        Args:
            entry: Словарь с данными записи
            reference_date: Опорная дата для сравнения (default: текущая дата)
        
        Returns:
            Человечное выражение времени или пустая строка
        """
        if reference_date is None:
            reference_date = datetime.now()
        
        # Извлекаем дату из записи
        entry_date = self._extract_entry_date(entry)
        if not entry_date:
            return ""
        
        # Вычисляем разницу
        time_diff = self._calculate_time_difference(entry_date, reference_date)
        
        # Форматируем в зависимости от разницы
        return self._format_time_difference(entry_date, time_diff, reference_date)
    
    def _extract_entry_date(self, entry: Dict) -> Optional[datetime]:
        """Извлекает дату из записи"""
        # Сначала пытаемся извлечь из parsed_date в metadata
        metadata = entry.get('metadata')
        if metadata:
            try:
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                parsed_date = metadata.get('parsed_date')
                if parsed_date:
                    # Парсим дату в формате YYYY-MM-DD HH:MM:SS
                    return datetime.strptime(parsed_date, '%Y-%m-%d %H:%M:%S')
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.debug(f"Не удалось распарсить parsed_date: {e}")
        
        # Если нет parsed_date, используем created_at
        created_at = entry.get('created_at')
        if created_at:
            try:
                if isinstance(created_at, str):
                    # Парсим дату в формате YYYY-MM-DD HH:MM:SS
                    return datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                logger.debug(f"Не удалось распарсить created_at: {e}")
        
        return None
    
    def _calculate_time_difference(self, entry_date: datetime, reference_date: datetime) -> Dict:
        """
        Вычисляет разницу между датами
        
        Returns:
            Dict с ключами: days, weeks, months, is_past, is_future
        """
        # Нормализуем до дат без времени для сравнения
        entry_date_normalized = entry_date.date()
        reference_date_normalized = reference_date.date()
        
        # Вычисляем разницу в днях
        delta = entry_date_normalized - reference_date_normalized
        days_diff = delta.days
        
        # Определяем направление времени
        is_past = days_diff < 0
        is_future = days_diff > 0
        
        # Вычисляем разницу в неделях и месяцах
        weeks_diff = abs(days_diff) // 7
        months_diff = abs(days_diff) // 30  # Приблизительно
        years_diff = abs(days_diff) // 365
        
        return {
            'days': abs(days_diff),
            'weeks': weeks_diff,
            'months': months_diff,
            'years': years_diff,
            'is_past': is_past,
            'is_future': is_future,
            'original_days': days_diff
        }
    
    def _format_time_difference(self, entry_date: datetime, time_diff: Dict, reference_date: datetime) -> str:
        """Форматирует разницу времени в человечное выражение"""
        days = time_diff['days']
        weeks = time_diff['weeks']
        months = time_diff['months']
        years = time_diff['years']
        is_past = time_diff['is_past']
        is_future = time_diff['is_future']
        
        # Сегодня - обрабатываем первым
        if days == 0:
            return "Сегодня"
        
        # Будущее время (напоминания)
        if is_future:
            if days == 1:
                return "Завтра"
            elif days == 2:
                return "Послезавтра"
            elif days <= 7:
                return f"Через {days} {self._pluralize_days(days)}"
            elif weeks == 1:
                return "Через неделю"
            elif weeks <= 4:
                return f"Через {weeks} {self._pluralize_weeks(weeks)}"
            elif months <= 3:
                return f"Через {months} {self._pluralize_months(months)}"
            else:
                return self._format_date(entry_date)
        
        # Прошлое время
        if is_past:
            # Вчера и позавчера
            if days == 1:
                return "Вчера"
            elif days == 2:
                return "Позавчера"
            
            # На этой неделе
            elif days <= 7:
                # Проверяем, была ли эта дата на этой неделе
                entry_week = entry_date.isocalendar()[1]
                reference_week = reference_date.isocalendar()[1]
                entry_year = entry_date.isocalendar()[0]
                reference_year = reference_date.isocalendar()[0]
                
                if entry_week == reference_week and entry_year == reference_year:
                    # На этой неделе - используем день недели в винительном падеже
                    return f"В {self.weekday_names_accusative[entry_date.weekday()]}"
                else:
                    # Более недели назад
                    return f"{days} {self._pluralize_days_genitive(days)} назад"
            
            # На прошлой неделе
            elif days <= 14:
                return f"На прошлой неделе, {self._format_date_short(entry_date)}"
            
            # В прошлом месяце
            elif months == 1:
                return f"В прошлом месяце, {self._format_date_short(entry_date)}"
            
            # Несколько месяцев назад
            elif months <= 12:
                return f"{months} {self._pluralize_months_genitive(months)} назад, {self._format_date_short(entry_date)}"
            
            # Более года назад
            elif years == 1:
                return f"В прошлом году, {self._format_date_short(entry_date)}"
            else:
                return f"{years} {self._pluralize_years_genitive(years)} назад, {self._format_date_short(entry_date)}"
        
        return ""
    
    def _format_date(self, dt: datetime) -> str:
        """Форматирует дату в формате 'DD месяца YYYY'"""
        day = dt.day
        month_name = self.month_names[dt.month]
        year = dt.year
        return f"{day} {month_name} {year}"
    
    def _format_date_short(self, dt: datetime) -> str:
        """Форматирует дату в формате 'DD месяца'"""
        day = dt.day
        month_name = self.month_names[dt.month]
        return f"{day} {month_name}"
    
    def _pluralize_days(self, count: int) -> str:
        """Склоняет 'день' в зависимости от числа"""
        if count == 1:
            return "день"
        elif 2 <= count <= 4:
            return "дня"
        else:
            return "дней"
    
    def _pluralize_days_genitive(self, count: int) -> str:
        """Склоняет 'день' в родительном падеже"""
        if count == 1:
            return "день"
        elif 2 <= count <= 4:
            return "дня"
        else:
            return "дней"
    
    def _pluralize_weeks(self, count: int) -> str:
        """Склоняет 'неделя' в зависимости от числа"""
        if count == 1:
            return "неделю"
        elif 2 <= count <= 4:
            return "недели"
        else:
            return "недель"
    
    def _pluralize_weeks_genitive(self, count: int) -> str:
        """Склоняет 'неделя' в родительном падеже"""
        if count == 1:
            return "неделю"
        elif 2 <= count <= 4:
            return "недели"
        else:
            return "недель"
    
    def _pluralize_months(self, count: int) -> str:
        """Склоняет 'месяц' в зависимости от числа"""
        if count == 1:
            return "месяц"
        elif 2 <= count <= 4:
            return "месяца"
        else:
            return "месяцев"
    
    def _pluralize_months_genitive(self, count: int) -> str:
        """Склоняет 'месяц' в родительном падеже"""
        if count == 1:
            return "месяц"
        elif 2 <= count <= 4:
            return "месяца"
        else:
            return "месяцев"
    
    def _pluralize_years_genitive(self, count: int) -> str:
        """Склоняет 'год' в родительном падеже"""
        if 2 <= count <= 4 or (count >= 22 and count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]):
            return "года"
        elif count == 1 or (count >= 21 and count % 10 == 1 and count % 100 != 11):
            return "год"
        else:
            return "лет"
    
    def format_entries_with_dates(self, entries: List[Dict], reference_date: datetime = None) -> List[Tuple[Dict, str]]:
        """
        Форматирует список записей с человечными датами
        
        Returns:
            List of tuples (entry, formatted_date)
        """
        return [(entry, self.format_entry_date(entry, reference_date)) for entry in entries]


# Пример использования
if __name__ == "__main__":
    formatter = SmartDateFormatter()
    
    # Текущая дата
    now = datetime.now()
    
    # Тестовые записи
    test_entries = [
        # Сегодня
        {
            'id': 1,
            'metadata': '{"parsed_date": "' + now.strftime('%Y-%m-%d %H:%M:%S') + '"}',
            'original_text': 'Встретил Дениса'
        },
        # Вчера
        {
            'id': 2,
            'metadata': '{"parsed_date": "' + (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S') + '"}',
            'original_text': 'Вес 85 кг'
        },
        # На прошлой неделе
        {
            'id': 3,
            'metadata': '{"parsed_date": "' + (now - timedelta(days=8)).strftime('%Y-%m-%d %H:%M:%S') + '"}',
            'original_text': 'Встреча с Денисом'
        },
        # 2 месяца назад
        {
            'id': 4,
            'metadata': '{"parsed_date": "' + (now - timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S') + '"}',
            'original_text': 'Купил машину'
        },
        # Через 2 дня (будущее)
        {
            'id': 5,
            'metadata': '{"parsed_date": "' + (now + timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S') + '"}',
            'original_text': 'Встреча с Георгием'
        }
    ]
    
    print("🧪 Тестирование форматтера дат:")
    print("=" * 80)
    
    for entry in test_entries:
        formatted_date = formatter.format_entry_date(entry, now)
        print(f"\n📝 Запись: {entry['original_text']}")
        print(f"📅 Дата записи: {entry['metadata']}")
        print(f"💬 Человечное выражение: {formatted_date}")
        if formatted_date:
            print(f"✨ Полный ответ: '{formatted_date} {entry['original_text']}'")

