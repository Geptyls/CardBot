import os
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ======== НАСТРОЙКИ ========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

# Модель на Hugging Face (русскую или мультиязычную можно заменить)
MODEL_URL = "https://api-inference.huggingface.co/models/facebook/blenderbot-400M-distill"
HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"}

# ======== ПАРСИНГ КАРТОЧКИ ТОВАРА ========
def parse_wb_card(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.find("h1")
        title = title.text.strip() if title else "Название не найдено"

        desc = soup.find("p", {"class": "product-description__text"})
        desc = desc.text.strip() if desc else "Описание отсутствует"

        rating = soup.find("span", {"class": "product-review__rating"})
        rating = rating.text.strip() if rating else "Рейтинг не указан"

        return f"Название: {title}\nОписание: {desc}\nРейтинг: {rating}"
    except Exception as e:
        return f"Ошибка при парсинге: {e}"

# ======== АНАЛИЗ ЧЕРЕЗ ИИ ========
def analyze_text(text):
    prompt = f"Проанализируй карточку товара Wildberries и дай краткий анализ:\n{text}\n\nДай оценку (0-10) и рекомендации по улучшению карточки."

    payload = {"inputs": prompt, "parameters": {"max_new_tokens": 250}}
    response = requests.post(MODEL_URL, headers=HEADERS, json=payload)

    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list) and len(data) > 0 and "generated_text" in data[0]:
            return data[0]["generated_text"]
        else:
            return str(data)
    else:
        return f"Ошибка Hugging Face API: {response.status_code}, {response.text}"

# ======== ОБРАБОТЧИКИ БОТА ========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Отправь мне ссылку на товар Wildberries, и я выдам анализ и рекомендации.")

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "wildberries.ru" not in url:
        await update.message.reply_text("Отправь ссылку на товар Wildberries 🔗")
        return

    await update.message.reply_text("⏳ Анализирую карточку, подожди пару секунд...")

    parsed = parse_wb_card(url)
    result = analyze_text(parsed)

    await update.message.reply_text(f"📊 Анализ:\n{result}")

# ======== ЗАПУСК ========
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze))

    print("✅ Бот запущен!")
    app.run_polling()


