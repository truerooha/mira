#!/usr/bin/env python3
"""
Демонстрация аналитических запросов - сравнение обычного и AI-парсинга
"""

import asyncio
import logging
from database import DatabaseManager
from smart_search import SmartSearchEngine
from ai_query_parser import AIQueryParser

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def demo_analytical_parsing():
    """Демонстрируем разницу между обычным и AI-парсингом"""
    print("🎯 Демонстрация аналитических запросов")
    print("=" * 60)
    
    # Инициализация
    db = DatabaseManager("mira_brain.db")
    search_engine = SmartSearchEngine(db, "test-key")  # С AI (fallback)
    
    # Аналитические запросы для демонстрации
    analytical_queries = [
        "расскажи как менялся мой вес за время наблюдений",
        "что я ремонтировал в своей машине",
        "где я менял масло",
        "сколько потратил на здоровье в этом году",
        "какие у меня были встречи с Васей",
        "покажи историю расходов на автомобиль"
    ]
    
    print("🔍 Сравнение парсинга запросов:")
    print("-" * 60)
    
    for query in analytical_queries:
        print(f"\n📝 Запрос: '{query}'")
        print("=" * 50)
        
        # Обычный парсинг (regex)
        print("🔧 Обычный парсинг (regex):")
        try:
            old_result = search_engine.parse_query(query)
            print(f"  Ключевые слова: {old_result.get('general', [])}")
            print(f"  Типы сущностей: {[k for k, v in old_result.items() if v and k != 'general']}")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
        
        # AI-парсинг (с fallback)
        print("\n🤖 AI-парсинг (с fallback):")
        try:
            if search_engine.ai_parser:
                ai_result = await search_engine.ai_parser.parse_query(query)
                print(f"  Намерение: {ai_result.get('intent', 'unknown')}")
                print(f"  Аналитический тип: {ai_result.get('analytical_type', 'none')}")
                print(f"  Основная тема: {ai_result.get('main_topic', 'unknown')}")
                print(f"  Стратегия поиска: {ai_result.get('search_strategy', 'unknown')}")
                print(f"  Уверенность: {ai_result.get('confidence', 0)}")
                
                # Показываем сущности
                entities = ai_result.get('entities', [])
                if entities:
                    print(f"  Сущности ({len(entities)}):")
                    for entity in entities[:3]:  # Показываем первые 3
                        print(f"    - {entity.get('original', '')} → {entity.get('normalized', '')} ({entity.get('type', 'unknown')})")
                
                # Проверяем аналитический тип
                is_analytical = search_engine.ai_parser.is_analytical_query(ai_result)
                print(f"  Аналитический запрос: {'✅' if is_analytical else '❌'}")
            else:
                print("  ❌ AI-парсер недоступен")
        except Exception as e:
            print(f"  ❌ Ошибка AI-парсинга: {e}")
        
        # Извлекаем термины для поиска
        print("\n🔍 Термины для поиска:")
        try:
            if search_engine.ai_parser:
                parsed_result = await search_engine.ai_parser.parse_query(query)
                search_terms = search_engine.ai_parser.extract_search_terms(parsed_result)
            else:
                search_terms = search_engine.parse_query(query)
            
            for entity_type, terms in search_terms.items():
                if terms:
                    print(f"  {entity_type}: {', '.join(terms)}")
        except Exception as e:
            print(f"  ❌ Ошибка извлечения терминов: {e}")

async def demo_structured_data_extraction():
    """Демонстрируем извлечение структурированных данных"""
    print("\n\n🔧 Демонстрация извлечения структурированных данных")
    print("=" * 60)
    
    # Тестовые записи с разными типами данных
    test_entries = [
        "В мае 2023 года мой вес был 79кг",
        "В декабре 2024 года весил 83кг",
        "Сегодня взвесился - 86кг",
        "Менял масло в машине 01.01.2024, потратил 3000руб",
        "Ремонтировал тормоза на улице Барбашова в гаражах",
        "Починил кондиционер в автосервисе за 5000 рублей",
        "Купил новые шины для автомобиля",
        "Встреча с Васей в офисе на улице Ленина"
    ]
    
    print("📝 Тестовые записи:")
    for i, entry in enumerate(test_entries, 1):
        print(f"  {i}. {entry}")
    
    print("\n🔍 Анализ структурированных данных:")
    print("-" * 40)
    
    # Простой анализ с помощью regex
    import re
    
    measurements = []
    actions = []
    amounts = []
    locations = []
    
    for entry in test_entries:
        # Измерения (вес)
        weight_match = re.search(r'(\d+)\s*(кг|килограмм)', entry, re.IGNORECASE)
        if weight_match:
            measurements.append({
                'value': int(weight_match.group(1)),
                'unit': 'kg',
                'text': entry
            })
        
        # Суммы
        amount_match = re.search(r'(\d+)\s*(руб|рублей|₽)', entry, re.IGNORECASE)
        if amount_match:
            amounts.append({
                'amount': int(amount_match.group(1)),
                'currency': 'RUB',
                'text': entry
            })
        
        # Действия
        if any(word in entry.lower() for word in ['менял', 'починил', 'ремонтировал', 'купил']):
            actions.append({
                'text': entry,
                'type': 'maintenance' if any(word in entry.lower() for word in ['масло', 'ремонт', 'тормоз', 'кондиционер']) else 'action'
            })
        
        # Локации
        location_words = ['улица', 'в', 'на', 'гараж', 'сервис', 'офис']
        if any(word in entry.lower() for word in location_words):
            locations.append({
                'text': entry,
                'type': 'location'
            })
    
    print(f"📏 Измерения ({len(measurements)}):")
    for measurement in measurements:
        print(f"  - {measurement['value']}{measurement['unit']}: {measurement['text'][:50]}...")
    
    print(f"\n🔧 Действия ({len(actions)}):")
    for action in actions:
        print(f"  - {action['type']}: {action['text'][:50]}...")
    
    print(f"\n💰 Суммы ({len(amounts)}):")
    for amount in amounts:
        print(f"  - {amount['amount']} {amount['currency']}: {amount['text'][:50]}...")
    
    print(f"\n📍 Локации ({len(locations)}):")
    for location in locations:
        print(f"  - {location['text'][:50]}...")
    
    # Анализ трендов
    print(f"\n📊 Анализ трендов:")
    if len(measurements) >= 2:
        weights = [m['value'] for m in measurements]
        print(f"  Вес: {min(weights)}кг → {max(weights)}кг (изменение: +{max(weights) - min(weights)}кг)")
    
    if amounts:
        total_amount = sum(a['amount'] for a in amounts)
        print(f"  Общие расходы: {total_amount} руб")
    
    if actions:
        maintenance_actions = [a for a in actions if a['type'] == 'maintenance']
        print(f"  Ремонтных работ: {len(maintenance_actions)}")

if __name__ == "__main__":
    asyncio.run(demo_analytical_parsing())
    asyncio.run(demo_structured_data_extraction())
