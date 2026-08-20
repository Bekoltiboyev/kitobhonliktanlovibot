import os
import time
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from config import FONT_PATH_REGULAR, FONT_PATH_BOLD
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


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(name="TitleUZ", fontName=FONT_NAME_BOLD, fontSize=16,
                           alignment=1, spaceAfter=10))
    ss.add(ParagraphStyle(name="NormalUZ", fontName=FONT_NAME, fontSize=10))
    ss.add(ParagraphStyle(name="SmallUZ", fontName=FONT_NAME, fontSize=8, textColor=colors.grey))
    return ss


def generate_user_result_pdf(path: str, user: dict, result: dict, questions: list, user_id: int):
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

    rows = [["#", "Sizning javobingiz", "To'g'ri javob", "Natija"]]
    answers = result.get("answers", {})
    for i, q in enumerate(questions):
        given = answers.get(str(i), "-")
        _, correct = get_user_shuffled_options(user_id, i, q)
        if given == "-":
            ok = "-"
        elif given == correct:
            ok = "+" if FONT_NAME == "Helvetica" else "✔"
        else:
            ok = "X" if FONT_NAME == "Helvetica" else "✘"
        rows.append([str(i + 1), given, correct, ok])

    table = Table(rows, colWidths=[15 * mm, 45 * mm, 45 * mm, 25 * mm], repeatRows=1)
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
        f"Hisobot yaratilgan sana: {time.strftime('%Y-%m-%d %H:%M', time.localtime())}",
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

    rows = [["O'rin", "F.I.Sh", "Telegram ID", "To'g'ri", "Xato", "Bo'sh", "Ball", "Vaqt (daq)"]]
    for idx, r in enumerate(results, start=1):
        duration = (r["finished_at"] - r["started_at"]) if r["finished_at"] and r["started_at"] else 0
        rows.append([
            str(idx),
            r["fullname"],
            str(r["telegram_id"]),
            str(r["correct_count"]),
            str(r["wrong_count"]),
            str(r["unanswered_count"]),
            str(r["score"]),
            f"{int(duration // 60)}",
        ])

    table = Table(rows, colWidths=[14 * mm, 45 * mm, 28 * mm, 15 * mm, 15 * mm, 15 * mm, 15 * mm, 20 * mm],
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
    medal_colors = {1: colors.HexColor("#ffd700"), 2: colors.HexColor("#c0c0c0"), 3: colors.HexColor("#cd7f32")}
    for place, color in medal_colors.items():
        if place < len(rows):
            style.append(("BACKGROUND", (0, place), (-1, place), color))
            style.append(("FONTNAME", (0, place), (-1, place), FONT_NAME_BOLD))

    table.setStyle(TableStyle(style))
    elements.append(table)
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        f"Hisobot yaratilgan sana: {time.strftime('%Y-%m-%d %H:%M', time.localtime())}",
        ss["SmallUZ"]))

    doc.build(elements)
    return path