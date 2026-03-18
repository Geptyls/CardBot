import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup

# === НАСТРОЙКИ ===
TOKEN = "8255039090:AAGc22jSl1MilEY7YDxbW6sosJJYOyJfCYQ"
WEBHOOK_PATH = "/webhook"
WEBAPP_HOST = "127.0.0.1"
WEBAPP_PORT = 8000

bot = Bot(token=TOKEN)
Bot.set_current(bot)  # ← ЭТА СТРОКА ОБЯЗАТЕЛЬНА для вебхука в aiogram 2.x
dp = Dispatcher(bot)

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
import os
import sys
# === АВАРИЙНАЯ ОСТАНОВКА СТАРЫХ ПРОЦЕССОВ ===
import os
import signal
import sys
print("🚀 Скрипт запущен!")
CATEGORY_CLEAN_MAP = {
    "🕯️ Свечи": "Свечи",
    "🌿 Диффузоры": "Диффузоры",
    "🌸 Аромасаше": "Аромасаше",
    "🚗 Автомобильные диффузоры": "Автомобильные диффузоры"
}
# Убиваем все процессы с таким же именем
def kill_existing_webhook():
    current_pid = os.getpid()
    for line in os.popen("ps ax -o pid,cmd"):
        parts = line.strip().split(maxsplit=1)
        if len(parts) < 2:
            continue
        pid, cmd = parts[0], parts[1]
        if "webhook.py" in cmd and int(pid) != current_pid:
            try:
                os.kill(int(pid), signal.SIGKILL)
                print(f"Убит старый процесс webhook.py: {pid}")
            except Exception as e:
                print(f"Не удалось убить {pid}: {e}")

# Вызываем при старте
kill_existing_webhook()
# ===========================================
# Защита от двойного запуска
if os.environ.get('RUNNING'):
    print("Бот уже запущен!")
    sys.exit(0)
os.environ['RUNNING'] = '1'

TELEGRAM_TOKEN = "8255039090:AAGc22jSl1MilEY7YDxbW6sosJJYOyJfCYQ"
ADMIN_CHAT_ID = 647688105  # ← замени на свой Telegram ID
GOOGLE_SHEET_NAME = "Lovely Time Shop"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
client = gspread.authorize(creds)
sh = client.open("Lovely Time Shop")  # ← сначала sh

sheet_aromas = sh.worksheet("Ароматы")
sheet_categories = sh.worksheet("Категории")
sheet_orders = sh.worksheet("Заказы")
sheet_stocks = sh.worksheet("Остатки")
sheet_norms = sh.worksheet("Нормы")

user_state = {}

def get_active_aromas():
    records = sheet_aromas.get_all_records()
    return [r for r in records if str(r.get('Активен?', '')).lower() in ('да', 'true')]

def get_parameters_for_category(category: str):
    try:
        records = sheet_categories.get_all_records()
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
    try:
        records = sheet_categories.get_all_records()
        for row in records:
            cat_match = str(row.get('Категория', '')).strip() == category
            if not cat_match:
                continue

            # Проверяем параметр
            table_param = str(row.get('Параметр', '')).strip()
            if parameter is None or parameter == "":
                # Ищем строку БЕЗ параметра (для свечей, саше)
                if table_param in ("", "—"):
                    price = row.get('Цена', '—')
                    return str(price).replace('.0', '') if str(price).endswith('.0') else str(price)
            else:
                # Ищем точное совпадение параметра
                if table_param == parameter:
                    price = row.get('Цена', '—')
                    return str(price).replace('.0', '') if str(price).endswith('.0') else str(price)
        return "—"
    except Exception as e:
        print("Ошибка загрузки цены:", e)
        return "—"

def get_aroma_by_name(name):
    aromas = get_active_aromas()
    for a in aromas:
        if a.get('Название аромата') == name:
            return a
    return None

def record_order(order_data):
    moscow_tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(moscow_tz).strftime("%d.%m.%Y %H:%M")
    row_number = len(sheet_orders.get_all_values())
    row = [
        row_number,
        now,
        order_data['telegram_id'],  # ← просто число
        order_data['name'],
        order_data['category'],
        order_data['aroma'],
        order_data['aroma_type'],
        order_data['parameter'] or '—',
        order_data['quantity'],
        order_data['comment'] or '',
        'Новый'
    ]
    sheet_orders.append_row(row)

def get_norm_ml(category: str, parameter: str = None) -> float:
    """Возвращает норму расхода отдушки (в мл) для категории."""
    try:
        norms = sheet_norms.get_all_records()
        key = category
        if category == "Диффузоры" and parameter:
            key = f"Диффузоры / {parameter}"
        elif category == "Автомобильные диффузоры":
            key = "Автомобильные диффузоры"

        print(f"DEBUG NORM: looking for key='{key}'")
        for row in norms:
            if row.get('Категория') == key:
                val = row.get('Объём на 1 шт (мл)', 0)
                return float(str(val).replace(',', '.'))
            print("  NOT FOUND")
        return 0.0
    except Exception as e:
        print("Ошибка загрузки норм:", e)
        return 0.0


def get_stock_ml(aroma_id: str) -> float:
    """Возвращает остаток отдушки (в мл) по аромату."""
    try:
        stocks = sheet_stocks.get_all_records()
        for row in stocks:
            if str(row.get('Аромат ID')).strip() == str(aroma_id).strip():
                val = row.get('Остаток (мл)', 0)
                return float(str(val).replace(',', '.'))
        return 0.0
    except Exception as e:
        print("Ошибка загрузки остатков:", e)
        return 0.0


def is_aroma_available(aroma_id: str, category: str, parameter: str = None, quantity: int = 1) -> bool:
    norm_per_item = get_norm_ml(category, parameter)
    total_needed = norm_per_item * quantity
    stock = get_stock_ml(aroma_id)
    result = stock >= total_needed
    print(f"DEBUG AVAIL: aroma={aroma_id}, cat={category}, param={parameter}, qty={quantity}")
    print(f"DEBUG AVAIL: stock={stock}, norm={norm_per_item}, total_needed={total_needed}, available={result}")
    return result

def get_max_quantity(aroma_id: str, category: str, parameter: str = None) -> int:
    """Возвращает максимальное количество товара, которое можно произвести из остатка."""
    norm = get_norm_ml(category, parameter)
    stock = get_stock_ml(aroma_id)
    if norm <= 0 or stock <= 0:
        return 0
    return int(stock // norm)

def deduct_stock(aroma_id: str, category: str, parameter: str = None, quantity: int = 1):
    """Списывает отдушку при оформлении заказа с учётом количества."""
    print(f"DEBUG DEDUCT: aroma_id={aroma_id}, category={category}, param={parameter}, qty={quantity}")
    norm_per_item = get_norm_ml(category, parameter)
    total_deduct = norm_per_item * quantity
    print(f"DEBUG DEDUCT: норма на 1 шт = {norm_per_item} мл, всего списываем = {total_deduct} мл")

    if total_deduct <= 0:
        print("DEBUG DEDUCT: ничего не списываем")
        return

    try:
        stocks = sheet_stocks.get_all_values()
        headers = stocks[0]
        id_col = headers.index('Аромат ID')
        stock_col = headers.index('Остаток (мл)')

        for i, row in enumerate(stocks[1:], start=2):
            if len(row) > id_col and row[id_col] == aroma_id:
                current = get_stock_ml(aroma_id)
                new_stock = max(0, current - total_deduct)
                print(f"DEBUG DEDUCT: {current} → {new_stock}")
                sheet_stocks.update_cell(i, stock_col + 1, str(new_stock))
                print("✅ Успешно списано!")
                return

        print("⚠️ Аромат не найден в остатках")
    except Exception as e:
        print(f"❌ Ошибка в deduct_stock: {e}")

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🕯️ Свечи")
    keyboard.add("🌿 Диффузоры")
    keyboard.add("🌸 Аромасаше")
    keyboard.add("🚗 Автомобильные диффузоры")
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
        # Получаем все строки (включая заголовки)
        all_values = sheet_orders.get_all_values()
        if not all_values:
            await message.answer("Таблица заказов пуста.")
            return

        headers = all_values[0]  # Первая строка — заголовки
        orders = all_values[1:]  # Остальное — данные

        # Находим индексы нужных колонок
        try:
            id_col = headers.index('Telegram ID')
            status_col = headers.index('Статус')
        except ValueError:
            await message.answer("Ошибка: в таблице нет колонок 'Telegram ID' или 'Статус'.")
            return

        # Ищем последний заказ с этим ID и статусом "Новый"
        target_row_index = None
        for i, row in enumerate(reversed(orders)):
            if len(row) > id_col and len(row) > status_col:
                if str(row[id_col]) == str(chat_id) and row[status_col] == "Новый":
                    # reversed, поэтому индекс считаем с конца
                    target_row_index = len(orders) - i
                    break

        if target_row_index is None:
            await message.answer("У вас нет активных заказов для отмены.")
            return

        # Обновляем статус на "Отменён"
        sheet_orders.update_cell(target_row_index + 1, status_col + 1, "Отменён")

        await message.answer(
            "Ваш последний заказ успешно отменён.\nСпасибо, что были с нами! ❤️"
        )

    except Exception as e:
        print("Ошибка при отмене:", e)
        await message.answer("Не удалось отменить заказ. Попробуйте позже.")

@dp.message_handler()
async def handle_message(message: types.Message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = user_state.get(chat_id, {})
    print(f"DEBUG: step='{state.get('step')}', text='{text}'")
    # 🔥 ОЧИСТКА КАТЕГОРИИ ОТ ЭМОДЗИ (вставь ЭТО)
    if 'category' in state:
        raw_cat = state['category']
        clean_map = {
            "🕯️ Свечи": "Свечи",
            "🌿 Диффузоры": "Диффузоры",
            "🌸 Аромасаше": "Аромасаше",
            "🚗 Автомобильные диффузоры": "Автомобильные диффузоры"
        }
        if raw_cat in clean_map:
            state['category'] = clean_map[raw_cat]
    if state.get('step') == 'main_menu':
        clean_map = {
            "🕯️ Свечи": "Свечи",
            "🌿 Диффузоры": "Диффузоры",
            "🌸 Аромасаше": "Аромасаше",
            "🚗 Автомобильные диффузоры": "Автомобильные диффузоры"
        }
        clean_category = clean_map.get(text, text)
        
        if text.strip() in ["🕯️ Свечи", "🌿 Диффузоры", "🌸 Аромасаше", "🚗 Автомобильные диффузоры"]:
            params = get_parameters_for_category(clean_category)
            if not params or (len(params) == 1 and params[0] == '—'):
                await show_aroma_types(chat_id, clean_category, None)
                user_state[chat_id] = {'step': 'selecting_aroma_type', 'category': clean_category, 'parameter': None}
            else:
                keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
                for p in params:
                    keyboard.add(p)
                prompt = "Выберите параметр:"
                if clean_category == "Диффузоры":
                    prompt = "В каком объёме вы хотели бы аромат?"
                elif clean_category == "Автомобильные диффузоры":
                    prompt = "Как удобнее крепить в машине? 🚗"
                await message.answer(prompt, reply_markup=keyboard)
                user_state[chat_id] = {'step': 'selecting_parameter', 'category': clean_category}

    elif state.get('step') == 'selecting_aroma_type':
        if text.strip() == "⬅️ Назад":
            await send_welcome(message)
            return

        category = state['category']
        parameter = state['parameter']

        # Получаем ВСЕ активные ароматы
        all_aromas = get_active_aromas()

        if text.strip() == "Парфюмерные":
            aromas = [a for a in all_aromas if str(a.get('Парфюмерный?', '')).lower() in ('да', 'true')]
        else:
            aromas = [a for a in all_aromas if a.get('Основной тип') == text]

        # 🔥 ФИЛЬТРУЕМ по доступности (остаток >= норма для 1 шт)
        available_aromas = []
        for a in aromas:
            aroma_id = a.get('Аромат ID')
            if aroma_id and is_aroma_available(aroma_id, category, parameter, quantity=1):
                available_aromas.append(a)

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

    elif state.get('step') == 'selecting_parameter':
        if text.strip() == "⬅️ Назад":
            if state.get('editing'):
                await show_order_summary(chat_id, state)
                return
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
            return  # ← ОБЯЗАТЕЛЬНО!
        else:
            await message.answer("Пожалуйста, выберите параметр из списка.")
            return  # ← и это

    elif state.get('step') == 'selecting_aroma':
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

        # 🔁 РЕЖИМ РЕДАКТИРОВАНИЯ
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

        # 🆕 НОВЫЙ ЗАКАЗ
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
        print("DEBUG: → confirm_add")

    elif state.get('step') == 'confirm_add':
        print(f"DEBUG: editing = {state.get('editing')}")
        if text.strip() == "⬅️ Назад":
            # Возвращаемся к СПИСКУ АРОМАТОВ
            aromas = get_active_aromas()
            aroma_type = state.get('aroma_type')
            if not aroma_type:
                await send_welcome(message)
                return

            category = state['category']
            parameter = state['parameter']

            if aroma_type == "Парфюмерные":
                filtered = [a for a in aromas if str(a.get('Парфюмерный?', '')).lower() in ('да', 'true')]
            else:
                filtered = [a for a in aromas if a.get('Основной тип') == aroma_type]

            # Фильтруем по доступности (остаток >= норма)
            available_aromas = []
            for a in filtered:
                aroma_id = a.get('Аромат ID')
                if aroma_id and is_aroma_available(aroma_id, category, parameter, quantity=1):
                    available_aromas.append(a)

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

        elif "Добавить в заказ" in text:
            # 🔥 Проверяем, в режиме редактирования ли мы
            if state.get('editing'):
                # Режим редактирования — сразу возвращаемся к сводке
                new_state = {
                    **state,
                    'step': 'confirming_order'
                }
                user_state[chat_id] = {**state, 'step': 'confirming_order'}
                await show_order_summary(chat_id, new_state)
                print("DEBUG: → confirming_order (editing mode)")
            else:
                # Новый заказ — просим количество
                keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
                keyboard.add("⬅️ Назад")
                await message.answer("Сколько штук Вы хотите заказать?", reply_markup=keyboard)
                user_state[chat_id] = {
                    **state,
                    'step': 'entering_quantity'
                }
                print("DEBUG: → entering_quantity (new order)")
            return

        else:
            # Только если введено что-то НЕ "Назад" и не "Добавить"
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.add("✅ Добавить в заказ")
            keyboard.add("⬅️ Назад")
            await message.answer(
                "Пожалуйста, нажмите кнопку «✅ Добавить в заказ», чтобы продолжить,\n"
                "или «⬅️ Назад», чтобы выбрать другой аромат.",
                reply_markup=keyboard
            )
            return

    elif state.get('step') == 'entering_quantity':
        # 🔥 Проверяем "Назад" СРАЗУ, до любых преобразований
        if text.strip() == "⬅️ Назад":
            if state.get('editing'):
                # Восстанавливаем исходное состояние
                original_state = {
                    'step': 'confirming_order',
                    'category': state['category'],
                    'parameter': state['original_parameter'],
                    'aroma': state['aroma'],
                    'aroma_type': state['aroma_type'],
                    'price': get_price(state['category'], state['original_parameter']),
                    'name': state['name'],
                    'quantity': state['original_quantity'],
                    'comment': state['comment'],
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
                if aroma_type == "Парфюмерные":
                    filtered = [a for a in aromas if str(a.get('Парфюмерный?', '')).lower() in ('да', 'true')]
                else:
                    filtered = [a for a in aromas if a.get('Основной тип') == aroma_type]

                # Фильтруем по доступности
                available_aromas = []
                for a in filtered:
                    aroma_id = a.get('Аромат ID')
                    if aroma_id and is_aroma_available(aroma_id, category, parameter, quantity=1):
                        available_aromas.append(a)

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

        # Только теперь обрабатываем число
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
                    await message.answer(
                        "К сожалению, этого аромата нет в наличии. Попробуйте выбрать другой."
                    )
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

            # 🔥 РАЗДЕЛЕНИЕ ЛОГИКИ
            if state.get('editing'):
                # Редактирование → сразу к сводке
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
                # Новый заказ → к вводу имени
                new_state = {
                    **state,
                    'quantity': quantity_value,
                    'step': 'entering_name'
                }
                user_state[chat_id] = new_state
                await message.answer("Как вас зовут? Напишите, как вам удобно — Анна, Саша, Максим… ❤️")


        except ValueError:
            await message.answer("Пожалуйста, введите число.")
        return

    elif state.get('step') == 'entering_name':
        if text.strip() == "⬅️ Назад":
            # Возвращаемся к вводу количества
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.add("⬅️ Назад")
            await message.answer("Сколько штук Вы хотите заказать?", reply_markup=keyboard)
            user_state[chat_id] = {
                **{k: v for k, v in state.items() if k not in ('step', 'name')},
                'step': 'entering_quantity'
            }
            return

        # Сохраняем имя (любой непустой текст, кроме "Назад")
        if text.strip():
            new_state = {
                **state,
                'name': text.strip(),
                'step': 'awaiting_comment_choice'
            }
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
        return

    elif state.get('step') == 'awaiting_comment_choice':
        if text.strip() == "⏭️ Пропустить":
            # Сохраняем пустой комментарий и переходим к подтверждению
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
            # Возвращаемся к вводу имени — и ОБНОВЛЯЕМ клавиатуру!
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.add("⬅️ Назад")
            await message.answer("Как вас зовут? Напишите, как вам удобно — Анна, Саша, Максим… ❤️", reply_markup=keyboard)
            user_state[chat_id] = {**state, 'step': 'entering_name'}
            return
        else:
            # Если пользователь что-то написал вместо выбора
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.add("💬 Оставить комментарий")
            keyboard.add("⏭️ Пропустить")
            keyboard.add("⬅️ Назад")
            await message.answer(
                "Пожалуйста, выберите вариант из меню.",
                reply_markup=keyboard
            )
            return
            
    elif state.get('step') == 'entering_comment':
        if text.strip() == "⬅️ Назад":
            # Возвращаемся к выбору комментария
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
            return  # 🔥 ОБЯЗАТЕЛЬНО!

        # Сохраняем комментарий и идём к подтверждению
        new_state = {
            **state,
            'comment': text,
            'step': 'confirming_order'
        }
        user_state[chat_id] = new_state
        await show_order_summary(chat_id, new_state)
        return
        
    elif state.get('step') == 'editing_parameter':
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

        # 🔥 Проверяем доступность ОТДУШКИ для нового параметра
        aroma_id = state.get('aroma_id')
        quantity = state.get('quantity', 1)
        print(f"DEBUG EDIT PARAM: aroma_id={aroma_id}, category={category}, param={selected_param}, qty={quantity}")
        stock = get_stock_ml(aroma_id)
        norm = get_norm_ml(category, selected_param)
        total_needed = norm * quantity
        max_qty_calc = int(stock // norm) if norm > 0 else 0
        print(f"DEBUG: stock={stock}, norm={norm}, total_needed={total_needed}, max_qty_calc={max_qty_calc}")
        if not is_aroma_available(aroma_id, category, selected_param, quantity):
            max_qty = get_max_quantity(aroma_id, category, selected_param)
            if max_qty <= 0:
                # Нет вообще → возвращаем к выбору объёма
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
                # Есть, но не на текущее количество → предлагаем изменить количество
                await message.answer(
                    f"На складе недостаточно отдушки для {quantity} шт. в объёме «{selected_param}».\n"
                    f"Максимум, что можно заказать: {max_qty} шт."
                )
                # 🔁 Переходим к вводу количества (как при редактировании)
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

        # Если всё ок — обновляем заказ
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
        return
            
    elif state.get('step') == 'confirming_order':
        print(f"DEBUG: получено сообщение = '{text}'")  # ← ЭТА СТРОКА
        print(f"DEBUG: длина текста = {len(text)}")
        category = state['category']
        
        if text.strip() == "✅ Подтвердить заказ":
            await finalize_order(chat_id, state, state.get('comment', ''))
            return

        elif text == "🏠 Главное меню":
            await send_welcome(message)
            return

        elif text == "🕯️ Изменить аромат":
            user_state[chat_id] = {
                **state,  # ← КОПИРУЕМ ВСЁ СТАРОЕ СОСТОЯНИЕ
                'step': 'selecting_aroma_type'
            }
            await show_aroma_types(chat_id, state['category'], state['parameter'])
            return

        elif text == "💧 Изменить объём" and category == "Диффузоры":
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

 
        elif text == "🚗 Изменить крепление" and category == "Автомобильные диффузоры":
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
        
        elif text == "🔢 Изменить количество":
            user_state[chat_id] = {
                **state,  # ← КОПИРУЕМ ВСЁ, включая aroma_id!
                'step': 'entering_quantity',
                'editing': True
            }
            keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.add("⬅️ Назад")
            await message.answer("Сколько штук вам нужно?", reply_markup=keyboard)
            return

        elif text == "💬 Добавить/изменить комментарий":
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

        else:
            await show_order_summary(chat_id, state)

    else:
        print(f"DEBUG: неизвестный шаг = {state.get('step')}, текст = '{text}'")
        await send_welcome(message)

    

async def show_order_summary(chat_id, state):
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

    # Умная кнопка параметра
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
    print("DEBUG: finalize_order вызван!")
    print("DEBUG: state =", state)
    print(f"DEBUG FINALIZE: aroma_id = {state.get('aroma_id')}")
    print(f"DEBUG FINALIZE: category = {state.get('category')}")
    print(f"DEBUG FINALIZE: parameter = {state.get('parameter')}")
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
        # Можно отправить админу уведомление об ошибке
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

    # === Сообщение клиенту ===
    msg_client = f"Спасибо за заказ, {state.get('name', '')}! ❤️\n\n"
    msg_client += f"🕯️ {state['aroma']}\n"
    if state['parameter'] and state['parameter'] != '—':
        msg_client += f"({state['parameter']})\n"
    msg_client += f"\nКол-во: {state.get('quantity', 1)} шт\n"
    if comment:
        msg_client += f"\nКомментарий: {comment}\n"
    msg_client += "\nВаш заказ в работе — скоро я пришлю детали.\n\nНаслаждайтесь атмосферой LOVELY TIME 🌸"
    msg_client += "❗ Если вы передумаете — просто напишите /cancel в любой момент для отмены заказа."
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🆕 Новый заказ")
    await bot.send_message(chat_id, msg_client, reply_markup=keyboard)

    # === Уведомление админу ===
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

        # Кликабельная ссылка — работает всегда!
        contact_link = f"<a href='tg://user?id={chat_id}'>Открыть чат с клиентом</a>"
        msg_admin += f"\n{contact_link}"

        try:
            await bot.send_message(ADMIN_CHAT_ID, msg_admin, parse_mode="HTML")
        except Exception as e:
            print("Не удалось отправить уведомление админу:", e)

    # Сброс состояния
    if chat_id in user_state:
        del user_state[chat_id]

async def show_aroma_types(chat_id, category, parameter):
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

#from flask import Flask
#from threading import Thread

#app = Flask('')

#@app.route('/')
#def home():
    #return "Бот работает!"

#def run():
    #app.run(host='0.0.0.0', port=8080)

#def keep_alive():
    #t = Thread(target=run)
    #t.daemon = True  # ← чтобы поток не мешал завершению
    #t.start()

# === ВЕБХУК ===
async def on_startup(app):
    # Устанавливаем вебхук с сертификатом
    cert_path = "/root/bot/certs/cert.pem"
    await bot.set_webhook(
        url="https://194.87.98.45/webhook",
        certificate=open(cert_path, 'rb')
    )
    print("✅ Вебхук установлен")

async def handle_webhook(request):
    update = types.Update(**await request.json())
    await dp.process_update(update)
    return web.Response()

app = web.Application()
app.on_startup.append(on_startup)
app.router.add_post(WEBHOOK_PATH, handle_webhook)

if __name__ == "__main__":
    # ЗАПУСКАЕМ БЕЗ SSL! Только HTTP на localhost
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)
