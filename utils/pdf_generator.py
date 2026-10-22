import os
import time
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import datetime as _dt
from config import FONT_PATH_REGULAR, FONT_PATH_BOLD, TZ_TASHKENT
from utils.questions import get_user_shuffled_options

FONT_NAME = "Helvetica"
FONT_NAME_BOLD = "Helvetica-Bold"

if os.path.exists(FONT_PATH_REGULAR) and os.path.exists(FONT_PATH_BOLD):
    try:
        pdfmetrics.registerFont(TTFont("Custom", FONT_PATH_REGULAR))
        pdfmetrics.registerFont(TTFont("Custom-Bold", FONT_PATH_BOLD))
        FONT_NAME = "Custom"
        FONT_NAME_BOLD = "Custom-Bold"
    except Exception:
        pass



# To'g'ri javoblar PDF da ko'rsatilsinmi? (False — yashirin)
SHOW_CORRECT_ANSWERS = False

def _now_tashkent() -> str:
    """Hisobot sanasi — server (UTC) emas, Toshkent vaqtida."""
    return _dt.datetime.now(TZ_TASHKENT).strftime("%Y-%m-%d %H:%M")


def _fmt_score(v) -> str:
    """15.0 -> '15', 14.5 -> '14.5'"""
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f"{f:g}"
    except Exception:
        return str(v)


def _fmt_duration(sec) -> str:
    """Soniyani 'daq:son' ko'rinishida (masalan 12:05) — bir xil daqiqadagilarni ajratish uchun."""
    sec = max(0, int(sec or 0))
    return f"{sec // 60}:{sec % 60:02d}"


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(name="TitleUZ", fontName=FONT_NAME_BOLD, fontSize=16,
                           leading=20, alignment=1, spaceAfter=10))
    ss.add(ParagraphStyle(name="NormalUZ", fontName=FONT_NAME, fontSize=10))
    ss.add(ParagraphStyle(name="SmallUZ", fontName=FONT_NAME, fontSize=8, textColor=colors.grey))
    # Jadval katakchalari uchun — uzun matn (masalan uzun ism-familiya)
    # ustunga sig'masa, AVTOMATIK ikkinchi qatorga o'tadi, keyingi ustun
    # ustiga "chiqib ketmaydi". Oddiy matn (string) sifatida jadvalga
    # qo'yilgan uzun so'zlar reportlab'da o'z-o'zidan qatorga o'tmaydi —
    # shuning uchun Paragraph orqali beriladi.
    ss.add(ParagraphStyle(name="TableCellUZ", fontName=FONT_NAME, fontSize=8, leading=10))
    # Bloklangan foydalanuvchi qatorlari uchun - jadval darajasidagi
    # TEXTCOLOR buyrug'i Paragraph ichidagi matnga ta'sir qilmaydi
    # (reportlab'ning o'ziga xosligi), shuning uchun alohida qizil stil kerak.
    ss.add(ParagraphStyle(name="TableCellRedUZ", fontName=FONT_NAME, fontSize=8, leading=10,
                           textColor=colors.HexColor("#b91c1c")))
    # G'olib (1,2,3-o'rin) qatorlari uchun qalin shrift - jadval darajasidagi
    # FONTNAME buyrug'i ham Paragraph ichidagi matnga ta'sir qilmaydi.
    ss.add(ParagraphStyle(name="TableCellBoldUZ", fontName=FONT_NAME_BOLD, fontSize=8, leading=10))
    return ss


def _cell(text, style_sheet, red=False, bold=False):
    """Jadval katakchasi uchun matnni Paragraph obyektiga o'raydi (qatorga o'tishi uchun)."""
    safe_text = str(text).strip() if text and str(text).strip() else "(ism kiritilmagan)"
    safe_text = safe_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    style_name = "TableCellRedUZ" if red else ("TableCellBoldUZ" if bold else "TableCellUZ")
    return Paragraph(safe_text, style_sheet[style_name])


def generate_user_result_pdf(path: str, user: dict, result: dict, questions: list, user_id: int, order: list = None):
    ss = _styles()
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    elements = []

    elements.append(Paragraph("KITOBXONLIK TANLOVI — TEST NATIJASI", ss["TitleUZ"]))
    elements.append(Spacer(1, 6))

    duration = result["finished_at"] - result["started_at"]
    minutes, seconds = divmod(int(duration), 60)

    info_data = [
        ["F.I.Sh:", user["fullname"]],
        ["Username:", f"@{user['username']}" if user["username"] else "-"],
        ["Telegram ID:", str(user["telegram_id"])],
        ["Sarflangan vaqt:", f"{minutes} daq {seconds} son"],
        ["To'g'ri javoblar:", str(result["correct_count"])],
        ["Xato javoblar:", str(result["wrong_count"])],
        ["Javob berilmagan:", str(result["unanswered_count"])],
        ["Umumiy ball:", str(result["score"])],
    ]
    info_table = Table(info_data, colWidths=[55 * mm, 100 * mm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTNAME", (0, 0), (0, -1), FONT_NAME_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 14))
    elements.append(Paragraph("Savollar bo'yicha batafsil natija:", ss["NormalUZ"]))
    elements.append(Spacer(1, 6))

    # SHOW_CORRECT_ANSWERS=False bo'lsa, to'g'ri javob harfi ko'rsatilmaydi —
    # faqat foydalanuvchining javobi va natija (✔/✘) chiqadi. Shunda PDF
    # tarqalsa ham savollarning to'g'ri javoblari oshkor bo'lmaydi.
    if SHOW_CORRECT_ANSWERS:
        rows = [["#", "Sizning javobingiz", "To'g'ri javob", "Natija"]]
    else:
        rows = [["#", "Sizning javobingiz", "Natija"]]
    answers = result.get("answers", {})
    # Faqat shu foydalanuvchiga berilgan savollar (order) ko'rsatiladi, 1..N raqamlanadi.
    indices = list(order) if order is not None else list(range(len(questions)))
    for step, i in enumerate(indices):
        given = answers.get(str(i), "-")
        if i >= len(questions):
            correct = "-"
            given = "-"
        else:
            _, correct = get_user_shuffled_options(user_id, i, questions[i])
        if given == "-":
            ok = "-"
        elif given == correct:
            ok = "+" if FONT_NAME == "Helvetica" else "✔"
        else:
            ok = "X" if FONT_NAME == "Helvetica" else "✘"
        if SHOW_CORRECT_ANSWERS:
            rows.append([str(step + 1), given, correct, ok])
        else:
            rows.append([str(step + 1), given, ok])

    col_widths = [15 * mm, 45 * mm, 45 * mm, 25 * mm] if SHOW_CORRECT_ANSWERS else [15 * mm, 60 * mm, 40 * mm]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTNAME", (0, 0), (-1, 0), FONT_NAME_BOLD),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f4f6f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        f"Hisobot yaratilgan sana: {_now_tashkent()}",
        ss["SmallUZ"]))

    doc.build(elements)
    return path


def generate_admin_results_pdf(path: str, results: list):
    ss = _styles()
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    elements = [Paragraph("KITOBXONLIK TANLOVI — YAKUNIY NATIJALAR", ss["TitleUZ"]),
                Spacer(1, 4),
                Paragraph(f"Jami ishtirokchilar: {len(results)}", ss["NormalUZ"]),
                Spacer(1, 10)]

    rows = [["O'rin", "F.I.Sh", "Telegram ID", "To'g'ri", "Xato", "Bo'sh", "Ball", "Vaqt (daq:son)"]]
    for idx, r in enumerate(results, start=1):
        duration = (r["finished_at"] - r["started_at"]) if r["finished_at"] and r["started_at"] else 0
        is_top3 = idx <= 5
        rows.append([
            str(idx),
            _cell(r["fullname"], ss, bold=is_top3),
            str(r["telegram_id"]),
            str(r["correct_count"]),
            str(r["wrong_count"]),
            str(r["unanswered_count"]),
            _fmt_score(r["score"]),
            _fmt_duration(duration),
        ])

    table = Table(rows, colWidths=[14 * mm, 42 * mm, 28 * mm, 14 * mm, 13 * mm, 13 * mm, 14 * mm, 28 * mm],
                   repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTNAME", (0, 0), (-1, 0), FONT_NAME_BOLD),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f4f6f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]
    medal_colors = {
        1: colors.HexColor("#ffd700"),  # oltin
        2: colors.HexColor("#c0c0c0"),  # kumush
        3: colors.HexColor("#cd7f32"),  # bronza
        4: colors.HexColor("#b7e4c7"),  # ochiq yashil
        5: colors.HexColor("#bde0fe"),  # ochiq ko'k
    }
    for place, color in medal_colors.items():
        if place < len(rows):
            style.append(("BACKGROUND", (0, place), (-1, place), color))
            style.append(("FONTNAME", (0, place), (-1, place), FONT_NAME_BOLD))

    table.setStyle(TableStyle(style))
    elements.append(table)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        f"Hisobot yaratilgan sana: {_now_tashkent()}",
        ss["SmallUZ"]))

    doc.build(elements)
    return path

def generate_participants_pdf(path: str, participants: list):
    """
    To'lov qilib, tasdiqlangan (ishtirokchi) barcha foydalanuvchilar
    ro'yxati — admin panel uchun. Test natijalari bilan bog'liq emas,
    faqat "kim to'lov qildi va qachon" degan hisobot.

    participants: [{telegram_id, fullname, username, phone, is_blocked,
                     approved_at}, ...]
    """
    ss = _styles()
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)

    active_count = sum(1 for p in participants if not p["is_blocked"])
    blocked_count = len(participants) - active_count

    elements = [
        Paragraph("KITOBXONLIK TANLOVI — TO'LOV QILGANLAR HISOBOTI", ss["TitleUZ"]),
        Spacer(1, 4),
        Paragraph(
            f"Jami to'lov qilganlar: {len(participants)} "
            f"(faol: {active_count}, bloklangan: {blocked_count})",
            ss["NormalUZ"]),
        Spacer(1, 10),
    ]

    rows = [["#", "F.I.Sh", "Telegram ID", "Username", "Telefon", "To'lov sanasi", "Holat"]]
    for idx, p in enumerate(participants, start=1):
        approved_at = p.get("approved_at")
        if approved_at is not None and getattr(approved_at, "tzinfo", None):
            approved_at = approved_at.astimezone(TZ_TASHKENT)
        date_str = approved_at.strftime("%Y-%m-%d %H:%M") if approved_at else "-"
        phone_raw = str(p.get("phone") or "").strip()
        phone_display = phone_raw if phone_raw.startswith("+") else f"+{phone_raw}" if phone_raw else "-"
        status = "Bloklangan" if p["is_blocked"] else "Faol"
        rows.append([
            str(idx),
            _cell(p["fullname"], ss, red=p["is_blocked"]),
            str(p["telegram_id"]),
            _cell(f"@{p['username']}" if p.get("username") else "-", ss, red=p["is_blocked"]),
            phone_display,
            date_str,
            status,
        ])

    table = Table(
        rows,
        colWidths=[10 * mm, 40 * mm, 24 * mm, 26 * mm, 28 * mm, 30 * mm, 20 * mm],
        repeatRows=1,
    )
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTNAME", (0, 0), (-1, 0), FONT_NAME_BOLD),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f4f6f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]
    for idx, p in enumerate(participants, start=1):
        if p["is_blocked"]:
            style.append(("TEXTCOLOR", (0, idx), (-1, idx), colors.HexColor("#b91c1c")))

    table.setStyle(TableStyle(style))
    elements.append(table)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        f"Hisobot yaratilgan sana: {_now_tashkent()}",
        ss["SmallUZ"]))

    doc.build(elements)
    return path