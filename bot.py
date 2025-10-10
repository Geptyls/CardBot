# bot.py
import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from bs4 import BeautifulSoup

# Загружаем переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")


# -----------------------------
# Функция анализа через ЯндексGPT
# -----------------------------
def analyze_with_yandex(text):
    url = "https://llm.api.cloud.yandex.net/llm/v1/completions"
    headers = {
        "Authorization": f"Bearer {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "yandex/gpt-pro",
        "folderId": FOLDER_ID,
        "input": [
            {"role": "user", "content": f"Анализируй карточку товара Wildberries и дай оценку:\n{text}"}
        ],
        "maxOutputTokens": 400,
        "temperature": 0.5
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["output"][0]["content"][0]["text"]
    except Exception as e:
        return f"Ошибка Yandex API: {e}"


# -----------------------------
# Функция парсинга карточки WB
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
# Хэндлеры бота
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь ссылку на карточку товара Wildberries, и я дам анализ.")


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "wildberries.ru" not in url:
        await update.message.reply_text("Отправь ссылку на товар Wildberries 🔗")
        return

    await update.message.reply_text("⏳ Анализирую карточку...")

    parsed = parse_wb_card(url)
    result = analyze_with_yandex(parsed)

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
