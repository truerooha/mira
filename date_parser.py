#!/usr/bin/env python3
"""
Умный парсер дат для обработки относительных временных выражений
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class SmartDateParser:
    """Умный парсер дат для обработки относительных временных выражений"""
    
    def __init__(self):
        # Паттерны для распознавания относительных дат
        self.relative_patterns = {
            # Сегодня
            'сегодня': r'\b(сегодня|сейчас|только что)\b',
            'вчера': r'\b(вчера|накануне)\b',
            'позавчера': r'\b(позавчера|два дня назад)\b',
            
            # Дни недели
            'понедельник': r'\b(в понедельник|понедельник)\b',
            'вторник': r'\b(во вторник|вторник)\b',
            'среда': r'\b(в среду|среда)\b',
            'четверг': r'\b(в четверг|четверг)\b',
            'пятница': r'\b(в пятницу|пятница)\b',
            'суббота': r'\b(в субботу|суббота)\b',
            'воскресенье': r'\b(в воскресенье|воскресенье)\b',
            
            # Недели
            'на этой неделе': r'\b(на этой неделе|этой неделей)\b',
            'на прошлой неделе': r'\b(на прошлой неделе|прошлой неделей)\b',
            'на позапрошлой неделе': r'\b(на позапрошлой неделе|позапрошлой неделей)\b',
            
            # Месяцы
            'в этом месяце': r'\b(в этом месяце|этим месяцем)\b',
            'в прошлом месяце': r'\b(в прошлом месяце|прошлым месяцем)\b',
            
            # Годы
            'в этом году': r'\b(в этом году|этим годом)\b',
            'в прошлом году': r'\b(в прошлом году|прошлым годом)\b',
            
            # Количественные выражения
            'дней назад': r'\b(\d+)\s*(дней?|дня?)\s*назад\b',
            'недель назад': r'\b(\d+)\s*(недель?|недели?)\s*назад\b',
            'месяцев назад': r'\b(\d+)\s*(месяцев?|месяца?)\s*назад\b',
            'лет назад': r'\b(\d+)\s*(лет?|года?)\s*назад\b',
            
            # Время дня
            'утром': r'\b(утром|с утра)\b',
            'днем': r'\b(днем|в обед)\b',
            'вечером': r'\b(вечером|с вечера)\b',
            'ночью': r'\b(ночью|с ночи)\b',
        }
        
        # Маппинг дней недели
        self.weekday_names = {
            'понедельник': 0, 'вторник': 1, 'среда': 2, 'четверг': 3,
            'пятница': 4, 'суббота': 5, 'воскресенье': 6
        }
        
        # Маппинг месяцев
        self.month_names = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }
    
    def parse_text(self, text: str) -> Dict[str, any]:
        """
        Парсит текст и извлекает временную информацию
        
        Returns:
            Dict с полями:
            - original_text: исходный текст
            - processed_text: текст с замененными датами
            - datetime: объект datetime если дата определена
            - date_string: строка даты для записи в БД
            - time_info: информация о времени дня
            - confidence: уверенность в распознавании (0-1)
        """
        result = {
            'original_text': text,
            'processed_text': text,
            'datetime': None,
            'date_string': None,
            'time_info': None,
            'confidence': 0.0
        }
        
        # Ищем относительные даты
        relative_date = self._find_relative_date(text)
        if relative_date:
            result.update(relative_date)
            result['confidence'] = 0.9
            return result
        
        # Ищем абсолютные даты
        absolute_date = self._find_absolute_date(text)
        if absolute_date:
            result.update(absolute_date)
            result['confidence'] = 0.8
            return result
        
        # Ищем время дня
        time_info = self._find_time_of_day(text)
        if time_info:
            result['time_info'] = time_info
            result['confidence'] = 0.3
        
        return result
    
    def _find_relative_date(self, text: str) -> Optional[Dict]:
        """Ищет относительные даты в тексте"""
        text_lower = text.lower()
        
        # Сегодня
        if re.search(self.relative_patterns['сегодня'], text_lower):
            today = datetime.now()
            return {
                'datetime': today,
                'date_string': today.strftime('%Y-%m-%d %H:%M:%S'),
                'processed_text': re.sub(self.relative_patterns['сегодня'], 
                                       today.strftime('%d.%m.%Y'), text_lower, flags=re.IGNORECASE)
            }
        
        # Вчера
        if re.search(self.relative_patterns['вчера'], text_lower):
            yesterday = datetime.now() - timedelta(days=1)
            return {
                'datetime': yesterday,
                'date_string': yesterday.strftime('%Y-%m-%d %H:%M:%S'),
                'processed_text': re.sub(self.relative_patterns['вчера'], 
                                       yesterday.strftime('%d.%m.%Y'), text_lower, flags=re.IGNORECASE)
            }
        
        # Позавчера
        if re.search(self.relative_patterns['позавчера'], text_lower):
            day_before_yesterday = datetime.now() - timedelta(days=2)
            return {
                'datetime': day_before_yesterday,
                'date_string': day_before_yesterday.strftime('%Y-%m-%d %H:%M:%S'),
                'processed_text': re.sub(self.relative_patterns['позавчера'], 
                                       day_before_yesterday.strftime('%d.%m.%Y'), text_lower, flags=re.IGNORECASE)
            }
        
        # Дни недели
        for day_name, day_num in self.weekday_names.items():
            if re.search(self.relative_patterns[day_name], text_lower):
                target_date = self._get_weekday_date(day_num)
                return {
                    'datetime': target_date,
                    'date_string': target_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'processed_text': re.sub(self.relative_patterns[day_name], 
                                           target_date.strftime('%d.%m.%Y'), text_lower, flags=re.IGNORECASE)
                }
        
        # Количественные выражения
        # N дней назад
        days_match = re.search(self.relative_patterns['дней назад'], text_lower)
        if days_match:
            days = int(days_match.group(1))
            target_date = datetime.now() - timedelta(days=days)
            return {
                'datetime': target_date,
                'date_string': target_date.strftime('%Y-%m-%d %H:%M:%S'),
                'processed_text': re.sub(self.relative_patterns['дней назад'], 
                                       target_date.strftime('%d.%m.%Y'), text_lower, flags=re.IGNORECASE)
            }
        
        # N недель назад
        weeks_match = re.search(self.relative_patterns['недель назад'], text_lower)
        if weeks_match:
            weeks = int(weeks_match.group(1))
            target_date = datetime.now() - timedelta(weeks=weeks)
            return {
                'datetime': target_date,
                'date_string': target_date.strftime('%Y-%m-%d %H:%M:%S'),
                'processed_text': re.sub(self.relative_patterns['недель назад'], 
                                       target_date.strftime('%d.%m.%Y'), text_lower, flags=re.IGNORECASE)
            }
        
        # N месяцев назад
        months_match = re.search(self.relative_patterns['месяцев назад'], text_lower)
        if months_match:
            months = int(months_match.group(1))
            target_date = datetime.now() - timedelta(days=months * 30)  # Приблизительно
            return {
                'datetime': target_date,
                'date_string': target_date.strftime('%Y-%m-%d %H:%M:%S'),
                'processed_text': re.sub(self.relative_patterns['месяцев назад'], 
                                       target_date.strftime('%d.%m.%Y'), text_lower, flags=re.IGNORECASE)
            }
        
        return None
    
    def _find_absolute_date(self, text: str) -> Optional[Dict]:
        """Ищет абсолютные даты в тексте"""
        text_lower = text.lower()
        
        # Паттерны для абсолютных дат
        patterns = [
            # "15 января 2024"
            r'\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})\b',
            # "15.01.2024" или "15/01/2024"
            r'\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b',
            # "2024-01-15"
            r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    if 'января' in pattern:  # Месяц словом
                        day, month_name, year = match.groups()
                        month = self.month_names[month_name]
                        target_date = datetime(int(year), month, int(day))
                    else:  # Числовой формат
                        if pattern.endswith(r'\b'):  # YYYY-MM-DD
                            year, month, day = match.groups()
                        else:  # DD.MM.YYYY или DD/MM/YYYY
                            day, month, year = match.groups()
                        target_date = datetime(int(year), int(month), int(day))
                    
                    return {
                        'datetime': target_date,
                        'date_string': target_date.strftime('%Y-%m-%d %H:%M:%S'),
                        'processed_text': re.sub(pattern, target_date.strftime('%d.%m.%Y'), text_lower, flags=re.IGNORECASE)
                    }
                except ValueError:
                    continue
        
        return None
    
    def _find_time_of_day(self, text: str) -> Optional[str]:
        """Ищет информацию о времени дня"""
        text_lower = text.lower()
        
        for time_name, pattern in self.relative_patterns.items():
            if time_name in ['утром', 'днем', 'вечером', 'ночью']:
                if re.search(pattern, text_lower):
                    return time_name
        
        return None
    
    def _get_weekday_date(self, target_weekday: int) -> datetime:
        """Получает дату для указанного дня недели (0=понедельник, 6=воскресенье)"""
        today = datetime.now()
        current_weekday = today.weekday()
        
        # Вычисляем разность дней
        days_ahead = target_weekday - current_weekday
        
        # Если день уже прошел на этой неделе, берем следующий
        if days_ahead <= 0:
            days_ahead += 7
        
        return today + timedelta(days=days_ahead)
    
    def format_for_display(self, result: Dict) -> str:
        """Форматирует результат для отображения пользователю"""
        if result['datetime']:
            date_str = result['datetime'].strftime('%d.%m.%Y')
            time_info = f" ({result['time_info']})" if result['time_info'] else ""
            return f"📅 {date_str}{time_info}"
        return "📅 Дата не определена"

# Пример использования
if __name__ == "__main__":
    parser = SmartDateParser()
    
    test_texts = [
        "Сегодня я пошёл на бокс",
        "Позавчера мне посоветовали фильм Аватар",
        "Вчера утром был в магазине",
        "В понедельник встреча с клиентом",
        "3 дня назад купил новую машину",
        "2 недели назад был в отпуске",
        "15 января 2024 года важная встреча"
    ]
    
    print("🧪 Тестирование парсера дат:")
    print("=" * 50)
    
    for text in test_texts:
        result = parser.parse_text(text)
        print(f"\n📝 Исходный текст: {text}")
        print(f"📅 Результат: {parser.format_for_display(result)}")
        print(f"🔍 Обработанный текст: {result['processed_text']}")
        print(f"💾 Дата для БД: {result['date_string']}")
        print(f"🎯 Уверенность: {result['confidence']}")
