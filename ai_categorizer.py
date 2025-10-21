"""
AI агент для умной категоризации с использованием DeepSeek API
Проект "Второй мозг" - персональный голосовой интеллект
"""

import json
import asyncio
from typing import Dict, List, Optional
import openai
from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)

class AICategorizer:
    """AI агент для умной категоризации текста"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        # Схема категорий - "полки" для данных
        self.categories_schema = {
            "people": {
                "description": "Люди, знакомые, друзья, коллеги",
                "subcategories": ["friends", "family", "colleagues", "acquaintances"],
                "examples": ["встретил Васю", "у Руслана день рождения", "познакомился с Анной"]
            },
            "places": {
                "description": "Места, локации, адреса",
                "subcategories": ["restaurants", "offices", "homes", "shops", "services"],
                "examples": ["в ресторане", "в офисе", "дома", "в магазине", "в автосервисе"]
            },
            "objects": {
                "description": "Объекты, вещи, предметы",
                "subcategories": ["cars", "electronics", "clothes", "books", "tools"],
                "examples": ["машина", "телефон", "одежда", "книга", "инструменты"]
            },
            "events": {
                "description": "События, встречи, праздники",
                "subcategories": ["meetings", "birthdays", "holidays", "conferences", "appointments"],
                "examples": ["встреча завтра", "день рождения", "конференция", "прием у врача"]
            },
            "tasks": {
                "description": "Задачи, дела, покупки",
                "subcategories": ["shopping", "maintenance", "work", "personal", "health"],
                "examples": ["купить молоко", "поменять масло", "сделать отчет", "записаться к врачу"]
            },
            "reminders": {
                "description": "Напоминания, важные даты",
                "subcategories": ["time_based", "condition_based", "recurring", "one_time"],
                "examples": ["завтра", "через неделю", "через 3000 км", "каждый месяц"]
            },
            "health": {
                "description": "Здоровье, медицина, самочувствие",
                "subcategories": ["symptoms", "medications", "appointments", "fitness", "diet"],
                "examples": ["болит голова", "принял таблетку", "запись к врачу", "тренировка"]
            },
            "work": {
                "description": "Работа, карьера, проекты",
                "subcategories": ["projects", "meetings", "deadlines", "colleagues", "learning"],
                "examples": ["проект", "совещание", "дедлайн", "коллега", "обучение"]
            },
            "finance": {
                "description": "Финансы, деньги, покупки",
                "subcategories": ["income", "expenses", "investments", "bills", "budget"],
                "examples": ["зарплата", "траты", "инвестиции", "счета", "бюджет"]
            },
            "ideas": {
                "description": "Идеи, мысли, заметки",
                "subcategories": ["ideas", "thoughts", "notes"],
                "examples": ["идея", "мысль", "заметка", "размышление"]
            },
            "projects": {
                "description": "Проекты, задачи, цели",
                "subcategories": ["projects", "tasks", "goals"],
                "examples": ["проект", "задача", "цель"]
            },
            "goals": {
                "description": "Цели, задачи, цели",
                "subcategories": ["goals", "tasks", "goals"],
                "examples": ["цель", "задача", "цель"]
            },
            "unclassified": {
                "description": "Неразобранное - то, что не подходит под другие категории",
                "subcategories": ["misc", "ideas", "thoughts", "notes"],
                "examples": ["идея", "мысль", "заметка", "размышление"]
            }
        }
    
    def _create_system_prompt(self) -> str:
        """Создает системный промпт для AI агента"""
        schema_json = json.dumps(self.categories_schema, ensure_ascii=False, indent=2)
        
        return f"""Ты - умный ассистент для категоризации личных записей. Твоя задача - анализировать текст и извлекать из него структурированную информацию.

СХЕМА КАТЕГОРИЙ (твои "полки"):
{schema_json}

ИНСТРУКЦИИ:
1. Проанализируй текст и определи, к каким категориям он относится
2. Извлеки все сущности (люди, места, объекты, события)
3. Определи теги на основе категорий
4. Если есть временная информация - выдели её
5. Если текст не подходит ни под одну категорию - используй "unclassified"

ФОРМАТ ОТВЕТА (строго JSON):
{{
    "categories": ["category1", "category2"],
    "entities": [
        {{
            "name": "название сущности",
            "type": "person|place|object|event|task|reminder|health|work|finance|unclassified",
            "subcategory": "подкатегория",
            "confidence": 0.9
        }}
    ],
    "tags": ["#тег1", "#тег2"],
    "temporal_info": {{
        "type": "date|time|duration|condition",
        "value": "конкретное значение",
        "confidence": 0.8
    }},
    "reminders": [
        {{
            "text": "текст напоминания",
            "trigger": "условие срабатывания"
        }}
    ],
    "confidence": 0.9
}}

ВАЖНО:
- Отвечай ТОЛЬКО валидным JSON
- Не добавляй никакого текста кроме JSON
- Будь точным в извлечении сущностей
- Используй русские названия для тегов
- Если не уверен - снижай confidence"""

    async def categorize_text(self, text: str) -> Dict:
        """Категоризирует текст с помощью AI"""
        try:
            system_prompt = self._create_system_prompt()
            
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Проанализируй этот текст: {text}"}
                ],
                temperature=0.1,  # Низкая температура для стабильности
                max_tokens=1000
            )
            
            # Парсим JSON ответ
            content = response.choices[0].message.content.strip()
            
            # Убираем возможные markdown блоки
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content)
            
            # Валидируем результат
            return self._validate_result(result, text)
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON от AI: {e}")
            return self._fallback_categorization(text)
        except Exception as e:
            logger.error(f"Ошибка AI категоризации: {e}")
            return self._fallback_categorization(text)
    
    def _validate_result(self, result: Dict, original_text: str) -> Dict:
        """Валидирует и дополняет результат AI"""
        # Убеждаемся, что все обязательные поля есть
        if "entities" not in result:
            result["entities"] = []
        if "tags" not in result:
            result["tags"] = []
        if "categories" not in result:
            result["categories"] = ["unclassified"]
        if "confidence" not in result:
            result["confidence"] = 0.5
        
        # Добавляем контекст к сущностям
        for entity in result["entities"]:
            entity["context"] = original_text
            if "confidence" not in entity:
                entity["confidence"] = 0.7
        
        return result
    
    def _fallback_categorization(self, text: str) -> Dict:
        """Fallback категоризация при ошибке AI"""
        return {
            "categories": ["unclassified"],
            "entities": [],
            "tags": ["#неразобранное"],
            "temporal_info": None,
            "reminders": [],
            "confidence": 0.1,
            "fallback": True
        }

# Пример использования
async def test_ai_categorizer():
    """Тестируем AI категоризатор"""
    # Замените на ваш API ключ DeepSeek
    api_key = "your-deepseek-api-key"
    
    categorizer = AICategorizer(api_key)
    
    test_texts = [
        "Поменял масло в машине, надо снова через 3000 км",
        "Встретил Васю в автосервисе, у него новая Honda Civic",
        "У Руслана день рождения 12 ноября",
        "Напомни купить молоко завтра",
        "Болит голова, принял таблетку"
    ]
    
    for text in test_texts:
        print(f"\nТекст: {text}")
        result = await categorizer.categorize_text(text)
        print(f"Категории: {result['categories']}")
        print(f"Сущности: {[e['name'] for e in result['entities']]}")
        print(f"Теги: {result['tags']}")
        if result.get('temporal_info'):
            print(f"Время: {result['temporal_info']}")

if __name__ == "__main__":
    asyncio.run(test_ai_categorizer())
