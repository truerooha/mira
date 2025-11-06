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
from smart_tell import SmartTellEngine
from intent_classifier import IntentClassifier, IntentType
from greeting_response_agent import GreetingResponseAgent
from openai import OpenAI
try:
    # Исключения SDK для точной диагностики
    from openai import APIConnectionError, APIStatusError, RateLimitError
except Exception:
    APIConnectionError = Exception
    APIStatusError = Exception
    RateLimitError = Exception

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WHISPER_PATH = os.getenv("WHISPER_PATH")
WHISPER_MODEL = os.getenv("WHISPER_MODEL")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_API_KEY")

# Пути данных
BASE_DATA_DIR = Path("data")
TRANSCRIPTS_DIR = BASE_DATA_DIR / "transcripts"
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

# Инициализируем базу данных и движки категоризации
db = DatabaseManager(str(BASE_DATA_DIR / "mira_brain.db"))
categorizer = CategorizationEngine()
ai_categorizer = AICategorizer(DEEPSEEK_API_KEY) if DEEPSEEK_API_KEY else None
smart_tell = SmartTellEngine(db, DEEPSEEK_API_KEY)
intent_classifier = IntentClassifier(DEEPSEEK_API_KEY) if DEEPSEEK_API_KEY else None
greeting_agent = GreetingResponseAgent(DEEPSEEK_API_KEY) if DEEPSEEK_API_KEY else None
openai_client = None
if OPENAI_API_KEY:
    # Добавляем таймаут и ограниченное число ретраев на случай временных сетевых сбоев
    openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=60.0, max_retries=2)

def postprocess_transcript(transcript: str) -> str:
    """Постобработка транскрипта для восстановления вопросительных знаков"""
    if not transcript:
        return transcript
    
    # Список вопросительных слов
    question_words = [
        'кто', 'кого', 'кому', 'кем',
        'что', 'чего', 'чему', 'чем', 
        'где', 'куда', 'откуда',
        'когда', 'во сколько',
        'как', 'каким образом',
        'почему', 'зачем', 'отчего',
        'сколько', 'какой', 'какая', 'какие',
        'есть ли', 'есть у меня', 'знаешь ли'
    ]
    
    # Проверяем, начинается ли предложение с вопросительного слова
    words = transcript.lower().strip().split()
    if words and words[0] in question_words:
        # Если нет вопросительного знака в конце, добавляем
        if not transcript.strip().endswith('?'):
            return transcript.strip() + '?'
    
    return transcript

def cleanup_audio_files(ogg_path: Path, wav_path: Path) -> None:
    """Удаляет аудиофайлы после успешного распознавания речи"""
    try:
        # Удаляем .ogg файл
        if ogg_path.exists():
            ogg_path.unlink()
            logger.info(f"Удален аудиофайл: {ogg_path}")
        
        # Удаляем .wav файл
        if wav_path.exists():
            wav_path.unlink()
            logger.info(f"Удален аудиофайл: {wav_path}")
            
    except Exception as e:
        logger.error(f"Ошибка при удалении аудиофайлов: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения с помощью AI-классификатора намерений"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Отправляем сообщение "Думаю..."
    thinking_msg = await update.message.reply_text("🤔 Думаю...")
    
    try:
        # Классифицируем намерение пользователя
        if intent_classifier:
            intent_type, intent_info = await intent_classifier.classify_intent(text)
        else:
            # Fallback на простую логику
            intent_type, intent_info = IntentType.SAVE_INFO, {"original_text": text}
        
        logger.info(f"Намерение пользователя {user_id}: {intent_type.value}")
        
        # Обрабатываем в зависимости от намерения
        if intent_type == IntentType.SEARCH_INFO:
            # Поиск информации
            topic = intent_info.get("topic", text)
            response = await smart_tell.process_tell_request(user_id, topic)
            await thinking_msg.edit_text(response)
            
        elif intent_type == IntentType.SHOW_STATS:
            # Показать статистику
            response = smart_tell.get_user_stats_summary(user_id)
            await thinking_msg.edit_text(response)
            
        elif intent_type == IntentType.SHOW_INSIGHTS:
            # Показать инсайты
            response = smart_tell.get_quick_insights(user_id)
            await thinking_msg.edit_text(response)
            
        elif intent_type == IntentType.SHOW_REMINDERS:
            # Показать напоминания
            reminders = db.get_active_reminders(user_id)
            if reminders:
                response = "⏰ Твои активные напоминания:\n\n"
                for reminder in reminders[:5]:  # Показываем до 5 напоминаний
                    response += f"• {reminder['text']}\n"
                    if reminder['trigger_condition']:
                        response += f"  📅 {reminder['trigger_condition']}\n"
                    response += "\n"
            else:
                response = "⏰ У тебя нет активных напоминаний"
            await thinking_msg.edit_text(response)
            
        elif intent_type == IntentType.GREETING:
            # Приветствие или бессмысленное сообщение - НЕ сохраняем в базу
            greeting_type = intent_info.get("greeting_type", "hello")
            if greeting_agent:
                response = await greeting_agent.generate_response(text, greeting_type)
            else:
                # Fallback ответы
                if greeting_type == "check_presence":
                    response = "Да, я тут, что-то запомнить?"
                elif greeting_type == "nonsense":
                    response = "Извини, не совсем поняла. Повтори, пожалуйста?"
                else:
                    response = "Привет! Я тебя слушаю :)"
            await thinking_msg.edit_text(response)
            
        else:  # IntentType.SAVE_INFO или IntentType.UNKNOWN
            # Сохраняем информацию
            await process_text_entry(update, text, user_id, thinking_msg)
            
    except Exception as e:
        logger.error(f"Ошибка обработки текстового сообщения: {e}")
        await thinking_msg.edit_text("❌ Произошла ошибка при обработке сообщения. Попробуй еще раз!")

async def process_text_entry(update: Update, text: str, user_id: int, thinking_msg=None):
    """Обрабатывает текстовую запись как обычное сообщение для сохранения"""
    # Если сообщение не передано, создаем новое
    if thinking_msg is None:
        thinking_msg = await update.message.reply_text("🤔 Думаю...")
    
    # Сохраняем запись
    entry_id = db.add_entry(
        user_id=user_id,
        original_text=text,
        source_type='text',
        audio_file_path=None
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

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    user_id = update.effective_user.id
    user_dir = TRANSCRIPTS_DIR / str(user_id)
    user_dir.mkdir(exist_ok=True)
    ogg_path = user_dir / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.ogg"
    wav_path = ogg_path.with_suffix(".wav")

    # Скачиваем файл
    await file.download_to_drive(str(ogg_path))

    # Конвертируем ogg → wav
    subprocess.run(["ffmpeg", "-y", "-i", str(ogg_path), str(wav_path)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Распознаём через OpenAI Whisper API
    if not openai_client:
        await update.message.reply_text("❌ Не настроен OPENAI_API_KEY/OPEN_API_KEY для Whisper API")
        cleanup_audio_files(ogg_path, wav_path)
        return

    try:
        with open(wav_path, "rb") as audio_file:
            transcript_text = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )

        # Постобработка транскрипта для восстановления вопросительных знаков
        processed_text = postprocess_transcript(transcript_text.strip())

        # Отправляем сообщение "Думаю..."
        thinking_msg = await update.message.reply_text("🤔 Думаю...")

        try:
            # Классифицируем намерение пользователя
            if intent_classifier:
                intent_type, intent_info = await intent_classifier.classify_intent(processed_text)
            else:
                # Fallback на простую логику
                intent_type, intent_info = IntentType.SAVE_INFO, {"original_text": processed_text}
            
            logger.info(f"Намерение пользователя {user_id} (аудио): {intent_type.value}")
            
            # Обрабатываем в зависимости от намерения
            if intent_type == IntentType.SEARCH_INFO:
                # Поиск информации
                topic = intent_info.get("topic", processed_text)
                response = await smart_tell.process_tell_request(user_id, topic)
                await thinking_msg.edit_text(response)
                # Удаляем аудиофайлы после успешной обработки
                cleanup_audio_files(ogg_path, wav_path)
                
            elif intent_type == IntentType.SHOW_STATS:
                # Показать статистику
                response = smart_tell.get_user_stats_summary(user_id)
                await thinking_msg.edit_text(response)
                # Удаляем аудиофайлы после успешной обработки
                cleanup_audio_files(ogg_path, wav_path)
                
            elif intent_type == IntentType.SHOW_INSIGHTS:
                # Показать инсайты
                response = smart_tell.get_quick_insights(user_id)
                await thinking_msg.edit_text(response)
                # Удаляем аудиофайлы после успешной обработки
                cleanup_audio_files(ogg_path, wav_path)
                
            elif intent_type == IntentType.SHOW_REMINDERS:
                # Показать напоминания
                reminders = db.get_active_reminders(user_id)
                if reminders:
                    response = "⏰ Твои активные напоминания:\n\n"
                    for reminder in reminders[:5]:  # Показываем до 5 напоминаний
                        response += f"• {reminder['text']}\n"
                        if reminder['trigger_condition']:
                            response += f"  📅 {reminder['trigger_condition']}\n"
                        response += "\n"
                else:
                    response = "⏰ У тебя нет активных напоминаний"
                await thinking_msg.edit_text(response)
                # Удаляем аудиофайлы после успешной обработки
                cleanup_audio_files(ogg_path, wav_path)
                
            elif intent_type == IntentType.GREETING:
                # Приветствие или бессмысленное сообщение - НЕ сохраняем в базу
                greeting_type = intent_info.get("greeting_type", "hello")
                if greeting_agent:
                    response = await greeting_agent.generate_response(processed_text, greeting_type)
                else:
                    # Fallback ответы
                    if greeting_type == "check_presence":
                        response = "Да, я тут, что-то запомнить?"
                    elif greeting_type == "nonsense":
                        response = "Извини, не совсем поняла. Повтори, пожалуйста?"
                    else:
                        response = "Привет! Я тебя слушаю :)"
                await thinking_msg.edit_text(response)
                # Удаляем аудиофайлы после успешной обработки
                cleanup_audio_files(ogg_path, wav_path)
                
            else:  # IntentType.SAVE_INFO или IntentType.UNKNOWN
                # Сохраняем информацию
                # Сохраняем запись
                entry_id = db.add_entry(
                    user_id=user_id,
                    original_text=processed_text,
                    source_type='voice',
                    audio_file_path=str(ogg_path)
                )
                
                # Пытаемся использовать AI категоризацию
                if ai_categorizer:
                    try:
                        categorization_result = await ai_categorizer.categorize_text(processed_text)
                        ai_used = True
                    except Exception as e:
                        logger.error(f"Ошибка AI категоризации: {e}")
                        # Fallback на регулярные выражения
                        categorization_result = categorizer.categorize_text(processed_text)
                        ai_used = False
                else:
                    # Используем только регулярные выражения
                    categorization_result = categorizer.categorize_text(processed_text)
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
                            "context": entity_data.get("context", processed_text),
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
                
                # Удаляем аудиофайлы после успешной обработки
                cleanup_audio_files(ogg_path, wav_path)
                
        except Exception as e:
            logger.error(f"Ошибка обработки аудио сообщения: {e}")
            await thinking_msg.edit_text("❌ Произошла ошибка при обработке сообщения. Попробуй еще раз!")
            # Удаляем аудиофайлы даже при ошибке обработки
            cleanup_audio_files(ogg_path, wav_path)

    except APIConnectionError as e:
        logger.error(f"Ошибка сетевого подключения к Whisper API: {e}")
        await update.message.reply_text(
            "❌ Нет подключения к Whisper API. Проверь интернет/прокси. "
            "Если используешь прокси — задай переменные HTTP(S)_PROXY."
        )
    except RateLimitError as e:
        logger.error(f"Превышен лимит Whisper API: {e}")
        await update.message.reply_text("⏳ Превышен лимит Whisper API. Попробуй позже.")
    except APIStatusError as e:
        logger.error(f"Статусная ошибка Whisper API: {e}")
        await update.message.reply_text("❌ Whisper API вернул ошибку. Попробуй позже.")
    except Exception as e:
        logger.error(f"Неизвестная ошибка распознавания через Whisper API: {e}")
        await update.message.reply_text("❌ Ошибка распознавания речи через Whisper API")
        cleanup_audio_files(ogg_path, wav_path)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 Второй мозг готов!\n\n"
        "🎙️ Как я работаю:\n"
        "• Любое голосовое сообщение → автоматически сохраню в память\n"
        "• Любое текстовое сообщение → умно определю что ты хочешь\n\n"
        "🤖 Я понимаю намерения:\n"
        "• Вопросы → найду информацию\n"
        "• Факты → сохраню в память\n"
        "• Команды → выполню действие\n\n"
        "💡 Примеры:\n"
        "• 'Кого я встретил сегодня?' → поиск\n"
        "• 'Сегодня я встретил Ливана' → сохранение\n"
        "• 'Статистика' → покажу статистику\n"
        "• 'Что я знаю о Васе?' → поиск\n"
        "• 'Инсайты' → покажу инсайты\n\n"
        "✨ Просто говори или пиши естественно - я пойму!"
    )

def main():
    print("🧠 Запускаю Миру...")
    print("-" * 50)
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.COMMAND & filters.Regex("^/start$"), start))
    app.add_handler(MessageHandler(filters.VOICE, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()