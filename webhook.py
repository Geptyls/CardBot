import asyncio
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

import gspread
import pytz
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup
from google.oauth2.service_account import Credentials

# === НАСТРОЙКИ ===
# ⚠️ ВАЖНО: Вынесите токен в переменные окружения!
TOKEN = os.getenv("TELEGRAM_TOKEN", "8255039090:AAGZsu3WmAy-YcFWGhSgUpu4WqsQ69zFvow")
WEBHOOK_PATH = "/webhook"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = 8000
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "647688105"))
GOOGLE_SHEET_NAME = "Lovely Time Shop"
CREDENTIALS_FILE = "credentials.json"
CERT_PATH = os.getenv("CERT_PATH", "/root/bot/certs/cert.pem")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://194.87.98.45/webhook")

# Маппинг категорий для очистки от эмодзи
CATEGORY_CLEAN_MAP = {
    "🕯️ Свечи": "Свечи",
    "🌿 Диффузоры": "Диффузоры",
    "🌸 Аромасаше": "Аромасаше",
    "🚗 Автомобильные диффузоры": "Автомобильные диффузоры"
}

# Обратный маппинг для отображения
CATEGORY_DISPLAY_MAP = {v: k for k, v in CATEGORY_CLEAN_MAP.items()}

# Глобальное состояние пользователей
user_state = {}

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# === GOOGLE SHEETS ИНИЦИАЛИЗАЦИЯ ===
def init_google_sheets():
    """Инициализирует подключение к Google Sheets."""
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        if not Path(CREDENTIALS_FILE).exists():
            print(f"❌ Файл {CREDENTIALS_FILE} не найден!")
            sys.exit(1)

        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
        client = gspread.authorize(creds)
        sh = client.open(GOOGLE_SHEET_NAME)

        return {
            "aromas": sh.worksheet("Ароматы"),
            "categories": sh.worksheet("Категории"),
            "orders": sh.worksheet("Заказы"),
            "stocks": sh.worksheet("Остатки"),
            "norms": sh.worksheet("Нормы")
        }
    except Exception as e:
        print(f"❌ Ошибка подключения к Google Sheets: {e}")
        sys.exit(1)

sheets = init_google_sheets()


# === УТИЛИТЫ ===
def clean_category(text: str) -> str:
    """Очищает название категории от эмодзи."""
    return CATEGORY_CLEAN_MAP.get(text.strip(), text.strip())


def get_active_aromas():
    """Возвращает список активных ароматов."""
    try:
        records = sheets["aromas"].get_all_records()
        return [r for r in records if str(r.get('Активен?', '')).lower() in ('да', 'true')]
    except Exception as e:
        print("Ошибка загрузки ароматов:", e)
        return []


def get_parameters_for_category(category: str):
    """Возвращает параметры для категории."""
    try:
        records = sheets["categories"].get_all_records()
        params = set()
        for row in records:
            if str(row.get('Категория', '')).strip() == category:
                param = str(row.get('Параметр', '')).strip()
                if param and param not in ("", "—"):
                    params.add(param)
        return sorted(params) if params else []
    except Exception as e:
        print("Ошибка загрузки параметров:", e)
        return []


def get_price(category: str, parameter: str = None) -> str:
    """Возвращает цену для категории и параметра."""
    try:
        records = sheets["categories"].get_all_records()
        for row in records:
            cat_match = str(row.get('Категория', '')).strip() == category
            if not cat_match:
                continue

            table_param = str(row.get('Параметр', '')).strip()
            if parameter is None or parameter == "":
                if table_param in ("", "—"):
                    price = row.get('Цена', '—')
                    return str(price).replace('.0', '') if str(price).endswith('.0') else str(price)
            else:
                if table_param == parameter:
                    price = row.get('Цена', '—')
                    return str(price).replace('.0', '') if str(price).endswith('.0') else str(price)
        return "—"
    except Exception as e:
        print("Ошибка загрузки цены:", e)
        return "—"


def get_aroma_by_name(name):
    """Находит аромат по названию."""
    aromas = get_active_aromas()
    for a in aromas:
        if a.get('Название аромата') == name:
            return a
    return None


def get_norm_ml(category: str, parameter: str = None) -> float:
    """Возвращает норму расхода отдушки (в мл) для категории."""
    try:
        norms = sheets["norms"].get_all_records()
        key = category
        if category == "Диффузоры" and parameter:
            key = f"Диффузоры / {parameter}"
        elif category == "Автомобильные диффузоры":
            key = "Автомобильные диффузоры"

        for row in norms:
            if row.get('Категория') == key:
                val = row.get('Объём на 1 шт (мл)', 0)
                return float(str(val).replace(',', '.'))
        return 0.0
    except Exception as e:
        print("Ошибка загрузки норм:", e)
        return 0.0


def get_stock_ml(aroma_id: str) -> float:
    """Возвращает остаток отдушки (в мл) по аромату."""
    try:
        stocks = sheets["stocks"].get_all_records()
        for row in stocks:
            if str(row.get('Аромат ID')).strip() == str(aroma_id).strip():
                val = row.get('Остаток (мл)', 0)
                return float(str(val).replace(',', '.'))
        return 0.0
    except Exception as e:
        print("Ошибка загрузки остатков:", e)
        return 0.0


def is_aroma_available(aroma_id: str, category: str, parameter: str = None, quantity: int = 1) -> bool:
    """Проверяет доступность аромата для заказа."""
    norm_per_item = get_norm_ml(category, parameter)
    total_needed = norm_per_item * quantity
    stock = get_stock_ml(aroma_id)
    return stock >= total_needed


def get_max_quantity(aroma_id: str, category: str, parameter: str = None) -> int:
    """Возвращает максимальное количество товара, которое можно произвести."""
    norm = get_norm_ml(category, parameter)
    stock = get_stock_ml(aroma_id)
    if norm <= 0 or stock <= 0:
        return 0
    return int(stock // norm)


def deduct_stock(aroma_id: str, category: str, parameter: str = None, quantity: int = 1):
    """Списывает отдушку при оформлении заказа."""
    norm_per_item = get_norm_ml(category, parameter)
    total_deduct = norm_per_item * quantity

    if total_deduct <= 0:
        return

    try:
        stocks = sheets["stocks"].get_all_values()
        headers = stocks[0]
        id_col = headers.index('Аромат ID')
        stock_col = headers.index('Остаток (мл)')

        for i, row in enumerate(stocks[1:], start=2):
            if len(row) > id_col and row[id_col] == aroma_id:
                current = get_stock_ml(aroma_id)
                new_stock = max(0, current - total_deduct)
                sheets["stocks"].update_cell(i, stock_col + 1, str(new_stock))
                return
    except Exception as e:
        print(f"❌ Ошибка в deduct_stock: {e}")


def record_order(order_data):
    """Записывает заказ в Google Sheets."""
    moscow_tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(moscow_tz).strftime("%d.%m.%Y %H:%M")
    row_number = len(sheets["orders"].get_all_values())
    row = [
        row_number,
        now,
        order_data['telegram_id'],
        order_data['name'],
        order_data['category'],
        order_data['aroma'],
        order_data['aroma_type'],
        order_data['parameter'] or '—',
        order_data['quantity'],
        order_data['comment'] or '',
        'Новый'
    ]
    sheets["orders"].append_row(row)


# === ХЕНДЛЕРЫ ===
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    for cat in CATEGORY_CLEAN_MAP.keys():
        keyboard.add(cat)

    await message.answer(
        "Добро пожаловать в пространство LOVELY TIME!\n"
        "Здесь вы найдёте свечи, диффузоры и саше, созданные с заботой о Вашем уюте.\n\n"
        "Что Вас интересует?",
        reply_markup=keyboard
    )
    user_state[message.chat.id] = {'step': 'main_menu'}


@dp.message_handler(commands=['cancel'])
async def cancel_last_order(message: types.Message):
    chat_id = message.chat.id
    try:
        all_values = sheets["orders"].get_all_values()
        if not all_values:
            await message.answer("Таблица заказов пуста.")
            return

        headers = all_values[0]
        orders = all_values[1:]

        try:
            id_col = headers.index('Telegram ID')
            status_col = headers.index('Статус')
        except ValueError:
            await message.answer("Ошибка: в таблице нет колонок 'Telegram ID' или 'Статус'.")
            return

        target_row_index = None
        for i, row in enumerate(reversed(orders)):
            if len(row) > id_col and len(row) > status_col:
                if str(row[id_col]) == str(chat_id) and row[status_col] == "Новый":
                    target_row_index = len(orders) - i
                    break

        if target_row_index is None:
            await message.answer("У вас нет активных заказов для отмены.")
            return

        sheets["orders"].update_cell(target_row_index + 1, status_col + 1, "Отменён")
        await message.answer("Ваш последний заказ успешно отменён.\nСпасибо, что были с нами! ❤️")

    except Exception as e:
        print("Ошибка при отмене:", e)
        await message.answer("Не удалось отменить заказ. Попробуйте позже.")


async def show_aroma_types(chat_id, category, parameter):
    """Показывает типы ароматов."""
    aromas = get_active_aromas()
    types = sorted(set(a['Основной тип'] for a in aromas if a.get('Основной тип')))
    perfumery_exists = any(str(a.get('Парфюмерный?', '')).lower() in ('да', 'true') for a in aromas)
    if perfumery_exists:
        types.append("Парфюмерные")

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    for t in types:
        keyboard.add(t)
    keyboard.add("⬅️ Назад")
    await bot.send_message(chat_id, "Какое настроение вы хотите создать?", reply_markup=keyboard)


async def show_order_summary(chat_id, state):
    """Показывает сводку заказа."""
    comment = state.get('comment', '') or "—"
    msg = "🔍 <b>Пожалуйста, проверьте свой заказ!</b>\n\n"
    msg += f"👤 Имя: {state.get('name', '—')}\n"
    msg += f"🕯️ Аромат: {state['aroma']}\n"

    category = state['category']
    parameter = state.get('parameter')

    if category == "Диффузоры" and parameter and parameter != '—':
        msg += f"💧 Объём: {parameter}\n"
    elif category == "Автомобильные диффузоры" and parameter and parameter != '—':
        msg += f"🚗 Крепление: {parameter}\n"
    elif parameter and parameter != '—':
        msg += f"⚙️ Параметр: {parameter}\n"

    msg += f"🔢 Количество: {state.get('quantity', 1)} шт\n"
    msg += f"💬 Комментарий: {comment}\n"
    msg += f"\n💰 Цена: {state.get('price', '—')} ₽ за шт"

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("🕯️ Изменить аромат")

    if category == "Диффузоры":
        keyboard.row("💧 Изменить объём")
    elif category == "Автомобильные диффузоры":
        keyboard.row("🚗 Изменить крепление")
    elif parameter and parameter != '—':
        keyboard.row("⚙️ Изменить параметр")

    keyboard.row("🔢 Изменить количество")
    keyboard.row("💬 Добавить/изменить комментарий")
    keyboard.row("✅ Подтвердить заказ")
    keyboard.row("🏠 Главное меню")

    await bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=keyboard)
    user_state[chat_id] = {**state, 'step': 'confirming_order'}


async def finalize_order(chat_id, state, comment):
    """Завершает оформление заказа."""
    # Списание отдушки
    try:
        deduct_stock(
            state['aroma_id'],
            state['category'],
            state.get('parameter'),
            state.get('quantity', 1)
        )
    except Exception as e:
        print("Ошибка списания отдушки:", e)

    order = {
        'telegram_id': chat_id,
        'name': state.get('name', ''),
        'category': state['category'],
        'aroma': state['aroma'],
        'aroma_type': state['aroma_type'],
        'parameter': state['parameter'],
        'quantity': state.get('quantity', 1),
        'comment': comment
    }
    record_order(order)

    # Сообщение клиенту
    msg_client = f"Спасибо за заказ, {state.get('name', '')}! ❤️\n\n"
    msg_client += f"🕯️ {state['aroma']}\n"
    if state['parameter'] and state['parameter'] != '—':
        msg_client += f"({state['parameter']})\n"
    msg_client += f"\nКол-во: {state.get('quantity', 1)} шт\n"
    if comment:
        msg_client += f"\nКомментарий: {comment}\n"
    msg_client += "\nВаш заказ в работе — скоро я пришлю детали.\n\nНаслаждайтесь атмосферой LOVELY TIME 🌸"
    msg_client += "\n❗ Если вы передумаете — просто напишите /cancel в любой момент для отмены заказа."

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🆕 Новый заказ")
    await bot.send_message(chat_id, msg_client, reply_markup=keyboard)

    # Уведомление админу
    if ADMIN_CHAT_ID:
        msg_admin = (
            f"🔔 <b>НОВЫЙ ЗАКАЗ!</b>\n\n"
            f"👤 Имя: {state.get('name', '')}\n"
            f"🆔 ID: <code>{chat_id}</code>\n"
            f"📦 Категория: {state['category']}\n"
            f"🕯️ Аромат: {state['aroma']}\n"
            f"🔢 Кол-во: {state.get('quantity', 1)}\n"
        )
        if state['parameter'] and state['parameter'] != '—':
            msg_admin += f"⚙️ Параметр: {state['parameter']}\n"
        if comment:
            msg_admin += f"💬 Комментарий: {comment}\n"

        contact_link = f"<a href='tg://user?id={chat_id}'>Открыть чат с клиентом</a>"
        msg_admin += f"\n{contact_link}"

        try:
            await bot.send_message(ADMIN_CHAT_ID, msg_admin, parse_mode="HTML")
        except Exception as e:
            print("Не удалось отправить уведомление админу:", e)

    # Сброс состояния
    user_state.pop(chat_id, None)


def get_filtered_aromas(aromas, aroma_type, category, parameter):
    """Фильтрует ароматы по типу и доступности."""
    if aroma_type == "Парфюмерные":
        filtered = [a for a in aromas if str(a.get('Парфюмерный?', '')).lower() in ('да', 'true')]
    else:
        filtered = [a for a in aromas if a.get('Основной тип') == aroma_type]

    available_aromas = []
    for a in filtered:
        aroma_id = a.get('Аромат ID')
        if aroma_id and is_aroma_available(aroma_id, category, parameter, quantity=1):
            available_aromas.append(a)

    return available_aromas


async def handle_main_menu(message, chat_id, text, state):
    """Обрабатывает главное меню."""
    clean_category_name = clean_category(text)

    if text.strip() in CATEGORY_CLEAN_MAP.keys():
        params = get_parameters_for_category(clean_category_name)
        if not params or (len(params) == 1 and params[0] == '—'):
            await show_aroma_types(chat_id, clean_category_name, None)
            user_state[chat_id] = {'step': 'selecting_aroma_type', 'category': clean_category_name, 'parameter': None}
        else:
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            for p in params:
                keyboard.add(p)

            prompt = "Выберите параметр:"
            if clean_category_name == "Диффузоры":
                prompt = "В каком объёме вы хотели бы аромат?"
            elif clean_category_name == "Автомобильные диффузоры":
                prompt = "Как удобнее крепить в машине? 🚗"

            await message.answer(prompt, reply_markup=keyboard)
            user_state[chat_id] = {'step': 'selecting_parameter', 'category': clean_category_name}


async def handle_selecting_aroma_type(message, chat_id, text, state):
    """Обрабатывает выбор типа аромата."""
    if text.strip() == "⬅️ Назад":
        await send_welcome(message)
        return

    category = state['category']
    parameter = state['parameter']
    all_aromas = get_active_aromas()

    available_aromas = get_filtered_aromas(all_aromas, text.strip(), category, parameter)

    if not available_aromas:
        await message.answer("К сожалению, в этой категории пока нет доступных ароматов.")
        await send_welcome(message)
        return

    names = sorted(set(a['Название аромата'] for a in available_aromas))
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    for name in names:
        keyboard.add(name)
    keyboard.add("⬅️ Назад")

    await message.answer(f"Ароматы в категории «{text}»:", reply_markup=keyboard)
    user_state[chat_id] = {
        **state,
        'step': 'selecting_aroma',
        'aroma_type': text
    }


async def handle_selecting_parameter(message, chat_id, text, state):
    """Обрабатывает выбор параметра."""
    if text.strip() == "⬅️ Назад":
        if state.get('editing'):
            await show_order_summary(chat_id, state)
        else:
            await send_welcome(message)
        return

    category = state['category']
    params = get_parameters_for_category(category)

    if text in params:
        new_state = {
            'step': 'selecting_aroma_type',
            'category': category,
            'parameter': text
        }
        if state.get('editing'):
            new_state.update({
                'editing': True,
                'name': state.get('name', ''),
                'quantity': state.get('quantity', 1),
                'comment': state.get('comment', ''),
                'price': state.get('price', '—'),
                'aroma': state.get('aroma', ''),
                'aroma_type': state.get('aroma_type', '')
            })
        user_state[chat_id] = new_state
        await show_aroma_types(chat_id, category, text)


async def handle_selecting_aroma(message, chat_id, text, state):
    """Обрабатывает выбор аромата."""
    if text.strip() == "⬅️ Назад":
        user_state[chat_id] = {
            'step': 'selecting_aroma_type',
            'category': state['category'],
            'parameter': state['parameter'],
        }
        await show_aroma_types(chat_id, state['category'], state['parameter'])
        return

    aroma = get_aroma_by_name(text)
    if not aroma:
        await message.answer("Аромат не найден. Выберите из списка.")
        return

    category = state['category']
    parameter = state['parameter']
    price_value = get_price(category, parameter)
    aroma_type_value = aroma.get('Основной тип', '—')
    aroma_id_value = aroma.get('Аромат ID', 'unknown')

    if state.get('editing'):
        new_state = {
            'step': 'confirming_order',
            'category': category,
            'parameter': parameter,
            'aroma': text,
            'aroma_type': aroma_type_value,
            'price': price_value,
            'name': state.get('name', ''),
            'quantity': state.get('quantity', 1),
            'comment': state.get('comment', ''),
            'aroma_id': aroma_id_value
        }
        user_state[chat_id] = new_state
        await show_order_summary(chat_id, new_state)
        return

    msg = f"🕯️ <b>{text}</b>\n"
    msg += f"Тип: {aroma_type_value}\n\n"
    msg += f"🌿 Верхние ноты: {aroma.get('Верхние ноты', '—')}\n"
    msg += f"💐 Средние ноты: {aroma.get('Средние ноты', '—')}\n"
    msg += f"🌰 Базовые ноты: {aroma.get('Базовые ноты', '—')}\n\n"
    if str(aroma.get('Парфюмерный?', '')).lower() in ('да', 'true'):
        msg += "✨ <i>Парфюмерная композиция</i>\n\n"
    msg += f"💰 Цена: {price_value} ₽"

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("✅ Добавить в заказ")
    keyboard.add("⬅️ Назад")

    await message.answer(msg, parse_mode="HTML", reply_markup=keyboard)
    user_state[chat_id] = {
        **state,
        'step': 'confirm_add',
        'aroma': text,
        'aroma_type': aroma_type_value,
        'price': price_value,
        'aroma_id': aroma_id_value
    }


async def handle_confirm_add(message, chat_id, text, state):
    """Обрабатывает подтверждение добавления в заказ."""
    if text.strip() == "⬅️ Назад":
        aromas = get_active_aromas()
        aroma_type = state.get('aroma_type')
        if not aroma_type:
            await send_welcome(message)
            return

        category = state['category']
        parameter = state['parameter']

        available_aromas = get_filtered_aromas(aromas, aroma_type, category, parameter)

        if not available_aromas:
            await message.answer("К сожалению, в этой категории нет доступных ароматов.")
            await send_welcome(message)
            return

        names = sorted(set(a['Название аромата'] for a in available_aromas))
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        for name in names:
            keyboard.add(name)
        keyboard.add("⬅️ Назад")

        await message.answer(f"Ароматы в категории «{aroma_type}»:", reply_markup=keyboard)
        user_state[chat_id] = {
            'step': 'selecting_aroma',
            'category': category,
            'parameter': parameter
        }
        return

    if "Добавить в заказ" in text:
        if state.get('editing'):
            new_state = {**state, 'step': 'confirming_order'}
            user_state[chat_id] = new_state
            await show_order_summary(chat_id, new_state)
        else:
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.add("⬅️ Назад")
            await message.answer("Сколько штук Вы хотите заказать?", reply_markup=keyboard)
            user_state[chat_id] = {**state, 'step': 'entering_quantity'}
        return

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("✅ Добавить в заказ")
    keyboard.add("⬅️ Назад")
    await message.answer(
        "Пожалуйста, нажмите кнопку «✅ Добавить в заказ», чтобы продолжить,\n"
        "или «⬅️ Назад», чтобы выбрать другой аромат.",
        reply_markup=keyboard
    )


async def handle_entering_quantity(message, chat_id, text, state):
    """Обрабатывает ввод количества."""
    if text.strip() == "⬅️ Назад":
        if state.get('editing'):
            original_state = {
                'step': 'confirming_order',
                'category': state['category'],
                'parameter': state.get('original_parameter', state.get('parameter')),
                'aroma': state['aroma'],
                'aroma_type': state['aroma_type'],
                'price': get_price(state['category'], state.get('original_parameter', state.get('parameter'))),
                'name': state['name'],
                'quantity': state.get('original_quantity', state.get('quantity', 1)),
                'comment': state.get('comment', ''),
                'aroma_id': state['aroma_id']
            }
            user_state[chat_id] = original_state
            await show_order_summary(chat_id, original_state)
            return
        else:
            aromas = get_active_aromas()
            aroma_type = state.get('aroma_type')
            if not aroma_type:
                await send_welcome(message)
                return

            category = state['category']
            parameter = state['parameter']

            available_aromas = get_filtered_aromas(aromas, aroma_type, category, parameter)

            if not available_aromas:
                await message.answer("К сожалению, в этой категории нет доступных ароматов.")
                await send_welcome(message)
                return

            names = sorted(set(a['Название аромата'] for a in available_aromas))
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            for name in names:
                keyboard.add(name)
            keyboard.add("⬅️ Назад")

            await message.answer(f"Ароматы в категории «{aroma_type}»:", reply_markup=keyboard)
            user_state[chat_id] = {
                'step': 'selecting_aroma',
                'category': category,
                'parameter': parameter
            }
            return

    try:
        quantity_value = int(text)
        if quantity_value < 1:
            await message.answer("Пожалуйста, введите положительное число.")
            return

        aroma_id = state.get('aroma_id')
        if not aroma_id:
            await message.answer("Ошибка: аромат не выбран.")
            return

        category = state['category']
        parameter = state.get('new_parameter') or state.get('parameter')

        if not is_aroma_available(aroma_id, category, parameter, quantity_value):
            max_qty = get_max_quantity(aroma_id, category, parameter)
            if max_qty <= 0:
                await message.answer("К сожалению, этого аромата нет в наличии. Попробуйте выбрать другой.")
                user_state[chat_id] = {
                    'step': 'selecting_aroma_type',
                    'category': category,
                    'parameter': parameter
                }
                await show_aroma_types(chat_id, category, parameter)
                return
            else:
                await message.answer(
                    f"На складе недостаточно отдушки для {quantity_value} шт.\n"
                    f"Максимум, что можно заказать: {max_qty} шт.\n"
                    f"Пожалуйста, введите новое количество, либо вернитесь к выбору ароматов кнопкой \"Назад\"."
                )
                return

        if state.get('editing'):
            new_state = {
                'step': 'confirming_order',
                'category': category,
                'parameter': parameter,
                'aroma': state.get('aroma'),
                'aroma_type': state.get('aroma_type'),
                'price': get_price(category, parameter),
                'name': state.get('name', ''),
                'quantity': quantity_value,
                'comment': state.get('comment', ''),
                'aroma_id': aroma_id
            }
            user_state[chat_id] = new_state
            await show_order_summary(chat_id, new_state)
        else:
            new_state = {**state, 'quantity': quantity_value, 'step': 'entering_name'}
            user_state[chat_id] = new_state
            await message.answer("Как вас зовут? Напишите, как вам удобно — Анна, Саша, Максим… ❤️")

    except ValueError:
        await message.answer("Пожалуйста, введите число.")


async def handle_entering_name(message, chat_id, text, state):
    """Обрабатывает ввод имени."""
    if text.strip() == "⬅️ Назад":
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("⬅️ Назад")
        await message.answer("Сколько штук Вы хотите заказать?", reply_markup=keyboard)
        user_state[chat_id] = {
            **{k: v for k, v in state.items() if k not in ('step', 'name')},
            'step': 'entering_quantity'
        }
        return

    if text.strip():
        new_state = {**state, 'name': text.strip(), 'step': 'awaiting_comment_choice'}
        user_state[chat_id] = new_state

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("💬 Оставить комментарий")
        keyboard.add("⏭️ Пропустить")
        keyboard.add("⬅️ Назад")

        await message.answer(
            "Хотите что-то особенное? Например:\n"
            "• Подарочная упаковка\n"
            "• Доставка после 18:00\n\n"
            "Нажмите «Оставить комментарий» или «Пропустить».",
            reply_markup=keyboard
        )
    else:
        await message.answer("Пожалуйста, введите ваше имя.")


async def handle_awaiting_comment_choice(message, chat_id, text, state):
    """Обрабатывает выбор комментария."""
    if text.strip() == "⏭️ Пропустить":
        user_state[chat_id] = {**state, 'comment': ''}
        await show_order_summary(chat_id, user_state[chat_id])
        return
    elif text == "💬 Оставить комментарий":
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("⬅️ Назад")
        await message.answer("Напишите ваш комментарий:", reply_markup=keyboard)
        user_state[chat_id] = {**state, 'step': 'entering_comment'}
        return
    elif text == "⬅️ Назад":
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("⬅️ Назад")
        await message.answer("Как вас зовут? Напишите, как вам удобно — Анна, Саша, Максим… ❤️", reply_markup=keyboard)
        user_state[chat_id] = {**state, 'step': 'entering_name'}
        return
    else:
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("💬 Оставить комментарий")
        keyboard.add("⏭️ Пропустить")
        keyboard.add("⬅️ Назад")
        await message.answer("Пожалуйста, выберите вариант из меню.", reply_markup=keyboard)


async def handle_entering_comment(message, chat_id, text, state):
    """Обрабатывает ввод комментария."""
    if text.strip() == "⬅️ Назад":
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("💬 Оставить комментарий")
        keyboard.add("⏭️ Пропустить")
        keyboard.add("⬅️ Назад")

        await message.answer(
            "Хотите что-то особенное? Например:\n"
            "• Подарочная упаковка\n"
            "• Доставка после 18:00\n\n"
            "Нажмите «Оставить комментарий» или «Пропустить».",
            reply_markup=keyboard
        )
        user_state[chat_id] = {
            **{k: v for k, v in state.items() if k != 'step'},
            'step': 'awaiting_comment_choice'
        }
        return

    new_state = {**state, 'comment': text, 'step': 'confirming_order'}
    user_state[chat_id] = new_state
    await show_order_summary(chat_id, new_state)


async def handle_editing_parameter(message, chat_id, text, state):
    """Обрабатывает редактирование параметра."""
    if text.strip() == "⬅️ Назад":
        await show_order_summary(chat_id, state)
        return

    category = state['category']
    params = get_parameters_for_category(category)
    if not params:
        await message.answer("Параметры недоступны.")
        return

    text_clean = text.strip()
    selected_param = None
    for p in params:
        if p.strip() == text_clean:
            selected_param = p
            break

    if not selected_param:
        await message.answer("Пожалуйста, выберите объём из списка.")
        return

    aroma_id = state.get('aroma_id')
    quantity = state.get('quantity', 1)

    if not is_aroma_available(aroma_id, category, selected_param, quantity):
        max_qty = get_max_quantity(aroma_id, category, selected_param)
        if max_qty <= 0:
            await message.answer("К сожалению, этого аромата нет в наличии для выбранного объёма.")
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            for p in params:
                keyboard.add(p)
            keyboard.add("⬅️ Назад")

            prompt = "Выберите другой объём:"
            if category == "Диффузоры":
                prompt = "В каком объёме вы хотели бы аромат?"
            elif category == "Автомобильные диффузоры":
                prompt = "Как удобнее крепить в машине? 🚗"

            await message.answer(prompt, reply_markup=keyboard)
            return
        else:
            await message.answer(
                f"На складе недостаточно отдушки для {quantity} шт. в объёме «{selected_param}».\n"
                f"Максимум, что можно заказать: {max_qty} шт."
            )

            user_state[chat_id] = {
                'step': 'entering_quantity',
                'category': category,
                'parameter': selected_param,
                'aroma': state.get('aroma'),
                'aroma_type': state.get('aroma_type'),
                'price': get_price(category, selected_param),
                'name': state.get('name', ''),
                'comment': state.get('comment', ''),
                'editing': True,
                'aroma_id': aroma_id,
                'original_parameter': state.get('current_parameter'),
                'original_quantity': state.get('quantity')
            }
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.add("⬅️ Назад")
            await message.answer("Пожалуйста, введите новое количество:", reply_markup=keyboard)
            return

    new_price = get_price(category, selected_param)
    aroma_name = state.get('aroma')
    aroma_type_value = state.get('aroma_type', '—')

    if aroma_name and aroma_type_value == '—':
        aroma_obj = get_aroma_by_name(aroma_name)
        if aroma_obj:
            aroma_type_value = aroma_obj.get('Основной тип', '—')

    new_state = {
        'step': 'confirming_order',
        'category': category,
        'parameter': selected_param,
        'aroma': aroma_name,
        'aroma_type': aroma_type_value,
        'price': new_price,
        'name': state.get('name', ''),
        'quantity': quantity,
        'comment': state.get('comment', ''),
        'editing': True,
        'aroma_id': aroma_id
    }
    user_state[chat_id] = new_state
    await show_order_summary(chat_id, new_state)


async def handle_confirming_order(message, chat_id, text, state):
    """Обрабатывает подтверждение заказа."""
    if text.strip() == "✅ Подтвердить заказ":
        await finalize_order(chat_id, state, state.get('comment', ''))
        return

    if text == "🏠 Главное меню":
        await send_welcome(message)
        return

    if text == "🕯️ Изменить аромат":
        user_state[chat_id] = {**state, 'step': 'selecting_aroma_type'}
        await show_aroma_types(chat_id, state['category'], state['parameter'])
        return

    category = state['category']

    if text == "💧 Изменить объём" and category == "Диффузоры":
        params = get_parameters_for_category(category)
        if not params:
            await message.answer("Объёмы временно недоступны.")
            return

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        for p in params:
            keyboard.add(p)
        keyboard.add("⬅️ Назад")

        await message.answer("В каком объёме вы хотели бы аромат?", reply_markup=keyboard)
        user_state[chat_id] = {
            'step': 'editing_parameter',
            'category': category,
            'aroma': state['aroma'],
            'aroma_type': state['aroma_type'],
            'name': state.get('name', ''),
            'quantity': state.get('quantity', 1),
            'comment': state.get('comment', ''),
            'aroma_id': state.get('aroma_id'),
            'current_parameter': state.get('parameter'),
            'editing': True
        }
        return

    if text == "🚗 Изменить крепление" and category == "Автомобильные диффузоры":
        params = get_parameters_for_category(category)
        if not params:
            await message.answer("Способы крепления временно недоступны.")
            return

        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        for p in params:
            keyboard.add(p)
        keyboard.add("⬅️ Назад")

        await message.answer("Как удобнее крепить в машине? 🚗", reply_markup=keyboard)
        user_state[chat_id] = {
            'step': 'editing_parameter',
            'category': category,
            'editing': True,
            'aroma': state['aroma'],
            'aroma_type': state['aroma_type'],
            'name': state.get('name', ''),
            'quantity': state.get('quantity', 1),
            'comment': state.get('comment', ''),
            'price': state.get('price', '—')
        }
        return

    if text == "🔢 Изменить количество":
        user_state[chat_id] = {**state, 'step': 'entering_quantity', 'editing': True}
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("⬅️ Назад")
        await message.answer("Сколько штук вам нужно?", reply_markup=keyboard)
        return

    if text == "💬 Добавить/изменить комментарий":
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("⬅️ Назад")
        await message.answer("Напишите ваш комментарий:", reply_markup=keyboard)
        user_state[chat_id] = {
            'step': 'entering_comment',
            'category': state['category'],
            'parameter': state['parameter'],
            'aroma': state['aroma'],
            'aroma_type': state['aroma_type'],
            'price': state['price'],
            'name': state.get('name', ''),
            'quantity': state.get('quantity', 1)
        }
        return

    await show_order_summary(chat_id, state)


@dp.message_handler()
async def handle_message(message: types.Message):
    """Основной обработчик сообщений."""
    chat_id = message.chat.id
    text = message.text.strip() if message.text else ""
    state = user_state.get(chat_id, {})

    # Очищаем категорию от эмодзи если нужно
    if 'category' in state and state.get('category') in CATEGORY_DISPLAY_MAP:
        state['category'] = CATEGORY_CLEAN_MAP.get(state['category'], state['category'])

    step = state.get('step', '')

    handlers = {
        'main_menu': handle_main_menu,
        'selecting_aroma_type': handle_selecting_aroma_type,
        'selecting_parameter': handle_selecting_parameter,
        'selecting_aroma': handle_selecting_aroma,
        'confirm_add': handle_confirm_add,
        'entering_quantity': handle_entering_quantity,
        'entering_name': handle_entering_name,
        'awaiting_comment_choice': handle_awaiting_comment_choice,
        'entering_comment': handle_entering_comment,
        'editing_parameter': handle_editing_parameter,
        'confirming_order': handle_confirming_order,
    }

    handler = handlers.get(step)
    if handler:
        await handler(message, chat_id, text, state)
    else:
        print(f"DEBUG: неизвестный шаг = {step}, текст = '{text}'")
        await send_welcome(message)


# === ВЕБХУК ===
async def on_startup(app):
    """Устанавливает вебхук при старте."""
    try:
        cert_path = Path(CERT_PATH)
        if cert_path.exists():
            await bot.set_webhook(
                url=WEBHOOK_URL,
                certificate=open(cert_path, 'rb')
            )
        else:
            await bot.set_webhook(url=WEBHOOK_URL)
        print("✅ Вебхук установлен")
    except Exception as e:
        print(f"❌ Ошибка установки вебхука: {e}")


async def handle_webhook(request):
    """Обрабатывает входящие webhook запросы."""
    try:
        update = types.Update(**await request.json())
        await dp.process_update(update)
        return web.Response()
    except Exception as e:
        print(f"Ошибка обработки webhook: {e}")
        return web.Response(status=400)


async def on_shutdown(app):
    """Корректно завершает работу бота."""
    print("🛑 Завершение работы...")
    await bot.delete_webhook()
    await bot.session.close()


# === ЗАПУСК ===
def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    app.router.add_post(WEBHOOK_PATH, handle_webhook)

    print(f"🚀 Запуск сервера на {WEBAPP_HOST}:{WEBAPP_PORT}")
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)


if __name__ == "__main__":
    main()
