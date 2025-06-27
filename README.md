# 🔴 Red Planet Telegram Bot

Этот бот автоматически:
- отправляет изображение с текущей ценой Bitcoin в Telegram-чат Red Planet DAO каждые 4 часа,
- обрабатывает команды `/price`, `/reroll`, `/gm`, `/gn`,
- пересылает все сообщения и изображения из Telegram в Discord.

---

## 📦 Функционал

- 🕓 Автопубликация изображения с ценой BTC каждые 4 часа
- 🖼 Генерация изображений на фоне с текстом:
  - `/price` — BTC цена
  - `/gm` — доброе утро (случайная фраза)
  - `/gn` — спокойной ночи (случайная фраза)
- 🎲 Команда `/reroll` — случайный выбор: 🪨 камень, ✂️ ножницы или 📄 бумага
- 🔁 Автоматическая пересылка всех сообщений и фото в Discord
- 📝 Подробное логирование в файл `logs.txt`
- 🛡️ Защита от двойного запуска (через `bot.lock`)

---

## 🛠 Требования

- Python 3.8+
- Telegram Bot Token
- Telegram Chat ID (например, `-1001234567890`)
- Discord Webhook URL (для пересылки в Discord)
- Изображения:
  - `background.jpg` — для BTC цены
  - `morning.jpg` — для команды `/gm`
  - `night.jpg` — для команды `/gn`
- Шрифт: `SpicyRice-Regular.ttf`

---

## 🔧 Установка

1. Клонируй репозиторий или скачай скрипт:

```bash
git clone https://github.com/KOT0628/RPDAO-TG-bot.git
cd rpdao-btc-bot
```

2. Установи зависимости:

```bash
pip install -r requirements.txt
```

Содержимое `requirements.txt`:
```
python-dotenv
pyTelegramBotAPI
Pillow
psutil
schedule
requests
```

3. Создай `.env` файл со следующими переменными:

```env
TELEGRAM_TOKEN=your_telegram_bot_token
CHAT_ID=-100xxxxxxxxxx
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

4. Помести в корень проекта файлы:

 - `background.jpg`          # для /price
 - `morning.jpg`             # для /gm
 - `night.jpg`               # для /gn
 - `SpicyRice-Regular.ttf`   # шрифт

---

## 🚀 Запуск

```bash
python btc_bot.py
```

Бот начнёт работу и будет:
- каждые 4 часа публиковать изображение с ценой BTC,
- реагировать на команды `/price` и `/reroll`.

---

## 🗂 Структура проекта

```
project/
├── background.jpg               # Фон для BTC
├── morning.jpg                  # Фон для доброго утра
├── night.jpg                    # Фон для спокойной ночи
├── SpicyRice-Regular.ttf        # Шрифт
├── bot.py                       # Основной код бота
├── .env                         # Переменные окружения
├── logs.txt                     # Логи
└── requirements.txt             # Зависимости
```

---

## 🧹 Завершение работы

При завершении скрипта автоматически удаляется `bot.lock`, чтобы бот мог быть перезапущен без конфликтов.

---

## ⚠️ Примечания

- Если бот не отвечает — проверь лог `logs.txt`.
- Убедись, что переменные окружения заданы корректно.
- Если бот запускается в группе, добавь его как администратора с правами на отправку сообщений и медиа.

---

## 👤 Автор

Создан с ❤️ [Red Planet DAO](https://linktr.ee/rpdao)  
Автор: [KOT0628](https://github.com/KOT0628)

---

## 📝 Лицензия

RPDAO
