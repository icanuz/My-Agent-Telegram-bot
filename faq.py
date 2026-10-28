"""Tayyor savol-javoblar. FAQAT SHU FAYLNI tahrirlab botning javoblarini o'zgartirasiz.

Har bir element: kalit -> (tugma nomi, javob matni, kalit so'zlar)
Kalit so'zlar — foydalanuvchi o'zi yozganda mos javobni topish uchun (Gemini ishlatilmaydi).
{contact} avtomatik ADMIN_CONTACT bilan almashadi.
"""

WELCOME = (
    "Assalomu alaykum! 👋\n"
    "Men ICANUZ — Andijondagi premium, loyihaga asoslangan IT va AI akademiyasining yordamchisiman.\n\n"
    "Quyidagi tugmalardan kerakli savolni tanlang yoki o'zingizning savolingizni yozing 👇"
)

FAQ = {
    "about": (
        "🎓 ICANUZ nima?",
        "ICANUZ — Andijondagi premium IT va AI akademiyasi.\n\n"
        "Bizda nazariyadan ko'ra amaliyot ko'proq: o'quvchilar 8 oy davomida real loyihalar ustida ishlaydi "
        "va kurs oxirida o'z portfoliosi bilan chiqadi.",
        ["icanuz", "nima", "akademiya", "markaz", "kurs haqida", "o'quv markaz", "haqida"],
    ),
    "who": (
        "👶 Kimlar uchun?",
        "ICANUZ 12 yosh va undan katta o'quvchilar uchun.\n\n"
        "Dasturlash va AI'ni boshidan o'rganmoqchi bo'lganlar, o'z loyihasini qilishni xohlaganlar va "
        "kelajakda IT sohasida ishlashni rejalaganlar uchun mos.",
        ["yosh", "yoshdan", "necha yosh", "kimlar", "kim o'qiy", "bolam", "farzand", "o'g'lim", "qizim", "boshlovchi", "noldan"],
    ),
    "duration": (
        "🗓 Kurs qancha davom etadi?",
        "Kurs 8 oy davom etadi va to'liq loyihaga asoslangan: har bosqich real natija bilan yakunlanadi.",
        ["davom", "necha oy", "muddat", "qancha vaqt", "oy davom", "davomiylik"],
    ),
    "method": (
        "🧩 Qanday o'qitiladi?",
        "Biz loyiha asosida o'qitamiz: o'quvchi mavzuni o'rganadi va darhol uni real loyihada qo'llaydi.\n\n"
        "Guruhlar kichik, shuning uchun har bir o'quvchiga e'tibor yetarli bo'ladi. "
        "Yo'nalishlar: web dasturlash, dizayn va AI vositalari bilan ishlash.",
        ["qanday o'qit", "metod", "loyiha", "amaliyot", "dars", "o'qitish", "yo'nalish", "nimalar o'rgat", "dastur"],
    ),
    "admission": (
        "📝 Qabul qanday?",
        "Qabul tanlov asosida: avval qisqa suhbat (intervyu) o'tkaziladi.\n\n"
        "Joylar soni cheklangan, chunki biz kichik guruhlar bilan ishlaymiz. "
        "Suhbatga yozilish uchun «✍️ Ariza qoldirish» tugmasini bosing.",
        ["qabul", "intervyu", "suhbat", "kirish", "ro'yxatdan", "yozilish", "joy bor", "joylar", "qanday qabul"],
    ),
    "price": (
        "💰 Narx qancha?",
        "ICANUZ'da bir nechta tarif mavjud, narx tanlangan tarifga qarab farq qiladi.\n\n"
        "Aniq narx va to'lov shartlarini suhbatda aytamiz. Bog'lanish: {contact}",
        ["narx", "qancha turadi", "necha pul", "to'lov", "tarif", "pul", "qimmat", "arzon", "chegirma", "narxi"],
    ),
    "profile": (
        "🗂 ICANUZ Profile nima?",
        "ICANUZ Profile — har bir o'quvchining shaxsiy portfolio tizimi.\n\n"
        "Unda o'quvchi qilgan loyihalari, ko'nikmalari va yutuqlari jamlanadi. "
        "Kelajakda ish yoki o'qishga topshirganda shu portfolio ko'rsatiladi.",
        ["portfolio", "profile", "profil", "sertifikat", "natija"],
    ),
    "location": (
        "📍 Manzil va jadval",
        "Akademiya Andijon shahrida joylashgan.\n\n"
        "Aniq manzil, dars kunlari va vaqtlari haqida bu yerda bog'laning: {contact}",
        ["manzil", "qayerda", "qayerga", "adres", "joylashgan", "jadval", "soat", "kun", "andijon", "lokatsiya"],
    ),
    "contact": (
        "📞 Bog'lanish",
        "Biz bilan bog'lanish: {contact}\n\n"
        "Yoki «✍️ Ariza qoldirish» tugmasini bosing, o'zimiz sizga aloqaga chiqamiz.",
        ["aloqa", "telefon", "nomer", "raqam", "bog'lan", "admin", "menejer", "qo'ng'iroq"],
    ),
}

# Tugmalar tartibi (2 tadan qatorda)
ORDER = ["about", "who", "duration", "method", "admission", "price", "profile", "location", "contact"]

GREETINGS = {"salom", "assalomu alaykum", "assalom", "hi", "hello", "привет", "здравствуйте", "салом", "menu", "menyu"}
