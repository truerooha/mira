"""
AI генератор умных ответов для функции "расскажи"
Проект "Второй мозг" - персональный голосовой интеллект
"""

import json
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import openai
from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)

class AIResponseGenerator:
    """AI генератор умных и человечных ответов"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        # Шаблоны для разных типов ответов
        self.response_templates = {
            'found_info': {
                'neutral': [
                    "Найдена информация о {topic}:",
                    "Данные о {topic}:",
                    "Информация о {topic}:",
                    "Результат поиска по {topic}:"
                ]
            },
            'not_found': {
                'neutral': [
                    "Информации о {topic} не найдено.",
                    "Данных о {topic} пока нет.",
                    "Записей о {topic} не обнаружено.",
                    "Информация о {topic} отсутствует."
                ]
            },
            'recent_activity': [
                "Кстати, недавно ты упоминал:",
                "А вот что было недавно:",
                "Кстати, в последнее время:",
                "Недавно ты говорил:"
            ],
            'related_info': [
                "Также связанное с этим:",
                "Еще по теме:",
                "Кстати, есть связанная информация:",
                "Также упоминалось:"
            ]
        }
    
    def _create_system_prompt(self) -> str:
        """Создает системный промпт для генерации ответов"""
        return """Ты - персональный ассистент "Мира". Твоя задача - анализировать найденную информацию и генерировать полезные, информативные ответы.

СТИЛЬ ОБЩЕНИЯ:
- Нейтральный, профессиональный тон
- Короткие, понятные предложения
- Минимум эмодзи (только для структурирования)
- Личное обращение "ты"
- Фактический подход

ПРИНЦИПЫ:
1. Если есть информация - расскажи кратко и по делу
2. Если информации нет - сообщи об этом нейтрально
3. Используй найденные данные для контекста
4. НЕ добавляй фразы типа "Эта информация сохранена в системе"
5. НЕ добавляй рекомендации типа "Рекомендую отслеживать динамику"
6. НЕ предлагай дополнительные действия
7. НЕ указывай количество найденных записей отдельно
8. Отвечай ТОЛЬКО релевантной информацией

ЗАПРЕЩЕНО:
- "Эта информация сохранена в системе"
- "Рекомендую отслеживать динамику"
- "Рекомендую продолжить мониторинг"
- "Советую обратить внимание"
- Любые рекомендации и советы
- Упоминания о системе хранения данных

ОСОБЫЕ СЛУЧАИ:
- Для аналитических запросов (вес, расходы, ремонт) - структурируй ответ
- Для временных запросов - группируй по датам/периодам
- Для поиска локаций - выделяй места
- Извлекай числа, даты, суммы когда возможно

ФОРМАТ ОТВЕТА (строго JSON):
{
    "response": "основной ответ пользователю",
    "tone": "caring|informative|encouraging",
    "has_info": true/false,
    "confidence": 0.8,
    "suggestions": []
}

ВАЖНО:
- Отвечай ТОЛЬКО валидным JSON
- Не добавляй никакого текста кроме JSON
- Будь искренней и заботливой
- Используй русский язык
- Максимум 3-4 предложения в ответе
- suggestions всегда должен быть пустым массивом []"""
    
    def _format_search_data(self, search_results: Dict) -> str:
        """Форматирует результаты поиска для AI"""
        data_summary = []
        
        # Основная информация
        if search_results['entities_found']:
            entities_text = []
            for entity in search_results['entities_found'][:3]:  # Топ-3 сущности
                entities_text.append(f"{entity['name']} ({entity['type']})")
            data_summary.append(f"Найденные сущности: {', '.join(entities_text)}")
        
        if search_results['entries_found']:
            entries_text = []
            for entry in search_results['entries_found'][:3]:  # Топ-3 записи
                # Обрезаем длинный текст
                text = entry['original_text'][:100] + "..." if len(entry['original_text']) > 100 else entry['original_text']
                entries_text.append(f'"{text}"')
            data_summary.append(f"Записи: {'; '.join(entries_text)}")
        
        if search_results['related_entities']:
            related_text = [e['name'] for e in search_results['related_entities'][:2]]
            data_summary.append(f"Связанные сущности: {', '.join(related_text)}")
        
        if search_results['recent_entries']:
            recent_text = []
            for entry in search_results['recent_entries'][:2]:
                text = entry['original_text'][:80] + "..." if len(entry['original_text']) > 80 else entry['original_text']
                recent_text.append(f'"{text}"')
            data_summary.append(f"Недавние записи: {'; '.join(recent_text)}")
        
        return "\n".join(data_summary)
    
    def _extract_topic_from_query(self, query: str) -> str:
        """Извлекает основную тему из запроса"""
        # Убираем служебные слова
        stop_words = {'расскажи', 'о', 'про', 'что', 'знаешь', 'ли', 'покажи', 'есть'}
        words = query.lower().split()
        topic_words = [w for w in words if w not in stop_words and len(w) > 2]
        
        if topic_words:
            return ' '.join(topic_words[:3])  # Первые 3 значимых слова
        return query
    
    def _extract_structured_data(self, search_results: Dict) -> Dict:
        """Извлекает структурированные данные из записей"""
        structured_data = {
            'measurements': [],  # вес: 79кг, дата: май 2023
            'actions': [],       # менял масло, дата: 01.01.2024
            'locations': [],     # где: улица Барбашова
            'amounts': [],       # суммы: 3000руб
            'dates': []          # даты: 01.01.2024
        }
        
        # Простое извлечение из текста записей
        for entry in search_results.get('entries_found', []):
            text = entry.get('original_text', '')
            
            # Ищем измерения (вес, давление и т.д.)
            import re
            weight_match = re.search(r'(\d+)\s*(кг|килограмм)', text, re.IGNORECASE)
            if weight_match:
                structured_data['measurements'].append({
                    'type': 'weight',
                    'value': int(weight_match.group(1)),
                    'unit': 'kg',
                    'text': text
                })
            
            # Ищем суммы
            amount_match = re.search(r'(\d+)\s*(руб|рублей|₽)', text, re.IGNORECASE)
            if amount_match:
                structured_data['amounts'].append({
                    'amount': int(amount_match.group(1)),
                    'currency': 'RUB',
                    'text': text
                })
            
            # Ищем действия
            if any(word in text.lower() for word in ['менял', 'починил', 'ремонтировал', 'купил']):
                structured_data['actions'].append({
                    'text': text,
                    'type': 'maintenance' if any(word in text.lower() for word in ['масло', 'ремонт']) else 'action'
                })
            
            # Ищем локации
            location_words = ['улица', 'в', 'на', 'гараж', 'сервис', 'офис']
            if any(word in text.lower() for word in location_words):
                structured_data['locations'].append({
                    'text': text,
                    'type': 'location'
                })
        
        return structured_data
    
    def _format_structured_data(self, search_results: Dict) -> str:
        """Форматирует структурированные данные для AI"""
        structured_data = self._extract_structured_data(search_results)
        formatted = []
        
        if structured_data['measurements']:
            formatted.append("ИЗМЕРЕНИЯ:")
            for measurement in structured_data['measurements']:
                formatted.append(f"- {measurement['type']}: {measurement['value']}{measurement['unit']}")
        
        if structured_data['actions']:
            formatted.append("ДЕЙСТВИЯ:")
            for action in structured_data['actions']:
                formatted.append(f"- {action['text']}")
        
        if structured_data['amounts']:
            formatted.append("СУММЫ:")
            for amount in structured_data['amounts']:
                formatted.append(f"- {amount['amount']} {amount['currency']}")
        
        if structured_data['locations']:
            formatted.append("ЛОКАЦИИ:")
            for location in structured_data['locations']:
                formatted.append(f"- {location['text']}")
        
        return "\n".join(formatted) if formatted else "Структурированных данных не найдено"
    
    def _format_temporal_analysis(self, search_results: Dict) -> str:
        """Форматирует временной анализ для AI"""
        temporal_analysis = search_results.get('temporal_analysis')
        if not temporal_analysis:
            return "Временной анализ не выполнен"
        
        formatted = []
        formatted.append(f"ТИП АНАЛИЗА: {temporal_analysis.get('type', 'unknown')}")
        
        # Измерения во времени
        measurements = temporal_analysis.get('measurements_over_time', [])
        if measurements:
            formatted.append("ИЗМЕРЕНИЯ ПО ВРЕМЕНИ:")
            for measurement in measurements:
                formatted.append(f"- {measurement['date']}: {measurement['value']}{measurement['unit']}")
        
        # Временная линия действий
        actions = temporal_analysis.get('actions_timeline', [])
        if actions:
            formatted.append("ВРЕМЕННАЯ ЛИНИЯ ДЕЙСТВИЙ:")
            for action in actions:
                formatted.append(f"- {action['date']}: {action['action']}")
        
        # Сводка локаций
        locations = temporal_analysis.get('locations_summary', [])
        if locations:
            formatted.append("НАЙДЕННЫЕ ЛОКАЦИИ:")
            for location in locations:
                formatted.append(f"- {location}")
        
        return "\n".join(formatted) if formatted else "Временных данных не найдено"
    
    async def generate_response(self, query: str, search_results: Dict) -> Dict:
        """Генерирует умный ответ на основе поиска"""
        try:
            topic = self._extract_topic_from_query(query)
            has_info = len(search_results['entries_found']) > 0 or len(search_results['entities_found']) > 0
            
            # Извлекаем структурированные данные
            structured_data = self._format_search_data(search_results)
            
            # Формируем контекст для AI
            context = f"""
ЗАПРОС ПОЛЬЗОВАТЕЛЯ: "{query}"
ТЕМА: {topic}
ЕСТЬ ЛИ ИНФОРМАЦИЯ: {has_info}

ДАННЫЕ ИЗ ПОИСКА:
{structured_data}

СТАТИСТИКА ПОИСКА:
- Найдено сущностей: {search_results['search_stats']['total_entities']}
- Найдено записей: {search_results['search_stats']['total_entries']}
- Типы поиска: {', '.join(search_results['search_stats']['search_types_used'])}

СТРУКТУРИРОВАННЫЕ ДАННЫЕ:
{self._format_structured_data(search_results)}

ВРЕМЕННОЙ АНАЛИЗ:
{self._format_temporal_analysis(search_results)}
"""
            
            system_prompt = self._create_system_prompt()
            
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                temperature=0.7,  # Немного креативности для человечности
                max_tokens=500
            )
            
            # Парсим JSON ответ
            content = response.choices[0].message.content.strip()
            
            # Убираем возможные markdown блоки
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content)
            
            # Валидируем и дополняем результат
            return self._validate_response(result, has_info, topic)
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON от AI: {e}")
            return self._fallback_response(query, search_results)
        except Exception as e:
            logger.error(f"Ошибка генерации ответа: {e}")
            return self._fallback_response(query, search_results)
    
    def _validate_response(self, result: Dict, has_info: bool, topic: str) -> Dict:
        """Валидирует и дополняет ответ AI"""
        # Убеждаемся, что все обязательные поля есть
        if "response" not in result:
            result["response"] = self._generate_fallback_text(has_info, topic)
        
        if "tone" not in result:
            result["tone"] = "caring" if not has_info else "informative"
        
        if "has_info" not in result:
            result["has_info"] = has_info
        
        if "confidence" not in result:
            result["confidence"] = 0.8 if has_info else 0.6
        
        if "suggestions" not in result:
            result["suggestions"] = self._generate_suggestions(has_info, topic)
        
        return result
    
    def _generate_fallback_text(self, has_info: bool, topic: str) -> str:
        """Генерирует fallback текст при ошибке AI"""
        if has_info:
            return f"Вот что я знаю о {topic} 📚"
        else:
            return f"Пока я ничего не знаю о {topic}, но готова запомнить! 💭"
    
    def _generate_suggestions(self, has_info: bool, topic: str) -> List[str]:
        """Генерирует предложения для пользователя"""
        if has_info:
            return [
                "Хочешь узнать больше деталей?",
                "Расскажи что-то новое об этом!",
                "Есть еще вопросы?"
            ]
        else:
            return [
                "Расскажи мне что-нибудь об этом!",
                "Поделись историей!",
                "Что бы ты хотел, чтобы я запомнила?"
            ]
    
    def _fallback_response(self, query: str, search_results: Dict) -> Dict:
        """Fallback ответ при ошибке AI"""
        topic = self._extract_topic_from_query(query)
        has_info = len(search_results['entries_found']) > 0 or len(search_results['entities_found']) > 0
        
        if has_info:
            # Есть информация - показываем кратко
            response_text = f"Вот что я знаю о {topic}:\n\n"
            
            if search_results['entities_found']:
                entities = [e['name'] for e in search_results['entities_found'][:3]]
                response_text += f"🏷️ Сущности: {', '.join(entities)}\n"
            
            if search_results['entries_found']:
                response_text += "📝 Записи:\n"
                for entry in search_results['entries_found'][:2]:
                    text = entry['original_text'][:100] + "..." if len(entry['original_text']) > 100 else entry['original_text']
                    response_text += f"• {text}\n"
        else:
            # Нет информации - заботливый ответ
            response_text = f"Пока я ничего не знаю о {topic}, но я внимательно слушаю и запоминаю все, что ты говоришь! 💭"
        
        return {
            "response": response_text,
            "tone": "caring" if not has_info else "informative",
            "has_info": has_info,
            "confidence": 0.5,
            "suggestions": [],  # Не генерируем предложения
            "fallback": True
        }
    
    def format_final_response(self, ai_response: Dict, search_results: Dict) -> str:
        """Форматирует финальный ответ для пользователя"""
        response = ai_response["response"]
        
        # Минимальное форматирование - только для структурирования
        if ai_response["tone"] == "informative":
            response = "📊 " + response
        
        # Убираем все дополнительные элементы:
        # - Не показываем количество записей
        # - Не добавляем предложения (suggestions всегда пустой)
        # - Не добавляем лишние эмодзи
        # - Не добавляем рекомендации
        
        # Дополнительная очистка от нежелательных фраз
        unwanted_phrases = [
            "Эта информация сохранена в системе",
            "Рекомендую отслеживать динамику",
            "Рекомендую продолжить мониторинг",
            "Советую обратить внимание",
            "Рекомендую",
            "Советую",
            "Стоит",
            "Желательно"
        ]
        
        for phrase in unwanted_phrases:
            if phrase in response:
                # Удаляем предложение с нежелательной фразой
                sentences = response.split('.')
                cleaned_sentences = []
                for sentence in sentences:
                    if phrase.lower() not in sentence.lower():
                        cleaned_sentences.append(sentence)
                response = '.'.join(cleaned_sentences).strip()
                if response and not response.endswith('.'):
                    response += '.'
        
        return response

# Пример использования
async def test_response_generator():
    """Тестируем генератор ответов"""
    # Замените на ваш API ключ DeepSeek
    api_key = "your-deepseek-api-key"
    
    generator = AIResponseGenerator(api_key)
    
    # Тестовые данные
    test_query = "расскажи о Васе"
    test_search_results = {
        'entities_found': [
            {'id': 1, 'name': 'Вася', 'type': 'person', 'mention_count': 3}
        ],
        'entries_found': [
            {'id': 1, 'original_text': 'Встретил Васю в автосервисе', 'entity_names': 'Вася', 'tag_names': 'люди,места'},
            {'id': 2, 'original_text': 'Вася купил новую машину', 'entity_names': 'Вася', 'tag_names': 'люди,автомобили'}
        ],
        'search_stats': {'total_entities': 1, 'total_entries': 2, 'search_types_used': ['entities_person']}
    }
    
    result = await generator.generate_response(test_query, test_search_results)
    print(f"Ответ: {result['response']}")
    print(f"Тон: {result['tone']}")
    print(f"Есть информация: {result['has_info']}")

if __name__ == "__main__":
    asyncio.run(test_response_generator())
