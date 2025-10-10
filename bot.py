import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from bs4 import BeautifulSoup

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_API_KEY = os.getenv("HF_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME")

# -----------------------------
# Функция запроса к Hugging Face
# -----------------------------
def analyze_with_hf(text):
    url = f"https://api-inference.huggingface.co/models/{MODEL_NAME}"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    payload = {"inputs": f"Анализируй карточку товара Wildberries и дай рекомендации:\n{text}"}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and "generated_text" in data[0]:
            return data[0]["generated_text"]
        return str(data)
    except Exception as e:
        return f"Ошибка HF API: {e}"

# -----------------------------
# Парсинг карточки WB
# -----------------------------
def parse_wb_card(url):
    try:
        r = requests.get(url, timeout=10)
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
    result = analyze_with_hf(parsed)
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
