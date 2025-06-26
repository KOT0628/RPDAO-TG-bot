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

# === Загрузка переменных окружения ===
load_dotenv()

# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("logs.txt", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

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

# ==== НАСТРОЙКИ ====
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = str(os.getenv("CHAT_ID"))  # Приводим к строке для единообразия
BACKGROUND_PATH = 'background.jpg'
FONT_PATH = 'SpicyRice-Regular.ttf'

# Проверка обязательных переменных
if not TOKEN or not CHAT_ID:
    logging.critical("TELEGRAM_TOKEN или CHAT_ID не заданы в переменных окружения.")
    sys.exit(1)

# Инициализируем бота
bot = telebot.TeleBot(TOKEN)

# ==== ПОЛУЧЕНИЕ ЦЕНЫ ====
def get_btc_price():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url, timeout=10)
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
        font = ImageFont.truetype(FONT_PATH, 100)

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
        logging.error("Ошибка при отправке: {e}")

# ==== НАСТРОЙКА РАСПИСАНИЯ (1 раз в 4 часа) ====
schedule.every(4).hours.do(send_price_image)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

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
            logging.info(f"Команда /reroll от {message.from_user.username or message.from_user.id}: {choice_name} {choice_emoji}")
    except Exception as e:
        logging.error(f"Ошибка в обработчике /reroll: {e}")

# ==== ОБРАБОТЧИК КОМАНДЫ /gm ====
@bot.message_handler(commands=['gm'])
def handle_gm_command(message):
    try:
        if str(message.chat.id) == CHAT_ID:
            if create_greeting_image("Good morning Red Planet ☀️", "morning.jpg", "gm_output.jpg"):
                with open("gm_output.jpg", "rb") as photo:
                    bot.send_photo(message.chat.id, photo, caption=f"Всем бодрого утра, друзья! ☕\nGood morning to all, friends! ☕")
                logging.info(f"{message.from_user.username or message.from_user.id} использовал /gm")
    except Exception as e:
        logging.error(f"Ошибка в /gm: {e}")

# ==== ОБРАБОТЧИК КОМАНДЫ /gn ====
@bot.message_handler(commands=['gn'])
def handle_gn_command(message):
    try:
        if str(message.chat.id) == CHAT_ID:
            if create_greeting_image("Good night Red Planet 🌙", "night.jpg", "gn_output.jpg"):
                with open("gn_output.jpg", "rb") as photo:
                    bot.send_photo(message.chat.id, photo, caption=f"Спокойной ночи, Легенды! 🌌\nGood night, Legends! 🌌")
                logging.info(f"{message.from_user.username or message.from_user.id} использовал /gn")
    except Exception as e:
        logging.error(f"Ошибка в /gn: {e}")

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
