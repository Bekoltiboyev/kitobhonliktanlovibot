# 📚 Kitobxonlik Tanlovi — Telegram Bot

To'liq funksional Telegram bot: ro'yxatdan o'tish → majburiy obuna → kitob sotib olish →
to'lov chekini admin tasdiqlashi → kitob yuklab berish → test (60 savol, 1 soat) →
avtomatik natija (PDF) → jonli reyting → yakuniy g'oliblar ro'yxati (PDF).

## 1. Talablar

- Python 3.10+
- Telegram bot tokeni ([@BotFather](https://t.me/BotFather) orqali)
- Adminlar/moderatorlar joylashgan yopiq Telegram guruh (to'lov cheklarini ko'rish uchun)
- Majburiy obuna kanali

## 2. O'rnatish

```bash
python3 -m venv venv
source venv/bin/activate          # Windowsda: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Sozlash

`config.py` faylini oching yoki muhit o'zgaruvchilari (`.env`) orqali quyidagilarni to'ldiring:

| O'zgaruvchi | Tavsif |
|---|---|
| `BOT_TOKEN` | @BotFather bergan token |
| `ADMIN_IDS` | Adminlarning telegram ID lari, vergul bilan: `111,222` |
| `ADMIN_GROUP_ID` | To'lov cheklari yuboriladigan yopiq guruh ID si (manfiy son) |
| `REQUIRED_CHANNEL` | Majburiy obuna kanali, masalan `@mychannel` |
| `CONTEST_GROUP_LINK` | Tasdiqlangandan keyin userga beriladigan guruh havolasi |
| `PAYMENT_CARD_NUMBER`, `PAYMENT_CARD_OWNER` | To'lov kartasi ma'lumotlari |
| `BOOK_NAME`, `BOOK_PRICE` | Tanlov kitobi haqida |
| `BOOK_FILE_PATH` | Kitob fayli joylashgan yo'l (masalan `data/book.pdf`) |
| `TEST_DURATION_MINUTES` | Test davomiyligi (standart: 60) |
| `TOTAL_QUESTIONS` | Savollar soni (standart: 60, `data/questions.json` bilan mos bo'lishi kerak) |

**Admin ID va guruh ID sini olish:** [@userinfobot](https://t.me/userinfobot) ga yozing yoki
botni guruhga admin qilib qo'shib, guruhga biror xabar yuboring — loglarda ID ko'rinadi.

**Muhim:** Bot `REQUIRED_CHANNEL` va `ADMIN_GROUP_ID` da albatta **admin** bo'lishi kerak
(aks holda obuna tekshiruvi va chek yuborish ishlamaydi).

## 4. Savollarni tayyorlash

`data/questions.json` faylini o'zingizning 60 ta savolingiz bilan to'ldiring:

```json
[
  {
    "question": "Savol matni?",
    "options": {"A": "Variant 1", "B": "Variant 2", "C": "Variant 3", "D": "Variant 4"},
    "correct": "A"
  }
]
```

Hozircha faylda **60 ta namuna (placeholder) savol** bor — ularni albatta almashtiring.

## 5. Kitob faylini joylashtirish

Kitobni `data/book.pdf` (yoki `BOOK_FILE_PATH` da ko'rsatgan yo'l) ga joylashtiring.
Bot uni `protect_content=True` bilan yuboradi — bu Telegramning o'z darajasida
forward/saqlashni cheklaydi (pastdagi "Xavfsizlik" bo'limiga qarang).

## 6. Ishga tushirish

```bash
python bot.py
```

## 7. Admin buyruqlari

| Buyruq | Vazifasi |
|---|---|
| `/settesttime 2026-08-05 18:00` | Test boshlanish sanasi/vaqtini belgilaydi — shu vaqtda test avtomatik barcha tasdiqlangan ishtirokchilarga boshlanadi va eslatmalar shu vaqtgacha har kuni yuboriladi |
| `/finalresults` | Barcha tugatgan ishtirokchilarning yakuniy reytingi PDF holida (g'oliblar tepada, oltin/kumush/bronza rang bilan ajratilgan) |
| `/setblock <telegram_id> <sabab>` | Foydalanuvchini qo'lda bloklash (masalan yolg'on chek yuborgan bo'lsa) |
| `/unblock <telegram_id>` | Blokdan chiqarish |
| To'lov cheki tagidagi **✅ Tasdiqlash / ❌ Rad etish / 🚫 Bloklash** tugmalari | Har bir chekni alohida ko'rib chiqish |

## 8. Foydalanuvchi buyruqlari

| Buyruq | Vazifasi |
|---|---|
| `/leaderboard` | Test davomida jonli reyting — kim nechta savolni tugatganini, kim to'g'ri javoblar soni bo'yicha oldinda ketayotganini **hoxlagan odam** ko'rishi mumkun |
| `/finish_test` | Testni muddatidan oldin yakunlash (ixtiyoriy) |

## 9. Butun jarayon oqimi

1. `/start` → kanalga obuna tekshiriladi → obuna bo'lmasa rad etiladi
2. Ro'yxatdan o'tish: ism-familiya + telefon raqam → bazaga yoziladi
3. Mukofotlar e'lon qilinadi, "Tanlovda ishtirok etish" tugmasi chiqadi
4. Kitob nomi/narxi + "To'lov qilish" tugmasi
5. Karta raqami ko'rsatiladi, foydalanuvchi chek (rasm/PDF) yuboradi
6. Chek adminlar guruhiga tugmalar bilan yuboriladi
7. Admin tasdiqlasa → foydalanuvchi ishtirokchi bo'ladi, "Kitobni yuklab olish" tugmasi chiqadi
8. Kitob yuklab olingach, test boshlanishigacha qolgan vaqt haqida eslatmalar keladi (har kuni)
9. Belgilangan vaqtda test **avtomatik** barcha ishtirokchilarga boshlanadi (60 savol, 1 soat)
10. Har bir ishtirokchi javob berib boradi; vaqt tugasa yoki savollar tugasa, avtomatik yakunlanadi
11. Har birga shaxsiy natija PDF holida yuboriladi
12. Admin `/finalresults` orqali umumiy reytingni PDF holida oladi (g'oliblar ajratilgan)

## 10. Xavfsizlik bo'yicha tavsiyalar (qo'shimcha qilingan/tavsiya etiladigan)

**Botda allaqachon mavjud himoyalar:**
- ✅ Bitta foydalanuvchi bir vaqtning o'zida faqat bitta pending/approved to'lovga ega bo'la oladi (qayta-qayta soxta chek yuborib spam qilish oldini olish)
- ✅ Faqat rasm yoki PDF formatidagi fayllar chek sifatida qabul qilinadi
- ✅ Har bir chek — bitta admin xabari + Tasdiqlash/Rad etish/Bloklash tugmalari (inson tomonidan tasdiqlash — avtomatik emas, chunki soxta chekni dastur bilan 100% aniqlab bo'lmaydi)
- ✅ Bloklangan foydalanuvchi botning hech qanday funksiyasidan foydalana olmaydi
- ✅ Kitob fayli `protect_content=True` bilan yuboriladi (Telegram darajasida forward/saqlash qiyinlashtiriladi — 100% kafolat emas, lekin oddiy tarqatishni ancha qiyinlashtiradi)
- ✅ Test paytida har bir savol faqat bitta marta javoblanadi, orqaga qaytib javobni o'zgartirib bo'lmaydi

**Qo'shimcha qilishni tavsiya qilaman:**
1. **Chek raqami/summasi bo'yicha dublikat tekshiruvi** — agar bank chekida tranzaksiya ID/summasi ko'rinsa, adminlar buni qo'lda solishtirsin; xohlasangiz keyingi bosqichda buni yarim-avtomatlashtirish (OCR) mumkin.
2. **Rad etilgan/bloklangan foydalanuvchilar logi** — hozir `block_reason` bazada saqlanadi, buni admin panel/statistika sifatida kengaytirish mumkin.
3. **Rate limiting** — bitta IP/qurilmadan juda ko'p soxta akkount ochishning oldini olish uchun `aiogram` uchun throttling middleware qo'shish tavsiya etiladi (hozirgi bazaviy versiyada yo'q).
4. **Backup** — `bot_database.db` faylini har kuni avtomatik zaxira qiling (test kuni ayniqsa muhim!).
5. **Load testing** — agar 1000+ kishi bir vaqtda test topshirsa, SQLite emas, PostgreSQL ga o'tish tavsiya etiladi (kod tuzilishi shunga tayyor, faqat `database.py` dagi connection qatlamini almashtirish kifoya).
6. **HTTPS/webhook** — production uchun polling o'rniga webhook + HTTPS server ishlatish tavsiya etiladi (yuqori yuklama va tezlik uchun).
7. **Test savollarini tasodifiy tartibda berish** — hozirgi versiyada barcha userlarga bir xil tartibda savollar boradi; xohlasangiz har user uchun savollar random tartibda aralashtirilishi mumkin (nusxa ko'chirish/ko'chirib berishni qiyinlashtiradi).

## 11. Loyihaning fayl tuzilishi

```
kitobxonlik_bot/
├── bot.py                  # Ishga tushirish nuqtasi
├── config.py                # Barcha sozlamalar
├── database.py               # SQLite bilan ishlash (async)
├── keyboards.py              # Inline/reply klaviaturalar
├── states.py                 # FSM holatlar
├── requirements.txt
├── data/
│   ├── questions.json         # 60 ta test savoli (o'zingiznikiga almashtiring)
│   ├── book.pdf                # Tanlov kitobi (o'zingiz qo'shing)
│   └── fonts/                   # PDF hisobotlar uchun shriftlar
├── handlers/
│   ├── registration.py         # /start, obuna tekshiruvi, ro'yxatdan o'tish
│   ├── contest.py                # Tanlovga qo'shilish, kitob haqida ma'lumot
│   ├── payment.py                 # To'lov cheki qabul qilish, kitob yuklab berish
│   ├── admin.py                    # Chekni tasdiqlash/rad etish/bloklash, /finalresults, /settesttime
│   ├── test.py                      # Test savollari, javoblar, natija PDF
│   └── leaderboard.py                # /leaderboard — jonli reyting
└── utils/
    ├── subscription.py                # Kanalga obuna tekshirish
    ├── questions.py                    # Savollarni JSON dan yuklash
    ├── pdf_generator.py                 # PDF hisobotlar
    └── scheduler.py                      # Eslatmalar, test avto-boshlanishi/tugashi
```

## 12. Muhim eslatmalar

- Kod **sintaksis va asosiy DB/PDF funksiyalari** jihatidan sinovdan o'tkazilgan (bu muhitda
  haqiqiy Telegram tokeni bilan to'liq oqim sinalmagan — buning uchun o'z bot tokeningiz kerak).
- `/settesttime` faqat bot **ishlab turgan vaqtda** berilgan buyruqni eslab qoladi (bot qayta
  ishga tushsa, saqlangan vaqt bazadan o'qib qayta rejalashtiriladi — kod shunga moslashtirilgan).
- Production muhitda botni doim ishlab turishi uchun `systemd`, `pm2`, yoki Docker + `restart:
  always` ishlatishni tavsiya qilaman.
