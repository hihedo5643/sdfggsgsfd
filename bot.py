import os
import logging
from datetime import datetime, timedelta
import random
import threading
import time
import csv
import json

import requests
from flask import Flask, request

# ======= КОНФІГУРАЦІЯ =======
TOKEN = os.getenv("API_TOKEN")
if not TOKEN:
    raise RuntimeError("Environment variable API_TOKEN is required")

try:
    ADMIN_ID = int(os. getenv("ADMIN_ID", "0"))
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

# ======= ГЛОБАЛЬНІ ЗМІННІ =======
active_chats = {}
admin_targets = {}
user_orders = {}

# Блокування для потокобезпеки
data_lock = threading.Lock()

# ======= IDLE MODE =======
idle_mode_enabled = True
idle_min_interval = 240
idle_max_interval = 480
idle_thread = None
idle_stop_event = threading.Event()
idle_counter = 0

# ======= ЛОГ ФАЙЛ =======
LOG_PATH = "admin_chat_log.csv"

def log_admin_communication(sender, user_id, message_text):
    """Логує комунікацію адміна з клієнтом"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.isfile(LOG_PATH)
    try:
        with open(LOG_PATH, "a", encoding="utf-8", newline='') as csvfile:
            writer = csv.  writer(csvfile, delimiter=',', quoting=csv.QUOTE_ALL)
            if not file_exists:
                writer.  writerow(["timestamp", "sender", "user_id", "text"])
            writer.writerow([timestamp, sender, user_id, message_text])
    except Exception as e:
        logger.error(f"Log error: {e}")

# ======= ТЕКСТОВІ КОНСТАНТИ =======
TEXTS = {
    "welcome": (
        "<b>🛍️ Ласкаво просимо!   </b>\n\n"
        "Оберіть, як ми можемо вам допомогти:"
    ),
    "about": (
        "<b>📌 Про нас</b>\n\n"
        "✅ Найбільший вибір вейпів в Україні\n"
        "✅ Доставка по всій країні\n"
        "✅ Швидка обробка замовлень\n"
        "✅ Гарантія якості\n\n"
        "☎️ +38 (095) 123-45-67\n"
        "📧 shop@example.com\n"
        "📱 Канал:  @betaPapiros"
    ),
    "order_help": (
        "<b>📦 Як замовити?   </b>\n\n"
        "1️⃣ Натисніть '🛒 Замовити товар'\n"
        "2️⃣ Напишіть посилання або назву товару\n"
        "3️⃣ Виберіть доставку\n"
        "4️⃣ Адміністратор зв'яжеться з вами\n"
        "5️⃣ Готово! ✅"
    ),
    "delivery_help": (
        "<b>🚚 Способи доставки</b>\n\n"
        "🏤 Укрпошта (2-5 днів) - дешево\n"
        "📦 Нова Пошта (1-2 дні) - швидко\n"
        "📦 Meest (1-2 дні) - зручно\n"
        "🚗 Самовивіз Київ (сьогодні)"
    ),
    "payment_help": (
        "<b>💳 Способи оплати</b>\n\n"
        "💳 Карта (Visa/Mastercard)\n"
        "📱 Apple Pay / Google Pay\n"
        "💰 Готівка при отриманні\n"
        "🏪 Переводи на карту"
    ),
    "return_help": (
        "<b>🔄 Повернення товару</b>\n\n"
        "⏰ Протягом 14 днів після покупки\n"
        "📋 Заповніть форму повернення\n"
        "🚚 Відправте товар назад\n"
        "💵 Отримайте гроші"
    ),
    "off_hours": (
        "<b>⏰ Позаробочий час</b>\n\n"
        "Адміністрація не працює, але ми\n"
        "зв'яжемося з вами найближчим часом!"
    ),
    "chat_start": (
        "<b>💬 Чат з адміном</b>\n\n"
        "Напишіть своє питання..."
    ),
    "chat_end": (
        "<b>✅ Дякуємо!   </b>\n\n"
        "Чат завершено.  До слова!"
    ),
    "order_sent": (
        "<b>✅ Замовлення отримано!  </b>\n\n"
        "Адміністратор розглянув ваше замовлення\n"
        "і скоро зв'яжеться з вами.\n\n"
        "Дякуємо за замовлення!   🙏"
    ),
    "ask_product": (
        "<b>📦 Що ви хочете замовити? </b>\n\n"
        "✏️ Напишіть:\n"
        "• Посилання на товар з @betaPapiros\n"
        "• Або просто назву/опис товару\n\n"
        "Приклад:  'Elektronny sigara VAPE 5000'\n"
        "або 't. me/betaPapiros/123'"
    ),
    "ask_delivery": (
        "<b>🚚 Як доставити?  </b>"
    ),
    "order_received": (
        "<b>📬 ЗАМОВЛЕННЯ</b>\n\n"
        "<b>Товар:</b> {product}\n"
        "<b>Доставка:</b> {delivery}\n\n"
        "<b>User ID:</b> <code>{user_id}</code>\n"
        "<b>Час: </b> {time}"
    ),
}

# ======= КНОПКИ =======
def get_main_menu():
    """Головне меню"""
    return {
        "keyboard": [
            [{"text": "🛒 Замовити товар"}],
            [{"text": "❓ Питання"}],
            [{"text": "📌 Про нас"}, {"text": "💬 Взяти з адміном"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Виберіть опцію...",
    }

def get_questions_menu():
    """Меню швидких питань"""
    return {
        "inline_keyboard": [
            [{"text": "📦 Як замовити?", "callback_data": "q_order"}],
            [{"text": "🚚 Доставка", "callback_data": "q_delivery"}],
            [{"text": "💳 Оплата", "callback_data":  "q_payment"}],
            [{"text": "🔄 Повернення", "callback_data": "q_return"}],
            [{"text": "⬅️ Назад", "callback_data": "menu_main"}],
        ]
    }

def get_delivery_menu():
    """Меню вибору доставки"""
    return {
        "inline_keyboard": [
            [{"text":  "🏤 Укрпошта (2-5 днів)", "callback_data": "del_1"}],
            [{"text":  "📦 Нова Пошта (1-2 дні)", "callback_data": "del_2"}],
            [{"text": "📦 Meest (1-2 дні)", "callback_data": "del_3"}],
            [{"text": "🚗 Самовивіз Київ", "callback_data": "del_4"}],
            [{"text": "⬅️ Назад", "callback_data": "order_back"}],
        ]
    }

def get_chat_menu():
    """Меню чату"""
    return {
        "keyboard": [[{"text": "✓ Завершити"}]],
        "resize_keyboard": True,
    }

def get_admin_menu(user_id):
    """Кнопки для адміна"""
    return {
        "inline_keyboard": [
            [{"text": "✉️ Відповісти", "callback_data": f"reply_{user_id}"}],
            [{"text": "✗ Закрити", "callback_data":  f"close_{user_id}"}],
        ]
    }

# ======= IDLE MODE =======
def simulate_user_activity():
    """Імітує дію користувача"""
    global idle_counter
    try:
        activities = [
            "переглядає товари 👀",
            "читає описи 📖",
            "вибирає доставку 🚚",
        ]
        activity = random.choice(activities)
        idle_counter += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n[IDLE #{idle_counter}] {timestamp} - Клієнт {activity}")
        logger.info(f"[IDLE] #{idle_counter}:  {activity}")
    except Exception as e:
        logger.error(f"Idle error: {e}")

def idle_worker():
    """Потік для імітації"""
    logger.info("[IDLE] Запущено")
    while not idle_stop_event.is_set():
        try:
            wait = random.randint(idle_min_interval, idle_max_interval)
            if idle_stop_event.wait(timeout=wait):
                break
            simulate_user_activity()
        except Exception as e: 
            logger.error(f"Idle worker error: {e}")
            time.sleep(5)

def start_idle_mode():
    """Запуск імітації"""
    global idle_thread
    try:
        if idle_mode_enabled and idle_thread is None:
            idle_stop_event.clear()
            idle_thread = threading.Thread(target=idle_worker, daemon=True)
            idle_thread.start()
            logger.info("[IDLE] Потік запущено")
    except Exception as e:
        logger.error(f"Idle start error: {e}")

def stop_idle_mode():
    """Зупинка імітації"""
    global idle_thread
    try:
        if idle_thread is not None:
            idle_stop_event.set()
            idle_thread.join(timeout=2)
            idle_thread = None
            logger. info("[IDLE] Потік зупинено")
    except Exception as e: 
        logger.error(f"Idle stop error: {e}")

# ======= WEBHOOK =======
def register_webhook():
    """Реєструє webhook"""
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    try:
        resp = requests.post(url, json={"url":  WEBHOOK_URL}, timeout=10)
        if resp.json().get("ok"):
            logger. info(f"✅ Webhook:  {WEBHOOK_URL}")
            return True
        logger.error(f"❌ Webhook error: {resp.json()}")
        return False
    except Exception as e:
        logger.error(f"Webhook register error: {e}")
        return False

def delete_webhook():
    """Видаляє webhook"""
    url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook"
    try:
        requests.post(url, timeout=10)
        logger.info("✅ Webhook deleted")
    except Exception as e: 
        logger.error(f"Webhook delete error: {e}")

# ======= ВІДПРАВКА ПОВІДОМЛЕНЬ =======
def send_msg(chat_id, text, markup=None, parse_mode="HTML"):
    """Відправляє нове повідомлення"""
    if not chat_id or not text: 
        logger.error(f"Invalid message params: chat_id={chat_id}")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if markup:
        payload["reply_markup"] = json.dumps(markup)
    try:
        resp = requests.post(url, json=payload, timeout=8)
        if not resp.json().get("ok"):
            logger.error(f"Send message failed: {resp.json()}")
            return False
        return True
    except Exception as e: 
        logger.error(f"Send message error: {e}")
        return False

def edit_msg(chat_id, msg_id, text, markup=None, parse_mode="HTML"):
    """Редагує повідомлення (ТІЛЬКИ INLINE КЛАВІАТУРА)"""
    if not chat_id or not msg_id or not text:
        logger.error(f"Invalid edit params: chat_id={chat_id}, msg_id={msg_id}")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": msg_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if markup: 
        payload["reply_markup"] = json.dumps(markup)
    try:
        resp = requests. post(url, json=payload, timeout=8)
        if not resp.json().get("ok"):
            logger.warning(f"Edit message failed: {resp.json().get('description')}")
            return False
        return True
    except Exception as e: 
        logger.error(f"Edit message error: {e}")
        return False

# ======= ДОПОМІЖНІ ФУНКЦІЇ =======
def check_hours():
    """Перевіряє, працює магазин"""
    now = datetime.utcnow() + timedelta(hours=2)
    day = now.weekday()
    time_min = now.hour * 60 + now.minute

    if day >= 5:  # Сб-Вс
        return False
    if day == 4:  # Пт
        return 9 * 60 <= time_min < 15 * 60
    return 9 * 60 <= time_min < 18 * 60  # Пн-Чт

# ======= ОБРОБКА КОМАНД (ПОТІК) =======
def process_command(cmd, chat_id, user_id):
    """Обробляє команди в окремому потоці"""
    try:
        logger.info(f"[COMMAND] {cmd} from {chat_id}")

        with data_lock:
            if cmd == "/start" or cmd == "🏠":
                active_chats. pop(chat_id, None)
                admin_targets.pop(ADMIN_ID, None)
                user_orders.pop(chat_id, None)
                send_msg(chat_id, TEXTS["welcome"], get_main_menu())

            elif cmd == "🛒 Замовити товар":
                user_orders[chat_id] = {"status": "waiting_product"}
                send_msg(chat_id, TEXTS["ask_product"])

            elif cmd == "❓ Питання":
                send_msg(chat_id, "Виберіть питання:", get_questions_menu())

            elif cmd == "📌 Про нас":
                send_msg(chat_id, TEXTS["about"], get_main_menu())

            elif cmd == "💬 Взяти з адміном":
                if chat_id not in active_chats:
                    active_chats[chat_id] = "pending"

                    if not check_hours():
                        send_msg(chat_id, TEXTS["off_hours"], get_main_menu())
                    else:
                        send_msg(chat_id, TEXTS["chat_start"], get_chat_menu())

                    admin_msg = (
                        f"<b>📬 Новий чат</b>\n\n"
                        f"User:  <code>{chat_id}</code>\n"
                        f"⏰ {datetime.now().strftime('%H:%M')}"
                    )
                    send_msg(ADMIN_ID, admin_msg, get_admin_menu(chat_id))

            elif cmd == "✓ Завершити" and chat_id in active_chats:
                active_chats. pop(chat_id, None)
                admin_targets.pop(ADMIN_ID, None)
                send_msg(chat_id, TEXTS["chat_end"], get_main_menu())
                send_msg(ADMIN_ID, "✅ Чат завершено")
                log_admin_communication("user", chat_id, "Чат завершено")

    except Exception as e:
        logger.error(f"Command processing error: {e}", exc_info=True)

# ======= ОБРОБКА CALLBACK (ПОТІК) =======
def process_callback(cb_data, chat_id, msg_id, from_id, username):
    """Обробляє callback queries в окремому потоці"""
    try:
        logger.info(f"[CALLBACK] {cb_data} from {from_id} in {chat_id}")

        with data_lock:
            # Меню питань
            if cb_data == "q_order":
                edit_msg(chat_id, msg_id, TEXTS["order_help"], get_questions_menu())
            elif cb_data == "q_delivery":
                edit_msg(chat_id, msg_id, TEXTS["delivery_help"], get_questions_menu())
            elif cb_data == "q_payment": 
                edit_msg(chat_id, msg_id, TEXTS["payment_help"], get_questions_menu())
            elif cb_data == "q_return":
                edit_msg(chat_id, msg_id, TEXTS["return_help"], get_questions_menu())

            # Повернення в меню
            elif cb_data == "menu_main":
                edit_msg(chat_id, msg_id, TEXTS["welcome"], get_main_menu())
                user_orders. pop(chat_id, None)
            elif cb_data == "order_back":
                # Видаляємо inline клавіатуру та надсилаємо нове повідомлення
                send_msg(chat_id, TEXTS["ask_product"])
                user_orders. pop(chat_id, None)

            # ===== ВИБІР ДОСТАВКИ І ПЕРЕДАЧА АДМІНУ =====
            elif cb_data. startswith("del_"):
                delivery_map = {
                    "del_1": "🏤 Укрпошта (2-5 днів)",
                    "del_2": "📦 Нова Пошта (1-2 дні)",
                    "del_3": "📦 Meest (1-2 дні)",
                    "del_4": "🚗 Самовивіз Київ",
                }

                if chat_id in user_orders and user_orders[chat_id]. get("status") == "waiting_delivery":
                    order = user_orders[chat_id]
                    order["delivery"] = delivery_map.get(cb_data, "? ")
                    order["username"] = username or "unknown"
                    order["status"] = "sent_to_admin"

                    logger.info(f"[ORDER] Product:  {order. get('product')}, Delivery: {order.get('delivery')}")

                    # Редагуємо повідомлення з кнопками
                    edit_msg(chat_id, msg_id, TEXTS["order_sent"], get_main_menu())

                    # Передаємо адміну
                    admin_msg = TEXTS["order_received"]. format(
                        product=order. get("product", "?"),
                        delivery=order.get("delivery", "?"),
                        user_id=chat_id,
                        time=datetime.now().strftime("%H:%M:%S")
                    )
                    send_msg(ADMIN_ID, admin_msg, get_admin_menu(chat_id))
                    log_admin_communication("order", chat_id, f"Товар:  {order.get('product')} | Доставка: {order.get('delivery')}")

                    # Активуємо чат
                    active_chats[chat_id] = "order"
                    admin_targets[ADMIN_ID] = chat_id
                else:
                    logger.warning(f"Order not found for {chat_id} or wrong status")

            # Адмін - відповідь
            elif cb_data. startswith("reply_") and from_id == ADMIN_ID: 
                try:
                    user_id = int(cb_data.split("_")[1])
                    if user_id in active_chats:
                        active_chats[user_id] = "active"
                        admin_targets[from_id] = user_id
                        edit_msg(chat_id, msg_id, "✅ Ви відповідаєте клієнту")
                        send_msg(from_id, f"💬 Чат з {user_id}", get_chat_menu())
                        send_msg(user_id, "✅ Адмін відповідає.. .", get_chat_menu())
                        logger.info(f"[ADMIN] Reply started with {user_id}")
                except ValueError:
                    logger.error(f"Invalid user_id in reply callback: {cb_data}")

            # Адмін - закрити
            elif cb_data. startswith("close_") and from_id == ADMIN_ID: 
                try:
                    user_id = int(cb_data.split("_")[1])
                    active_chats.pop(user_id, None)
                    admin_targets.pop(from_id, None)
                    send_msg(user_id, TEXTS["chat_end"], get_main_menu())
                    edit_msg(chat_id, msg_id, "✅ Чат закрито")
                    log_admin_communication("admin", user_id, "Чат закрито")
                    logger.info(f"[ADMIN] Chat closed with {user_id}")
                except ValueError: 
                    logger.error(f"Invalid user_id in close callback:  {cb_data}")

    except Exception as e:
        logger.error(f"Callback processing error: {e}", exc_info=True)

# ======= WEBHOOK HANDLER =======
@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    if request.method == "GET":
        return "OK", 200

    try:
        data = request.get_json(force=True)
        if not data:
            logger.warning("Empty webhook data")
            return "ok", 200

        # ===== CALLBACK QUERIES =====
        if "callback_query" in data:
            cb = data["callback_query"]
            cb_data = cb.get("data", "")
            from_id = cb.get("from", {}).get("id")
            msg = cb.get("message") or {}
            chat_id = msg.get("chat", {}).get("id")
            msg_id = msg.get("message_id")
            username = cb.get("from", {}).get("username")

            if chat_id and msg_id: 
                logger.info(f"[CB] {cb_data} in {chat_id}")
                threading.Thread(
                    target=process_callback,
                    args=(cb_data, chat_id, msg_id, from_id, username),
                    daemon=True
                ).start()
            return "ok", 200

        # ===== MESSAGES =====
        msg = data.get("message")
        if not msg:
            return "ok", 200

        chat_id = msg.get("chat", {}).get("id")
        user_id = msg.get("from", {}).get("id")
        text = msg.get("text", "").strip()
        username = msg. get("from", {}).get("username")

        if not chat_id or not user_id: 
            logger.warning("Invalid message data")
            return "ok", 200

        logger.info(f"[MSG] {chat_id}:  {text[: 50]}")

        # Команди
        if text in ["/start", "🏠", "🛒 Замовити товар", "❓ Питання", "📌 Про нас", "💬 Взяти з адміном", "✓ Завершити"]:
            threading.Thread(
                target=process_command,
                args=(text, chat_id, user_id),
                daemon=True
            ).start()
            return "ok", 200

        with data_lock:
            # ===== ОПИС ТОВАРА =====
            if chat_id in user_orders and user_orders[chat_id].get("status") == "waiting_product":
                if text: 
                    user_orders[chat_id]["product"] = text
                    user_orders[chat_id]["status"] = "waiting_delivery"
                    logger.info(f"[ORDER] Product received: {text}")
                    send_msg(chat_id, TEXTS["ask_delivery"], get_delivery_menu())
                return "ok", 200

            # ===== АКТИВНИЙ ЧАТ З АДМІНОМ (від клієнта) =====
            if chat_id in active_chats and active_chats[chat_id] in ["active", "order", "pending"] and user_id != ADMIN_ID:
                if text:
                    logger.info(f"[CHAT_USER] {chat_id} -> admin: {text[: 50]}")
                    send_msg(ADMIN_ID, f"<b>💬 {chat_id}:</b>\n{text}", get_admin_menu(chat_id))
                    log_admin_communication("user", chat_id, text)
                    # Активуємо чат якщо був pending
                    if active_chats[chat_id] == "pending":
                        active_chats[chat_id] = "active"
                        admin_targets[ADMIN_ID] = chat_id
                return "ok", 200

            # ===== АКТИВНИЙ ЧАТ (від адміна) =====
            if chat_id == ADMIN_ID: 
                target = admin_targets.get(ADMIN_ID)
                if target and text:
                    logger.info(f"[CHAT_ADMIN] admin -> {target}: {text[:50]}")
                    send_msg(target, text, get_chat_menu())
                    log_admin_communication("admin", target, text)
                return "ok", 200

        return "ok", 200

    except Exception as e:
        logger. error(f"Webhook error:  {e}", exc_info=True)
        return "error", 500

@app.route("/", methods=["GET"])
def index():
    return "✅ Shop is running", 200

if __name__ == "__main__": 
    start_idle_mode()
    register_webhook()
    port = int(os.getenv("PORT", "5000"))
    try:
        app.run("0.0.0.0", port=port, threaded=True)
    except Exception as e:
        logger.error(f"App error: {e}")
    finally:
        stop_idle_mode()
        delete_webhook()
        
