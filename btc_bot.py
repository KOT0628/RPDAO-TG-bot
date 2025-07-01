import os
import sys
import psutil
import random
import requests
from PIL import Image, ImageDraw, ImageFont
import datetime
import time
import telebot
from requests.exceptions import ReadTimeout
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

# Пишем текущий PID в файл
with open(LOCK_FILE, "w") as f:
    f.write(str(os.getpid()))

# Инициализируем клиента
bot = telebot.TeleBot(TOKEN)

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

# ==== ОБРАБОТЧИК КОМАНДЫ /price ====
@bot.message_handler(commands=['price'])
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

# ==== ЗАПУСК РАУНДА ROLL ====
roll_round_active = False
roll_results = {}  # user_id: (score, display_name, username)
roll_timer = None

def start_roll_round(chat_id):
    global roll_round_active, roll_results, roll_timer

    if roll_round_active:
        return False                                        # Раунд уже идёт

    roll_round_active = True
    roll_results = {}
    roll_timer = Timer(120, finish_roll_round)              # 2 минуты
    roll_timer.start()

    bot.send_message(chat_id, f"🎲 The round has begun! Use /roll to roll a number from 0 to 100. You have 2 minutes!\n🎲 Раунд начался! Используйте /roll, чтобы бросить число от 0 до 100. У вас 2 минуты!")
    return True

# ==== ОБРАБОТЧИК КОМАНДЫ /start_roll ====
@bot.message_handler(commands=['start_roll'])
def handle_start_roll(message):
    if str(message.chat.id) != CHAT_ID:
        return

    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)

    # Проверка: только админ может стартовать
    try:
        member = bot.get_chat_member(message.chat.id, user_id)
        if not (member.status in ['administrator', 'creator']):
            bot.reply_to(message, f"⛔ Only the administrator can start a round.\n⛔ Только администратор может запустить раунд.")
            return
    except Exception as e:
        logging.error(f"Ошибка при проверке прав администратора: {e}")
        bot.reply_to(message, f"❌ Unable to verify rights.\n❌ Не удалось проверить права.")
        return

    # Запускаем раунд
    if start_roll_round(message.chat.id):
        logging.info(f"{username} запустил раунд через /start_roll")
    else:
        bot.reply_to(message, f"⚠️ The round has already been launched.\n⚠️ Раунд уже запущен.")

# ==== ОБРАБОТЧИК КОМАНДЫ /roll ====
@bot.message_handler(commands=['roll'])
def handle_roll_command(message):
    global roll_round_active, roll_results

    if str(message.chat.id) != CHAT_ID:
        return

    user_id = message.from_user.id
    display_name = message.from_user.first_name or "Игрок"
    username = message.from_user.username or str(user_id)

    # Старт раунда, если он не начат
    if not roll_round_active:
        bot.reply_to(message, f"⚠️ Round has not started. Wait for the administrator to start it.\n⚠️ Раунд не начался. Ожидайте запуска от администратора.")
        return

    # Игрок уже бросал
    if str(user_id) in roll_results:
        bot.reply_to(message, f"⛔ You have already rolled a number this round.\n⛔ Вы уже бросили число в этом раунде.")
        return

    # Генерация числа
    score = random.randint(0, 100)
    roll_results[str(user_id)] = (score, display_name, username)
    bot.reply_to(message, f"🎲 {score}")
    logging.info(f"{username} использовал /roll: {score}")

# ==== Завершение раунда Roll ====
def finish_roll_round():
    global roll_round_active, roll_results

    if not roll_results:
        bot.send_message(CHAT_ID, f"⏱ There were no participants in the /roll round.\n⏱ В раунде /roll не было участников.")
        roll_round_active = False
        return

    # Ищем наибольшее число
    max_score = max(score for score, _, _ in roll_results.values())
    winners = [(uid, name, username) for uid, (score, name, username) in roll_results.items() if score == max_score]

    if len(winners) == 1:
        # Победитель один
        winner_id, winner_name, winner_username = winners[0]
        scores[str(winner_id)] = scores.get(str(winner_id), 0) + 1
        save_scores(scores)
        bot.send_message(CHAT_ID, f"🏆 Round winner: {winner_name} with {max_score}!\n🏆 Победитель раунда: {winner_name} с результатом {max_score}!")
        logging.info(f"Победитель /roll: {winner_username} ({winner_id}) ({max_score})")
    else:
        winner_names = [name for _, name, _ in winners]
        winner_usernames = [username for _, _, username in winners]

        # Ничья
        bot.send_message(
            CHAT_ID,
            f"🤝 Tie between: {', '.join(winner_names)} with score {max_score}!\n\nUse /reroll to determine the winner.\n🤝 Ничья между: {', '.join(winner_names)} с результатом {max_score}!\n\nИспользуйте /reroll, чтобы определить победителя."
        )
        logging.info(f"Ничья в /roll между: {', '.join(winner_usernames)} ({max_score})")

    # Сброс раунда
    roll_results.clear()
    roll_round_active = False

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
def handle_reroll_command(message):
    try:
        if str(message.chat.id) != CHAT_ID:
            return

        user_id = message.from_user.id
        display_name = message.from_user.first_name or "Игрок"

        emoji = random.choice(list(CHOICES.keys()))
        name = CHOICES[emoji]                               # Название выбора
        
        # [лог] Первый игрок бросил
        logging.info(f"{message.from_user.username or message.from_user.id} бросил: {name}")

        # Первый игрок
        if not game_state:
            game_state[user_id] = (name, emoji, display_name)
            bot.reply_to(message, f"{emoji}\n\nWaiting for the second player...\nЖдём второго игрока...")
            return

        # Если второй игрок — сравнение
        for opponent_id, (opp_name, opp_emoji, opp_display) in game_state.items():
            if opponent_id == user_id:
                bot.reply_to(message, "⛔ You have already played. We are waiting for another player.\n⛔ Вы уже сыграли. Ждём другого игрока.")
                return

            # [лог] Второй игрок бросил
            logging.info(f"{message.from_user.username or message.from_user.id} бросил: {name}")
            logging.info(f"{message.from_user.username or message.from_user.id} бросил: {opp_name}")
            
            # Второй игрок сыграл
            game_state.clear()

            result = f"{opp_display} {opp_emoji}\n\n{emoji} {display_name}\n\n"

            if emoji == opp_emoji:
                result += f"🤝 Draw!\n🤝 Ничья!"
                logging.info("Результат игры: Ничья!")
            elif BEATS[emoji] == opp_emoji:
                result += f"🎉 {display_name} wins!\n🎉 Победил {display_name}!"
                scores[str(user_id)] = scores.get(str(user_id), 0) + 1
                save_scores(scores)
                logging.info(f"Победитель: {message.from_user.username or message.from_user.id}")
            else:
                result += f"🎉 {opp_display} wins!\n🎉 Победил {opp_display}!"
                scores[str(opponent_id)] = scores.get(str(opponent_id), 0) + 1
                save_scores(scores)
                logging.info(f"Победитель: {message.from_user.username or message.from_user.id}")

            bot.send_message(message.chat.id, result)
            return
    except Exception as e:
        logging.error(f"Ошибка в /reroll: {e}")

# ==== ОБРАБОТЧИК КОМАНДЫ /score ====
@bot.message_handler(commands=['score'])
def handle_score_command(message):
    try:
        if not scores:
            bot.reply_to(message, f"🏆 There are no winners yet.\n🏆 Ещё нет победителей.")
            return

        # Сортировка по убыванию очков
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = sorted_scores[:5]

        text = "🏆 Top players:\n🏆 Топ игроков:\n"
        for i, (user_id, points) in enumerate(top, 1):
            try:
                user = bot.get_chat_member(message.chat.id, int(user_id)).user
                name = user.first_name or f"ID:{user_id}"
            except:
                name = f"ID:{user_id}"
            text += f"{i}. {name} - {points} $LEG\n"

        bot.reply_to(message, text)
    except Exception as e:
        logging.error(f"Ошибка в /score: {e}")

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
@bot.message_handler(func=lambda message: True, content_types=['text', 'photo'])
def handle_all_messages(message):
    if str(message.chat.id) != CHAT_ID:
        return

    # Получаем имя пользователя для отображения
    if message.from_user.full_name:
        user_display = message.from_user.full_name
    elif message.from_user.username:
        user_display = f"@{message.from_user.username}"
    else:
        user_display = "Unknown"

    # Аватарка (одна общая кастомная)
    avatar_url = DISCORD_AVATAR_URL

    # Проверка, является ли сообщение ответом
    if message.reply_to_message:
        reply_author = message.reply_to_message.from_user.full_name or "Unknown"
        reply_text = message.reply_to_message.text or message.reply_to_message.caption or "<медиа>"
        quoted = f"Ответ на сообщение от **{reply_author}**:\n> {reply_text}\n\n"
    else:
        quoted = ""

    # Обработка текстового сообщения
    if message.content_type == 'text':
        full_text = f"{quoted} {message.text}"
        send_to_discord(full_text, username=user_display, avatar_url=avatar_url)

    # Обработка фото
    elif message.content_type == 'photo':
        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            # Создаём временный файл и сохраняем туда фото
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                tmp_file.write(downloaded_file)
                temp_path = tmp_file.name

            caption = message.caption or ""
            full_caption = f"{quoted} {caption}"
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
