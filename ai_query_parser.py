"""
AI парсер запросов для умного поиска
Проект "Второй мозг" - персональный голосовой интеллект
"""

import json
import asyncio
from typing import Dict, List, Optional, Tuple
import openai
from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)

class AIQueryParser:
    """AI парсер для умного анализа запросов пользователя"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        # Схема типов сущностей для AI
        self.entity_types_schema = {
            "person": {
                "description": "Люди, знакомые, друзья, коллеги",
                "examples": ["Вася", "Анна", "коллега", "друг", "врач", "клиент"],
                "synonyms": ["человек", "личность", "знакомый", "приятель"]
            },
            "place": {
                "description": "Места, локации, адреса",
                "examples": ["офис", "дом", "магазин", "ресторан", "автосервис"],
                "synonyms": ["место", "локация", "адрес", "точка", "площадка"]
            },
            "object": {
                "description": "Объекты, вещи, предметы",
                "examples": ["машина", "телефон", "книга", "молоко", "документ"],
                "synonyms": ["вещь", "предмет", "объект", "товар", "изделие"]
            },
            "event": {
                "description": "События, встречи, мероприятия",
                "examples": ["встреча", "конференция", "праздник", "событие"],
                "synonyms": ["мероприятие", "событие", "акция", "действие"]
            },
            "task": {
                "description": "Задачи, дела, покупки",
                "examples": ["покупка", "задача", "дело", "работа", "проект"],
                "synonyms": ["задание", "поручение", "обязанность", "функция"]
            },
            "reminder": {
                "description": "Напоминания, важные даты",
                "examples": ["напоминание", "напоминалка", "дедлайн", "срок"],
                "synonyms": ["уведомление", "предупреждение", "сигнал", "алерт"]
            },
            "work": {
                "description": "Работа, карьера, профессиональная деятельность",
                "examples": ["работа", "карьера", "профессия", "должность"],
                "synonyms": ["труд", "деятельность", "занятие", "служба"]
            },
            "health": {
                "description": "Здоровье, медицина, самочувствие",
                "examples": ["здоровье", "болезнь", "лечение", "врач"],
                "synonyms": ["медицина", "самочувствие", "состояние", "терапия"]
            },
            "finance": {
                "description": "Финансы, деньги, покупки",
                "examples": ["деньги", "покупка", "трата", "бюджет"],
                "synonyms": ["финансы", "средства", "капитал", "ресурсы"]
            }
        }
    
    def _create_system_prompt(self) -> str:
        """Создает системный промпт для AI парсера"""
        schema_json = json.dumps(self.entity_types_schema, ensure_ascii=False, indent=2)
        
        return f"""Ты - умный парсер запросов для персонального ассистента. Твоя задача - анализировать запросы пользователя и извлекать структурированную информацию для поиска.

СХЕМА ТИПОВ СУЩНОСТЕЙ:
{schema_json}

ИНСТРУКЦИИ:
1. Проанализируй запрос пользователя
2. Извлеки ключевые слова и определи их типы
3. Нормализуй слова (приведи к базовой форме)
4. Найди синонимы и связанные понятия
5. Определи намерение пользователя
6. Предложи варианты поиска

ФОРМАТ ОТВЕТА (строго JSON):
{{
    "intent": "search|statistics|insights|reminders",
    "main_topic": "основная тема запроса",
    "entities": [
        {{
            "original": "оригинальное слово",
            "normalized": "нормализованная форма",
            "type": "person|place|object|event|task|reminder|work|health|finance",
            "confidence": 0.9,
            "synonyms": ["синоним1", "синоним2"],
            "context": "контекст использования"
        }}
    ],
    "search_keywords": ["ключевое_слово1", "ключевое_слово2"],
    "search_strategy": "exact|fuzzy|semantic|contextual",
    "suggestions": ["предложение1", "предложение2"],
    "confidence": 0.8
}}

ВАЖНО:
- Отвечай ТОЛЬКО валидным JSON
- Не добавляй никакого текста кроме JSON
- Будь точным в определении типов
- Используй русский язык
- Нормализуй слова правильно (васе → вася, машине → машина)
- Находи синонимы (авто → машина, автомобиль)"""
    
    async def parse_query(self, query: str) -> Dict:
        """Парсит запрос пользователя с помощью AI"""
        try:
            system_prompt = self._create_system_prompt()
            
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Проанализируй этот запрос: {query}"}
                ],
                temperature=0.1,  # Низкая температура для стабильности
                max_tokens=800
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
            return self._validate_result(result, query)
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON от AI: {e}")
            return self._fallback_parsing(query)
        except Exception as e:
            logger.error(f"Ошибка AI парсинга: {e}")
            return self._fallback_parsing(query)
    
    def _validate_result(self, result: Dict, original_query: str) -> Dict:
        """Валидирует и дополняет результат AI"""
        # Убеждаемся, что все обязательные поля есть
        if "intent" not in result:
            result["intent"] = "search"
        
        if "main_topic" not in result:
            result["main_topic"] = original_query
        
        if "entities" not in result:
            result["entities"] = []
        
        if "search_keywords" not in result:
            result["search_keywords"] = []
        
        if "search_strategy" not in result:
            result["search_strategy"] = "fuzzy"
        
        if "suggestions" not in result:
            result["suggestions"] = []
        
        if "confidence" not in result:
            result["confidence"] = 0.7
        
        # Валидируем сущности
        for entity in result["entities"]:
            if "original" not in entity:
                entity["original"] = ""
            if "normalized" not in entity:
                entity["normalized"] = entity.get("original", "")
            if "type" not in entity:
                entity["type"] = "object"
            if "confidence" not in entity:
                entity["confidence"] = 0.7
            if "synonyms" not in entity:
                entity["synonyms"] = []
            if "context" not in entity:
                entity["context"] = original_query
        
        return result
    
    def _fallback_parsing(self, query: str) -> Dict:
        """Fallback парсинг при ошибке AI"""
        # Простая нормализация
        words = query.lower().split()
        normalized_words = []
        
        for word in words:
            if len(word) > 2:
                # Простая нормализация
                if word.endswith('е') and len(word) > 3:
                    normalized = word[:-1] + 'а'  # васе → вася
                elif word.endswith('у') and len(word) > 3:
                    normalized = word[:-1] + 'а'  # машину → машина
                else:
                    normalized = word
                normalized_words.append(normalized)
        
        return {
            "intent": "search",
            "main_topic": query,
            "entities": [
                {
                    "original": word,
                    "normalized": word,
                    "type": "object",
                    "confidence": 0.5,
                    "synonyms": [],
                    "context": query
                } for word in normalized_words
            ],
            "search_keywords": normalized_words,
            "search_strategy": "fuzzy",
            "suggestions": [],
            "confidence": 0.3,
            "fallback": True
        }
    
    def extract_search_terms(self, parsed_result: Dict) -> Dict[str, List[str]]:
        """Извлекает термины для поиска из результата парсинга"""
        search_terms = {
            'person': [],
            'place': [],
            'object': [],
            'event': [],
            'task': [],
            'reminder': [],
            'work': [],
            'health': [],
            'finance': [],
            'general': []
        }
        
        # Группируем сущности по типам
        for entity in parsed_result.get("entities", []):
            entity_type = entity.get("type", "object")
            normalized = entity.get("normalized", "")
            synonyms = entity.get("synonyms", [])
            
            if entity_type in search_terms:
                search_terms[entity_type].append(normalized)
                # Добавляем синонимы
                search_terms[entity_type].extend(synonyms)
        
        # Добавляем общие ключевые слова
        search_keywords = parsed_result.get("search_keywords", [])
        for keyword in search_keywords:
            if not any(keyword in terms for terms in search_terms.values() if terms != search_terms['general']):
                search_terms['general'].append(keyword)
        
        # Убираем дубликаты
        for entity_type in search_terms:
            search_terms[entity_type] = list(set(search_terms[entity_type]))
        
        return search_terms
    
    def get_search_strategy(self, parsed_result: Dict) -> str:
        """Определяет стратегию поиска"""
        return parsed_result.get("search_strategy", "fuzzy")
    
    def get_intent(self, parsed_result: Dict) -> str:
        """Определяет намерение пользователя"""
        return parsed_result.get("intent", "search")
    
    def get_suggestions(self, parsed_result: Dict) -> List[str]:
        """Получает предложения для пользователя"""
        return parsed_result.get("suggestions", [])

# Пример использования
async def test_ai_parser():
    """Тестируем AI парсер"""
    # Замените на ваш API ключ DeepSeek
    api_key = "your-deepseek-api-key"
    
    parser = AIQueryParser(api_key)
    
    test_queries = [
        "расскажи о Васе",
        "что знаешь о работе",
        "покажи напоминания",
        "где встреча с клиентом",
        "что с автомобилем",
        "расскажи про здоровье",
        "покажи финансы"
    ]
    
    for query in test_queries:
        print(f"\nЗапрос: {query}")
        result = await parser.parse_query(query)
        print(f"Намерение: {result['intent']}")
        print(f"Основная тема: {result['main_topic']}")
        print(f"Сущности: {[e['normalized'] for e in result['entities']]}")
        print(f"Стратегия поиска: {result['search_strategy']}")
        print(f"Уверенность: {result['confidence']}")

if __name__ == "__main__":
    asyncio.run(test_ai_parser())
