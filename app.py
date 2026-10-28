"""ICANUZ yordamchi Telegram boti: tugmali tayyor javoblar + (ixtiyoriy) Gemini.

Flask + webhook, Render'da gunicorn bilan ishlaydi. cron-job.org /health ni ping qiladi.
Gemini limiti tugasa ham bot tugmalar va kalit so'zlar orqali ishlashda davom etadi.
"""
import logging
import os
import re
import threading
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

import requests
from flask import Flask, abort, jsonify, request

import faq

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
AI_ENABLED = os.environ.get("AI_ENABLED", "1") == "1" and bool(GEMINI_API_KEY)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "change-me-secret")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "").strip()
ADMIN_CONTACT = os.environ.get("ADMIN_CONTACT", "Muhammadaziz bilan Telegram orqali yozing")
ALLOWED_CHAT_IDS = {c.strip() for c in os.environ.get("ALLOWED_CHAT_IDS", "").split(",") if c.strip()}
PUBLIC_URL = (os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
HISTORY_LEN = int(os.environ.get("HISTORY_LEN", "12"))
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "12"))

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

KNOWLEDGE = "\n\n".join(
    f"{faq.FAQ[k][0]}\n{faq.FAQ[k][1].format(contact=ADMIN_CONTACT)}" for k in faq.ORDER
)
PERSONA = (
    (Path(__file__).parent / "persona.txt").read_text(encoding="utf-8").strip()
    + "\n\nKURS HAQIDA RASMIY MA'LUMOTLAR (faqat shularga tayan, boshqa narsa o'ylab topma):\n"
    + KNOWLEDGE
)

app = Flask(__name__)

# ---------- Xotira (RAM'da; server qayta ishga tushsa tozalanadi) ----------
history = defaultdict(lambda: deque(maxlen=HISTORY_LEN))
seen_updates = OrderedDict()
rate = defaultdict(deque)
state = {}  # chat_id -> "apply"
ai_blocked_until = 0.0
lock = threading.Lock()


# ---------- Telegram yordamchilari ----------
def tg(method, **payload):
    try:
        r = requests.post(f"{TG_API}/{method}", json=payload, timeout=20)
        if not r.ok:
            log.warning("Telegram %s xato: %s %s", method, r.status_code, r.text[:200])
        return r
    except requests.RequestException as e:
        log.warning("Telegram %s ulanish xatosi: %s", method, e)


def menu_keyboard():
    rows, row = [], []
    for k in faq.ORDER:
        row.append({"text": faq.FAQ[k][0], "callback_data": f"faq:{k}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "✍️ Ariza qoldirish", "callback_data": "apply"}])
    rows.append([{"text": "💬 Boshqa savol yozish", "callback_data": "ask"}])
    return {"inline_keyboard": rows}


def back_keyboard(with_apply=True):
    rows = []
    if with_apply:
        rows.append([{"text": "✍️ Ariza qoldirish", "callback_data": "apply"}])
    rows.append([{"text": "⬅️ Menyu", "callback_data": "menu"}])
    return {"inline_keyboard": rows}


def send_text(chat_id, text, reply_markup=None):
    text = text.strip() or "…"
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    for i, c in enumerate(chunks):
        extra = {"reply_markup": reply_markup} if reply_markup and i == len(chunks) - 1 else {}
        tg("sendMessage", chat_id=chat_id, text=c, **extra)


def show_menu(chat_id, text=None):
    send_text(chat_id, text or faq.WELCOME, menu_keyboard())


def fill(text):
    return text.format(contact=ADMIN_CONTACT)


# ---------- Kalit so'z bo'yicha qidiruv (API kerak emas) ----------
def norm(s):
    s = s.lower()
    for ch in "ʻʼ’‘`´":
        s = s.replace(ch, "'")
    return re.sub(r"\s+", " ", s).strip()


def match_faq(text):
    t = norm(text)
    best, best_score = None, 0
    for key in faq.ORDER:
        score = sum(len(kw) for kw in faq.FAQ[key][2] if norm(kw) in t)
        if score > best_score:
            best, best_score = key, score
    return best if best_score >= 4 else None


# ---------- Gemini (zaxira) ----------
def ask_gemini(chat_id):
    global ai_blocked_until
    if not AI_ENABLED or time.time() < ai_blocked_until:
        return None
    body = {
        "systemInstruction": {"parts": [{"text": PERSONA}]},
        "contents": [{"role": m["role"], "parts": [{"text": m["text"]}]} for m in history[chat_id]],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
    }
    if "2.5" in GEMINI_MODEL and "pro" not in GEMINI_MODEL:
        body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
    try:
        r = requests.post(GEMINI_URL, json=body, timeout=40, headers={"x-goog-api-key": GEMINI_API_KEY})
        if r.status_code == 429:
            ai_blocked_until = time.time() + 600  # 10 daqiqa Gemini'ni urib turmaymiz
            log.warning("Gemini limit (429). 10 daqiqa tugmali rejim.")
            return None
        if not r.ok:
            log.error("Gemini %s: %s", r.status_code, r.text[:300])
            if r.status_code in (400, 401, 403, 404):
                ai_blocked_until = time.time() + 600
            return None
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip() or None
    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        log.warning("Gemini xato: %s", e)
        return None


# ---------- Mantiq ----------
def handle_callback(cq):
    chat_id = str(cq["message"]["chat"]["id"])
    mid = cq["message"]["message_id"]
    data = cq.get("data", "")
    tg("answerCallbackQuery", callback_query_id=cq["id"])

    def edit(text, kb):
        r = tg("editMessageText", chat_id=chat_id, message_id=mid, text=text, reply_markup=kb)
        if r is None or not r.ok:  # eski/o'zgarmagan xabar bo'lsa yangisini yuboramiz
            send_text(chat_id, text, kb)

    if data == "menu":
        state.pop(chat_id, None)
        edit(faq.WELCOME, menu_keyboard())
    elif data.startswith("faq:") and data[4:] in faq.FAQ:
        title, answer, _ = faq.FAQ[data[4:]]
        edit(f"{title}\n\n{fill(answer)}", back_keyboard())
    elif data == "ask":
        send_text(chat_id, "Savolingizni yozing, javob berishga harakat qilaman 🙂", back_keyboard(False))
    elif data == "apply":
        state[chat_id] = "apply"
        send_text(
            chat_id,
            "✍️ Ariza qoldirish\n\nIsmingiz, yoshingiz va telefon raqamingizni bitta xabarda yozing.\n"
            "Masalan: Ali, 14 yosh, +998 90 123 45 67",
            back_keyboard(False),
        )


def handle_apply(chat_id, msg, text):
    state.pop(chat_id, None)
    u = msg.get("from", {})
    who = f"@{u['username']}" if u.get("username") else (u.get("first_name") or "noma'lum")
    lead = f"🆕 Yangi ariza\nKimdan: {who} (id {u.get('id')})\n\n{text[:600]}"
    log.info("ARIZA: %s", lead.replace("\n", " | "))
    if OWNER_CHAT_ID:
        send_text(OWNER_CHAT_ID, lead)
    send_text(chat_id, "Rahmat! Arizangiz qabul qilindi ✅ Tez orada siz bilan bog'lanamiz.", back_keyboard(False))


def handle_message(msg):
    chat_id = str(msg["chat"]["id"])
    text = (msg.get("text") or "").strip()

    if text.startswith("/id"):
        send_text(chat_id, f"Sizning chat_id: {chat_id}")
        return
    if text.startswith("/start") or text.startswith("/menu") or norm(text) in faq.GREETINGS:
        state.pop(chat_id, None)
        show_menu(chat_id)
        return
    if text.startswith("/reset"):
        history[chat_id].clear()
        state.pop(chat_id, None)
        send_text(chat_id, "Suhbat tozalandi ✅", back_keyboard(False))
        return
    if not text:
        show_menu(chat_id, "Hozircha faqat matn tushunaman. Tugmalardan tanlang 👇")
        return

    now = time.time()
    q = rate[chat_id]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        send_text(chat_id, "Sekinroq, bir daqiqa kuting 🙂")
        return
    q.append(now)

    if state.get(chat_id) == "apply":
        handle_apply(chat_id, msg, text)
        return

    # 1) tayyor javob (API ishlatilmaydi)
    key = match_faq(text)
    if key:
        title, answer, _ = faq.FAQ[key]
        send_text(chat_id, f"{title}\n\n{fill(answer)}", back_keyboard())
        return

    # 2) Gemini (ixtiyoriy)
    tg("sendChatAction", chat_id=chat_id, action="typing")
    history[chat_id].append({"role": "user", "text": text})
    answer = ask_gemini(chat_id)
    if answer:
        history[chat_id].append({"role": "model", "text": answer})
        send_text(chat_id, answer, back_keyboard())
        return
    history[chat_id].pop()

    # 3) zaxira: menyu
    show_menu(
        chat_id,
        "Bu savolga aniq javobim yo'q 🤔 Quyidagi bo'limlardan tanlang yoki "
        f"to'g'ridan-to'g'ri bog'laning: {ADMIN_CONTACT}",
    )


def handle_update(update):
    cq = update.get("callback_query")
    msg = update.get("message") or update.get("edited_message")
    chat = (cq["message"]["chat"] if cq and cq.get("message") else (msg or {}).get("chat")) or {}
    if not chat:
        return
    chat_id = str(chat["id"])
    if ALLOWED_CHAT_IDS and chat_id not in ALLOWED_CHAT_IDS and chat_id != OWNER_CHAT_ID:
        log.info("Ruxsat yo'q: %s", chat_id)
        return
    if cq:
        handle_callback(cq)
    elif msg:
        handle_message(msg)


# ---------- Flask yo'llari ----------
@app.get("/")
def index():
    return "ICANUZ bot ishlayapti ✅"


@app.get("/health")
def health():  # cron-job.org shuni ping qiladi
    return jsonify(ok=True, ts=int(time.time()), ai=AI_ENABLED)


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
    threading.Thread(target=_safe_handle, args=(update,), daemon=True).start()
    return "ok"


def _safe_handle(update):
    try:
        handle_update(update)
    except Exception:
        log.exception("handle_update yiqildi")


def setup_webhook():
    if not GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY yo'q — faqat tugmali rejim ishlaydi")
    if not (BOT_TOKEN and PUBLIC_URL):
        log.warning("BOT_TOKEN yoki PUBLIC_URL yo'q — webhook o'rnatilmadi")
        return
    r = tg("setWebhook", url=f"{PUBLIC_URL}/webhook", secret_token=WEBHOOK_SECRET,
           allowed_updates=["message", "edited_message", "callback_query"], drop_pending_updates=True)
    log.info("setWebhook: %s", r.text if r is not None else "xato")
    tg("setMyCommands", commands=[{"command": "menu", "description": "Asosiy menyu"},
                                  {"command": "id", "description": "Chat ID"}])
    if OWNER_CHAT_ID:
        send_text(OWNER_CHAT_ID, "🟢 Bot ishga tushdi")


setup_webhook()

if __name__ == "__main__":  # lokal test: polling
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
