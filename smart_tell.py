"""
Умная функция "расскажи" - главный модуль
Проект "Второй мозг" - персональный голосовой интеллект
"""

import logging
from typing import Dict, Optional
from database import DatabaseManager
from smart_search import SmartSearchEngine
from ai_response_generator import AIResponseGenerator

logger = logging.getLogger(__name__)

class SmartTellEngine:
    """Главный движок умной функции 'расскажи'"""
    
    def __init__(self, db_manager: DatabaseManager, ai_api_key: str = None):
        self.db = db_manager
        self.search_engine = SmartSearchEngine(db_manager, ai_api_key)
        self.ai_generator = AIResponseGenerator(ai_api_key) if ai_api_key else None
        
        # Простые ответы для случаев без AI
        self.simple_responses = {
            'no_data': [
                "Пока я ничего не знаю об этом, но я внимательно слушаю и запоминаю все, что ты говоришь! 💭",
                "Моя память об этом пока чиста. Расскажи мне что-нибудь, и я запомню! ✨",
                "Пока у меня нет информации об этом. Но я готова учиться и запоминать! 📚"
            ],
            'found_data': [
                "Вот что я знаю:",
                "Нашла информацию:",
                "Вот что удалось найти:"
            ]
        }
    
    async def process_tell_request(self, user_id: int, query: str) -> str:
        """Обрабатывает запрос 'расскажи' и возвращает умный ответ"""
        try:
            logger.info(f"Обработка запроса 'расскажи' от пользователя {user_id}: {query}")
            
            # Выполняем комплексный поиск
            search_results = await self.search_engine.search_comprehensive(user_id, query)
            
            # Проверяем, есть ли данные
            has_data = (len(search_results['entities_found']) > 0 or 
                       len(search_results['entries_found']) > 0)
            
            if not has_data:
                # Нет данных - заботливый ответ
                return self._generate_no_data_response(query)
            
            # Есть данные - генерируем умный ответ
            if self.ai_generator:
                try:
                    # Используем AI для генерации ответа
                    ai_response = await self.ai_generator.generate_response(query, search_results)
                    final_response = self.ai_generator.format_final_response(ai_response, search_results)
                    return final_response
                except Exception as e:
                    logger.error(f"Ошибка AI генерации ответа: {e}")
                    # Fallback на простой ответ
                    return self._generate_simple_data_response(query, search_results)
            else:
                # Нет AI - используем простой ответ
                return self._generate_simple_data_response(query, search_results)
                
        except Exception as e:
            logger.error(f"Ошибка обработки запроса 'расскажи': {e}")
            return "Извини, произошла ошибка при поиске информации. Попробуй еще раз! 😔"
    
    def _generate_no_data_response(self, query: str) -> str:
        """Генерирует ответ когда данных нет"""
        import random
        
        # Извлекаем тему из запроса
        topic = self._extract_topic(query)
        
        # Выбираем случайный заботливый ответ
        response_template = random.choice(self.simple_responses['no_data'])
        
        if topic:
            response = response_template.replace("об этом", f"о {topic}")
        else:
            response = response_template
        
        # Добавляем предложение
        suggestions = [
            "Расскажи мне что-нибудь об этом!",
            "Поделись историей!",
            "Что бы ты хотел, чтобы я запомнила?"
        ]
        suggestion = random.choice(suggestions)
        
        return f"💕 {response}\n\n💡 {suggestion}"
    
    def _generate_simple_data_response(self, query: str, search_results: Dict) -> str:
        """Генерирует простой ответ с найденными данными"""
        import random
        
        topic = self._extract_topic(query)
        response_parts = []
        
        # Заголовок
        if topic:
            header = f"📚 Вот что я знаю о {topic}:"
        else:
            header = random.choice(self.simple_responses['found_data'])
        response_parts.append(header)
        
        # Сущности
        if search_results['entities_found']:
            entities = [e['name'] for e in search_results['entities_found'][:3]]
            response_parts.append(f"\n🏷️ Сущности: {', '.join(entities)}")
        
        # Записи
        if search_results['entries_found']:
            response_parts.append("\n📝 Записи:")
            for i, entry in enumerate(search_results['entries_found'][:3], 1):
                text = entry['original_text']
                if len(text) > 80:
                    text = text[:80] + "..."
                response_parts.append(f"{i}. {text}")
        
        # Связанная информация
        if search_results['related_entities']:
            related = [e['name'] for e in search_results['related_entities'][:2]]
            response_parts.append(f"\n🔗 Связанное: {', '.join(related)}")
        
        # Статистика
        total_entries = search_results['search_stats']['total_entries']
        if total_entries > 3:
            response_parts.append(f"\n📊 Всего найдено {total_entries} записей")
        
        # Предложение
        suggestions = [
            "Хочешь узнать больше деталей?",
            "Расскажи что-то новое об этом!",
            "Есть еще вопросы?"
        ]
        import random
        suggestion = random.choice(suggestions)
        response_parts.append(f"\n💡 {suggestion}")
        
        return "\n".join(response_parts)
    
    def _extract_topic(self, query: str) -> str:
        """Извлекает основную тему из запроса"""
        # Убираем служебные слова
        stop_words = {'расскажи', 'о', 'про', 'что', 'знаешь', 'ли', 'покажи', 'есть'}
        words = query.lower().split()
        topic_words = [w for w in words if w not in stop_words and len(w) > 2]
        
        if topic_words:
            return ' '.join(topic_words[:3])  # Первые 3 значимых слова
        return ""
    
    def get_user_stats_summary(self, user_id: int) -> str:
        """Получает краткую статистику пользователя"""
        try:
            stats = self.db.get_stats(user_id)
            
            if stats['entries'] == 0:
                return "💭 Твоя память пока пуста. Расскажи мне что-нибудь, и я запомню!"
            
            summary_parts = [f"📊 Твоя память содержит:"]
            summary_parts.append(f"📝 {stats['entries']} записей")
            summary_parts.append(f"🏷️ {stats['entities']} сущностей")
            
            if stats['active_reminders'] > 0:
                summary_parts.append(f"⏰ {stats['active_reminders']} напоминаний")
            
            # Получаем недавние записи
            recent_entries = self.search_engine.get_recent_entries(user_id, days=7, limit=3)
            if recent_entries:
                summary_parts.append(f"\n📅 Недавно ты упоминал:")
                for entry in recent_entries:
                    text = entry['original_text'][:60] + "..." if len(entry['original_text']) > 60 else entry['original_text']
                    summary_parts.append(f"• {text}")
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return "📊 Не могу получить статистику сейчас. Попробуй позже!"
    
    def get_quick_insights(self, user_id: int) -> str:
        """Получает быстрые инсайты о пользователе"""
        try:
            # Получаем топ сущности
            entities = self.db.get_user_entities(user_id)
            if not entities:
                return "💭 Пока нет данных для анализа. Расскажи мне что-нибудь!"
            
            # Группируем по типам
            entity_types = {}
            for entity in entities:
                entity_type = entity['type']
                if entity_type not in entity_types:
                    entity_types[entity_type] = []
                entity_types[entity_type].append(entity['name'])
            
            insights = ["🔍 Быстрые инсайты:"]
            
            # Топ типы сущностей
            type_counts = {t: len(entities) for t, entities in entity_types.items()}
            top_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            
            for entity_type, count in top_types:
                type_names = {
                    'person': 'люди',
                    'place': 'места', 
                    'object': 'объекты',
                    'event': 'события',
                    'task': 'задачи',
                    'reminder': 'напоминания'
                }
                type_name = type_names.get(entity_type, entity_type)
                insights.append(f"📌 {type_name}: {count}")
            
            # Топ сущности
            if entities:
                top_entities = entities[:5]
                entity_names = [e['name'] for e in top_entities]
                insights.append(f"\n🏷️ Часто упоминаемые: {', '.join(entity_names)}")
            
            return "\n".join(insights)
            
        except Exception as e:
            logger.error(f"Ошибка получения инсайтов: {e}")
            return "🔍 Не могу получить инсайты сейчас. Попробуй позже!"

# Пример использования
async def test_smart_tell():
    """Тестируем умную функцию расскажи"""
    from database import DatabaseManager
    
    # Инициализируем
    db = DatabaseManager("mira_brain.db")
    smart_tell = SmartTellEngine(db)
    
    # Тестовые запросы
    test_queries = [
        "расскажи о Васе",
        "что знаешь о работе",
        "покажи напоминания",
        "расскажи о машине"
    ]
    
    for query in test_queries:
        print(f"\nЗапрос: {query}")
        response = await smart_tell.process_tell_request(1, query)  # user_id = 1
        print(f"Ответ: {response}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_smart_tell())
