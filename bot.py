import os
import sqlite3
import time
import threading
import queue
import asyncio
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# === НАСТРОЙКИ — ОБЯЗАТЕЛЬНО ЗАМЕНИ ===
BOT_TOKEN = "8304828272:AAER7l8wyoZA-8jlhaYfyxteId5Kt2lGa-A"  # ← из @BotFather
GEMINI_API_KEY = "AIzaSyBxYoaTIukZqxAMZaTISJKjoPRpdzW9e4U"  # ← из Google AI Studio
YOUR_TELEGRAM_ID = 647688105  # ← твой ID (узнай у @userinfobot)

# Инициализация ИИ
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# === БАЗА ===
def get_db():
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            free_analyses INTEGER DEFAULT 3,
            is_premium BOOLEAN DEFAULT 0
        )
    ''')
    conn.commit()
    return conn

# === ОЧЕРЕДЬ ИИ ===
task_queue = queue.Queue()

def ai_worker(loop):
    """Фоновый поток для ИИ"""
    while True:
        task = task_queue.get()
        if task is None:
            break
        user_id, prompt, is_premium = task
        try:
            response = model.generate_content(
                f"Ты — эксперт по Wildberries. Проанализируй карточку и дай ПРАКТИЧНЫЙ совет селлеру.\n\n{prompt}\n\nОтвет дай в 1–2 предложения. Без воды. На русском.",
                safety_settings=[
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                ]
            )
            result = response.text.strip()
        except Exception as e:
            result = "✅ Карточка в хорошей форме! (ИИ временно недоступен)"

        # Безопасная отправка в Telegram из другого потока
        asyncio.run_coroutine_threadsafe(
            send_analysis_result(user_id, result, is_premium),
            loop
        )
        task_queue.task_done()

# === ОТПРАВКА РЕЗУЛЬТАТА ===
async def send_analysis_result(user_id, result, is_premium):
    db = get_db()
    cur = db.cursor()
    if not is_premium:
        cur.execute("INSERT OR IGNORE INTO users (user_id, free_analyses) VALUES (?, 3)", (user_id,))
        cur.execute("UPDATE users SET free_analyses = free_analyses - 1 WHERE user_id = ?", (user_id,))
        db.commit()
        cur.execute("SELECT free_analyses FROM users WHERE user_id = ?", (user_id,))
        new_free = cur.fetchone()[0]
        footer = f"\n\nℹ️ Осталось бесплатных: {new_free}" if new_free > 0 else "\n\n💡 Хотите безлимит? Напишите в поддержку!"
    else:
        footer = ""
    await bot.send_message(user_id, f"🧠 <b>ИИ-анализ:</b>\n{result}{footer}", parse_mode="HTML")

# === ПАРСЕР WB ===
def parse_wb_card(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(resp.text, 'html.parser')
    title = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Нет названия"
    price_meta = soup.find('meta', {'itemprop': 'price'})
    price = float(price_meta['content']) if price_meta else 0
    images = len([img for img in soup.find_all('img', {'src': True}) if 'wbstatic' in img['src']])
    return {"title": title, "price": price, "images_count": images}

# === БОТ ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

def main_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔍 Анализ карточки"))
    kb.add(KeyboardButton("ℹ️ FAQ"), KeyboardButton("💬 Поддержка"))
    return kb

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привет! Я — CardDoctor.\n\n"
        "Пришлите ссылку на карточку Wildberries — проанализирую с помощью ИИ.",
        reply_markup=main_kb()
    )

@dp.message_handler(lambda m: m.text == "ℹ️ FAQ")
async def faq_cmd(message: types.Message):
    await message.answer(
        "📘 <b>FAQ:</b>\n\n"
        "1. <b>Как пользоваться?</b>\n   → Нажмите «Анализ карточки» → пришлите ссылку на Wildberries.\n\n"
        "2. <b>Сколько бесплатно?</b>\n   → 3 анализа. Потом — премиум.\n\n"
        "3. <b>Как получить премиум?</b>\n   → Нажмите «Поддержка» → напишите мне в ЛС.",
        parse_mode="HTML"
    )

@dp.message_handler(lambda m: m.text == "💬 Поддержка")
async def support_cmd(message: types.Message):
    await message.answer(
        "📩 Напишите мне напрямую:",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("👉 Перейти в ЛС", url=f"tg://user?id={YOUR_TELEGRAM_ID}")
        )
    )

@dp.message_handler(lambda m: m.text == "🔍 Анализ карточки")
async def ask_link(message: types.Message):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT free_analyses, is_premium FROM users WHERE user_id = ?", (message.from_user.id,))
    row = cur.fetchone()
    free = row[0] if row else 3
    is_premium = row[1] if row else False

    if not is_premium and free <= 0:
        await message.answer(
            "❌ Закончились бесплатные анализы.",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("💎 Получить Премиум", url=f"tg://user?id={YOUR_TELEGRAM_ID}")
            )
        )
        return
    await message.answer("Пришлите ссылку на карточку Wildberries:")

@dp.message_handler(lambda m: "wildberries.ru" in m.text)
async def analyze_card(message: types.Message):
    user_id = message.from_user.id
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT free_analyses, is_premium FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    free = row[0] if row else 3
    is_premium = row[1] if row else False

    if not is_premium and free <= 0:
        await message.answer("Сначала получите Премиум-доступ.")
        return

    try:
        data = parse_wb_card(message.text)
        await message.answer("🔍 Анализирую... (1–2 минуты)")

        prompt = (
            f"Категория: Одежда\n"
            f"Название: \"{data['title']}\"\n"
            f"Фото: {data['images_count']} шт\n"
            f"Цена: {data['price']} ₽"
        )

        # Добавляем задачу в очередь
        task_queue.put((user_id, prompt, is_premium))

    except Exception as e:
        await message.answer("Ошибка. Проверьте ссылку.")

# Команда для выдачи премиума (только тебе)
@dp.message_handler(commands=['premium'])
async def give_premium(message: types.Message):
    if message.from_user.id == YOUR_TELEGRAM_ID:
        try:
            target_id = int(message.get_args())
            db = get_db()
            cur = db.cursor()
            cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (target_id,))
            cur.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (target_id,))
            db.commit()
            await message.answer(f"✅ Премиум выдан {target_id}")
        except:
            await message.answer("UsageId: /premium USER_ID")

# === ЗАПУСК ===
if __name__ == '__main__':
    print("✅ Бот запускается...")
    # Запускаем фоновый поток ИИ с передачей loop'а
    loop = asyncio.get_event_loop()
    threading.Thread(target=ai_worker, args=(loop,), daemon=True).start()
    executor.start_polling(dp, skip_updates=True)
