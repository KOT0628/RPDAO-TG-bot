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
from dotenv import load_dotenv
import schedule
import logging
import threading
import json

# === ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ===
load_dotenv()

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = str(os.getenv("CHAT_ID"))  # Приводим к строке для единообразия
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
def send_photo_to_discord(caption, photo_path, username="RPDAO Telegram", avatar_url=None):
    if not DISCORD_WEBHOOK_URL:
        logging.warning("DISCORD_WEBHOOK_URL не задан")
        return
    try:
        with open(photo_path, 'rb') as f:
            files = {"file": f}
            payload = {
                "content": caption or "",
                "username": username,
                "avatar_url": avatar_url or DISCORD_AVATAR_URL
            }
            response = requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
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

# ==== ОБРАБОТЧИК КОМАНДЫ /reroll ====
@bot.message_handler(commands=['reroll'])
def handle_reroll_command(message):
    try:
        if str(message.chat.id) == CHAT_ID:
            options = {
                '🪨': 'Камень',
                '✂️': 'Ножницы',
                '📄': 'Бумага'
            }
            choice_emoji = random.choice(list(options.keys()))
            choice_name = options[choice_emoji]

            bot.reply_to(message, f"{choice_emoji}")
            logging.info(f"Команда /reroll от {message.from_user.username or message.from_user.id}: {choice_name}")
    except Exception as e:
        logging.error(f"Ошибка в обработчике /reroll: {e}")
        
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

    if message.content_type == 'text':
        send_to_discord(f"{message.text}", username=user_display, avatar_url=avatar_url)

    elif message.content_type == 'photo':
        photo_path = os.path.join(TEMP_DIR, "temp_photo.jpg")
        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            with open(photo_path, 'wb') as f:
                f.write(downloaded_file)

            caption = message.caption or ""
            full_caption = f"{caption}"
            send_photo_to_discord(full_caption, photo_path, username=user_display, avatar_url=avatar_url)
        except Exception as e:
            logging.error(f"Ошибка при обработке фото: {e}")
        finally:
            if os.path.exists(photo_path):
                os.remove(photo_path)

# ==== НАСТРОЙКА РАСПИСАНИЯ (1 раз в 4 часа) ====
schedule.every(4).hours.do(send_price_image)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# ==== ЗАПУСК ====
logging.info("Бот запущен. Ожидаем запуск каждые 4 часа и по команде /price...")

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
