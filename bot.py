import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# -----------------------------
# Функция запроса к Qwen
# -----------------------------
def analyze_with_qwen(text):
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "qwen-max-2025-01-25",
        "messages": [
            {"role": "system", "content": "Ты эксперт по анализу карточек товаров Wildberries."},
            {"role": "user", "content": f"Анализируй карточку товара и дай рекомендации:\n{text}"}
        ],
        "temperature": 0.5,
        "max_tokens": 400
    }
    try:
        response = requests.post(QWEN_URL, headers=headers, json=data, timeout=20)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Ошибка Qwen API: {e}"

# -----------------------------
# Парсинг карточки WB
# -----------------------------
def parse_wb_card(url):
    try:
        r = requests.get(url, timeout=10)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("h1")
        description = soup.find("div", {"class": "about__text"})
        title_text = title.text.strip() if title else "Название не найдено"
        desc_text = description.text.strip() if description else "Описание не найдено"
        return f"{title_text}\n{desc_text}\nСсылка: {url}"
    except Exception as e:
        return f"Ошибка парсинга карточки: {e}"

# -----------------------------
# Хэндлеры Telegram
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь ссылку на карточку Wildberries, и я дам анализ.")

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "wildberries.ru" not in url:
        await update.message.reply_text("Отправь ссылку на товар Wildberries 🔗")
        return

    await update.message.reply_text("⏳ Анализирую карточку...")
    parsed = parse_wb_card(url)
    result = analyze_with_qwen(parsed)
    await update.message.reply_text(f"📊 Анализ:\n{result}")

# -----------------------------
# Запуск бота
# -----------------------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze))
    print("Бот запущен...")
    app.run_polling()

