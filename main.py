from flask import Flask, request, jsonify
import telebot
from telebot import types
import requests
from datetime import datetime, timedelta
import threading
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")

bot = telebot.TeleBot(BOT_TOKEN)
tasks = {}

def add_to_notion(text, remind_time):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Задача": {"title": [{"text": {"content": text}}]},
            "Дата": {"date": {"start": remind_time.strftime("%Y-%m-%dT%H:%M:00")}},
            "Статус": {"status": {"name": "Not started"}}
        }
    }
    try:
        requests.post(url, headers=headers, json=payload)
        print("Добавлено в Notion")
    except Exception as e:
        print("Ошибка Notion:", e)

def send_reminder(chat_id, text, task_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Сделано", callback_data=f"done_{task_id}"),
        types.InlineKeyboardButton("Перенести на час", callback_data=f"later_{task_id}"),
        types.InlineKeyboardButton("Удалить", callback_data=f"delete_{task_id}")
    )
    bot.send_message(chat_id, f"*Напоминание:*\n{text}", parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle(message):
    text = message.text.strip()
    chat_id = message.chat.id
    remind_time = datetime.now() + timedelta(minutes=1)  # тест

    lower = text.lower()
    if " в " in lower:
        try:
            t = lower.split(" в ", 1)[1].split()[0]
            h, m = map(int, t.split(":"))
            remind_time = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
            if remind_time < datetime.now():
                remind_time += timedelta(days=1)
            text = text.split(" в ", 1)[0].strip()
        except: pass
    elif " на " in lower:
        try:
            t = lower.split(" на ", 1)[1].split()[0]
            h, m = map(int, t.split(":"))
            remind_time = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
            if remind_time < datetime.now():
                remind_time += timedelta(days=1)
            text = text.split(" на ", 1)[0].strip()
        except: pass
    elif "через " in lower:
        try:
            num = int(lower.split("через ", 1)[1].split()[0])
            remind_time = datetime.now() + timedelta(hours=num)
            text = text.split("через ", 1)[0].strip()
        except: pass

    task_id = str(int(time.time() * 1000))
    tasks[task_id] = {"chat_id": chat_id, "text": text, "time": remind_time}

    add_to_notion(text, remind_time)
    bot.reply_to(message, "Принято")

    delay = (remind_time - datetime.now()).total_seconds()
    if delay > 0:
        threading.Timer(delay, send_reminder, [chat_id, text, task_id]).start()

@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    data = c.data
    tid = data.split("_", 1)[1]
    if tid not in tasks: return

    if data.startswith("done"):
        bot.edit_message_text(f"*Выполнено:*\n{tasks[tid]['text']}", c.message.chat.id, c.message.message_id, parse_mode="Markdown")
    elif data.startswith("later"):
        new_time = tasks[tid]["time"] + timedelta(hours=1)
        tasks[tid]["time"] = new_time
        bot.edit_message_text(f"*Перенесено на {new_time.strftime('%H:%M')}:*\n{tasks[tid]['text']}", c.message.chat.id, c.message.message_id, parse_mode="Markdown")
        delay = (new_time - datetime.now()).total_seconds()
        if delay > 0:
            threading.Timer(delay, send_reminder, [tasks[tid]["chat_id"], tasks[tid]["text"], tid]).start()
    elif data.startswith("delete"):
        bot.delete_message(c.message.chat.id, c.message.message_id)
    del tasks[tid]

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return jsonify({'status': 'ok'})

@app.route('/')
def index():
    return "Бот работает на Render!"

if __name__ == '__main__':
    print("Бот запущен на Render...")
    bot.infinity_polling(none_stop=True)
