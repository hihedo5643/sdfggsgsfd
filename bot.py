import os
import logging
from html import escape
from datetime import datetime, timedelta
import random
import threading
import time
import csv

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

# ======= Idle mode =======
idle_mode_enabled = True
idle_min_interval = 240
idle_max_interval = 480
idle_thread = None
idle_stop_event = threading.Event()
idle_counter = 0  # Счётчик симуляций

# ======= Лог файл =======
LOG_PATH = "admin_chat_log.csv"

def log_admin_communication(sender, user_id, message_text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.isfile(LOG_PATH)
    with open(LOG_PATH, "a", encoding="utf-8", newline='') as csvfile:
        writer = csv.   writer(csvfile, delimiter=',', quoting=csv.QUOTE_ALL)
        if not file_exists:
            writer.writerow(["timestamp", "sender", "user_id", "text"])
        writer.writerow([timestamp, sender, user_id, message_text])

# ======= КОНСТАНТИ МАГАЗИНУ =======
WELCOME_TEXT = (
    "<b>Ласкаво просимо до нашого магазину!  🛍️</b>\n\n"
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
    "Контакти:   +38 (095) 123-45-67\n"
    "Email: shop@example.com"
)

QUICK_ANSWERS_TEXT = (
    "<b>Швидкі відповіді ⚡</b>\n\n"
    "Натисніть на питання, щоб дізнатися відповідь:"
)

MENU_TEXT = (
    "<b>Каталог товарів 📦</b>\n\n"
    "Оберіть категорію:"
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
    "Клієнт:     <code>%s</code>"
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
        logger.info(f"[IDLE MODE] #{idle_counter}:     {timestamp} → {activity}")
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
            logger.error(f"[IDLE MODE] Помилка:     {e}")
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
            logger.    info("[IDLE MODE] Потік зупинен")
    except Exception as e:       
        logger.error(f"Error stopping idle mode: {e}")

# ======= Функція для реєстрації вебхука =======
def register_webhook():
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    payload = {
        "url":     WEBHOOK_URL,
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
            logger. error(f"❌ Помилка:     {result.   get('description')}")
            return False
    except Exception as e:
        logger.   error(f"❌ Помилка реєстрації вебхука: {e}")
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
            [{"text":     "📦 Меню"}],
            [{"text":  "❓ Швидкі відповіді"}],
            [{"text":    "📌 Про нас"}, {"text": "💬 Написати адміну"}],
        ],
        "resize_keyboard":   True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Виберіть опцію..  .",
    }

def user_finish_markup():
    return {
        "keyboard": [[{"text": "✓ Завершити"}, {"text": "🏠 Меню"}]],
        "resize_keyboard":  True,
        "one_time_keyboard": False,
    }

def admin_chat_markup():
    """Розмітка для адміністратора під час спілкування з клієнтом"""
    return {
        "keyboard": [[{"text": "✓ Завершити чат"}]],
        "resize_keyboard":     True,
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
            [{"text": "🚚 Як здійснюється доставка?", "callback_data": "qa_delivery"}],
            [{"text": "💰 Які способи оплати?", "callback_data": "qa_payment"}],
            [{"text": "🔄 Як повернути товар?", "callback_data":   "qa_return"}],
            [{"text": "❓ Як замовити товар?", "callback_data": "qa_order"}],
            [{"text":     "🏠 Назад", "callback_data": "back_to_menu"}],
        ]
    }

quick_answers = {
    "qa_delivery":   (
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
    "qa_return": (
        "<b>🔄 Як повернути товар?</b>\n\n"
        "Ви можете повернути товар протягом 14 днів після покупки:\n"
        "1. Напишіть нам для оформлення повернення\n"
        "2. Отримайте адресу для відправки\n"
        "3. Відправте товар поштою\n"
        "4. Після перевірки - повернення грошей\n\n"
        "Товар повинен бути у оригіналі та без використання"
    ),
    "qa_order": (
        "<b>❓ Як замовити товар?</b>\n\n"
        "Це легко:\n"
        "1. Оберіть товари з каталогу\n"
        "2. Додайте до кошика\n"
        "3. Оформіть замовлення\n"
        "4. Виберіть спосіб доставки і оплати\n"
        "5. Отримайте товар!\n\n"
        "Якщо потрібна допомога - напишіть адміну"
    ),
}

def menu_markup():
    """Кнопки для меню товарів - вейпи і сигарети"""
    return {
        "inline_keyboard": [
            [{"text": "🚬 Одноразові сигарети", "callback_data": "cat_disposable"}],
            [{"text":   "♻️ Багаторазові сигарети", "callback_data":   "cat_reusable"}],
            [{"text":   "🔌 Картриджи", "callback_data":  "cat_cartridges"}],
            [{"text": "🎧 Аксесуари", "callback_data": "cat_accessories"}],
            [{"text":     "🏠 Назад", "callback_data": "back_to_menu"}],
        ]
    }

# ======= Описи категорій =======
category_descriptions = {
    "cat_disposable": (
        "<b>🚬 Одноразові сигарети</b>\n\n"
        "Великий вибір одноразових вейпів:\n"
        "• Різні смаки і ароми\n"
        "• Різні рівні нікотину\n"
        "• Від надійних виробників\n\n"
        "Ціна: від 150 грн\n\n"
        "Для більш детальної інформації - напишіть адміну"
    ),
    "cat_reusable": (
        "<b>♻️ Багаторазові сигарети</b>\n\n"
        "Якісні багаторазові пристрої:\n"
        "• Тривала експлуатація\n"
        "• Регулювання потужності\n"
        "• Елегантний дизайн\n\n"
        "Ціна:  від 800 грн\n\n"
        "Для більш детальної інформації - напишіть адміну"
    ),
    "cat_cartridges": (
        "<b>🔌 Картриджи</b>\n\n"
        "Замінні картриджи для багаторазових пристроїв:\n"
        "• Сумісність з популярними моделями\n"
        "• Різні смаки\n"
        "• Високої якості\n\n"
        "Ціна: від 300 грн\n\n"
        "Для більш детальної інформації - напишіть адміну"
    ),
    "cat_accessories": (
        "<b>🎧 Аксесуари</b>\n\n"
        "Необхідні аксесуари для вейпів:\n"
        "• Батареї і зарядки\n"
        "• Чохли і кейси\n"
        "• Чистячі рідини\n"
        "• Запасні частини\n\n"
        "Ціна: від 50 грн\n\n"
        "Для більш детальної інформації - напишіть адміну"
    ),
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
        "message_id": message_id,
        "text":     text,
        "parse_mode": parse_mode
    }
    if reply_markup is not None:
        payload["reply_markup"] = __import__('json').dumps(reply_markup)
    try: 
        resp = requests.post(url, json=payload, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  
        logger.error(f"Failed to edit message:     {e}")
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
                    payload["caption"] = msg.    get("caption")
                try:  
                    resp = requests.   post(url, json=payload, timeout=8)
                    resp.   raise_for_status()
                    return True
                except Exception as e:  
                    logger.error(f"Failed to send media to {chat_id}: {e}")
                    return False
    except Exception as e:  
        logger.error(f"Error in send_media: {e}")
    return False

# ======= Обработка команд в отдельном потоке =======
def handle_command(command, chat_id, msg, user_id):
    try:
        logger.info(f"[THREAD] Команда: {command} від {chat_id}")
        # ADMIN COMMANDS
        if chat_id == ADMIN_ID and command == "/help":
            send_message(chat_id, WELCOME_TEXT, parse_mode="HTML")
        elif command.    startswith("/start") or command == "🏠 Меню":  
            active_chats.    pop(user_id, None)
            admin_targets.  pop(ADMIN_ID, None)
            send_message(chat_id, WELCOME_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        elif command == "📦 Меню": 
            send_message(chat_id, MENU_TEXT, reply_markup=menu_markup(), parse_mode="HTML")
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
                    send_message(chat_id, "Адміністратор прочитає ваше повідомлення в найближчий час..   .", reply_markup=user_finish_markup(), parse_mode="HTML")
                notif = (
                    f"<b>НОВИЙ ЗАПИТ ВІД КЛІЄНТА</b>\n\n"
                    f"User ID: <code>{chat_id}</code>\n"
                    f"Час:    {datetime.now().strftime('%H:%M:%S')}"
                )
                send_message(ADMIN_ID, notif, parse_mode="HTML", reply_markup=admin_reply_markup(chat_id))
                if any(k in msg for k in ("photo", "document", "video", "audio", "voice")):
                    send_media(ADMIN_ID, msg)
            else:
                if not is_working_hours():
                    send_message(chat_id, OFF_HOURS_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
                else:
                    send_message(chat_id, "Ваше повідомлення вже отправлено.     Очікуйте..   .", reply_markup=user_finish_markup(), parse_mode="HTML")
        elif command == "✓ Завершити" and chat_id in active_chats:
            active_chats.    pop(chat_id, None)
            if admin_targets.get(ADMIN_ID) == chat_id:
                admin_targets.pop(ADMIN_ID, None)
            send_message(chat_id, CHAT_CLOSED_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
            send_message(ADMIN_ID, f"Клієнт завершив чат", parse_mode="HTML")
            log_admin_communication("user", chat_id, "Чат завершен клієнтом")
        # НОВІ КОМАНДИ ДЛЯ АДМІНА
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

                # Quick answers callbacks
                if data in quick_answers:  
                    edit_message(chat_id, message_id, quick_answers[data], reply_markup=quick_answers_markup())
                    return "ok", 200

                # Menu categories callbacks
                if data.  startswith("cat_"):
                    category = data
                    cat_text = category_descriptions.get(category, "<b>Товар не знайдено</b>")
                    edit_message(chat_id, message_id, cat_text, reply_markup=menu_markup())
                    return "ok", 200

                # Back to menu
                if data == "back_to_menu":
                    edit_message(chat_id, message_id, WELCOME_TEXT, reply_markup=main_menu_markup())
                    return "ok", 200

                # Admin reply
                if data.    startswith("reply_") and from_id == ADMIN_ID:     
                    try:
                        user_id = int(data.split("_", 1)[1])
                    except Exception as e:
                        logger.    error(f"Error parsing user_id:     {e}")
                        return "ok", 200
                    active_chats[user_id] = "active"
                    admin_targets[from_id] = user_id
                    edit_message(chat_id, message_id, message.    get("text", ""), reply_markup=None)
                    send_message(from_id, f"Спілкуєтесь з клієнтом {user_id}\nТип 'завершити' для закриття", parse_mode="HTML", reply_markup=admin_chat_markup())
                    send_message(user_id, CHAT_START_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
                    return "ok", 200

                # Admin close chat
                if data.   startswith("close_") and from_id == ADMIN_ID:  
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
                    command = text.   strip()
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
            logger.    error(f"[WEBHOOK ERROR] {e}", exc_info=True)
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
