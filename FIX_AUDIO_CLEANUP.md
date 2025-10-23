# Исправление автоматической очистки аудиофайлов

## Проблема
После перезапуска бота новые аудиофайлы (.ogg, .wav) все еще оставались в папке transcripts, несмотря на добавленную функцию очистки.

## Причина
Функция `cleanup_audio_files()` вызывалась только в блоке `else` (для `IntentType.SAVE_INFO`), но не во всех ветках обработки намерений:
- ❌ `IntentType.SEARCH_INFO` - поиск информации
- ❌ `IntentType.SHOW_STATS` - показ статистики  
- ❌ `IntentType.SHOW_INSIGHTS` - показ инсайтов
- ❌ `IntentType.SHOW_REMINDERS` - показ напоминаний

## Решение
Добавлены вызовы `cleanup_audio_files(ogg_path, wav_path)` во все ветки обработки намерений:

```python
if intent_type == IntentType.SEARCH_INFO:
    # ... обработка ...
    cleanup_audio_files(ogg_path, wav_path)
    
elif intent_type == IntentType.SHOW_STATS:
    # ... обработка ...
    cleanup_audio_files(ogg_path, wav_path)
    
elif intent_type == IntentType.SHOW_INSIGHTS:
    # ... обработка ...
    cleanup_audio_files(ogg_path, wav_path)
    
elif intent_type == IntentType.SHOW_REMINDERS:
    # ... обработка ...
    cleanup_audio_files(ogg_path, wav_path)
```

## Результат
- ✅ **7 вызовов** функции очистки в коде (все ветки + обработка ошибок)
- ✅ **0 аудиофайлов** в папке transcripts
- ✅ **41 текстовый файл** сохранен для тестовых целей

## Проверка
```bash
# Проверить, что аудиофайлы удалены
find transcripts -name "*.ogg" -o -name "*.wav" | wc -l
# Должно вернуть: 0

# Проверить, что текстовые файлы сохранены  
find transcripts -name "*.txt" | wc -l
# Должно вернуть: 41
```

## Статус
✅ **ИСПРАВЛЕНО** - Теперь аудиофайлы будут автоматически удаляться во всех сценариях обработки.
