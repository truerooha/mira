import os
import subprocess
import json
import logging
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except Exception:
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception
from pathlib import Path
import shutil
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from database import DatabaseManager
from categorization import CategorizationEngine
from ai_categorizer import AICategorizer
from smart_tell import SmartTellEngine
from intent_classifier import IntentClassifier, IntentType
from greeting_response_agent import GreetingResponseAgent
from openai import OpenAI
from versioning import CURRENT_VERSION, get_pending_releases
try:
    # Исключения SDK для точной диагностики
    from openai import APIConnectionError, APIStatusError, RateLimitError
except Exception:
    APIConnectionError = Exception
    APIStatusError = Exception
    RateLimitError = Exception

# Фразы ожидания
from waiting_messages import get_waiting_message

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

# Настройка часового пояса пользователя/бота (важно для напоминаний)
USER_TZ = os.getenv("USER_TZ")  # например, "Europe/Moscow" или упрощённо "Moscow"

def _resolve_user_tz(user_tz_value: str):
    if not ZoneInfo:
        return datetime.now().astimezone().tzinfo
    if not user_tz_value:
        return datetime.now().astimezone().tzinfo
    alias = user_tz_value.strip()
    # Простейшие алиасы → IANA
    aliases_map = {
        "moscow": "Europe/Moscow",
        "msk": "Europe/Moscow",
        "spb": "Europe/Moscow",
        "kiev": "Europe/Kyiv",
        "kyiv": "Europe/Kyiv",
        "minsk": "Europe/Minsk",
        "tbilisi": "Asia/Tbilisi",
        "almaty": "Asia/Almaty",
        "astana": "Asia/Almaty",
        "ekb": "Asia/Yekaterinburg",
        "yekaterinburg": "Asia/Yekaterinburg",
        "novosibirsk": "Asia/Novosibirsk",
        "samara": "Europe/Samara",
        "omsk": "Asia/Omsk",
        "utc": "UTC",
        "gmt": "UTC",
    }
    key = alias.lower()
    if "/" not in alias and key in aliases_map:
        alias = aliases_map[key]
    try:
        return ZoneInfo(alias)
    except ZoneInfoNotFoundError:
        logger.warning(f"Не найден IANA TZ '{user_tz_value}', использую UTC")
        return timezone.utc

USER_TZINFO = _resolve_user_tz(USER_TZ)
logger.info(f"Использую часовой пояс: {USER_TZ or str(USER_TZINFO)}")

# Пути данных/БД с поддержкой ENV для персистентности
DB_PATH_ENV = os.getenv("DB_PATH")
DATA_DIR_ENV = os.getenv("DATA_DIR")

if DB_PATH_ENV:
    DB_PATH = Path(DB_PATH_ENV)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
else:
    BASE_DATA_DIR = Path(DATA_DIR_ENV) if DATA_DIR_ENV else Path("data")
    BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = BASE_DATA_DIR / "mira_brain.db"

BASE_DATA_DIR = DB_PATH.parent
TRANSCRIPTS_DIR = BASE_DATA_DIR / "transcripts"
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

# Инициализируем базу данных и движки категоризации
logger.info(f"Использую путь БД: {DB_PATH}")
db = DatabaseManager(str(DB_PATH))
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

import re


async def send_release_announcements(bot: Bot, user_id: int) -> None:
    """Отправляет пользователю сообщения о релизах, которые он ещё не видел."""

    last_seen_version = db.get_user_last_seen_version(user_id)
    pending_releases = get_pending_releases(last_seen_version)

    if not pending_releases:
        if last_seen_version != CURRENT_VERSION:
            db.update_user_last_seen_version(user_id, CURRENT_VERSION)
        return

    for release in pending_releases:
        await bot.send_message(chat_id=user_id, text=release.message)

    db.update_user_last_seen_version(user_id, pending_releases[-1].version)


async def ensure_release_announcements(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Безопасно отправляет релизы через контекст обработчика."""

    try:
        await send_release_announcements(context.bot, user_id)
    except Exception as e:
        logger.error(f"Ошибка отправки релизного уведомления пользователю {user_id}: {e}")


async def broadcast_release_announcements(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Рассылает актуальные релизные сообщения всем известным пользователям."""

    try:
        user_ids = db.get_known_user_ids()
        if not user_ids:
            logger.info("Нет известных пользователей для рассылки релизов")
            return

        logger.info(f"Запускаю массовую рассылку релизов для {len(user_ids)} пользователей")
        for user_id in user_ids:
            try:
                await send_release_announcements(context.bot, user_id)
            except Exception as user_err:
                logger.error(f"Ошибка релизной рассылки пользователю {user_id}: {user_err}")
    except Exception as e:
        logger.error(f"Ошибка при массовой рассылке релизов: {e}")


def parse_reminder_datetime(text: str, date_parser):
    """
    Вычисляет точный datetime для напоминания из произвольной русской фразы.
    Поддерживает: завтра/дни недели/абсолютные даты + время вида 'в 7 вечера', 'в 19:00', 'в 7', 'к 7 утра',
    а также относительные выражения вида 'через 10 минут'.
    """
    t = text.lower()
    base = date_parser.parse_text(t)

    def _normalize_unit(word: str):
        cleaned = re.sub(r"[^а-яё]", "", word.lower())
        units_map = {
            'seconds': {'секунд', 'секунда', 'секунды', 'секунду'},
            'minutes': {'минута', 'минуту', 'минуты', 'минут'},
            'hours': {'час', 'часа', 'часов'},
            'days': {'день', 'дня', 'дней', 'сутки', 'суток'},
            'weeks': {'неделя', 'неделю', 'недели', 'недель'},
            'months': {'месяц', 'месяца', 'месяцев'},
            'years': {'год', 'года', 'лет'},
        }
        for key, variants in units_map.items():
            if cleaned in variants:
                return key
        return None

    def _extract_relative_delta(text_lower: str):
        if 'через' not in text_lower:
            return None

        after_keyword = text_lower.split('через', 1)[1]
        total = timedelta(0)

        for value, unit in re.findall(r"(\d+)\s*(секунд[а-я]*|минут[а-я]*|час[а-я]*|дн[еяй]+|сут[а-я]*|недел[яей]*|месяц[а-я]*|год[а-я]*)", after_keyword):
            unit_key = _normalize_unit(unit)
            amount = int(value)
            if unit_key == 'seconds':
                total += timedelta(seconds=amount)
            elif unit_key == 'minutes':
                total += timedelta(minutes=amount)
            elif unit_key == 'hours':
                total += timedelta(hours=amount)
            elif unit_key == 'days':
                total += timedelta(days=amount)
            elif unit_key == 'weeks':
                total += timedelta(weeks=amount)
            elif unit_key == 'months':
                total += timedelta(days=30 * amount)
            elif unit_key == 'years':
                total += timedelta(days=365 * amount)

        if total == timedelta(0):
            singular_patterns = [
                (r"пол\s*-?\s*часа", timedelta(minutes=30)),
                (r"секунд[ау]", timedelta(seconds=1)),
                (r"минут[ау]", timedelta(minutes=1)),
                (r"час(ик)?", timedelta(hours=1)),
                (r"сутк[аи]", timedelta(days=1)),
                (r"день", timedelta(days=1)),
                (r"недел[яю]", timedelta(weeks=1)),
                (r"месяц", timedelta(days=30)),
                (r"год", timedelta(days=365)),
            ]
            for pattern, delta in singular_patterns:
                if re.search(rf"\b{pattern}\b", after_keyword):
                    total += delta

        return total if total > timedelta(0) else None

    relative_delta = _extract_relative_delta(t)

    dt = None
    dt_source = None

    if relative_delta is not None:
        dt = datetime.now(USER_TZINFO) + relative_delta
        dt_source = 'relative'
    elif base.get('datetime'):
        dt = base.get('datetime')
        dt_source = 'parsed'

    if dt is None:
        if 'завтра' in t:
            dt = datetime.now(USER_TZINFO) + timedelta(days=1)
        else:
            dt = datetime.now(USER_TZINFO)
        dt_source = 'fallback'

    m = re.search(r"\bв\s*(\d{1,2})(?::(\d{2}))?\s*(утра|дня|вечера|ночи)?\b", t)
    hour = None
    minute = 0
    tod = None
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        tod = m.group(3)

        if tod in ('вечера', 'ночи'):
            if 1 <= hour <= 11:
                hour += 12
        elif tod in ('дня',):
            if 1 <= hour <= 11:
                hour += 12

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=USER_TZINFO)

    if hour is not None:
        dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    elif dt_source != 'relative':
        time_info = base.get('time_info')
        if time_info == 'вечером':
            dt = dt.replace(hour=19, minute=0, second=0, microsecond=0)
        elif time_info == 'утром':
            dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)
        elif time_info == 'днем':
            dt = dt.replace(hour=13, minute=0, second=0, microsecond=0)
        elif time_info == 'ночью':
            dt = dt.replace(hour=23, minute=0, second=0, microsecond=0)
        else:
            dt = dt.replace(hour=10, minute=0, second=0, microsecond=0)
    else:
        time_info = base.get('time_info')
        if time_info and relative_delta is not None and relative_delta >= timedelta(hours=12):
            if time_info == 'вечером':
                dt = dt.replace(hour=19, minute=0, second=0, microsecond=0)
            elif time_info == 'утром':
                dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)
            elif time_info == 'днем':
                dt = dt.replace(hour=13, minute=0, second=0, microsecond=0)
            elif time_info == 'ночью':
                dt = dt.replace(hour=23, minute=0, second=0, microsecond=0)

    return dt

async def send_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    user_id = data["user_id"]
    reminder_id = data["reminder_id"]
    text = data["text"]

    try:
        await context.bot.send_message(chat_id=user_id, text=f"⏰ Напоминание: {text}")
        db.mark_reminder_completed(reminder_id)
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания #{reminder_id} пользователю {user_id}: {e}")

def schedule_reminder(job_queue, reminder_row: dict):
    """
    Планирует напоминание через job_queue по trigger_date.
    """
    if job_queue is None:
        logger.warning("JobQueue не инициализирован, пропускаю планирование напоминания")
        return
    trigger = reminder_row.get("trigger_date")
    if not trigger:
        return
    run_at = datetime.fromisoformat(trigger) if isinstance(trigger, str) else trigger
    # Делаем datetime timezone-aware и приводим к таймзоне JobQueue
    jq_tz = getattr(job_queue, 'timezone', None)
    if jq_tz is None:
        jq_tz = USER_TZINFO
    if run_at.tzinfo is None:
        # считаем, что сохранено локальное время пользователя
        run_at = run_at.replace(tzinfo=USER_TZINFO)
    run_at = run_at.astimezone(jq_tz)
    # Сравнение во временной зоне JobQueue
    if run_at <= datetime.now(jq_tz):
        logger.info(f"Пропускаю планирование прошедшего времени: {run_at.isoformat()}")
        return
    job_queue.run_once(
        send_reminder_job,
        when=run_at,
        data={
            "user_id": reminder_row["user_id"],
            "reminder_id": reminder_row["id"],
            "text": reminder_row["text"],
        },
        name=f"reminder_{reminder_row['id']}"
    )
    logger.info(f"Запланировано напоминание #{reminder_row['id']} на {run_at.isoformat()}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения с помощью AI-классификатора намерений"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Отправляем динамическое сообщение ожидания
    thinking_msg = await update.message.reply_text(f"🤔 {get_waiting_message()}")
    
    try:
        await ensure_release_announcements(user_id, context)

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
            await process_text_entry(update, context, text, user_id, thinking_msg)
            
    except Exception as e:
        logger.error(f"Ошибка обработки текстового сообщения: {e}")
        await thinking_msg.edit_text("❌ Произошла ошибка при обработке сообщения. Попробуй еще раз!")

async def process_text_entry(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, user_id: int, thinking_msg=None):
    """Обрабатывает текстовую запись как обычное сообщение для сохранения"""
    # Если сообщение не передано, создаем новое
    if thinking_msg is None:
        thinking_msg = await update.message.reply_text(f"🤔 {get_waiting_message()}")
    
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
                trigger_condition = categorization_result["temporal_info"].get("match") or categorization_result["temporal_info"].get("value")
            else:
                trigger_condition = str(categorization_result["temporal_info"])

        trigger_dt = parse_reminder_datetime(text, db.date_parser)

        reminder_id = db.add_reminder(
            user_id=user_id,
            text=reminder_data["text"],
            trigger_date=trigger_dt,
            trigger_condition=trigger_condition,
            entry_id=entry_id
        )

        if trigger_dt:
            schedule_reminder(context.job_queue, {
                "id": reminder_id,
                "user_id": user_id,
                "text": reminder_data["text"],
                "trigger_date": trigger_dt.isoformat()
            })
    
    # Формируем ответ
    response = f"🧠 Запомнила!"
    
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

    # Распознаём через OpenAI Whisper API (напрямую из .ogg, без ffmpeg)
    if not openai_client:
        await update.message.reply_text("❌ Не настроен OPENAI_API_KEY/OPEN_API_KEY для Whisper API")
        cleanup_audio_files(ogg_path, wav_path)
        return

    try:
        with open(ogg_path, "rb") as audio_file:
            transcript_text = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )

        # Постобработка транскрипта для восстановления вопросительных знаков
        processed_text = postprocess_transcript(transcript_text.strip())

        # Отправляем динамическое сообщение ожидания
        thinking_msg = await update.message.reply_text(f"🤔 {get_waiting_message()}")

        try:
            await ensure_release_announcements(user_id, context)

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
                            trigger_condition = categorization_result["temporal_info"].get("match") or categorization_result["temporal_info"].get("value")
                        else:
                            trigger_condition = str(categorization_result["temporal_info"])

                    trigger_dt = parse_reminder_datetime(processed_text, db.date_parser)

                    reminder_id = db.add_reminder(
                        user_id=user_id,
                        text=reminder_data["text"],
                        trigger_date=trigger_dt,
                        trigger_condition=trigger_condition,
                        entry_id=entry_id
                    )

                    if trigger_dt:
                        schedule_reminder(context.job_queue, {
                            "id": reminder_id,
                            "user_id": user_id,
                            "text": reminder_data["text"],
                            "trigger_date": trigger_dt.isoformat()
                        })
                
                # Формируем ответ
                response = f"🧠 Запомнила!"

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
        "🧠 Привет! Я - Мира, твой второй мозг!\n\n"
        "🎙️ Как я работаю:\n"
        "• Ты присылаешь мне голосовое или текстовое сообщение\n"
        "• Я сохраняю информацию в твою личную базу знаний\n"
        "🤖 Я умею:\n"
        "• Запоминать информацию, которую тебе важно не потерять\n"
        "• Напоминать тебе о важных событиях и задачах. Только скажи в слово Напомни\n"
        "• Искать информацию в твоей базе знаний. Даты, имена, события, что угодно\n\n"

        "💡 Примеры:\n"
        "• 'Привет, Мира. Напомни мне сходить к парикмахему завтра в 10:00' → добавлю напоминание\n"
        "• 'Напомни мне выключить кастрюлю через 20 минут→ добавлю напоминание\n"
        "• 'Сегодня я встретил Александра, он порекомендовал фильм Звездные войны' → сохраню информацию о встречах с людьми. Сохраню фильм в список просмотра\n"
        "• 'Что я знаю о Тимуре?' → расскажу информацию о Тимуре, когда ты с ним встречался, что о нём запоминал\n"
        "• 'Статистика' → покажу статистику по всем записям\n"
        "• 'Инсайты' → покажу инсайты, связи между записями, о которых ты даже не задумывался\n\n"
        "✨ Просто говори или пиши естественно - я пойму!"
    )

    if update.effective_user:
        await ensure_release_announcements(update.effective_user.id, context)

def main():
    print("🧠 Запускаю Миру...")
    print("-" * 50)
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Гарантируем наличие JobQueue даже без extras-пакета
    if getattr(app, 'job_queue', None) is None:
        try:
            from telegram.ext import JobQueue
            jq = JobQueue(timezone=USER_TZINFO)
            jq.set_application(app)
            jq.start()
            app.job_queue = jq
            logger.info("Инициализирован собственный JobQueue (fallback)")
        except Exception as e:
            logger.error(f"Не удалось инициализировать JobQueue: {e}")

    # Перепланировать будущие активные напоминания
    try:
        future_reminders = db.get_future_active_reminders()
        for r in future_reminders:
            schedule_reminder(app.job_queue, r)
        logger.info(f"Перепланировано напоминаний: {len(future_reminders)}")
    except Exception as e:
        logger.error(f"Ошибка перепланирования напоминаний на старте: {e}")

    if getattr(app, 'job_queue', None) is not None:
        app.job_queue.run_once(broadcast_release_announcements, when=0)
    else:
        logger.warning("JobQueue недоступен, пропускаю массовую рассылку релизов")
    app.add_handler(MessageHandler(filters.COMMAND & filters.Regex("^/start$"), start))
    app.add_handler(MessageHandler(filters.VOICE, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()