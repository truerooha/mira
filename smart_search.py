"""
Умный поиск и анализ для функции "расскажи"
Проект "Второй мозг" - персональный голосовой интеллект
"""

import json
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
from database import DatabaseManager
from ai_query_parser import AIQueryParser

logger = logging.getLogger(__name__)

class SmartSearchEngine:
    """Движок умного поиска для анализа записей пользователя"""
    
    def __init__(self, db_manager: DatabaseManager, ai_api_key: str = None):
        self.db = db_manager
        self.ai_parser = AIQueryParser(ai_api_key) if ai_api_key else None
        
        # Паттерны для извлечения ключевых слов из запроса
        self.query_patterns = {
            'person': [
                r'о\s+(\w+)', r'про\s+(\w+)', r'(\w+)\s+кто', r'кто\s+такой\s+(\w+)',
                r'(\w+)\s+что', r'что\s+знаешь\s+о\s+(\w+)', r'(\w+)\s+расскажи'
            ],
            'place': [
                r'в\s+(\w+)', r'где\s+(\w+)', r'(\w+)\s+где', r'место\s+(\w+)',
                r'локация\s+(\w+)', r'адрес\s+(\w+)'
            ],
            'object': [
                r'(\w+)\s+что', r'что\s+такое\s+(\w+)', r'объект\s+(\w+)',
                r'вещь\s+(\w+)', r'предмет\s+(\w+)'
            ],
            'event': [
                r'событие\s+(\w+)', r'встреча\s+(\w+)', r'(\w+)\s+когда',
                r'когда\s+(\w+)', r'мероприятие\s+(\w+)'
            ],
            'task': [
                r'задача\s+(\w+)', r'дело\s+(\w+)', r'(\w+)\s+нужно',
                r'нужно\s+(\w+)', r'покупка\s+(\w+)'
            ],
            'reminder': [
                r'напоминание\s+(\w+)', r'(\w+)\s+напомни', r'напомни\s+(\w+)',
                r'важно\s+(\w+)', r'срочно\s+(\w+)'
            ]
        }
        
        # Словарь для нормализации слов (приведение к базовой форме)
        self.word_normalization = {
            'васе': 'вася', 'васю': 'вася', 'васи': 'вася',
            'машине': 'машина', 'машину': 'машина', 'машины': 'машина',
            'работе': 'работа', 'работу': 'работа', 'работы': 'работа',
            'встречах': 'встреча', 'встречи': 'встреча', 'встречу': 'встреча',
            'молоке': 'молоко', 'молока': 'молоко', 'молоко': 'молоко',
            'напоминания': 'напоминание', 'напоминаний': 'напоминание'
        }
        
        # Стоп-слова для фильтрации
        self.stop_words = {
            'что', 'как', 'где', 'когда', 'кто', 'расскажи', 'покажи', 'знаешь',
            'ли', 'о', 'про', 'в', 'на', 'с', 'у', 'для', 'от', 'до', 'за', 'по',
            'и', 'а', 'но', 'или', 'если', 'чтобы', 'потому', 'что', 'также',
            'еще', 'уже', 'все', 'всего', 'всех', 'всем', 'всеми', 'всему',
            'это', 'этого', 'этому', 'этим', 'этом', 'эта', 'этой', 'эту',
            'этот', 'эти', 'этих', 'этим', 'этими', 'этим', 'этот'
        }
    
    def parse_query(self, query: str) -> Dict[str, List[str]]:
        """Парсит запрос пользователя и извлекает ключевые слова"""
        query_lower = query.lower().strip()
        extracted = {
            'person': [],
            'place': [],
            'object': [],
            'event': [],
            'task': [],
            'reminder': [],
            'general': []
        }
        
        # Извлекаем ключевые слова по типам
        for entity_type, patterns in self.query_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, query_lower)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    if match and len(match) > 2 and match not in self.stop_words:
                        # Нормализуем слово
                        normalized_word = self.word_normalization.get(match, match)
                        extracted[entity_type].append(normalized_word)
        
        # Извлекаем общие ключевые слова
        words = re.findall(r'\b\w+\b', query_lower)
        for word in words:
            if (len(word) > 2 and 
                word not in self.stop_words and 
                not any(word in extracted[entity_type] for entity_type in extracted if entity_type != 'general')):
                # Нормализуем слово
                normalized_word = self.word_normalization.get(word, word)
                extracted['general'].append(normalized_word)
        
        # Убираем дубликаты
        for entity_type in extracted:
            extracted[entity_type] = list(set(extracted[entity_type]))
        
        return extracted
    
    async def parse_query_ai(self, query: str) -> Dict[str, List[str]]:
        """Парсит запрос пользователя с помощью AI"""
        if not self.ai_parser:
            # Fallback на обычный парсинг
            return self.parse_query(query)
        
        try:
            # Используем AI для парсинга
            parsed_result = await self.ai_parser.parse_query(query)
            search_terms = self.ai_parser.extract_search_terms(parsed_result)
            
            logger.info(f"AI парсинг запроса '{query}': {len(parsed_result.get('entities', []))} сущностей")
            return search_terms
            
        except Exception as e:
            logger.error(f"Ошибка AI парсинга: {e}")
            # Fallback на обычный парсинг
            return self.parse_query(query)
    
    def search_entities(self, user_id: int, keywords: List[str], entity_type: str = None) -> List[Dict]:
        """Поиск сущностей по ключевым словам"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                if entity_type:
                    # Поиск по конкретному типу сущности
                    placeholders = ' OR '.join(['LOWER(name) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?)' for _ in keywords])
                    query = f"""
                        SELECT DISTINCT e.*, COUNT(ee.entry_id) as mention_count
                        FROM entities e
                        LEFT JOIN entry_entities ee ON e.id = ee.entity_id
                        WHERE e.user_id = ? AND e.type = ? AND ({placeholders})
                        GROUP BY e.id
                        ORDER BY mention_count DESC, e.name
                    """
                    # Добавляем поиск как по точному совпадению, так и по частичному
                    params = [user_id, entity_type]
                    for kw in keywords:
                        params.extend([f'%{kw}%', f'{kw}%'])  # Частичное и начинающееся с
                else:
                    # Поиск по всем типам
                    placeholders = ' OR '.join(['LOWER(name) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?)' for _ in keywords])
                    query = f"""
                        SELECT DISTINCT e.*, COUNT(ee.entry_id) as mention_count
                        FROM entities e
                        LEFT JOIN entry_entities ee ON e.id = ee.entity_id
                        WHERE e.user_id = ? AND ({placeholders})
                        GROUP BY e.id
                        ORDER BY mention_count DESC, e.name
                    """
                    # Добавляем поиск как по точному совпадению, так и по частичному
                    params = [user_id]
                    for kw in keywords:
                        params.extend([f'%{kw}%', f'{kw}%'])  # Частичное и начинающееся с
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Ошибка поиска сущностей: {e}")
            return []
    
    def search_entries_by_entities(self, user_id: int, entity_ids: List[int], limit: int = 10) -> List[Dict]:
        """Поиск записей по сущностям"""
        if not entity_ids:
            return []
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['?' for _ in entity_ids])
                query = f"""
                    SELECT DISTINCT e.*, 
                           GROUP_CONCAT(DISTINCT ent.name) as entity_names,
                           GROUP_CONCAT(DISTINCT t.name) as tag_names
                    FROM entries e
                    JOIN entry_entities ee ON e.id = ee.entry_id
                    JOIN entities ent ON ee.entity_id = ent.id
                    LEFT JOIN entry_tags et ON e.id = et.entry_id
                    LEFT JOIN tags t ON et.tag_id = t.id
                    WHERE e.user_id = ? AND ee.entity_id IN ({placeholders})
                    GROUP BY e.id
                    ORDER BY e.created_at DESC
                    LIMIT ?
                """
                params = [user_id] + entity_ids + [limit]
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Ошибка поиска записей по сущностям: {e}")
            return []
    
    def search_entries_by_text(self, user_id: int, keywords: List[str], limit: int = 10) -> List[Dict]:
        """Поиск записей по тексту"""
        if not keywords:
            return []
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ' OR '.join(['LOWER(original_text) LIKE LOWER(?)' for _ in keywords])
                query = f"""
                    SELECT e.*, 
                           GROUP_CONCAT(DISTINCT ent.name) as entity_names,
                           GROUP_CONCAT(DISTINCT t.name) as tag_names
                    FROM entries e
                    LEFT JOIN entry_entities ee ON e.id = ee.entry_id
                    LEFT JOIN entities ent ON ee.entity_id = ent.id
                    LEFT JOIN entry_tags et ON e.id = et.entry_id
                    LEFT JOIN tags t ON et.tag_id = t.id
                    WHERE e.user_id = ? AND ({placeholders})
                    GROUP BY e.id
                    ORDER BY e.created_at DESC
                    LIMIT ?
                """
                params = [user_id] + [f'%{kw}%' for kw in keywords] + [limit]
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Ошибка поиска записей по тексту: {e}")
            return []
    
    def get_related_entities(self, user_id: int, entity_id: int) -> List[Dict]:
        """Получить связанные сущности"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                query = """
                    SELECT DISTINCT e2.*, COUNT(*) as co_occurrence_count
                    FROM entities e1
                    JOIN entry_entities ee1 ON e1.id = ee1.entity_id
                    JOIN entry_entities ee2 ON ee1.entry_id = ee2.entry_id
                    JOIN entities e2 ON ee2.entity_id = e2.id
                    WHERE e1.id = ? AND e2.id != ? AND e2.user_id = ?
                    GROUP BY e2.id
                    ORDER BY co_occurrence_count DESC
                    LIMIT 5
                """
                cursor.execute(query, (entity_id, entity_id, user_id))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Ошибка получения связанных сущностей: {e}")
            return []
    
    def get_recent_entries(self, user_id: int, days: int = 7, limit: int = 5) -> List[Dict]:
        """Получить недавние записи"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cutoff_date = datetime.now() - timedelta(days=days)
                query = """
                    SELECT e.*, 
                           GROUP_CONCAT(DISTINCT ent.name) as entity_names,
                           GROUP_CONCAT(DISTINCT t.name) as tag_names
                    FROM entries e
                    LEFT JOIN entry_entities ee ON e.id = ee.entry_id
                    LEFT JOIN entities ent ON ee.entity_id = ent.id
                    LEFT JOIN entry_tags et ON e.id = et.tag_id
                    LEFT JOIN tags t ON et.tag_id = t.id
                    WHERE e.user_id = ? AND e.created_at >= ?
                    GROUP BY e.id
                    ORDER BY e.created_at DESC
                    LIMIT ?
                """
                cursor.execute(query, (user_id, cutoff_date, limit))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Ошибка получения недавних записей: {e}")
            return []
    
    async def search_comprehensive(self, user_id: int, query: str) -> Dict:
        """Комплексный поиск по запросу пользователя"""
        # Используем AI-парсинг если доступен
        if self.ai_parser:
            parsed_result = await self.ai_parser.parse_query(query)
            parsed_query = self.ai_parser.extract_search_terms(parsed_result)
            is_analytical = self.ai_parser.is_analytical_query(parsed_result)
            analytical_type = self.ai_parser.get_analytical_type(parsed_result)
        else:
            parsed_query = self.parse_query(query)
            is_analytical = False
            analytical_type = None
            parsed_result = None
        
        results = {
            'query': query,
            'parsed_keywords': parsed_query,
            'parsed_result': parsed_result,
            'is_analytical': is_analytical,
            'analytical_type': analytical_type,
            'entities_found': [],
            'entries_found': [],
            'related_entities': [],
            'recent_entries': [],
            'search_stats': {
                'total_entities': 0,
                'total_entries': 0,
                'search_types_used': []
            }
        }
        
        # Поиск по сущностям
        for entity_type, keywords in parsed_query.items():
            if keywords and entity_type != 'general':
                entities = self.search_entities(user_id, keywords, entity_type)
                results['entities_found'].extend(entities)
                results['search_stats']['search_types_used'].append(f'entities_{entity_type}')
        
        # Поиск по общим ключевым словам
        if parsed_query['general']:
            general_entities = self.search_entities(user_id, parsed_query['general'])
            results['entities_found'].extend(general_entities)
            results['search_stats']['search_types_used'].append('entities_general')
        
        # Убираем дубликаты сущностей
        seen_entities = set()
        unique_entities = []
        for entity in results['entities_found']:
            if entity['id'] not in seen_entities:
                seen_entities.add(entity['id'])
                unique_entities.append(entity)
        results['entities_found'] = unique_entities
        
        # Поиск записей по найденным сущностям
        if results['entities_found']:
            entity_ids = [e['id'] for e in results['entities_found']]
            entries = self.search_entries_by_entities(user_id, entity_ids)
            results['entries_found'].extend(entries)
            results['search_stats']['search_types_used'].append('entries_by_entities')
        
        # Поиск записей по тексту
        all_keywords = []
        for keywords in parsed_query.values():
            all_keywords.extend(keywords)
        
        if all_keywords:
            text_entries = self.search_entries_by_text(user_id, all_keywords)
            # Добавляем только новые записи
            existing_entry_ids = {e['id'] for e in results['entries_found']}
            for entry in text_entries:
                if entry['id'] not in existing_entry_ids:
                    results['entries_found'].append(entry)
            results['search_stats']['search_types_used'].append('entries_by_text')
        
        # Получаем связанные сущности для топ-сущностей
        if results['entities_found']:
            top_entity = results['entities_found'][0]
            related = self.get_related_entities(user_id, top_entity['id'])
            results['related_entities'] = related
        
        # Получаем недавние записи как контекст
        recent = self.get_recent_entries(user_id, days=7, limit=3)
        results['recent_entries'] = recent
        
        # Статистика
        results['search_stats']['total_entities'] = len(results['entities_found'])
        results['search_stats']['total_entries'] = len(results['entries_found'])
        
        # Если это аналитический запрос, добавляем временной анализ
        if is_analytical and analytical_type:
            results['temporal_analysis'] = self._analyze_temporal_data(results['entries_found'], analytical_type)
        
        return results
    
    def _analyze_temporal_data(self, entries: List[Dict], analytical_type: str) -> Dict:
        """Анализирует временные данные для аналитических запросов"""
        temporal_analysis = {
            'type': analytical_type,
            'measurements_over_time': [],
            'actions_timeline': [],
            'locations_summary': [],
            'amounts_summary': []
        }
        
        # Группируем записи по датам
        entries_by_date = {}
        for entry in entries:
            date = entry.get('created_at', '')
            if date:
                date_key = date[:10]  # YYYY-MM-DD
                if date_key not in entries_by_date:
                    entries_by_date[date_key] = []
                entries_by_date[date_key].append(entry)
        
        # Анализируем измерения во времени
        if analytical_type == 'weight_tracking':
            for date, day_entries in entries_by_date.items():
                for entry in day_entries:
                    text = entry.get('original_text', '')
                    # Ищем вес в тексте
                    import re
                    weight_match = re.search(r'(\d+)\s*(кг|килограмм)', text, re.IGNORECASE)
                    if weight_match:
                        temporal_analysis['measurements_over_time'].append({
                            'date': date,
                            'value': int(weight_match.group(1)),
                            'unit': 'kg',
                            'text': text
                        })
        
        # Анализируем действия
        elif analytical_type == 'maintenance_history':
            for date, day_entries in entries_by_date.items():
                for entry in day_entries:
                    text = entry.get('original_text', '')
                    if any(word in text.lower() for word in ['менял', 'починил', 'ремонтировал']):
                        temporal_analysis['actions_timeline'].append({
                            'date': date,
                            'action': text,
                            'type': 'maintenance'
                        })
        
        # Анализируем локации
        elif analytical_type == 'location_search':
            locations = set()
            for entry in entries:
                text = entry.get('original_text', '')
                # Простое извлечение локаций
                location_words = ['улица', 'в', 'на', 'гараж', 'сервис', 'офис']
                for word in location_words:
                    if word in text.lower():
                        locations.add(text)
            temporal_analysis['locations_summary'] = list(locations)
        
        return temporal_analysis
