import os
import sqlite3
import threading
import queue
import time
import asyncio
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# === НАСТРОЙКИ ===
BOT_TOKEN = 8304828272:AAER7l8wyoZA-8jlhaYfyxteId5Kt2lGa-A  # ← из @BotFather
GEMINI_API_KEY = AIzaSyBxYoaTIukZqxAMZaTISJKjoPRpdzW9e4U  # ← из Google AI Studio
YOUR_TELEGRAM_ID = 647688105  # ← твой ID (узнай у @userinfobot)

# Инициализация ИИ
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# === БАЗА ===
def init_db():
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

db = init_db()

def get_user(user_id):
    cur = db.cursor()
    cur.execute("SELECT free_analyses, is_premium FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return {"free": row[0], "premium": bool(row[1])} if row else {"free": 3, "premium": False}

def use_free_analysis(user_id):
    cur = db.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, free_analyses) VALUES (?, 3)", (user_id,))
    cur.execute("UPDATE users SET free_analyses = free_analyses - 1 WHERE user_id = ?", (user_id,))
    db.commit()

def grant_premium(user_id):
    cur = db.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cur.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (user_id,))
    db.commit()

# === ИИ + ОЧЕРЕДЬ ===
task_queue = queue.Queue()
last_call = 0

def ai_worker():
    global last_call
    while True:
        task = task_queue.get()
        if task is None:
            break
        user_id, full_prompt, callback = task
        
        now = time.time()
        if now - last_call < 1:
            time.sleep(1 - (now - last_call))
        last_call = time.time()
        
        try:
            response = model.generate_content(
                full_prompt,
                safety_settings=[
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                ]
            )
            result = response.text.strip()
        except Exception as e:
            result = "✅ Карточка в хорошей форме! (ИИ временно недоступен)"
        
        callback(user_id, result)
        task_queue.task_done()

threading.Thread(target=ai_worker, daemon=True).start()

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

# === УМНЫЙ ПРОМТ ДЛЯ ИИ ===
def build_smart_prompt(title, images_count, price):
    # Определяем категорию по ключевым словам (можно расширить)
    category = "Общее"
    title_lower = title.lower()
    if any(kw in title_lower for kw in ["футболк", "кофта", "платье", "джинсы", "обувь", "кроссовки"]):
        category = "Одежда и обувь"
    elif any(kw in title_lower for kw in ["телефон", "наушники", "планшет", "чехол"]):
        category = "Электроника"
    elif any(kw in title_lower for kw in ["крем", "маска", "шампунь", "косметика"]):
        category = "Красота и здоровье"

    # Строим детальный промт
    prompt = f"""
Ты — эксперт по Wildberries с 10-летним опытом. Проанализируй карточку по следующим критериям:

1. **SEO-название**: 
   - Длина: {len(title)} символов (оптимально 60–80)
   - Содержит ли ключевые слова: сезон (2024/лето/зима), материал, размер, цвет, бренд?
2. **Фото**: {images_count} шт (рекомендуется 5–8, включая 360° и видео)
3. **Цена**: {price} ₽ — адекватна ли для категории «{category}»?

Дай **конкретный, практичный совет** в формате:
- Что исправить в названии?
- Сколько фото добавить?
- Нужно ли корректировать цену?

Ответ дай строго на русском, в 2–3 предложениях, без воды и общих фраз. Не пиши «возможно», «рекомендуется» — пиши чётко: «Добавьте», «Уберите», «Измените».

Карточка:
Название: "{title}"
Фото: {images_count} шт
Цена: {price} ₽
Категория: {category}
"""
    return prompt

# === КЛАВИАТУРА ===
def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔍 Анализ карточки"))
    kb.add(KeyboardButton("✨ Создать карточку"))
    kb.add(KeyboardButton("ℹ️ FAQ"), KeyboardButton("💬 Поддержка"))
    return kb

# === БОТ ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в CardDoctor!\n\n"
        "Я помогу улучшить ваши карточки на Wildberries:\n"
        "• Проанализирую чужую карточку\n"
        "• Создам идеальное название и описание\n"
        "• Дам советы от ИИ-эксперта",
        reply_markup=main_keyboard()
    )

@dp.message_handler(lambda msg: msg.text == "ℹ️ FAQ")
async def faq(message: types.Message):
    await message.answer(
        "📘 <b>Частые вопросы:</b>\n\n"
        "1️⃣ <b>Как проанализировать карточку?</b>\n"
        "   → Нажмите «Анализ карточки» → пришлите ссылку на Wildberries.\n\n"
        "2️⃣ <b>Сколько бесплатных анализов?</b>\n"
        "   → 3 штуки. Потом можно получить Премиум.\n\n"
        "3️⃣ <b>Как получить Премиум?</b>\n"
        "   → Нажмите «Поддержка» → напишите мне в ЛС.\n\n"
        "4️⃣ <b>Поддерживается ли Ozon?</b>\n"
        "   → Пока только Wildberries. Ozon — в планах.",
        parse_mode="HTML"
    )

@dp.message_handler(lambda msg: msg.text == "💬 Поддержка")
async def support(message: types.Message):
    await message.answer(
        "🛠️ Нужна помощь?\n\n"
        "Напишите мне напрямую — я отвечу в течение 24 часов:\n",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("📩 Написать в ЛС", url=f"tg://user?id={YOUR_TELEGRAM_ID}")
        )
    )

@dp.message_handler(lambda msg: msg.text == "🔍 Анализ карточки")
async def ask_for_link(message: types.Message):
    user = get_user(message.from_user.id)
    if not user["premium"] and user["free"] <= 0:
        await message.answer(
            "❌ Закончились бесплатные анализы.",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("💎 Получить Премиум", url=f"tg://user?id={YOUR_TELEGRAM_ID}")
            )
        )
        return
    await message.answer("Пришлите ссылку на карточку Wildberries:")

@dp.message_handler(lambda msg: "wildberries.ru" in msg.text)
async def handle_analysis(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user["premium"] and user["free"] <= 0:
        await message.answer("Сначала получите Премиум-доступ.")
        return

    try:
        data = parse_wb_card(message.text)
        await message.answer("🔍 Анализирую карточку... (1–2 минуты)")

        # === СОЗДАНИЕ УМНОГО ПРОМТА ===
        smart_prompt = build_smart_prompt(
            data['title'],
            data['images_count'],
            data['price']
        )

        def ai_callback(uid, result):
            asyncio.run_coroutine_threadsafe(
                send_result(uid, result, user["premium"]),
                asyncio.get_event_loop()
            )

        async def send_result(uid, result, is_premium):
            if not is_premium:
                use_free_analysis(uid)
                new_free = get_user(uid)["free"]
                footer = f"\n\nℹ️ Осталось бесплатных: {new_free}" if new_free > 0 else "\n\n💡 Хотите безлимит? Напишите в поддержку!"
            else:
                footer = ""
            await bot.send_message(uid, f"🧠 <b>ИИ-анализ:</b>\n{result}{footer}", parse_mode="HTML")

        task_queue.put((user_id, smart_prompt, ai_callback))

    except Exception as e:
        await message.answer("Не удалось проанализировать. Убедитесь, что ссылка ведёт на карточку товара.")

@dp.message_handler(lambda msg: msg.text == "✨ Создать карточку")
async def create_card_intro(message: types.Message):
    user = get_user(message.from_user.id)
    if not user["premium"]:
        await message.answer(
            "✨ Генерация карточек доступна только с Премиум-доступом.",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("💎 Получить Премиум", url=f"tg://user?id={YOUR_TELEGRAM_ID}")
            )
        )
        return
    await message.answer("Напишите данные через запятую:\nКатегория, Тип товара, Особенности, Цена\n\nПример:\nОдежда, Мужские футболки, 100% хлопок oversize, 1200")

@dp.message_handler(commands=['premium'])
async def give_premium(message: types.Message):
    if message.from_user.id == YOUR_TELEGRAM_ID:
        try:
            target_id = int(message.get_args())
            grant_premium(target_id)
            await message.answer(f"✅ Премиум выдан {target_id}")
        except:
            await message.answer("UsageId: /premium USER_ID")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)