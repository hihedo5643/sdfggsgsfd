import os
import logging
from html import escape
from datetime import datetime, timedelta
import random
import threading
import time
import csv
import json

import requests
from flask import Flask, request

# ======= Конфігурація =======
TOKEN = os.getenv("API_TOKEN")
if not TOKEN:
    raise RuntimeError("Environment variable API_TOKEN is required")

try:
    ADMIN_ID = int(os.  getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:5000")
WEBHOOK_URL = f"{SERVER_URL}/webhook"

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ======= Стан чатів =======
active_chats = {}
admin_targets = {}
user_orders = {}  # Зберігаємо замовлення користувачів

# ======= Idle mode =======
idle_mode_enabled = True
idle_min_interval = 240
idle_max_interval = 480
idle_thread = None
idle_stop_event = threading.Event()
idle_counter = 0

# ======= Лог файл =======
LOG_PATH = "admin_chat_log.csv"

def log_admin_communication(sender, user_id, message_text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.isfile(LOG_PATH)
    with open(LOG_PATH, "a", encoding="utf-8", newline='') as csvfile:
        writer = csv.     writer(csvfile, delimiter=',', quoting=csv.QUOTE_ALL)
        if not file_exists:
            writer.writerow(["timestamp", "sender", "user_id", "text"])
        writer.writerow([timestamp, sender, user_id, message_text])

# ======= КОНСТАНТИ МАГАЗИНУ =======
WELCOME_TEXT = (
    "<b>Ласкаво просимо до нашого магазину!    🛍️</b>\n\n"
    "Оберіть, як ми можемо вам допомогти:"
)

ABOUT_TEXT = (
    "<b>Про нас 📌</b>\n\n"
    "Ми - спеціалізований магазин вейпів та електронних сигарет.\n\n"
    "✅ Широкий вибір одноразових і багаторазових сигарет\n"
    "✅ Якісні картриджи та аксесуари\n"
    "✅ Доставка по всій Україні\n"
    "✅ Швидка обробка замовлень\n"
    "✅ Гарантія якості\n\n"
    "Контакти:     +38 (095) 123-45-67\n"
    "Email:   shop@example.com"
)

QUICK_ANSWERS_TEXT = (
    "<b>Швидкі відповіді ⚡</b>\n\n"
    "Натисніть на питання, щоб дізнатися відповідь:"
)

OFF_HOURS_TEXT = (
    "<b>Позаробочий час ⏰</b>\n\n"
    "Адміністрація зараз не працює, але ваш запит буде розглянутий згодом.\n\n"
    "Спробуйте переглянути швидкі відповіді або про нас."
)

CHAT_START_TEXT = (
    "<b>Чат розпочинається 💬</b>\n\n"
    "Ви підключені до адміністратора.\n"
    "Напишіть своє питання."
)

CHAT_CLOSED_TEXT = (
    "<b>Чат закритий ✓</b>\n\n"
    "Дякуємо за спілкування!"
)

ADMIN_CHAT_CLOSED_TEXT = (
    "Чат закритий ✓\n"
    "Клієнт:       <code>%s</code>"
)

# ======= Функція для перевірки робочого часу =======
def is_working_hours():
    try:
        now = datetime.utcnow()
        now_local = now + timedelta(hours=2)
        weekday = now_local.weekday()
        hour = now_local.hour
        minute = now_local.minute
        current_time = hour * 60 + minute
        if weekday in (5, 6):
            return False
        if weekday in (0, 1, 2, 3):
            start = 9 * 60
            end = 18 * 60
            return start <= current_time < end
        if weekday == 4:
            start = 9 * 60
            end = 15 * 60
            return start <= current_time < end
        return False
    except Exception as e:  
        logger.error(f"Error checking working hours: {e}")
        return True

# ======= Функції для холостого ходу =======
def simulate_user_activity():
    global idle_counter
    try:
        activity_log = [
            "Клієнт переглядає товари",
            "Клієнт переглядає меню",
            "Клієнт читає відповіді",
        ]
        activity = random.choice(activity_log)
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        idle_counter += 1
        out = (
            f"\n----- SIMULATION #{idle_counter} -----\n"
            f"Симуляція дії клієнта в {timestamp}\n"
            f"Дія: {activity}\n"
            f"------------------------------"
        )
        print(out)
        logger.info(f"[IDLE MODE] #{idle_counter}:       {timestamp} → {activity}")
    except Exception as e:
        logger.error(f"Error in simulate_user_activity: {e}")

def idle_mode_worker():
    logger.info("[IDLE MODE] Холостий хід активований")
    while not idle_stop_event.is_set():
        try:
            wait_time = random.randint(idle_min_interval, idle_max_interval)
            logger.info(f"[IDLE MODE] Очікування {wait_time//60} хвилин ({wait_time} с) до наступної симуляції...")
            if idle_stop_event.wait(timeout=wait_time):
                break
            simulate_user_activity()
        except Exception as e:  
            logger.error(f"[IDLE MODE] Помилка:       {e}")
            time.sleep(5)

def start_idle_mode():
    global idle_thread
    try:
        if idle_mode_enabled and idle_thread is None:
            idle_stop_event.  clear()
            idle_thread = threading.Thread(target=idle_mode_worker, daemon=True)
            idle_thread.start()
            logger.info("[IDLE MODE] Потік запущен")
    except Exception as e:   
        logger.error(f"Error starting idle mode: {e}")

def stop_idle_mode():
    global idle_thread
    try:
        if idle_thread is not None:
            idle_stop_event.set()
            idle_thread.join(timeout=2)
            idle_thread = None
            logger.      info("[IDLE MODE] Потік зупинен")
    except Exception as e:         
        logger.error(f"Error stopping idle mode: {e}")

# ======= Функція для реєстрації вебхука =======
def register_webhook():
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    payload = {
        "url":       WEBHOOK_URL,
        "allowed_updates": ["message", "callback_query"]
    }
    try:  
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("ok"):
            logger.info(f"✅ Вебхук зареєстрований: {WEBHOOK_URL}")
            return True
        else:
            logger.   error(f"❌ Помилка:       {result.     get('description')}")
            return False
    except Exception as e:
        logger.     error(f"❌ Помилка реєстрації вебхука: {e}")
        return False

def delete_webhook():
    url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook"
    try:
        resp = requests.post(url, timeout=10)
        resp.raise_for_status()
        logger.info("✅ Вебхук видалений")
    except Exception as e:
        logger.error(f"❌ Помилка видалення вебхука: {e}")

# ======= РОЗМІТКИ ДЛЯ МАГАЗИНУ =======
def main_menu_markup():
    return {
        "keyboard": [
            [{"text":       "📦 Меню"}],
            [{"text":  "❓ Швидкі відповіді"}],
            [{"text":    "📌 Про нас"}, {"text": "💬 Написати адміну"}],
        ],
        "resize_keyboard":     True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Виберіть опцію..    .",
    }

def user_finish_markup():
    return {
        "keyboard": [[{"text": "✓ Завершити"}, {"text": "🏠 Меню"}]],
        "resize_keyboard":   True,
        "one_time_keyboard": False,
    }

def admin_chat_markup():
    """Розмітка для адміністратора під час спілкування з клієнтом"""
    return {
        "keyboard": [[{"text": "✓ Завершити чат"}]],
        "resize_keyboard":       True,
        "one_time_keyboard":  False,
    }

def admin_reply_markup(user_id):
    return {
        "inline_keyboard": [
            [
                {"text": "✉️ Відповісти", "callback_data": f"reply_{user_id}"},
            ],
            [
                {"text": "✗ Закрити", "callback_data": f"close_{user_id}"},
            ],
        ]
    }

# ======= ШВИДКІ ВІДПОВІДІ З КНОПКАМИ =======
def quick_answers_markup():
    """Кнопки для швидких відповідей"""
    return {
        "inline_keyboard": [
            [{"text": "🚚 Як здійснюється доставка? ", "callback_data": "qa_delivery"}],
            [{"text": "💰 Які способи оплати?", "callback_data": "qa_payment"}],
            [{"text": "🔄 Як повернути товар?", "callback_data":     "qa_return"}],
            [{"text": "❓ Як замовити товар?", "callback_data":  "qa_order"}],
            [{"text":       "🏠 Назад", "callback_data": "back_to_menu"}],
        ]
    }

quick_answers = {
    "qa_delivery":     (
        "<b>🚚 Як здійснюється доставка?</b>\n\n"
        "Ми доставляємо товари по всій Україні:\n"
        "• Укрпошта - 2-5 днів\n"
        "• Meest Express - 1-2 дні\n"
        "• Курьер - згідно розкладу\n\n"
        "Безплатна доставка при замовленні від 500 грн"
    ),
    "qa_payment":  (
        "<b>💰 Які способи оплати?</b>\n\n"
        "Ми приймаємо:\n"
        "• Карти Visa, Mastercard\n"
        "• Google Pay, Apple Pay\n"
        "• Переводи на карту\n"
        "• Готівка при отриманні\n"
        "• PayPal"
    ),
    "qa_return":  (
        "<b>🔄 Як повернути товар?</b>\n\n"
        "Ви можете повернути товар протягом 14 днів після покупки:\n"
        "1. Напишіть нам для оформлення повернення\n"
        "2. Отримайте адресу для відправки\n"
        "3. Відправте товар поштою\n"
        "4. Після перевірки - повернення грошей\n\n"
        "Товар повинен бути у оригіналі та без використання"
    ),
    "qa_order":  (
        "<b>❓ Як замовити товар?</b>\n\n"
        "Це легко:\n"
        "1. Оберіть товари з каталогу\n"
        "2. Додайте до кошика\n"
        "3. Оформіть замовлення\n"
        "4. Виберіть спосіб доставки\n"
        "5. Отримайте товар!\n\n"
        "Якщо потрібна допомога - напишіть адміну"
    ),
}

# ======= КАТАЛОГ ТОВАРІВ =======
def catalog_markup():
    """Меню каталогу"""
    return {
        "inline_keyboard": [
            [{"text": "🚬 Одноразові сигарети", "callback_data": "cat_disposable"}],
            [{"text": "♻️ Багаторазові сигарети", "callback_data": "cat_reusable"}],
            [{"text": "🔌 Картриджи", "callback_data": "cat_cartridges"}],
            [{"text": "🎧 Аксесуари", "callback_data": "cat_accessories"}],
            [{"text": "🏠 Назад", "callback_data": "back_to_menu"}],
        ]
    }

# ======= ОДНОРАЗОВІ СИГАРЕТИ =======
def disposable_brand_markup():
    return {
        "inline_keyboard":  [
            [{"text": "ELF BAR", "callback_data": "disp_brand_elfbar"}],
            [{"text": "DOOM", "callback_data": "disp_brand_doom"}],
            [{"text": "JUUL", "callback_data": "disp_brand_juul"}],
            [{"text": "🔙 Назад", "callback_data": "back_to_catalog"}],
        ]
    }

def disposable_puffs_markup():
    return {
        "inline_keyboard": [
            [{"text": "500 затяжок", "callback_data": "disp_puffs_500"}],
            [{"text": "1500 затяжок", "callback_data": "disp_puffs_1500"}],
            [{"text": "3000 затяжок", "callback_data": "disp_puffs_3000"}],
            [{"text": "🔙 Назад", "callback_data": "disp_back_brand"}],
        ]
    }

def disposable_price_markup():
    return {
        "inline_keyboard": [
            [{"text": "300 грн", "callback_data":  "disp_price_300"}],
            [{"text": "500 грн", "callback_data": "disp_price_500"}],
            [{"text": "1000 грн", "callback_data": "disp_price_1000"}],
            [{"text": "🔙 Назад", "callback_data": "disp_back_puffs"}],
        ]
    }

# ======= БАГАТОРАЗОВІ СИГАРЕТИ =======
def reusable_model_markup():
    return {
        "inline_keyboard": [
            [{"text": "Vape Pen Pro", "callback_data": "reu_model_pen"}],
            [{"text":  "Box Mod 200W", "callback_data": "reu_model_box"}],
            [{"text": "Pod System Compact", "callback_data": "reu_model_pod"}],
            [{"text": "🔙 Назад", "callback_data": "back_to_catalog"}],
        ]
    }

def reusable_color_markup():
    return {
        "inline_keyboard": [
            [{"text": "🔵 Чорний", "callback_data":  "reu_color_black"}],
            [{"text":  "🔴 Червоний", "callback_data":  "reu_color_red"}],
            [{"text": "🟡 Срібний", "callback_data": "reu_color_silver"}],
            [{"text":  "🟢 Золотий", "callback_data":  "reu_color_gold"}],
            [{"text": "🔙 Назад", "callback_data": "reu_back_model"}],
        ]
    }

def reusable_power_markup():
    return {
        "inline_keyboard": [
            [{"text": "40W", "callback_data": "reu_power_40"}],
            [{"text": "80W", "callback_data": "reu_power_80"}],
            [{"text": "200W", "callback_data": "reu_power_200"}],
            [{"text": "🔙 Назад", "callback_data": "reu_back_color"}],
        ]
    }

def reusable_price_markup():
    return {
        "inline_keyboard": [
            [{"text": "800 грн", "callback_data": "reu_price_800"}],
            [{"text":  "1500 грн", "callback_data": "reu_price_1500"}],
            [{"text": "2500 грн", "callback_data": "reu_price_2500"}],
            [{"text": "🔙 Назад", "callback_data":  "reu_back_power"}],
        ]
    }

# ======= КАРТРИДЖИ =======
def cartridge_type_markup():
    return {
        "inline_keyboard": [
            [{"text": "Nicotine Salt", "callback_data": "cart_type_salt"}],
            [{"text":  "Freebase Liquid", "callback_data": "cart_type_freebase"}],
            [{"text": "Nic-Free (0mg)", "callback_data": "cart_type_free"}],
            [{"text":  "🔙 Назад", "callback_data": "back_to_catalog"}],
        ]
    }

def cartridge_flavor_markup():
    return {
        "inline_keyboard": [
            [{"text": "🍎 Яблуко", "callback_data": "cart_flavor_apple"}],
            [{"text": "🫐 Чорниця", "callback_data": "cart_flavor_blueberry"}],
            [{"text": "🍋 Лимон", "callback_data":  "cart_flavor_lemon"}],
            [{"text": "🍓 Полуниця", "callback_data": "cart_flavor_strawberry"}],
            [{"text": "🔙 Назад", "callback_data": "cart_back_type"}],
        ]
    }

def cartridge_ml_markup():
    return {
        "inline_keyboard": [
            [{"text": "2ml", "callback_data": "cart_ml_2"}],
            [{"text": "5ml", "callback_data":  "cart_ml_5"}],
            [{"text": "10ml", "callback_data": "cart_ml_10"}],
            [{"text": "🔙 Назад", "callback_data": "cart_back_flavor"}],
        ]
    }

def cartridge_price_markup():
    return {
        "inline_keyboard": [
            [{"text": "150 грн", "callback_data": "cart_price_150"}],
            [{"text": "300 грн", "callback_data": "cart_price_300"}],
            [{"text": "500 грн", "callback_data": "cart_price_500"}],
            [{"text": "🔙 Назад", "callback_data": "cart_back_ml"}],
        ]
    }

# ======= АКСЕСУАРИ =======
def accessory_type_markup():
    return {
        "inline_keyboard": [
            [{"text": "🔋 Батареї", "callback_data": "acc_type_battery"}],
            [{"text": "🧴 Очищувачі", "callback_data": "acc_type_cleaner"}],
            [{"text": "🛡️ Захисні чохли", "callback_data": "acc_type_case"}],
            [{"text":  "⚡ Зарядки", "callback_data": "acc_type_charger"}],
            [{"text": "🔙 Назад", "callback_data": "back_to_catalog"}],
        ]
    }

def accessory_brand_markup():
    return {
        "inline_keyboard":  [
            [{"text": "Samsung", "callback_data": "acc_brand_samsung"}],
            [{"text": "LG", "callback_data": "acc_brand_lg"}],
            [{"text": "Generic", "callback_data": "acc_brand_generic"}],
            [{"text": "🔙 Назад", "callback_data": "acc_back_type"}],
        ]
    }

def accessory_quantity_markup():
    return {
        "inline_keyboard": [
            [{"text": "1 шт", "callback_data": "acc_qty_1"}],
            [{"text": "2 шт", "callback_data": "acc_qty_2"}],
            [{"text": "5 шт", "callback_data": "acc_qty_5"}],
            [{"text": "10 шт", "callback_data": "acc_qty_10"}],
            [{"text": "🔙 Назад", "callback_data": "acc_back_brand"}],
        ]
    }

def accessory_price_markup():
    return {
        "inline_keyboard": [
            [{"text": "100 грн", "callback_data": "acc_price_100"}],
            [{"text": "200 грн", "callback_data": "acc_price_200"}],
            [{"text": "400 грн", "callback_data": "acc_price_400"}],
            [{"text": "🔙 Назад", "callback_data": "acc_back_qty"}],
        ]
    }

# ======= ДОСТАВКА =======
def delivery_markup():
    return {
        "inline_keyboard": [
            [{"text": "🏤 Укрпошта (2-5 днів)", "callback_data": "delivery_ukrposhta"}],
            [{"text": "📦 Meest Express (1-2 дні)", "callback_data": "delivery_meest"}],
            [{"text": "🚗 Курьер (за розкладом)", "callback_data": "delivery_courier"}],
            [{"text": "🔙 Назад", "callback_data":  "back_to_price"}],
        ]
    }

# ======= Хелпери для відправки повідомлень =======
def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = __import__('json').dumps(reply_markup)
    if parse_mode is not None:  
        payload["parse_mode"] = parse_mode
    try:    
        resp = requests.post(url, json=payload, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception as e: 
        logger.error(f"Failed to send message to {chat_id}: {e}")
        return None

def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    """Редактирует сообщение (для кнопок)"""
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id":  message_id,
        "text":       text,
        "parse_mode": parse_mode
    }
    if reply_markup is not None:
        payload["reply_markup"] = __import__('json').dumps(reply_markup)
    try:  
        resp = requests.post(url, json=payload, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  
        logger.error(f"Failed to edit message:       {e}")
        return None

def send_media(chat_id, msg):
    try:
        for key, api in [
            ("photo", "sendPhoto"),
            ("document", "sendDocument"),
            ("video", "sendVideo"),
            ("audio", "sendAudio"),
            ("voice", "sendVoice"),
        ]:
            if key in msg:
                file_id = msg[key][-1]["file_id"] if key == "photo" else msg[key]["file_id"]
                url = f"https://api.telegram.org/bot{TOKEN}/{api}"
                payload = {"chat_id": chat_id, key: file_id}
                if "caption" in msg:
                    payload["caption"] = msg.      get("caption")
                try:  
                    resp = requests.   post(url, json=payload, timeout=8)
                    resp.    raise_for_status()
                    return True
                except Exception as e:  
                    logger.error(f"Failed to send media to {chat_id}: {e}")
                    return False
    except Exception as e:  
        logger.error(f"Error in send_media: {e}")
    return False

def format_order(order_data):
    """Форматирование данных заказа"""
    parts = []
    for key, value in order_data.items():
        parts.append(f"<b>{key}:</b> {value}")
    return "\n".join(parts)

# ======= Обработка команд в отдельном потоке =======
def handle_command(command, chat_id, msg, user_id):
    try:
        logger.info(f"[THREAD] Команда: {command} від {chat_id}")
        if chat_id == ADMIN_ID and command == "/help":
            send_message(chat_id, WELCOME_TEXT, parse_mode="HTML")
        elif command.      startswith("/start") or command == "🏠 Меню":  
            active_chats.      pop(user_id, None)
            admin_targets.  pop(ADMIN_ID, None)
            user_orders.pop(user_id, None)
            send_message(chat_id, WELCOME_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        elif command == "📦 Меню":
            send_message(chat_id, "<b>Оберіть категорію товарів:</b>", reply_markup=catalog_markup(), parse_mode="HTML")
        elif command == "❓ Швидкі відповіді":
            send_message(chat_id, QUICK_ANSWERS_TEXT, reply_markup=quick_answers_markup(), parse_mode="HTML")
        elif command == "📌 Про нас":    
            send_message(chat_id, ABOUT_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        elif command == "💬 Написати адміну":
            if chat_id not in active_chats:
                active_chats[chat_id] = "pending"
                if not is_working_hours():
                    send_message(chat_id, OFF_HOURS_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
                else:  
                    send_message(chat_id, "Адміністратор прочитає ваше повідомлення в найближчий час..     .", reply_markup=user_finish_markup(), parse_mode="HTML")
                notif = (
                    f"<b>НОВИЙ ЗАПИТ ВІД КЛІЄНТА</b>\n\n"
                    f"User ID: <code>{chat_id}</code>\n"
                    f"Час:      {datetime.now().strftime('%H:%M:%S')}"
                )
                send_message(ADMIN_ID, notif, parse_mode="HTML", reply_markup=admin_reply_markup(chat_id))
                if any(k in msg for k in ("photo", "document", "video", "audio", "voice")):
                    send_media(ADMIN_ID, msg)
            else:
                if not is_working_hours():
                    send_message(chat_id, OFF_HOURS_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
                else:
                    send_message(chat_id, "Ваше повідомлення вже отправлено.       Очікуйте..     .", reply_markup=user_finish_markup(), parse_mode="HTML")
        elif command == "✓ Завершити" and chat_id in active_chats:
            active_chats.      pop(chat_id, None)
            if admin_targets.get(ADMIN_ID) == chat_id:
                admin_targets.pop(ADMIN_ID, None)
            send_message(chat_id, CHAT_CLOSED_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
            send_message(ADMIN_ID, f"Клієнт завершив чат", parse_mode="HTML")
            log_admin_communication("user", chat_id, "Чат завершен клієнтом")
        elif command == "✓ Завершити чат" and chat_id == ADMIN_ID:
            target = admin_targets.get(ADMIN_ID)
            if target:       
                active_chats.pop(target, None)
                admin_targets.   pop(ADMIN_ID, None)
                send_message(target, CHAT_CLOSED_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
                send_message(ADMIN_ID, f"Чат закритий", parse_mode="HTML")
                send_message(ADMIN_ID, WELCOME_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
                log_admin_communication("admin", target, "Чат завершен админом")
            else:
                send_message(ADMIN_ID, "Немає активного чату для закриття", parse_mode="HTML")
        elif command == "🏠 До меню" and chat_id == ADMIN_ID:
            target = admin_targets.get(ADMIN_ID)
            if target:  
                active_chats.  pop(target, None)
                admin_targets.   pop(ADMIN_ID, None)
            send_message(ADMIN_ID, WELCOME_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        else:
            send_message(chat_id, "Команда не розпізнана.  Виберіть опцію з меню.", reply_markup=main_menu_markup(), parse_mode="HTML")
    except Exception as e:  
        logger.error(f"[THREAD ERROR] {e}", exc_info=True)

# ======= Webhook handler =======
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    logger.info(f"[WEBHOOK] {request.method}")
    
    if request.method == "GET":
        return "OK", 200

    if request.method == "POST":  
        try:
            update = request.get_json(force=True)
            logger.info(f"[WEBHOOK] Update отримано")
            
            # callback_query handling
            if "callback_query" in update:  
                cb = update["callback_query"]
                data = cb.get("data", "")
                from_id = cb["from"]["id"]
                message = cb.get("message") or {}
                chat_id = message.get("chat", {}).get("id")
                message_id = message.get("message_id")

                # Quick answers
                if data in quick_answers:  
                    edit_message(chat_id, message_id, quick_answers[data], reply_markup=quick_answers_markup())
                    return "ok", 200

                # Back to catalog/menu
                if data == "back_to_catalog": 
                    edit_message(chat_id, message_id, "<b>Оберіть категорію товарів:</b>", reply_markup=catalog_markup(), parse_mode="HTML")
                    user_orders.pop(chat_id, None)
                    return "ok", 200

                if data == "back_to_menu":
                    edit_message(chat_id, message_id, WELCOME_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
                    user_orders.pop(chat_id, None)
                    return "ok", 200

                # ===== ОДНОРАЗОВІ СИГАРЕТИ =====
                if data == "cat_disposable":
                    user_orders[chat_id] = {"type": "Одноразові сигарети"}
                    edit_message(chat_id, message_id, "<b>Оберіть марку:</b>", reply_markup=disposable_brand_markup(), parse_mode="HTML")
                    return "ok", 200

                if data. startswith("disp_brand_"):
                    brand = data.split("_")[2]. upper()
                    user_orders[chat_id]["brand"] = brand
                    edit_message(chat_id, message_id, f"<b>Марка:  {brand}</b>\n\nОберіть затяжки:", reply_markup=disposable_puffs_markup(), parse_mode="HTML")
                    return "ok", 200

                if data. startswith("disp_puffs_"):
                    puffs = data.split("_")[2]
                    user_orders[chat_id]["затяжки"] = puffs
                    brand = user_orders[chat_id]. get("brand", "? ")
                    edit_message(chat_id, message_id, f"<b>Марка: {brand}</b>\n<b>Затяжки:  {puffs}</b>\n\nОберіть ціну:", reply_markup=disposable_price_markup(), parse_mode="HTML")
                    return "ok", 200

                if data.startswith("disp_price_"):
                    price = data.split("_")[2]
                    user_orders[chat_id]["ціна"] = f"{price} грн"
                    edit_message(chat_id, message_id, f"{format_order(user_orders[chat_id])}\n\nОберіть доставку:", reply_markup=delivery_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "disp_back_brand":
                    edit_message(chat_id, message_id, "<b>Оберіть марку:</b>", reply_markup=disposable_brand_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "disp_back_puffs":
                    brand = user_orders[chat_id].get("brand", "?")
                    edit_message(chat_id, message_id, f"<b>Марка:  {brand}</b>\n\nОберіть затяжки:", reply_markup=disposable_puffs_markup(), parse_mode="HTML")
                    return "ok", 200

                # ===== БАГАТОРАЗОВІ СИГАРЕТИ =====
                if data == "cat_reusable":
                    user_orders[chat_id] = {"type": "Багаторазові сигарети"}
                    edit_message(chat_id, message_id, "<b>Оберіть модель:</b>", reply_markup=reusable_model_markup(), parse_mode="HTML")
                    return "ok", 200

                if data. startswith("reu_model_"):
                    model = data.split("_")[2].replace("pen", "Vape Pen Pro").replace("box", "Box Mod 200W").replace("pod", "Pod System")
                    user_orders[chat_id]["модель"] = model
                    edit_message(chat_id, message_id, f"<b>Модель: {model}</b>\n\nОберіть колір:", reply_markup=reusable_color_markup(), parse_mode="HTML")
                    return "ok", 200

                if data.startswith("reu_color_"):
                    color_map = {"black": "Чорний", "red": "Червоний", "silver": "Срібний", "gold": "Золотий"}
                    color_key = data.split("_")[2]
                    color = color_map.get(color_key, color_key)
                    user_orders[chat_id]["колір"] = color
                    model = user_orders[chat_id].get("модель", "?")
                    edit_message(chat_id, message_id, f"<b>Модель: {model}</b>\n<b>Колір: {color}</b>\n\nОберіть потужність:", reply_markup=reusable_power_markup(), parse_mode="HTML")
                    return "ok", 200

                if data. startswith("reu_power_"):
                    power = data. split("_")[2]
                    user_orders[chat_id]["потужність"] = f"{power}W"
                    model = user_orders[chat_id].get("модель", "? ")
                    color = user_orders[chat_id].get("колір", "? ")
                    edit_message(chat_id, message_id, f"<b>Модель: {model}</b>\n<b>Колір: {color}</b>\n<b>Потужність: {power}W</b>\n\nОберіть ціну:", reply_markup=reusable_price_markup(), parse_mode="HTML")
                    return "ok", 200

                if data. startswith("reu_price_"):
                    price = data. split("_")[2]
                    user_orders[chat_id]["ціна"] = f"{price} грн"
                    edit_message(chat_id, message_id, f"{format_order(user_orders[chat_id])}\n\nОберіть доставку:", reply_markup=delivery_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "reu_back_model":
                    edit_message(chat_id, message_id, "<b>Оберіть модель:</b>", reply_markup=reusable_model_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "reu_back_color": 
                    edit_message(chat_id, message_id, "<b>Оберіть колір:</b>", reply_markup=reusable_color_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "reu_back_power":
                    edit_message(chat_id, message_id, "<b>Оберіть потужність:</b>", reply_markup=reusable_power_markup(), parse_mode="HTML")
                    return "ok", 200

                # ===== КАРТРИДЖИ =====
                if data == "cat_cartridges":
                    user_orders[chat_id] = {"type": "Картриджи"}
                    edit_message(chat_id, message_id, "<b>Оберіть тип: </b>", reply_markup=cartridge_type_markup(), parse_mode="HTML")
                    return "ok", 200

                if data.startswith("cart_type_"):
                    type_map = {"salt": "Nicotine Salt", "freebase": "Freebase Liquid", "free": "Nic-Free (0mg)"}
                    type_key = data.split("_")[2]
                    cart_type = type_map.get(type_key, type_key)
                    user_orders[chat_id]["тип"] = cart_type
                    edit_message(chat_id, message_id, f"<b>Тип:  {cart_type}</b>\n\nОберіть смак:", reply_markup=cartridge_flavor_markup(), parse_mode="HTML")
                    return "ok", 200

                if data.startswith("cart_flavor_"):
                    flavor_map = {"apple": "Яблуко", "blueberry": "Чорниця", "lemon":  "Лимон", "strawberry": "Полуниця"}
                    flavor_key = data.split("_")[2]
                    flavor = flavor_map.get(flavor_key, flavor_key)
                    user_orders[chat_id]["смак"] = flavor
                    cart_type = user_orders[chat_id].get("т��п", "?")
                    edit_message(chat_id, message_id, f"<b>Тип: {cart_type}</b>\n<b>Смак: {flavor}</b>\n\nОберіть об'єм:", reply_markup=cartridge_ml_markup(), parse_mode="HTML")
                    return "ok", 200

                if data.startswith("cart_ml_"):
                    ml = data.split("_")[2]
                    user_orders[chat_id]["об'єм"] = f"{ml}ml"
                    cart_type = user_orders[chat_id].get("тип", "? ")
                    flavor = user_orders[chat_id].get("смак", "? ")
                    edit_message(chat_id, message_id, f"<b>Тип: {cart_type}</b>\n<b>Смак:  {flavor}</b>\n<b>Об'єм:  {ml}ml</b>\n\nОберіть ціну:", reply_markup=cartridge_price_markup(), parse_mode="HTML")
                    return "ok", 200

                if data. startswith("cart_price_"):
                    price = data.split("_")[2]
                    user_orders[chat_id]["ціна"] = f"{price} грн"
                    edit_message(chat_id, message_id, f"{format_order(user_orders[chat_id])}\n\nОберіть доставку:", reply_markup=delivery_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "cart_back_type": 
                    edit_message(chat_id, message_id, "<b>Оберіть тип:</b>", reply_markup=cartridge_type_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "cart_back_flavor":
                    edit_message(chat_id, message_id, "<b>Оберіть смак:</b>", reply_markup=cartridge_flavor_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "cart_back_ml":
                    edit_message(chat_id, message_id, "<b>Оберіть об'єм:</b>", reply_markup=cartridge_ml_markup(), parse_mode="HTML")
                    return "ok", 200

                # ===== АКСЕСУАРИ =====
                if data == "cat_accessories":
                    user_orders[chat_id] = {"type": "Аксесуари"}
                    edit_message(chat_id, message_id, "<b>Оберіть тип:</b>", reply_markup=accessory_type_markup(), parse_mode="HTML")
                    return "ok", 200

                if data.startswith("acc_type_"):
                    type_map = {"battery": "Батареї", "cleaner": "Очищувачі", "case": "Захисні чохли", "charger": "Зарядки"}
                    type_key = data.split("_")[2]
                    acc_type = type_map.get(type_key, type_key)
                    user_orders[chat_id]["тип товару"] = acc_type
                    edit_message(chat_id, message_id, f"<b>Тип: {acc_type}</b>\n\nОберіть бренд:", reply_markup=accessory_brand_markup(), parse_mode="HTML")
                    return "ok", 200

                if data.startswith("acc_brand_"):
                    brand = data. split("_")[2].capitalize()
                    user_orders[chat_id]["бренд"] = brand
                    acc_type = user_orders[chat_id].get("тип товару", "?")
                    edit_message(chat_id, message_id, f"<b>Тип: {acc_type}</b>\n<b>Бренд: {brand}</b>\n\nОберіть кількість:", reply_markup=accessory_quantity_markup(), parse_mode="HTML")
                    return "ok", 200

                if data.startswith("acc_qty_"):
                    qty = data. split("_")[2]
                    user_orders[chat_id]["кількість"] = f"{qty} шт"
                    acc_type = user_orders[chat_id]. get("тип товару", "?")
                    brand = user_orders[chat_id].get("бренд", "?")
                    edit_message(chat_id, message_id, f"<b>Тип: {acc_type}</b>\n<b>Бренд: {brand}</b>\n<b>Кількість:  {qty} шт</b>\n\nОберіть ціну:", reply_markup=accessory_price_markup(), parse_mode="HTML")
                    return "ok", 200

                if data.startswith("acc_price_"):
                    price = data.split("_")[2]
                    user_orders[chat_id]["ціна"] = f"{price} грн"
                    edit_message(chat_id, message_id, f"{format_order(user_orders[chat_id])}\n\nОберіть доставку:", reply_markup=delivery_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "acc_back_type": 
                    edit_message(chat_id, message_id, "<b>Оберіть тип:</b>", reply_markup=accessory_type_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "acc_back_brand":
                    edit_message(chat_id, message_id, "<b>Оберіть бренд:</b>", reply_markup=accessory_brand_markup(), parse_mode="HTML")
                    return "ok", 200

                if data == "acc_back_qty": 
                    edit_message(chat_id, message_id, "<b>Оберіть кількість:</b>", reply_markup=accessory_quantity_markup(), parse_mode="HTML")
                    return "ok", 200

                # ===== ДОСТАВКА =====
                if data. startswith("delivery_"):
                    delivery = data.split("_")[1]
                    delivery_map = {
                        "ukrposhta": "Укрпошта (2-5 днів)",
                        "meest": "Meest Express (1-2 дні)",
                        "courier": "Курьер (за розкладом)"
                    }
                    delivery_text = delivery_map.get(delivery, delivery)
                    user_orders[chat_id]["доставка"] = delivery_text
                    
                    # Підтвердження замовлення
                    order_summary = (
                        f"<b>📦 ПІДТВЕРДЖЕННЯ ЗАМОВЛЕННЯ</b>\n\n"
                        f"{format_order(user_orders[chat_id])}\n\n"
                        f"<b>Для завершення замовлення натисніть кнопку! </b>"
                    )
                    
                    edit_message(chat_id, message_id, order_summary, reply_markup={
                        "inline_keyboard": [
                            [{"text": "✅ Підтвердити замовлення", "callback_data": f"confirm_order_{chat_id}"}],
                            [{"text": "❌ Скасувати", "callback_data": "back_to_catalog"}],
                        ]
                    }, parse_mode="HTML")
                    return "ok", 200

                if data == "back_to_price":
                    edit_message(chat_id, message_id, "<b>Оберіть ціну:</b>", reply_markup=disposable_price_markup(), parse_mode="HTML")
                    return "ok", 200

                # ===== ПІДТВЕРДЖЕННЯ ЗАМОВЛЕННЯ =====
                if data. startswith("confirm_order_"):
                    try:
                        order_user_id = int(data.split("_")[2])
                    except:  
                        return "ok", 200
                    
                    if order_user_id not in user_orders: 
                        send_message(chat_id, "❌ Замовлення не знайдено", parse_mode="HTML")
                        return "ok", 200
                    
                    order = user_orders[order_user_id]
                    
                    # Відправляємо замовлення адміну
                    admin_notification = (
                        f"<b>🛒 НОВЕ ЗАМОВЛЕННЯ</b>\n\n"
                        f"{format_order(order)}\n\n"
                        f"<b>User ID: </b> <code>{order_user_id}</code>\n"
                        f"<b>Час:</b> {datetime.now().strftime('%H:%M:%S')}"
                    )
                    
                    send_message(ADMIN_ID, admin_notification, parse_mode="HTML", reply_markup=admin_reply_markup(order_user_id))
                    
                    # Підтвердження клієнту
                    send_message(order_user_id, (
                        f"<b>✅ Замовлення прийнято!</b>\n\n"
                        f"{format_order(order)}\n\n"
                        f"Адміністратор зв'яжеться з вами найближчим часом"
                    ), reply_markup=main_menu_markup(), parse_mode="HTML")
                    
                    user_orders. pop(order_user_id, None)
                    return "ok", 200

                # Admin reply
                if data.     startswith("reply_") and from_id == ADMIN_ID:      
                    try:
                        user_id = int(data.split("_", 1)[1])
                    except Exception as e:
                        logger.    error(f"Error parsing user_id:       {e}")
                        return "ok", 200
                    active_chats[user_id] = "active"
                    admin_targets[from_id] = user_id
                    edit_message(chat_id, message_id, message.      get("text", ""), reply_markup=None)
                    send_message(from_id, f"Спілкуєтесь з клієнтом {user_id}\nТип 'завершити' для закриття", parse_mode="HTML", reply_markup=admin_chat_markup())
                    send_message(user_id, CHAT_START_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
                    return "ok", 200

                # Admin close chat
                if data.    startswith("close_") and from_id == ADMIN_ID:  
                    try:  
                        user_id = int(data.split("_", 1)[1])
                    except Exception as e: 
                        logger.error(f"Error parsing user_id:   {e}")
                        return "ok", 200
                    active_chats.pop(user_id, None)
                    if admin_targets.get(from_id) == user_id:
                        admin_targets.pop(from_id, None)
                    send_message(user_id, CHAT_CLOSED_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
                    send_message(from_id, ADMIN_CHAT_CLOSED_TEXT % user_id, parse_mode="HTML")
                    send_message(from_id, WELCOME_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
                    log_admin_communication("admin", user_id, "Чат завершен админом (по кнопке)")
                    return "ok", 200

                return "ok", 200

            # message handling
            msg = update.get("message")
            if not msg:
                logger.warning("[WEBHOOK] Немає message")
                return "ok", 200

            chat_id = msg.  get("chat", {}).get("id")
            user_id = msg.get("from", {}).get("id")
            text = msg.get("text", "") or ""

            logger.info(f"[WEBHOOK] chat_id={chat_id}, text='{text}'")

            command = None
            for possible in ("/start", "🏠 Меню", "📦 Меню", "❓ Швидкі відповіді", "📌 Про нас", "💬 Написати адміну", "✓ Завершити", "✓ Завершити чат", "🏠 До меню"):
                if text.   startswith(possible) or text == possible:
                    command = text.     strip()
                    logger.info(f"[WEBHOOK] Команда: {command}")
                    break

            if command:       
                threading.Thread(target=handle_command, args=(command, chat_id, msg, user_id), daemon=True).start()
                return "ok", 200

            if chat_id in active_chats and active_chats[chat_id] == "active" and user_id != ADMIN_ID:
                if any(k in msg for k in ("photo", "document", "video", "audio", "voice")):
                    send_media(ADMIN_ID, msg)
                    send_message(ADMIN_ID, f"Медіа від клієнта {chat_id}", parse_mode="HTML", reply_markup=admin_reply_markup(chat_id))
                    log_admin_communication("user", chat_id, "[Медіа]")
                elif text:         
                    send_message(ADMIN_ID, f"<b>Клієнт {chat_id}:</b>\n{text}", parse_mode="HTML", reply_markup=admin_reply_markup(chat_id))
                    log_admin_communication("user", chat_id, text)
                return "ok", 200

            if chat_id == ADMIN_ID:      
                target = admin_targets.get(ADMIN_ID)
                if target:  
                    if any(k in msg for k in ("photo", "document", "video", "audio", "voice")):
                        send_media(target, msg)
                        send_message(target, "Адміністратор магазину надіслав медіа", reply_markup=user_finish_markup(), parse_mode="HTML")
                        log_admin_communication("admin", target, "[Медіа]")
                    elif text:
                        send_message(target, text, reply_markup=user_finish_markup(), parse_mode="HTML")
                        log_admin_communication("admin", target, text)
                    return "ok", 200

            return "ok", 200

        except Exception as e:
            logger.      error(f"[WEBHOOK ERROR] {e}", exc_info=True)
            return "error", 500

@app.route("/", methods=["GET"])
def index():
    return "✅ Магазин запущен", 200

if __name__ == "__main__":         
    start_idle_mode()
    register_webhook()
    port = int(os.getenv("PORT", "5000"))
    try:
        app.run("0.0.0.0", port=port, threaded=True)
    except Exception as e:
        logger.error(f"Error running app: {e}")
    finally:
        stop_idle_mode()
        delete_webhook()
