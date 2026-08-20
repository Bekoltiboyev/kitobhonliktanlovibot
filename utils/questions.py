import json
import os
import random
import openpyxl
from config import QUESTIONS_FILE


def get_user_shuffled_options(user_id: int, real_q_index: int, q: dict):
    """Har bir (user_id, savol) jufti uchun variantlar joylashuvini (A,B,C,D)
    deterministik tasodifiy tartibda aralashtirib beradi.

    'Deterministik' — ya'ni bir xil user_id va real_q_index uchun har doim
    bir xil natija qaytaradi (seed sifatida shu ikkalasi ishlatiladi).
    Bu funksiya bir nechta joyda (savolni ko'rsatishda, javobni
    tekshirishda va PDF hisobot yaratishda) ishlatiladi — hammasida bir xil
    natija chiqishi shart, aks holda foydalanuvchi ko'rgan variant bilan
    bot/hisobot ko'rsatayotgan variant mos kelmay qoladi.

    Natija: (aralashtirilgan_options_dict, shu_user_uchun_togri_javob_harfi)
    """
    rng = random.Random(f"{user_id}:{real_q_index}")
    letters = ["A", "B", "C", "D"]
    pairs = [(q["options"][letter], letter == q["correct"]) for letter in letters]
    rng.shuffle(pairs)

    shuffled_options = {}
    shuffled_correct = None
    for letter, (value, is_correct) in zip(letters, pairs):
        shuffled_options[letter] = value
        if is_correct:
            shuffled_correct = letter

    return shuffled_options, shuffled_correct


def load_questions() -> list[dict]:
    """Test savollarini JSON fayldan o'qib olish."""
    if not os.path.exists(QUESTIONS_FILE):
        return []
    try:
        with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def parse_excel_questions(file_path: str) -> tuple[bool, str, int]:
    """Admin yuborgan Excel (.xlsx) faylni JSON ga o'girish."""
    try:
        wb = openpyxl.load_workbook(file_path)
        sheet = wb.active

        parsed_questions = []

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not row[0]:
                continue

            question_text = str(row[0]).strip()
            opt_a = str(row[1]).strip() if row[1] is not None else ""
            opt_b = str(row[2]).strip() if row[2] is not None else ""
            opt_c = str(row[3]).strip() if row[3] is not None else ""
            opt_d = str(row[4]).strip() if row[4] is not None else ""
            correct_ans = str(row[5]).strip().upper() if row[5] is not None else ""

            if not all([question_text, opt_a, opt_b, opt_c, opt_d, correct_ans]):
                return False, f"Xatolik {row_idx}-qatorda: Barcha ustunlar to'ldirilishi shart!", 0

            if correct_ans not in ["A", "B", "C", "D"]:
                return False, f"Xatolik {row_idx}-qatorda: To'g'ri javob faqat A, B, C yoki D bo'lishi kerak!", 0

            # Excel faylida to'g'ri javob har doim bitta variantda (masalan doim A da)
            # kelishi mumkin — bu holda ishtirokchilar hech narsa bilmasdan ham
            # doim shu harfni bosib yuqori ball to'plashi mumkin bo'lib qoladi.
            # Shuning uchun variantlarning joylashuvini (A/B/C/D) har bir savol
            # uchun tasodifiy aralashtirib, to'g'ri javob harfini ham shunga mos
            # yangilab saqlaymiz.
            letters = ["A", "B", "C", "D"]
            options_with_flag = [
                (opt_a, correct_ans == "A"),
                (opt_b, correct_ans == "B"),
                (opt_c, correct_ans == "C"),
                (opt_d, correct_ans == "D"),
            ]
            random.shuffle(options_with_flag)

            shuffled_options = {}
            shuffled_correct = None
            for letter, (value, is_correct) in zip(letters, options_with_flag):
                shuffled_options[letter] = value
                if is_correct:
                    shuffled_correct = letter

            parsed_questions.append({
                "question": question_text,
                "options": shuffled_options,
                "correct": shuffled_correct
            })

        if not parsed_questions:
            return False, "Faylda hech qanday savol topilmadi.", 0

        os.makedirs(os.path.dirname(QUESTIONS_FILE), exist_ok=True)
        with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(parsed_questions, f, ensure_ascii=False, indent=2)

        return True, "Muvaffaqiyatli saqlandi", len(parsed_questions)

    except Exception as e:
        return False, f"Faylni o'qishda xatolik: {str(e)}", 0