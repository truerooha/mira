"""
DatabaseManager для работы с SQLite базой данных
Проект "Второй мозг" - персональный голосовой интеллект
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Менеджер базы данных для проекта 'Второй мозг'"""
    
    def __init__(self, db_path: str = "mira_brain.db"):
        self.db_path = Path(db_path)
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            # Читаем схему из файла
            schema_file = Path(__file__).parent / "database_schema.sql"
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            
            # Создаем базу данных и таблицы
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript(schema_sql)
                conn.commit()
            
            logger.info(f"База данных инициализирована: {self.db_path}")
            
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
            raise
    
    def get_connection(self):
        """Получить соединение с базой данных"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
        return conn
    
    # === МЕТОДЫ ДЛЯ РАБОТЫ С ЗАПИСЯМИ ===
    
    def add_entry(self, user_id: int, original_text: str, 
                  processed_text: str = None, source_type: str = 'voice',
                  audio_file_path: str = None, metadata: Dict = None) -> int:
        """Добавить новую запись"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO entries (user_id, original_text, processed_text, 
                                       source_type, audio_file_path, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, original_text, processed_text, source_type, 
                      audio_file_path, json.dumps(metadata) if metadata else None))
                
                entry_id = cursor.lastrowid
                conn.commit()
                
                logger.info(f"Добавлена запись #{entry_id} для пользователя {user_id}")
                return entry_id
                
        except Exception as e:
            logger.error(f"Ошибка добавления записи: {e}")
            raise
    
    def get_user_entries(self, user_id: int, limit: int = 50, 
                        offset: int = 0) -> List[Dict]:
        """Получить записи пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM entries 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (user_id, limit, offset))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Ошибка получения записей: {e}")
            raise
    
    def search_entries(self, user_id: int, query: str) -> List[Dict]:
        """Поиск записей по тексту"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM entries 
                    WHERE user_id = ? 
                    AND (original_text LIKE ? OR processed_text LIKE ?)
                    ORDER BY created_at DESC
                """, (user_id, f'%{query}%', f'%{query}%'))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Ошибка поиска записей: {e}")
            raise
    
    # === МЕТОДЫ ДЛЯ РАБОТЫ С СУЩНОСТЯМИ ===
    
    def add_entity(self, user_id: int, name: str, entity_type: str, 
                   attributes: Dict = None) -> int:
        """Добавить сущность"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO entities (user_id, name, type, attributes)
                    VALUES (?, ?, ?, ?)
                """, (user_id, name, entity_type, 
                      json.dumps(attributes) if attributes else None))
                
                # Получаем ID существующей или новой записи
                cursor.execute("""
                    SELECT id FROM entities 
                    WHERE user_id = ? AND name = ? AND type = ?
                """, (user_id, name, entity_type))
                
                result = cursor.fetchone()
                entity_id = result['id'] if result else cursor.lastrowid
                conn.commit()
                
                logger.info(f"Добавлена сущность '{name}' (тип: {entity_type}) для пользователя {user_id}")
                return entity_id
                
        except Exception as e:
            logger.error(f"Ошибка добавления сущности: {e}")
            raise
    
    def link_entry_entity(self, entry_id: int, entity_id: int, 
                          relation_type: str = 'mentioned', confidence: float = 1.0):
        """Связать запись с сущностью"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO entry_entities 
                    (entry_id, entity_id, relation_type, confidence)
                    VALUES (?, ?, ?, ?)
                """, (entry_id, entity_id, relation_type, confidence))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Ошибка связывания записи с сущностью: {e}")
            raise
    
    def get_user_entities(self, user_id: int, entity_type: str = None) -> List[Dict]:
        """Получить сущности пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if entity_type:
                    cursor.execute("""
                        SELECT * FROM entities 
                        WHERE user_id = ? AND type = ?
                        ORDER BY name
                    """, (user_id, entity_type))
                else:
                    cursor.execute("""
                        SELECT * FROM entities 
                        WHERE user_id = ?
                        ORDER BY type, name
                    """, (user_id,))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Ошибка получения сущностей: {e}")
            raise
    
    # === МЕТОДЫ ДЛЯ РАБОТЫ С ТЕГАМИ ===
    
    def add_tag(self, user_id: int, name: str, color: str = None) -> int:
        """Добавить тег"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO tags (user_id, name, color)
                    VALUES (?, ?, ?)
                """, (user_id, name, color))
                
                # Получаем ID существующего или нового тега
                cursor.execute("""
                    SELECT id FROM tags 
                    WHERE user_id = ? AND name = ?
                """, (user_id, name))
                
                result = cursor.fetchone()
                tag_id = result['id'] if result else cursor.lastrowid
                conn.commit()
                
                return tag_id
                
        except Exception as e:
            logger.error(f"Ошибка добавления тега: {e}")
            raise
    
    def link_entry_tag(self, entry_id: int, tag_id: int):
        """Связать запись с тегом"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO entry_tags (entry_id, tag_id)
                    VALUES (?, ?)
                """, (entry_id, tag_id))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Ошибка связывания записи с тегом: {e}")
            raise
    
    # === МЕТОДЫ ДЛЯ РАБОТЫ С НАПОМИНАНИЯМИ ===
    
    def add_reminder(self, user_id: int, text: str, trigger_date: datetime = None,
                     trigger_condition: str = None, entry_id: int = None) -> int:
        """Добавить напоминание"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO reminders (user_id, text, trigger_date, 
                                         trigger_condition, entry_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, text, trigger_date, trigger_condition, entry_id))
                
                reminder_id = cursor.lastrowid
                conn.commit()
                
                logger.info(f"Добавлено напоминание #{reminder_id} для пользователя {user_id}")
                return reminder_id
                
        except Exception as e:
            logger.error(f"Ошибка добавления напоминания: {e}")
            raise
    
    def get_active_reminders(self, user_id: int) -> List[Dict]:
        """Получить активные напоминания пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM reminders 
                    WHERE user_id = ? AND status = 'active'
                    ORDER BY trigger_date ASC
                """, (user_id,))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Ошибка получения напоминаний: {e}")
            raise
    
    # === УТИЛИТЫ ===
    
    def get_stats(self, user_id: int) -> Dict:
        """Получить статистику пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Количество записей
                cursor.execute("SELECT COUNT(*) as count FROM entries WHERE user_id = ?", (user_id,))
                entries_count = cursor.fetchone()['count']
                
                # Количество сущностей
                cursor.execute("SELECT COUNT(*) as count FROM entities WHERE user_id = ?", (user_id,))
                entities_count = cursor.fetchone()['count']
                
                # Количество активных напоминаний
                cursor.execute("SELECT COUNT(*) as count FROM reminders WHERE user_id = ? AND status = 'active'", (user_id,))
                reminders_count = cursor.fetchone()['count']
                
                return {
                    'entries': entries_count,
                    'entities': entities_count,
                    'active_reminders': reminders_count
                }
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            raise
    
    def close(self):
        """Закрыть соединения (для SQLite не нужно, но для совместимости)"""
        pass
