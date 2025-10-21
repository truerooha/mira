import os
import subprocess
import json
from datetime import datetime
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from database import DatabaseManager

# Загружаем .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WHISPER_PATH = os.getenv("WHISPER_PATH")
WHISPER_MODEL = os.getenv("WHISPER_MODEL")

TRANSCRIPTS_DIR = Path("transcripts")
TRANSCRIPTS_DIR.mkdir(exist_ok=True)

# Инициализируем базу данных
db = DatabaseManager("mira_brain.db")

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
            # По умолчанию сохраняем все записи
            entry_id = db.add_entry(
                user_id=user_id,
                original_text=text,
                source_type='voice',
                audio_file_path=str(txt_path)
            )
            
            # TODO: Здесь будет извлечение сущностей и тегов
            # Пока просто сохраняем базовую запись
            
            await update.message.reply_text(f"🧠 Запомнил! (запись #{entry_id})")
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