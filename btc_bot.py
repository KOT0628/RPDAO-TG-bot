import os
import re
import sys
import psutil
import random
import requests
from PIL import Image, ImageDraw, ImageFont
import datetime
import time
import telebot
from requests.exceptions import ReadTimeout
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telebot.types import Message
from collections import defaultdict
from threading import Timer
from discord_webhook import DiscordWebhook
from dotenv import load_dotenv
import schedule
import logging
import threading
import json
import tempfile
import uuid

# === ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ===
load_dotenv()

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = str(os.getenv("CHAT_ID"))
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_AVATAR_URL = os.getenv("DISCORD_AVATAR_URL")
BACKGROUND_PATH = 'background.jpg'
FONT_PATH = 'SpicyRice-Regular.ttf'

# Проверка обязательных переменных
if not TOKEN or not CHAT_ID:
    logging.critical("TELEGRAM_TOKEN или CHAT_ID не заданы в переменных окружения.")
    sys.exit(1)

# Проверяем наличие папки temp, если нет — создаём
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# === НАСТРОЙКИ ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("logs.txt", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Очистка файла логов
LOG_FILE = "logs.txt"

def clear_log_file():
    try:
        with open(LOG_FILE, "w") as f:
            f.truncate(0)
        logging.info("Файл логов успешно очищен.")
    except Exception as e:
        logging.error(f"Ошибка при очистке файла логов: {e}")

# Каждые 3 дня выполнять очистку логов
schedule.every(3).days.do(clear_log_file)

# ==== БЛОКИРОВКА ЗАПУСКА ====
LOCK_FILE = "bot.lock"

# ==== ТАБЛИЦА ЛИДЕРОВ ====
SCORE_FILE = "scores.json"

# Загружаем счёт
def load_scores():
    if os.path.exists(SCORE_FILE):
        with open(SCORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# Сохраняем счёт
def save_scores(scores):
    with open(SCORE_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)

# Глобальная таблица очков
scores = load_scores()

def is_process_running(pid):
    return psutil.pid_exists(pid)

if os.path.exists(LOCK_FILE):
    with open(LOCK_FILE, "r") as f:
        try:
            pid = int(f.read())
            if is_process_running(pid):
                logging.error(f"❌ Бот уже запущен с PID {pid}. Выход.")
                sys.exit(1)
            else:
                logging.warning("Найден старый lock-файл от неактивного процесса. Продолжаем.")
        except ValueError:
            logging.warning("Поврежденный lock-файл. Продолжаем.")

# ==== СПИСОК ВОПРОСВ TRIVIA ====
TRIVIA_FILE = "trivia_questions.txt"

# Пишем текущий PID в файл
with open(LOCK_FILE, "w") as f:
    f.write(str(os.getpid()))

# Инициализируем клиента
bot = telebot.TeleBot(TOKEN)

# === ФУНКЦИЯ ДЛЯ ФИЛЬТРАЦИИ СТАРЫХ СООБЩЕНИЙ ===
def is_recent(message):
    now = datetime.datetime.utcnow()
    msg_time = datetime.datetime.utcfromtimestamp(message.date)
    return (now - msg_time).total_seconds() < 30           # Не обрабатывать сообщения старше 30 секунд

# ==== ПОЛУЧЕНИЕ ЦЕНЫ ====
def get_btc_price():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            logging.error(f"Ошибка ответа CoinGecko: {response.status_code}")
            return 0.0
        data = response.json()
        return round(data["bitcoin"]["usd"], 2)
    except Exception as e:
        logging.error(f"Ошибка при получении цены BTC: {e}")
        return 0.0

# ==== СОЗДАНИЕ ИЗОБРАЖЕНИЯ ====
def create_price_image(price):
    # Проверка наличия фонового изображения и шрифта
    if not os.path.exists(BACKGROUND_PATH):
        logging.error(f"❌ Фоновое изображение {BACKGROUND_PATH} не найдено.")
        return False

    if not os.path.exists(FONT_PATH):
        logging.error("❌ Шрифт SpicyRice-Regular.ttf не найден.")
        return False

    try:
        # Загрузка фонового изображения
        img = Image.open(BACKGROUND_PATH)
        draw = ImageDraw.Draw(img)

        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        text = f"BTC\n${price}"
        
        # Настройка шрифта
        font = ImageFont.truetype(FONT_PATH, 140)
        
        x, y = 35, 20  # Позиция текста

        # Цвета
        main_color = (255, 0, 0)          # красный основной текст
        shadow_color = (0, 0, 0)          # чёрная тень
        outline_color = (255, 215, 0)     # золотой контур

        # Рисуем ТЕНЬ (смещённый текст)
        draw.text((x+4, y+4), text, font=font, fill=shadow_color)
        
        # Рисуем КОНТУР (обводку) — вокруг текста
        for dx in [-2, -1, 1, 2]:
            for dy in [-2, -1, 1, 2]:
                if dx != 0 or dy != 0:
                    draw.text((x+dx, y+dy), text, font=font, fill=outline_color)
        
        # Рисуем САМ ТЕКСТ
        draw.text((x, y), text, font=font, fill=main_color)

        # Сохраняем результат
        img.save("btc_price_output.jpg")
        return True
    except Exception as e:
        logging.error(f"Ошибка при создании изображения: {e}")
        return False

def create_greeting_image(text, background_file, output_file):
    if not os.path.exists(background_file):
        logging.error(f"Файл фона {background_file} не найден.")
        return False

    if not os.path.exists(FONT_PATH):
        logging.error("❌ Шрифт SpicyRice-Regular.ttf не найден.")
        return False

    try:
        img = Image.open(background_file)
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(FONT_PATH, 90)

        x, y = 40, 570
        main_color = (255, 0, 0)          # красный основной текст
        shadow_color = (0, 0, 0)          # чёрная тень
        outline_color = (255, 215, 0)     # золотой контур

        # Тень
        draw.text((x+4, y+4), text, font=font, fill=shadow_color)

        # Контур
        for dx in [-2, -1, 1, 2]:
            for dy in [-2, -1, 1, 2]:
                if dx != 0 or dy != 0:
                    draw.text((x+dx, y+dy), text, font=font, fill=outline_color)

        # Основной текст
        draw.text((x, y), text, font=font, fill=main_color)

        img.save(output_file)
        return True
    except Exception as e:
        logging.error(f"Ошибка при создании поздравительной картинки: {e}")
        return False

# ==== ПЕРЕСЫЛКА В DISCORD ====
# Пересылка текстового сообщения
def send_to_discord(text, username="RPDAO Telegram", avatar_url=None):
    if not DISCORD_WEBHOOK_URL:
        logging.warning("DISCORD_WEBHOOK_URL не задан")
        return
    try:
        payload = {
            "content": text,
            "username": username,
            "avatar_url": avatar_url or DISCORD_AVATAR_URL         # путь к кастомной аватарке
        }
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code != 204:
            logging.warning(f"Ошибка отправки текста в Discord: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Ошибка при отправке текста в Discord: {e}")

# Пересылка фото с подписью
def send_photo_to_discord(caption, photo_path, username=None, avatar_url=None):
    try:
        webhook = DiscordWebhook(
            url=DISCORD_WEBHOOK_URL,
            content=caption,
            username=username or "Telegram",
            avatar_url=avatar_url or DISCORD_AVATAR_URL
        )
        with open(photo_path, 'rb') as f:
            webhook.add_file(file=f.read(), filename="photo.jpg")

        response = webhook.execute()
        logging.info(f"[DC] Фото отправлено. Статус: {response.status_code}")

        if response.status_code not in [200, 204]:
            logging.warning(f"Ошибка отправки фото в Discord: {response.status_code} - {response.text}")

    except Exception as e:
        logging.error(f"Ошибка при отправке фото в Discord: {e}")

# === БЕЗОПАСНОЕ УДАЛЕНИЕ СООБЩЕНИЙ ===
def safe_delete_message(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception as e:
        logging.warning(f"Не удалось удалить сообщение {message_id} из чата {chat_id}: {e}")

# ==== ОТПРАВКА ИЗОБРАЖЕНИЯ ====
def send_price_image():
    try:
        price = get_btc_price()
        if price == 0.0:
            logging.warning("Цена BTC не получена. Пропуск отправки.")
            return

        if create_price_image(price):
            with open("btc_price_output.jpg", "rb") as photo:
                bot.send_photo(CHAT_ID, photo, caption=f"Greetings Adventurers! Current #price $BTC: ${price}")
            logging.info("Сообщение отправлено.")
    except Exception as e:
        logging.error(f"Ошибка при отправке: {e}")

# === УДАЛЕНИЕ СЛЭШ-КОМАНД ===
def delete_command_after(func):
    def wrapper(message):
        try:
            func(message)
        finally:
            threading.Timer(5, lambda: safe_delete_message(message.chat.id, message.message_id)).start()
    return wrapper

# ==== ОБРАБОТЧИК КОМАНДЫ /price ====
@bot.message_handler(commands=['price'])
@delete_command_after
def handle_price_command(message):    
    try:
        if str(message.chat.id) == CHAT_ID:
            price = get_btc_price()
            if price == 0.0:
                bot.reply_to(message, "Не удалось получить цену BTC.")
                return
            if create_price_image(price):
                with open("btc_price_output.jpg", "rb") as photo:
                    bot.send_photo(CHAT_ID, photo, caption=f"Greetings Adventurers! Current #price $BTC: ${price}")
                logging.info(f"{message.from_user.username or message.from_user.id} использовал команду /price. Цена BTC: ${price}")
    except Exception as e:
        logging.error(f"Ошибка в обработчике /price: {e}")

# === ДОБАВЛЯЕМ ВИКТОРИНУ TRIVIA ===
trivia_active = False
current_trivia = None
current_mask = None
hint_index = 0
hint_timer = None

# Загружаем список вопросов
def load_trivia_questions():
    if os.path.exists(TRIVIA_FILE):
        with open(TRIVIA_FILE, "r", encoding="utf-8") as f:
            questions = [line.strip() for line in f if line.strip() and ':' in line]
        return [tuple(q.split(':', 1)) for q in questions]
    return []

trivia_questions = load_trivia_questions()

# Отправка следующего вопроса
def start_next_trivia():
    global current_trivia, current_mask, hint_index, trivia_active

    if trivia_question_pending:
        return                                             # Защита от повторного запуска
    trivia_question_pending = False                        # Сброс

    if not trivia_questions:
        msg = bot.send_message(CHAT_ID, f"❌ The list of questions is empty.\n\n❌ Список вопросов пуст.")
        threading.Timer(30, lambda: safe_delete_message(CHAT_ID, msg.message_id)).start()
        return

    current_trivia = random.choice(trivia_questions)
    question, answer = current_trivia
    current_mask = ['-' for _ in answer]
    hint_index = 0
    trivia_active = True

    msg = bot.send_message(CHAT_ID, f"🧠 Викторина началась!\n\n\n{question}")
    trivia_question_pending = True
    threading.Timer(180, lambda: safe_delete_message(CHAT_ID, msg.message_id)).start()
    schedule_hint()

# Подсказки
def schedule_hint():
    global hint_timer
    hint_timer = Timer(15, send_hint)                      # Подсказка каждые 15 секунд
    hint_timer.start()

def send_hint():
    global hint_index, current_trivia, trivia_active
    if not trivia_active or not current_trivia:
        return                                # Не отправляем подсказку, если викторина не активна

    question, answer = current_trivia

    # Найдём все скрытые позиции
    hidden_indices = [i for i, char in enumerate(current_mask) if char == '-']

    if hidden_indices:
        # Выбираем случайный индекс
        random_index = random.choice(hidden_indices)
        current_mask[random_index] = answer[random_index]

        msg = bot.send_message(CHAT_ID, f"🕵️‍♂️ Подсказка:\n\n{''.join(current_mask)}")
        threading.Timer(20, lambda: safe_delete_message(CHAT_ID, msg.message_id)).start()

        # Планируем следующую подсказку, если есть ещё скрытые буквы
        if '-' in current_mask:
            schedule_hint()
        else:
            bot.send_message(CHAT_ID, f"❌ Никто не угадал!\n\nОтвет был: {answer}")
            start_next_trivia()
    else:
        # Нет скрытых букв — завершаем
        bot.send_message(CHAT_ID, f"❌ Никто не угадал!\n\nОтвет был: {answer}")
        trivia_active = False
        trivia_question_pending = True
        threading.Timer(30, start_next_trivia).start()     # Запуск следующего вопроса через 15 сек

# === ЗАПУСК ВИКТОРИНЫ (только админ) ===
@bot.message_handler(commands=['rpdao_trivia'])
@delete_command_after
def handle_trivia_start(message):
    global trivia_active
    if str(message.chat.id) != CHAT_ID:
        return
    user_id = message.from_user.id

    # Получаем username без @, либо user_id
    username = message.from_user.username if message.from_user.username else str(user_id)

    try:
        member = bot.get_chat_member(message.chat.id, user_id)
        if not (member.status in ['administrator', 'creator']):
            msg = bot.reply_to(message, f"⛔ Only an administrator can start a Trivia.\n\n⛔ Только администратор может запустить викторину.")
            threading.Timer(10, lambda: safe_delete_message(CHAT_ID, msg.message_id)).start()
            return
    except:
        return

    if trivia_active:
        msg = bot.send_message(CHAT_ID, f"⚠️ The Trivia has already been launched.\n\n⚠️ Викторина уже запущена.")
        threading.Timer(10, lambda: safe_delete_message(CHAT_ID, msg.message_id)).start()
        return

    trivia_active = True
    bot.send_message(CHAT_ID, f"🔎 The Trivia has started! Get ready to answer!\n\n🔎 Викторина запущена! Готовьтесь отвечать!")
    logging.info(f"{username} запустил Trivia")

    # Старт первого вопроса через 60 секунд
    threading.Timer(60, start_next_trivia).start()

# === ОСТАНОВКА ВИКТОРИНЫ (только админ) ===
@bot.message_handler(commands=['rpdao_trivia_off'])
@delete_command_after
def handle_trivia_stop(message):
    global trivia_active, current_trivia, current_mask, hint_index, hint_timer
    if str(message.chat.id) != CHAT_ID:
        return
    user_id = message.from_user.id

    # Получаем username без @, либо user_id
    username = message.from_user.username if message.from_user.username else str(user_id)
   
    try:
        member = bot.get_chat_member(message.chat.id, user_id)
        if not (member.status in ['administrator', 'creator']):
            msg = bot.reply_to(message, f"⛔ Only an administrator can start a Trivia.\n\n⛔ Только администратор может остановить викторину.")
            threading.Timer(10, lambda: safe_delete_message(CHAT_ID, msg.message_id)).start()
            return
    except:
        return

    trivia_active = False
    current_trivia = None
    current_mask = None
    hint_index = 0
    if hint_timer:
        hint_timer.cancel()

    bot.send_message(CHAT_ID, f"🛑 The Trivia has been stopped.\n\n🛑 Викторина остановлена.")
    logging.info(f"{username} завершил Trivia")

# === ОБРАБОТКА ОТВЕТОВ TRIVIA ===
@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'), content_types=['text'])
def handle_text_messages(message):
    global trivia_active, current_trivia, hint_timer
    
    # Пропускаем старые сообщения (например, после запуска бота)
    if not is_recent(message):
        logging.info(f"[SKIP] Старое текстовое сообщение пропущено: {message.text}")
        return

    logging.info(f"[ALL_MSG] Текст от {message.from_user.username or message.from_user.id}")

    if str(message.chat.id) != CHAT_ID:
        return

    # === 1. TRIVIA логика ===
    if trivia_active and current_trivia:
        answer = current_trivia[1].strip().lower()
        user_answer = message.text.strip().lower()

        if user_answer == answer:
            # === Отключаем викторину сразу, чтобы принять только 1 ответ ===
            trivia_active = False

            if hint_timer:
                hint_timer.cancel()

            user_id = message.from_user.id
            display_name = message.from_user.first_name or "Игрок"

            # Получаем username без @, либо user_id
            username = message.from_user.username if message.from_user.username else str(user_id)

            scores[str(user_id)] = scores.get(str(user_id), 0) + 5
            save_scores(scores)

            bot.send_message(CHAT_ID, f"🎉 {display_name} угадал слово\n\n-----{answer}-----\n\nи получает 5 $LEG!")
            logging.info(f"Победитель викторины: {username}, +5 очков")

            # Запуск следующего вопроса через 15 секунд
            global trivia_question_pending
            trivia_question_pending = True
            threading.Timer(15, start_next_trivia).start()
            return                                         # ❗ Не продолжаем дальше    

    # === 2. Пересылка текста в Discord ===
	# Обработка обычных текстовых сообщений (не команд)
    # Получаем имя пользователя для отображения
    user_display = message.from_user.full_name or f"@{message.from_user.username}" if message.from_user.username else "Unknown"
    
	# Аватарка (одна общая кастомная)
    avatar_url = DISCORD_AVATAR_URL

    # Проверка, является ли сообщение ответом
    if message.reply_to_message:
        reply_author = message.reply_to_message.from_user.full_name or "Unknown"
        reply_text = message.reply_to_message.text or message.reply_to_message.caption or "<медиа>"
        quoted = f"Ответ на сообщение от **{reply_author}**:\n> {reply_text}\n\n"
    else:
        quoted = ""

    full_text = f"{quoted}{message.text}"
    send_to_discord(full_text, username=user_display, avatar_url=avatar_url)

# ==== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ РЕЖИМА /roll ====
roll_round_active = False
roll_results = {}                                          # user_id: (score, display_name, username)
roll_timer = None

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ РЕЖИМА /reroll ===
reroll_enabled = False
reroll_temp_players = set()

# Новый режим: 'tournament' или 'free'
reroll_mode = 'free'                                       # по умолчанию свободный

# Очередь для дуэлей в режиме 'tournament'
reroll_duel_queue = []                                     # Очередь игроков
current_duel_players = set()                               # Пара для текущей дуэли

def start_roll_round(chat_id):
    global roll_round_active, roll_results, roll_timer

    if roll_round_active:
        return False                                        # Раунд уже идёт

    roll_round_active = True
    roll_results = {}
    roll_timer = Timer(120, finish_roll_round)               # 2 минуты
    roll_timer.start()

    bot.send_message(chat_id, f"🎲 The round has begun! Use /roll to roll a number from 0 to 100. You have 2 minutes!\n\n🎲 Раунд начался! Используйте /roll, чтобы бросить число от 0 до 100. У вас 2 минуты!")
    return True

# ==== ОБРАБОТЧИК КОМАНДЫ /start_roll ====
@bot.message_handler(commands=['start_roll'])
@delete_command_after
def handle_start_roll(message):
    if str(message.chat.id) != CHAT_ID:
        return

    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)

    # Проверка: только админ может стартовать
    try:
        member = bot.get_chat_member(message.chat.id, user_id)
        if not (member.status in ['administrator', 'creator']):
            msg = bot.reply_to(message, f"⛔ Only the administrator can start a round.\n\n⛔ Только администратор может запустить раунд.")
            threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
            return
    except Exception as e:
        logging.error(f"Ошибка при проверке прав администратора: {e}")
        msg = bot.reply_to(message, f"❌ Unable to verify rights.\n\n❌ Не удалось проверить права.")
        threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
        return

    # Запускаем раунд
    if start_roll_round(message.chat.id):
        logging.info(f"{username} запустил раунд через /start_roll")
    else:
        msg = bot.reply_to(message, f"⚠️ The round has already been launched.\n\n⚠️ Раунд уже запущен.")
        threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()

# ==== ОБРАБОТЧИК КОМАНДЫ /roll ====
@bot.message_handler(commands=['roll'])
@delete_command_after
def handle_roll_command(message):
    global roll_round_active, roll_results

    if str(message.chat.id) != CHAT_ID:
        return

    # Блокировка использования от имени ботов и каналов
    if message.from_user is None or message.from_user.is_bot:
        msg = bot.reply_to(message, f"⛔ Bots and channels cannot use this command.\n\n⛔ Боты и каналы не могут использовать эту команду.")
        threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
        return

    user_id = message.from_user.id
    display_name = message.from_user.first_name or "Игрок"
    username = message.from_user.username or str(user_id)

    # Старт раунда, если он не начат
    if not roll_round_active:
        msg = bot.reply_to(message, f"⚠️ Round has not started. Wait for the administrator to start it.\n\n⚠️ Раунд не начался. Ожидайте запуска от администратора.")
        threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
        return

    # Игрок уже бросал
    if str(user_id) in roll_results:
        msg = bot.reply_to(message, f"⛔ You have already rolled a number this round.\n\n⛔ Вы уже бросили число в этом раунде.")
        threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
        return

    # Генерация числа
    score = random.randint(0, 100)
    roll_results[str(user_id)] = (score, display_name, username)
    msg = bot.reply_to(message, f"{display_name} 🎲 {score}")
    logging.info(f"{username} использовал /roll: {score}")

    # Удаляем сообщение через 2.5 минуты
    threading.Timer(150, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()

# ==== Завершение раунда Roll ====
def finish_roll_round():
    global roll_round_active, roll_results

    if not roll_results:
        bot.send_message(CHAT_ID, f"⏱ There were no participants in the /roll round.\n\n⏱ В раунде /roll не было участников.")
        roll_round_active = False
        return

    # Ищем наибольшее число
    max_score = max(score for score, _, _ in roll_results.values())
    winners = [(uid, name, username) for uid, (score, name, username) in roll_results.items() if score == max_score]

    mentions_for_msg = []
    mentions_for_log = []
    mentions_name = []
    name_by_uid = {}
    username_by_uid = {}

    for uid, name, username in winners:
        # Для сообщений — с @username, если есть
        mentions_for_msg.append(f"@{username}" if username else name)

        # Для логов — просто username, если есть, иначе name
        display_log = f"{username} ({uid})" if username else f"{name} ({uid})"
        mentions_for_log.append(display_log)

        mentions_name.append(name)
        name_by_uid[int(uid)] = name
        username_by_uid[int(uid)] = username if username else name

    if len(winners) == 1:
        # Победитель один
        winner_id, winner_name, winner_username = winners[0]
        scores[str(winner_id)] = scores.get(str(winner_id), 0) + 1
        save_scores(scores)
        mention = f"@{winner_username}" if winner_username else winner_name
        msg = bot.send_message(CHAT_ID, f"🏆 Round winner: {mention} with {max_score}!\n\n🏆 Победитель раунда: {mention} с результатом {max_score}!")
        logging.info(f"Победитель /roll: {winner_username} ({winner_id}) ({max_score})")
        
    else:
        # Ничья
        global reroll_enabled, reroll_mode, reroll_duel_queue, current_duel_players
        
        # В случае ничьей:
        reroll_enabled = True
        reroll_mode = 'tournament'
        reroll_duel_queue = [int(uid) for uid, _, _ in winners]
        first_id = reroll_duel_queue.pop(0)
        second_id = reroll_duel_queue.pop(0)
        current_duel_players = {first_id, second_id}
        bot.send_message(
            CHAT_ID,
            f"🤝 Tie between: {', '.join(mentions_for_msg)} with score {max_score}!\n\n/reroll enabled for tie-breaker.\n\n🤝 Ничья между: {', '.join(mentions_for_msg)} с результатом {max_score}!\n\n/reroll включён для определения победителя.\n\n"
            f"⚔️ First duel: {name_by_uid[first_id]} vs {name_by_uid[second_id]}\n⚔️ Первая дуель: {name_by_uid[first_id]} против {name_by_uid[second_id]}"
        )    
        logging.info(f"Ничья в /roll между: {', '.join(mentions_for_log)} ({max_score})")

    # Сброс раунда
    roll_results.clear()
    roll_round_active = False

# ==== ОБРАБОТЧИК КОМАНДЫ /stop_roll ====
@bot.message_handler(commands=['stop_roll'])
@delete_command_after
def handle_stop_roll(message):
    global roll_round_active, roll_results, reroll_enabled, reroll_temp_players, current_duel_players, reroll_duel_queue, reroll_mode

    if str(message.chat.id) != CHAT_ID:
        return

    user_id = message.from_user.id

    # Проверка: только админ может остановить
    try:
        member = bot.get_chat_member(message.chat.id, user_id)
        if member.status not in ['administrator', 'creator']:
            msg = bot.reply_to(message, f"⛔ Only the administrator can stop the tournament.\n\n⛔ Только администратор может остановить турнир.")
            threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
            return
    except Exception as e:
        logging.error(f"Ошибка при проверке прав администратора: {e}")
        msg = bot.reply_to(message, f"❌ Unable to verify rights.\n\n❌ Не удалось проверить права.")
        threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
        return

    # Сбрасываем все переменные турнира
    roll_round_active = False
    roll_results.clear()
    reroll_enabled = False
    reroll_temp_players.clear()
    current_duel_players.clear()
    reroll_duel_queue.clear()
    reroll_mode = 'free'

    bot.send_message(message.chat.id, f"🛑 The /roll round and tournament have been forcibly stopped.\n\n🛑 Раунд и турнир /roll были принудительно остановлены.")
    logging.info(f"{message.from_user.username or message.from_user.id} остановил раунд и турнир /roll через /stop_roll.")

# ==== ОБРАБОТЧИК КОМАНДЫ /reroll_on ====
@bot.message_handler(commands=['reroll_on'])
@delete_command_after
def handle_reroll_on(message):
    global reroll_enabled, reroll_mode, reroll_temp_players, current_duel_players, reroll_duel_queue
    if str(message.chat.id) != CHAT_ID:
        return

    try:
        member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ['administrator', 'creator']:
            msg = bot.reply_to(message, f"⛔ Available to administrators only.\n\n⛔ Доступно только администраторам.")
            threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
            return
    except Exception as e:
        logging.error(f"Ошибка при проверке прав администратора: {e}")
        msg = bot.reply_to(message, f"❌ Unable to verify rights.\n\n❌ Не удалось проверить права.")
        threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
        return

    reroll_enabled = True
    reroll_mode = 'free'
    reroll_temp_players.clear()
    current_duel_players.clear()
    reroll_duel_queue.clear()
    bot.reply_to(message, f"✅ The /reroll command is now enabled.\n\n✅ Команда /reroll теперь включена.")
    logging.info(f"{message.from_user.username or message.from_user.id} включил использование команды /reroll (режим: free)")

# ==== ОБРАБОТЧИК КОМАНДЫ /reroll_off ====
@bot.message_handler(commands=['reroll_off'])
@delete_command_after
def handle_reroll_off(message):
    global reroll_enabled
    if str(message.chat.id) != CHAT_ID:
        return

    try:
        member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ['administrator', 'creator']:
            msg = bot.reply_to(message, f"⛔ Available to administrators only.\n\n⛔ Доступно только администраторам.")
            threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
            return
    except Exception as e:
        logging.error(f"Ошибка при проверке прав администратора: {e}")
        msg = bot.reply_to(message, f"❌ Unable to verify rights.\n\n❌ Не удалось проверить права.")
        threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
        return

    reroll_enabled = False
    reroll_temp_players.clear()
    bot.reply_to(message, f"⛔ The /reroll command is now disabled.\n\n⛔ Команда /reroll теперь отключена.")
    logging.info(f"{message.from_user.username or message.from_user.id} отключил использование команды /reroll")

# === ПАМЯТЬ ДЛЯ ИГРЫ ===
game_state = {}                                             # Храним одного игрока
CHOICES = {
    '🪨': 'Камень',
    '✂️': 'Ножницы',
    '📄': 'Бумага'
}
BEATS = {
    '🪨': '✂️',
    '✂️': '📄',
    '📄': '🪨'
}

# ==== ОБРАБОТЧИК КОМАНДЫ /reroll ====
@bot.message_handler(commands=['reroll'])
@delete_command_after
def handle_reroll_command(message):
    try:
        global reroll_enabled, reroll_temp_players, reroll_mode
        global current_duel_players, reroll_duel_queue

        if str(message.chat.id) != CHAT_ID:
            return

        user_id = message.from_user.id
        username = message.from_user.username
        display_name = message.from_user.first_name or "Игрок"
        mention = f"@{username}" if username else display_name

        # === Проверка доступа к команде ===
        if not reroll_enabled:
            msg = bot.reply_to(message, "⛔ The /reroll command is temporarily disabled.\n\n⛔ Команда /reroll временно отключена.")
            threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
            return

        # Если active duel идёт (после /roll), разрешены только игроки из current_duel_players
        if reroll_mode == 'tournament' and user_id not in current_duel_players:
            msg = bot.reply_to(message, "⛔ Only current duel participants can use /reroll.\n⛔ Только участники текущей дуэли могут использовать /reroll.")
            threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
            return

        # === Генерация выбора ===
        emoji = random.choice(list(CHOICES.keys()))
        name = CHOICES[emoji]                                 # Название выбора

        # Первый игрок
        if not game_state:
            game_state[user_id] = (name, emoji, display_name, username)
            msg = bot.reply_to(message, f"{emoji}\n\nWaiting for the second player...\nЖдём второго игрока...")
            threading.Timer(60, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
            return

        # Если второй игрок - сравнение
        for opponent_id, (opp_name, opp_emoji, opp_display, opp_username) in list(game_state.items()):
            if opponent_id == user_id:
                bot.reply_to(message, f"⛔ You have already played. We are waiting for another player.\n\n⛔ Вы уже сыграли. Ждём другого игрока.")
                return

            # [лог] Второй игрок бросил
            logging.info(f"{username or user_id} бросил: {name}")
            logging.info(f"{opp_username or opponent_id} бросил: {opp_name}")

            # Второй игрок сыграл
            game_state.clear()

            player1_line = f"{opp_display} {opp_emoji}"
            player2_line = f"{emoji} {display_name}"
            result = f"{player1_line}\n\n{player2_line}\n\n"

            # === Ничья ===
            if emoji == opp_emoji:
                result += "🤝 It's a draw!\n🤝 Ничья!"
                logging.info("Результат игры: Ничья!")

                if reroll_mode == 'tournament':
                    # Те же игроки снова
                    current_duel_players = {user_id, opponent_id}
                    msg = bot.send_message(message.chat.id, result + "\n\n⚔️ Use /reroll again.\n⚔️ Используйте /reroll снова.")
                else:
                    reroll_temp_players = {user_id, opponent_id}
                    msg = bot.send_message(message.chat.id, result + "\n\n⚔️ Use /reroll again to resolve tie.\n⚔️ Используйте /reroll снова для определения победителя.")
                threading.Timer(60, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
                return

            # === Победитель ===
            if emoji != opp_emoji:
                if BEATS[emoji] == opp_emoji:
                    winner_id = user_id
                    winner_display = display_name
                    winner_mention = f"@{username}" if username else display_name
                    winner_log_name = username if username else display_name
                else:
                    winner_id = opponent_id
                    winner_display = opp_display
                    winner_mention = f"@{opp_username}" if opp_username else opp_display
                    winner_log_name = opp_username if opp_username else opp_display

            result += f"🎉 Winner: {winner_mention}!\n🎉 Победитель: {winner_mention}!\n"

            scores[str(winner_id)] = scores.get(str(winner_id), 0) + 1
            save_scores(scores)

            logging.info(f"Победитель: {winner_log_name} ({winner_id})")

            if reroll_mode == 'tournament':
                if reroll_duel_queue:
                    next_id = reroll_duel_queue.pop(0)
                    current_duel_players = {winner_id, next_id}

                    try:
                        next_user = bot.get_chat_member(message.chat.id, next_id).user
                        next_name = next_user.first_name or f"ID:{next_id}"
                    except:
                        next_name = f"ID:{next_id}"

                    # Используем display_name победителя (winner_mention был first_name ранее)
                    current_name = winner_display or f"ID:{winner_id}"

                    result += (
                        f"\n\n⚔️ Next duel: {current_name} vs {next_name}\n"
                        f"⚔️ Следующая дуэль: {current_name} против {next_name}"
                    )
                    bot.send_message(message.chat.id, result)
                else:
                    try:
                        final_user = bot.get_chat_member(message.chat.id, winner_id).user
                        final_username = f"{final_user.username}" if final_user.username else final_user.first_name or f"ID:{final_user.id}"
                        final_name = final_user.first_name or f"ID:{winner_id}"
                    except:
                        final_name = f"ID:{winner_id}"

                    result += (
                        f"\n\n🏆 Grand Champion: {final_name}\n"
                        f"🏆 Финальный победитель турнира: {final_name}"
                    )
                    bot.send_message(message.chat.id, result)
                    logging.info(f"Победитель /roll: {final_username} ({final_user.id})")
                    reroll_enabled = False
                    current_duel_players.clear()

            else:
                reroll_temp_players.clear()
                bot.send_message(message.chat.id, result)
                return

    except Exception as e:
        logging.error(f"Ошибка в /reroll: {e}")

# ==== ОБРАБОТЧИК КОМАНДЫ /score ====
def escape_md(text):
    """Экранирует спецсимволы MarkdownV2"""
    return re.sub(r'([_\*\[\]\(\)~`>#+\-=|{}.!\\])', r'\\\1', str(text))

# Показать лидерборд (с пагинацией)
@bot.message_handler(commands=['score'])
@delete_command_after
def handle_score_command(message):
    show_score_page(message.chat.id, page=0, reply_to=message.message_id)

# Общая функция отображения страницы лидерборда
def show_score_page(chat_id, page=0, reply_to=None):
    per_page = 10
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    start = page * per_page
    end = start + per_page
    page_scores = sorted_scores[start:end]

    try:
        if not page_scores:
            msg = bot.send_message(chat_id, "🏆 There are no winners yet.")
            threading.Timer(30, lambda: safe_delete_message(message.chat.id, msg.message_id)).start()
            return

        rows = []

        # Эмодзи для топ-3
        for i, (user_id, points) in enumerate(page_scores, start=1 + start):
            if i == 1:
                place = "🥇"
            elif i == 2:
                place = "🥈"
            elif i == 3:
                place = "🥉"
            else:
                place = f"{i}."

            try:
                user = bot.get_chat_member(chat_id, int(user_id)).user
                name = f"@{user.username}" if user.username else user.first_name
                display_name = message.from_user.first_name or "Игрок"
            except:
                name = f"ID:{user_id}"

            rows.append((place, name, f"{points} $LEG"))

        # Вычисляем максимальные ширины
        col1 = max(len(r[0]) for r in rows)
        col2 = max(len(r[1]) for r in rows)
        col3 = max(len(r[2]) for r in rows)

        # Строим таблицу
        lines = []
        lines.append("#".ljust(col1) + " | " + "Purtorican".ljust(col2) + " | " + "Score".rjust(col3))
        lines.append("-" * (col1 + col2 + col3 + 6))
        for place, name, score in rows:
            line = place.ljust(col1) + " | " + display_name.ljust(col2) + " | " + score.rjust(col3)
            lines.append(line)

        text = "*🏆 Top players:*\n\n```" + "\n".join(lines) + "```"

        # Кнопки: Назад | В начало | Вперёд
        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"score_{page-1}"))
        if page > 1:
            buttons.append(InlineKeyboardButton("⏮️ В начало", callback_data="score_0"))
        if end < len(sorted_scores):
            buttons.append(InlineKeyboardButton("➡️ Далее", callback_data=f"score_{page+1}"))

        markup = InlineKeyboardMarkup()
        if buttons:
            markup.row(*buttons)

        msg = bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup, reply_to_message_id=reply_to)
        threading.Timer(300, lambda: safe_delete_message(chat_id, msg.message_id)).start()
        logging.info(f"{user.username} использует команду /score")

    except Exception as e:
        logging.error(f"Ошибка в /score: {e}")

# Обработка кнопок
@bot.callback_query_handler(func=lambda call: call.data.startswith("score_"))
def handle_score_pagination(call: CallbackQuery):
    try:
        page = int(call.data.split("_")[1])
        bot.delete_message(call.message.chat.id, call.message.message_id)
        show_score_page(call.message.chat.id, page)
    except Exception as e:
        logging.error(f"Ошибка в пагинации лидерборда: {e}")

# ==== СОЗДАЁМ СПИСОК ФРАЗ ====
GOOD_MORNING_PHRASES = [
    "Good morning Red Planet",
    "Wake up, Legends!",
    "It's time to do good",
    "Good morning Purtoricans!",
    "Happy new day, Red Planetians!"
]

GOOD_NIGHT_PHRASES = [
    "Good night Red Planet",
    "Until tomorrow, Legends!",
    "The Red Planet guards your sleep!",
    "Sleep tight, warrior of light",
    "Sweet dreams, Purtorican"
]

# ==== ОБРАБОТЧИК КОМАНДЫ /gm ====
@bot.message_handler(commands=['gm'])
@delete_command_after
def handle_gm_command(message):
    try:
        if str(message.chat.id) == CHAT_ID:
            text = random.choice(GOOD_MORNING_PHRASES)
            if create_greeting_image(text, "morning.jpg", "gm_output.jpg"):
                with open("gm_output.jpg", "rb") as photo:
                    bot.send_photo(message.chat.id, photo, caption=f"Всем бодрого утра, друзья! ☕\nGood morning to all, friends! ☕")
                logging.info(f"{message.from_user.username or message.from_user.id} использовал /gm: {text}")
    except Exception as e:
        logging.error(f"Ошибка в /gm: {e}")

# ==== ОБРАБОТЧИК КОМАНДЫ /gn ====        
@bot.message_handler(commands=['gn'])
@delete_command_after
def handle_gn_command(message):
    try:
        if str(message.chat.id) == CHAT_ID:
            text = random.choice(GOOD_NIGHT_PHRASES)
            if create_greeting_image(text, "night.jpg", "gn_output.jpg"):
                with open("gn_output.jpg", "rb") as photo:
                    bot.send_photo(message.chat.id, photo, caption=f"Спокойной ночи, Легенды! 🌌\nGood night, Legends! 🌌")
                logging.info(f"{message.from_user.username or message.from_user.id} использовал /gn: {text}")
    except Exception as e:
        logging.error(f"Ошибка в /gn: {e}")

# === ПЕРЕСЫЛКА СООБЩЕНИЙ В DISCORD ===
# Обработка фото
@bot.message_handler(content_types=['photo'])
def handle_photo_message(message):

    # Пропускаем старые фото (например, после запуска бота)
    if not is_recent(message):
        logging.info("[SKIP] Старое фото сообщение пропущено.")
        return

    if str(message.chat.id) != CHAT_ID:
        return

    # Получаем имя пользователя для отображения
    user_display = message.from_user.full_name or f"@{message.from_user.username}" if message.from_user.username else "Unknown"

	# Аватарка (одна общая кастомная)
    avatar_url = DISCORD_AVATAR_URL

    if message.reply_to_message:
        reply_author = message.reply_to_message.from_user.full_name or "Unknown"
        reply_text = message.reply_to_message.text or message.reply_to_message.caption or "<медиа>"
        quoted = f"Ответ на сообщение от **{reply_author}**:\n> {reply_text}\n\n"
    else:
        quoted = ""

    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Создаём временный файл и сохраняем туда фото
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
            temp_path = tmp_file.name
            logging.info(f"[TEMP FILE] Сохраняем фото во временный файл: {temp_path}")
            tmp_file.write(downloaded_file)

        caption = message.caption or ""
        full_caption = f"{quoted}{caption}"
        send_photo_to_discord(full_caption, temp_path, username=user_display, avatar_url=avatar_url)

    except Exception as e:
        logging.error(f"Ошибка при обработке фото: {e}")

    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            logging.warning(f"❗ Не удалось удалить временный файл: {e}")

# ==== НАСТРОЙКА РАСПИСАНИЯ (1 раз в 4 часа) ====
schedule.every(4).hours.do(send_price_image)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# ==== ЗАПУСК ====
logging.info("Бот запущен.")

# Поток для schedule
threading.Thread(target=run_scheduler, daemon=True).start()

# Основной поток - polling
try:
    bot.remove_webhook()
    bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
finally:
    # Удаляем lock-файл при завершении
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
        logging.info("Lock-файл удалён. Бот завершил работу.")
