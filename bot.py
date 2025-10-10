import os
import openai
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# -----------------------------
# Функция запроса к OpenAI GPT
# -----------------------------
def analyze_with_openai(text):
    try:
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=f"Анализируй карточку товара Wildberries и дай рекомендации:\n{text}",
            max_tokens=400,
            temperature=0.5
        )
        return response.choices[0].text.strip()
    except Exception as e:
        return f"Ошибка OpenAI API: {e}"

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
    result = analyze_with_openai(parsed)
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
