import os
import subprocess
import json
import logging
from datetime import datetime
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from database import DatabaseManager
from categorization import CategorizationEngine
from ai_categorizer import AICategorizer

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WHISPER_PATH = os.getenv("WHISPER_PATH")
WHISPER_MODEL = os.getenv("WHISPER_MODEL")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

TRANSCRIPTS_DIR = Path("transcripts")
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

# Инициализируем базу данных и движки категоризации
db = DatabaseManager("mira_brain.db")
categorizer = CategorizationEngine()
ai_categorizer = AICategorizer(DEEPSEEK_API_KEY) if DEEPSEEK_API_KEY else None

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    user_id = update.effective_user.id
    user_dir = TRANSCRIPTS_DIR / str(user_id)
    user_dir.mkdir(exist_ok=True)
    ogg_path = user_dir / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.ogg"
    wav_path = ogg_path.with_suffix(".wav")
    txt_path = ogg_path.with_suffix(".txt")

    # Скачиваем файл
    await file.download_to_drive(str(ogg_path))

    # Конвертируем ogg → wav
    subprocess.run(["ffmpeg", "-y", "-i", str(ogg_path), str(wav_path)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Распознаём через whisper.cpp
    subprocess.run([WHISPER_PATH, "-m", WHISPER_MODEL, "-f", str(wav_path), "-otxt", "--language", "ru"])
    # whisper.cpp создаёт .wav.txt, переименуем
    generated_txt = str(wav_path) + ".txt"
    if Path(generated_txt).exists():
        Path(generated_txt).rename(txt_path)
        
        # Читаем расшифрованный текст
        with open(txt_path, 'r', encoding='utf-8') as f:
            text = f.read().strip()
        
        # Проверяем команды в тексте
        
        if "расскажи" in text.lower() or "tell me" in text.lower() or "show me" in text.lower():
            # Получаем записи из базы данных
            entries = db.get_user_entries(user_id, limit=5)
            if entries:
                response = "📚 Твои записи:\n\n"
                for entry in entries:
                    response += f"#{entry['id']}: {entry['original_text']}\n"
                    response += f"📅 {entry['created_at']}\n\n"
                await update.message.reply_text(response)
            else:
                await update.message.reply_text("📭 Память пуста.")
                
        elif "статистика" in text.lower() or "stats" in text.lower():
            # Показываем статистику пользователя
            stats = db.get_stats(user_id)
            response = f"📊 Твоя статистика:\n\n"
            response += f"📝 Записей: {stats['entries']}\n"
            response += f"🏷️ Сущностей: {stats['entities']}\n"
            response += f"⏰ Напоминаний: {stats['active_reminders']}\n"
            await update.message.reply_text(response)
            
        else:
            # Отправляем сообщение "Думаю..."
            thinking_msg = await update.message.reply_text("🤔 Думаю...")
            
            # Сохраняем запись
            entry_id = db.add_entry(
                user_id=user_id,
                original_text=text,
                source_type='voice',
                audio_file_path=str(txt_path)
            )
            
            # Пытаемся использовать AI категоризацию
            if ai_categorizer:
                try:
                    categorization_result = await ai_categorizer.categorize_text(text)
                    ai_used = True
                except Exception as e:
                    logger.error(f"Ошибка AI категоризации: {e}")
                    # Fallback на регулярные выражения
                    categorization_result = categorizer.categorize_text(text)
                    ai_used = False
            else:
                # Используем только регулярные выражения
                categorization_result = categorizer.categorize_text(text)
                ai_used = False
            
            # Сохраняем сущности
            for entity_data in categorization_result["entities"]:
                entity_id = db.add_entity(
                    user_id=user_id,
                    name=entity_data["name"],
                    entity_type=entity_data["type"],
                    attributes={
                        "template": entity_data.get("template", "ai"),
                        "confidence": entity_data["confidence"],
                        "context": entity_data.get("context", text),
                        "ai_used": ai_used
                    }
                )
                # Связываем запись с сущностью
                db.link_entry_entity(entry_id, entity_id, "mentioned")
            
            # Сохраняем теги
            for tag_name in categorization_result["tags"]:
                tag_id = db.add_tag(user_id, tag_name)
                db.link_entry_tag(entry_id, tag_id)
            
            # Создаем напоминания если есть
            for reminder_data in categorization_result["reminders"]:
                trigger_condition = None
                if categorization_result.get("temporal_info"):
                    if isinstance(categorization_result["temporal_info"], dict):
                        trigger_condition = categorization_result["temporal_info"].get("value")
                    else:
                        trigger_condition = str(categorization_result["temporal_info"])
                
                db.add_reminder(
                    user_id=user_id,
                    text=reminder_data["text"],
                    trigger_condition=trigger_condition,
                    entry_id=entry_id
                )
            
            # Формируем ответ
            response = f"🧠 Запомнил! (запись #{entry_id})"
            if ai_used:
                response += " 🤖"
            
            if categorization_result["entities"]:
                entities_text = ", ".join([e["name"] for e in categorization_result["entities"][:3]])
                response += f"\n🏷️ Сущности: {entities_text}"
            
            if categorization_result["tags"]:
                tags_text = " ".join(categorization_result["tags"][:5])
                response += f"\n📌 Теги: {tags_text}"
            
            if categorization_result.get("categories"):
                categories_text = ", ".join(categorization_result["categories"][:2])
                response += f"\n📂 Категории: {categories_text}"
            
            # Обновляем сообщение
            await thinking_msg.edit_text(response)
    else:
        await update.message.reply_text("❌ Ошибка распознавания речи")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 Второй мозг готов!\n\n"
        "Команды:\n"
        "• Любое голосовое сообщение → автоматически сохраню в память\n"
        "• Скажи 'расскажи' или 'tell me' → покажу твои записи\n"
        "• Скажи 'статистика' или 'stats' → покажу статистику\n"
        "• Просто говори - я все запомню!"
    )

def main():
    print("🧠 Запускаю Миру...")
    print("-" * 50)
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.COMMAND & filters.Regex("^/start$"), start))
    app.add_handler(MessageHandler(filters.VOICE, handle_audio))
    app.run_polling()

if __name__ == "__main__":
    main()