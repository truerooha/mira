"""
Система категоризации и извлечения сущностей
Проект "Второй мозг" - персональный голосовой интеллект
"""

import re
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CategorizationEngine:
    """Движок категоризации для извлечения сущностей из текста"""
    
    def __init__(self):
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict:
        """Загружает шаблоны для категоризации"""
        return {
            # Шаблоны для людей
            "person_info": {
                "patterns": [
                    r"(.+?)\s+(?:родился|родилась)\s+(\d{1,2}\s+\w+)",
                    r"(.+?)\s+(?:день рождения|др)\s+(\d{1,2}\s+\w+)",
                    r"(.+?)\s+(?:имя|зовут)\s+(.+)",
                    r"(?:встретил|встретила|познакомился|познакомилась)\s+([а-яё]+)",
                    r"([а-яё]+)\s+(?:мой|моя)\s+(?:друг|подруга|знакомый|знакомая)",
                ],
                "entity_type": "person",
                "tags": ["#люди", "#события"],
                "extract_name": True
            },
            
            # Шаблоны для автомобилей и обслуживания
            "car_maintenance": {
                "patterns": [
                    r"(?:поменял|заменил|сделал)\s+(?:масло|фильтр|тормоза|покрышки)\s+(?:в|на)\s+([а-яё\s]+?)(?:\s|$)",
                    r"(?:обслуживание|ремонт|диагностика)\s+([а-яё\s]+?)(?:\s|$)",
                    r"([а-яё\s]+?)\s+(?:нужно|надо)\s+(?:через|через)\s+(\d+)\s*(?:км|тысяч|тыс)",
                    r"([а-яё\s]+?)\s+(?:пробег|километраж)\s+(\d+)",
                ],
                "entity_type": "object",
                "tags": ["#авто", "#обслуживание"],
                "extract_name": True
            },
            
            # Шаблоны для напоминаний
            "reminders": {
                "patterns": [
                    r"(?:напомни|не забудь|надо|нужно)\s+(.+?)(?:\s|$)",
                    r"(.+?)\s+(?:завтра|послезавтра|через неделю|через месяц)",
                    r"(.+?)\s+(?:в|на)\s+(\d{1,2}:\d{2})",
                    r"(.+?)\s+(?:в|на)\s+(?:понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)",
                ],
                "entity_type": "reminder",
                "tags": ["#напоминания", "#задачи"],
                "extract_name": False
            },
            
            # Шаблоны для мест
            "places": {
                "patterns": [
                    r"(?:был|была|еду|еду|иду|иду)\s+(?:в|на)\s+(.+)",
                    r"(?:встреча|встречаемся)\s+(?:в|на)\s+(.+)",
                    r"(.+?)\s+(?:ресторан|кафе|магазин|офис|дом|квартира)",
                ],
                "entity_type": "place",
                "tags": ["#места", "#встречи"],
                "extract_name": True
            },
            
            # Шаблоны для событий
            "events": {
                "patterns": [
                    r"(?:конференция|семинар|встреча|совещание|праздник|день рождения)\s+(.+)",
                    r"(.+?)\s+(?:завтра|послезавтра|в понедельник|на выходных)",
                    r"(?:планирую|планируем|собираемся)\s+(.+)",
                ],
                "entity_type": "event",
                "tags": ["#события", "#планы"],
                "extract_name": True
            },
            
            # Шаблоны для покупок
            "shopping": {
                "patterns": [
                    r"(?:купить|приобрести|заказать)\s+(.+)",
                    r"(.+?)\s+(?:в магазине|онлайн|в интернете)",
                    r"(?:нужно|надо)\s+(.+)",
                ],
                "entity_type": "task",
                "tags": ["#покупки", "#задачи"],
                "extract_name": True
            }
        }
    
    def extract_entities(self, text: str) -> Dict:
        """Извлекает сущности из текста на основе шаблонов"""
        entities = []
        tags = set()
        reminders = []
        
        text_lower = text.lower()
        
        for template_name, template in self.templates.items():
            for pattern in template["patterns"]:
                matches = re.finditer(pattern, text_lower, re.IGNORECASE)
                
                for match in matches:
                    if template["extract_name"]:
                        # Извлекаем имя сущности из группы и нормализуем в нижний регистр
                        entity_name = match.group(1).strip().lower()
                        if len(match.groups()) > 1:
                            # Если есть дополнительная информация
                            additional_info = match.group(2).strip().lower()
                            entity_name = f"{entity_name} {additional_info}"
                    else:
                        # Для напоминаний берем весь текст и нормализуем в нижний регистр
                        entity_name = match.group(0).strip().lower()
                    
                    # Создаем сущность
                    entity = {
                        "name": entity_name,
                        "type": template["entity_type"],
                        "template": template_name,
                        "confidence": 0.9,  # Высокая уверенность для шаблонов
                        "context": text
                    }
                    
                    entities.append(entity)
                    
                    # Добавляем теги
                    tags.update(template["tags"])
                    
                    # Специальная обработка для напоминаний
                    if template_name == "reminders":
                        reminders.append({
                            "text": entity_name,
                            "template": template_name,
                            "original_text": text
                        })
        
        return {
            "entities": entities,
            "tags": list(tags),
            "reminders": reminders,
            "confidence": 0.8 if entities else 0.0
        }
    
    def extract_temporal_info(self, text: str) -> Optional[Dict]:
        """Извлекает временную информацию из текста"""
        temporal_patterns = {
            "today": r"(?:сегодня|сейчас)",
            "tomorrow": r"(?:завтра)",
            "next_week": r"(?:через неделю|на следующей неделе)",
            "next_month": r"(?:через месяц|в следующем месяце)",
            "specific_date": r"(\d{1,2})\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)",
            "specific_time": r"(\d{1,2}):(\d{2})",
            "days_from_now": r"через\s+(\d+)\s+(?:дней?|дня)",
            "km_reminder": r"через\s+(\d+)\s*(?:км|тысяч|тыс)",
        }
        
        for pattern_name, pattern in temporal_patterns.items():
            match = re.search(pattern, text.lower())
            if match:
                return {
                    "type": pattern_name,
                    "match": match.group(0),
                    "groups": match.groups()
                }
        
        return None
    
    def categorize_text(self, text: str) -> Dict:
        """Основной метод категоризации текста"""
        result = {
            "original_text": text,
            "entities": [],
            "tags": [],
            "reminders": [],
            "temporal_info": None,
            "category": "general",
            "confidence": 0.0
        }
        
        # Извлекаем сущности
        extraction_result = self.extract_entities(text)
        result.update(extraction_result)
        
        # Извлекаем временную информацию
        temporal_info = self.extract_temporal_info(text)
        result["temporal_info"] = temporal_info
        
        # Определяем основную категорию
        if result["entities"]:
            # Берем категорию самой уверенной сущности
            best_entity = max(result["entities"], key=lambda x: x["confidence"])
            result["category"] = best_entity["template"]
            result["confidence"] = best_entity["confidence"]
        
        return result

# Пример использования
if __name__ == "__main__":
    engine = CategorizationEngine()
    
    test_texts = [
        "Поменял масло в машине, надо снова через 3000 км",
        "Встретил Васю в автосервисе, у него новая Honda Civic",
        "Напомни позвонить маме завтра",
        "У Руслана день рождения 12 ноября",
        "Нужно купить молоко завтра"
    ]
    
    for text in test_texts:
        print(f"\nТекст: {text}")
        result = engine.categorize_text(text)
        print(f"Категория: {result['category']}")
        print(f"Сущности: {[e['name'] for e in result['entities']]}")
        print(f"Теги: {result['tags']}")
        if result['reminders']:
            print(f"Напоминания: {[r['text'] for r in result['reminders']]}")
