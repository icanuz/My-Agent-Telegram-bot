"""Muhammadaziz uslubida javob beradigan Telegram bot (Flask + webhook + Gemini).

Render'da gunicorn orqali ishga tushadi. cron-job.org /health ni ping qilib
bepul serverni uxlatmaydi.
"""
import logging
import os
import threading
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

import requests
from flask import Flask, abort, jsonify, request

try:  # lokal ishlatish uchun .env; Render'da env vars o'zi beriladi
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

# ---------- Sozlamalar ----------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change-me-secret")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "").strip()
# Bo'sh bo'lsa hamma yozishi mumkin. Misol: "123456,789012"
ALLOWED_CHAT_IDS = {c.strip() for c in os.environ.get("ALLOWED_CHAT_IDS", "").split(",") if c.strip()}
PUBLIC_URL = (os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
HISTORY_LEN = int(os.environ.get("HISTORY_LEN", "20"))
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "12"))

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
PERSONA = (Path(__file__).parent / "persona.txt").read_text(encoding="utf-8").strip()

app = Flask(__name__)

# ---------- Xotira (RAM'da; server qayta ishga tushsa tozalanadi) ----------
history = defaultdict(lambda: deque(maxlen=HISTORY_LEN))  # chat_id -> [{role, text}]
seen_updates = OrderedDict()  # update_id dedup
rate = defaultdict(deque)
lock = threading.Lock()


def tg(method, **payload):
    try:
        r = requests.post(f"{TG_API}/{method}", json=payload, timeout=20)
        if not r.ok:
            log.warning("Telegram %s xato: %s %s", method, r.status_code, r.text[:200])
        return r
    except requests.RequestException as e:
        log.warning("Telegram %s ulanish xatosi: %s", method, e)


def send_text(chat_id, text, reply_to=None):
    text = text.strip() or "…"
    for i in range(0, len(text), 4000):  # Telegram limiti 4096
        tg("sendMessage", chat_id=chat_id, text=text[i : i + 4000],
           **({"reply_to_message_id": reply_to} if reply_to and i == 0 else {}))


def ask_gemini(chat_id):
    contents = [
        {"role": m["role"], "parts": [{"text": m["text"]}]} for m in history[chat_id]
    ]
    body = {
        "systemInstruction": {"parts": [{"text": PERSONA}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 800},
    }
    for attempt in range(3):
        try:
            r = requests.post(
                GEMINI_URL, json=body, timeout=45,
                headers={"x-goog-api-key": GEMINI_API_KEY},
            )
            if r.status_code in (429, 500, 503):
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            log.warning("Gemini xato (urinish %s): %s", attempt + 1, e)
            time.sleep(1.5)
    return None


def handle_update(update):
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat_id = str(msg["chat"]["id"])
    text = (msg.get("text") or "").strip()

    if ALLOWED_CHAT_IDS and chat_id not in ALLOWED_CHAT_IDS and chat_id != OWNER_CHAT_ID:
        log.info("Ruxsat yo'q: %s", chat_id)
        return

    # /id — chat_id ni bilib olish uchun (OWNER_CHAT_ID ga qo'yasiz)
    if text.startswith("/id"):
        send_text(chat_id, f"Sizning chat_id: {chat_id}")
        return
    if text.startswith("/start"):
        send_text(chat_id, "Assalomu alaykum! Men Muhammadazizning AI yordamchisiman. Savolingizni yozing 🙂")
        return
    if text.startswith("/reset"):
        history[chat_id].clear()
        send_text(chat_id, "Suhbat tozalandi ✅")
        return
    if not text:
        send_text(chat_id, "Hozircha faqat matn tushunaman, yozib yuboring 🙂", msg["message_id"])
        return

    # oddiy rate limit
    now = time.time()
    q = rate[chat_id]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        send_text(chat_id, "Sekinroq, bir daqiqa kuting 🙂")
        return
    q.append(now)

    tg("sendChatAction", chat_id=chat_id, action="typing")
    history[chat_id].append({"role": "user", "text": text})
    answer = ask_gemini(chat_id)
    if not answer:
        history[chat_id].pop()
        send_text(chat_id, "Hozir javob bera olmayapman, birozdan keyin qayta yozing.")
        return
    history[chat_id].append({"role": "model", "text": answer})
    send_text(chat_id, answer)


# ---------- Flask yo'llari ----------
@app.get("/")
def index():
    return "ICANUZ bot ishlayapti ✅"


@app.get("/health")
def health():  # cron-job.org shuni ping qiladi
    return jsonify(ok=True, ts=int(time.time()))


@app.post("/webhook")
def webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        abort(403)
    update = request.get_json(silent=True) or {}
    uid = update.get("update_id")
    with lock:
        if uid in seen_updates:
            return "ok"
        seen_updates[uid] = 1
        while len(seen_updates) > 1000:
            seen_updates.popitem(last=False)
    # Telegram'ga darhol 200 qaytaramiz, javobni fonda tayyorlaymiz
    threading.Thread(target=_safe_handle, args=(update,), daemon=True).start()
    return "ok"


def _safe_handle(update):
    try:
        handle_update(update)
    except Exception:
        log.exception("handle_update yiqildi")


def setup_webhook():
    if not (BOT_TOKEN and PUBLIC_URL):
        log.warning("BOT_TOKEN yoki PUBLIC_URL yo'q — webhook o'rnatilmadi")
        return
    r = tg("setWebhook", url=f"{PUBLIC_URL}/webhook", secret_token=WEBHOOK_SECRET,
           allowed_updates=["message", "edited_message"], drop_pending_updates=True)
    log.info("setWebhook: %s", r.text if r is not None else "xato")
    if OWNER_CHAT_ID:
        send_text(OWNER_CHAT_ID, "🟢 Bot ishga tushdi")


setup_webhook()

if __name__ == "__main__":  # lokal test: webhook'siz, polling bilan
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN kerak")
    tg("deleteWebhook")
    offset = None
    log.info("Polling rejimi (lokal)")
    while True:
        r = requests.get(f"{TG_API}/getUpdates", params={"timeout": 30, "offset": offset}, timeout=40)
        for u in r.json().get("result", []):
            offset = u["update_id"] + 1
            _safe_handle(u)
