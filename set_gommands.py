import requests
import os
import json

TOKEN = "YOUR_TELEGRAM_TOKEN"

url = f"https://api.telegram.org/bot{TOKEN}/setMyCommands"

commands = [
    {"command": "price", "description": "Show current price $BTC"},
    {"command": "start_roll", "description": "Start ROLL (only admins)"},
    {"command": "roll", "description": "ROLL"},
    {"command": "reroll", "description": "Throw the dice"},
    {"command": "score", "description": "Leaderboard"},
    {"command": "gm", "description": "Good morning RPDAO"},
    {"command": "gn", "description": "Good night RPDAO"},
    {"command": "start", "description": "Restart RPDAO Harvester"},
]

response = requests.post(url, json={"commands": commands})

if response.ok:
    print("✅ Команды успешно установлены!")
else:
    print("❌ Ошибка при установке команд:")
    print(response.text)
    
