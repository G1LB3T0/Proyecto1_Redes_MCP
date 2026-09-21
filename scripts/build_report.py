"""Render the project report and packet-analysis appendix using ReportLab.

Run with a Python environment containing reportlab. Source text stays editable
in docs/report.md and docs/network-analysis.md. Font files are standard Windows
Arial and Consolas; adjust FONT_DIR when building on another platform.
"""

from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether


ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = Path("C:/Windows/Fonts")
NAVY = colors.HexColor("#153047")
TEAL = colors.HexColor("#087F8C")
PALE = colors.HexColor("#EDF5F6")
GRAY = colors.HexColor("#546575")
WIDTH = A4[0] - 96


def inline(text: str) -> str:
    text = escape(text)
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r'<link href="\2" color="#087F8C">\1</link>', text)
    text = re.sub(r"`([^`]+)`", r'<font name="Mono" size="8.1">\1</font>', text)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)


def render_markdown(path: Path, styles: dict) -> list:
    lines = path.read_text(encoding="utf-8").splitlines()
    result = []
    position = 0
    while position < len(lines):
        line = lines[position].strip()
        if not line:
            position += 1
            continue
        if line.startswith("```"):
            code = []
            position += 1
            while position < len(lines) and not lines[position].startswith("```"):
                code.append(escape(lines[position]).replace(" ", "&#160;"))
                position += 1
            result.append(Paragraph("<br/>".join(code), styles["CodeBlock"]))
            position += 1
            continue
        if line.startswith("|"):
            rows = []
            while position < len(lines) and lines[position].lstrip().startswith("|"):
                raw = lines[position].strip().strip("|").split("|")
                if not all(re.fullmatch(r"\s*:?-+:?\s*", cell) for cell in raw):
                    rows.append([Paragraph(inline(cell.strip()), styles["Cell"]) for cell in raw])
                position += 1
            count = len(rows[0])
            widths = {2: [WIDTH * .32, WIDTH * .68],
                      3: [WIDTH * .28, WIDTH * .34, WIDTH * .38],
                      4: [WIDTH * .14, WIDTH * .13, WIDTH * .43, WIDTH * .30]}[count]
            table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("LINEBELOW", (0, 0), (-1, 0), 1, TEAL),
                ("LINEBELOW", (0, 1), (-1, -1), .3, colors.HexColor("#D6E1E6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            result.extend([KeepTogether([table]), Spacer(1, 9)])
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if line.lstrip("# ") in {
                "4. Especificación del servidor desarrollado", "6. Verificación funcional",
                "8. Dificultades, límites y lecciones", "Clasificación de todos los intercambios",
                "Capa de enlace", "Reproducción y revisión en Wireshark",
            }:
                result.append(PageBreak())
            result.append(Paragraph(inline(line.lstrip("# ")), styles["Title2" if level == 1 else "Heading2"]))
            position += 1
            continue
        paragraph = [line]
        position += 1
        while position < len(lines) and lines[position].strip() and not lines[position].startswith(("#", "|", "```")):
            paragraph.append(lines[position].strip())
            position += 1
        result.append(Paragraph(inline(" ".join(paragraph)), styles["BodyText"]))
    return result


def footer(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D6E1E6"))
    canvas.line(48, 42, A4[0] - 48, 42)
    canvas.setFont("Body", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(48, 29, "CC3067 Redes  |  Inventario de farmacia con MCP")
    canvas.drawRightString(A4[0] - 48, 29, str(document.page))
    canvas.restoreState()


def main():
    for name, file in [("Body", "arial.ttf"), ("BodyBold", "arialbd.ttf"), ("Mono", "consola.ttf")]:
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="BodyBold", italic="Body", boldItalic="BodyBold")
    styles = getSampleStyleSheet()
    styles["BodyText"].fontName = "Body"
    styles["BodyText"].fontSize = 9.6
    styles["BodyText"].leading = 13.2
    styles["BodyText"].spaceAfter = 7
    styles["BodyText"].allowWidows = 0
    styles["BodyText"].allowOrphans = 0
    styles["BodyText"].textColor = NAVY
    styles["Heading2"].fontName = "BodyBold"
    styles["Heading2"].fontSize = 13
    styles["Heading2"].leading = 17
    styles["Heading2"].spaceBefore = 13
    styles["Heading2"].spaceAfter = 8
    styles["Heading2"].textColor = TEAL
    styles.add(ParagraphStyle("Title2", parent=styles["Heading2"], fontSize=20, leading=25, textColor=NAVY))
    styles.add(ParagraphStyle("Cell", parent=styles["BodyText"], fontSize=8.3, leading=11.4, spaceAfter=0))
    styles.add(ParagraphStyle("CodeBlock", fontName="Mono", fontSize=7.7, leading=10.6,
                              backColor=PALE, borderPadding=8, spaceBefore=6, spaceAfter=12,
                              textColor=NAVY, splitLongWords=True))
    styles.add(ParagraphStyle("CoverTitle", fontName="BodyBold", fontSize=32, leading=38, textColor=NAVY, spaceAfter=20))
    styles.add(ParagraphStyle("CoverSubtitle", parent=styles["BodyText"], fontSize=15, leading=22, spaceAfter=18))
    output = ROOT / "output/pdf/Informe_Proyecto1_MCP.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=48, leftMargin=48,
                                  topMargin=44, bottomMargin=58, title="Proyecto 1 - Inventario de farmacia con MCP",
                                  author="", subject="CC3067 Redes: implementación y evidencia de comunicación remota")
    story = [Spacer(1, 65), Paragraph("CC3067 · REDES", styles["Heading2"]),
             Paragraph("Inventario de farmacia<br/>con MCP", styles["CoverTitle"]),
             Paragraph("Proyecto 1: uso de un protocolo existente", styles["CoverSubtitle"]),
             Paragraph("Universidad del Valle de Guatemala<br/>21 de septiembre de 2026", styles["CoverSubtitle"]),
             Spacer(1, 30), Paragraph("Implementación manual · Servidores locales y remotos · Evidencia de red", styles["BodyText"]),
             Spacer(1, 12), Paragraph("27 pruebas aprobadas<br/>6 turnos con Gemini real<br/>181 paquetes capturados<br/>13 mensajes JSON-RPC clasificados", styles["CoverSubtitle"]),
             Spacer(1, 28), Paragraph("Incluye especificación, arquitectura, verificación funcional, análisis por capas, conclusiones y procedimiento de reproducción.", styles["BodyText"]),
             PageBreak()]
    story.extend(render_markdown(ROOT / "docs/report.md", styles))
    story.append(PageBreak())
    story.extend(render_markdown(ROOT / "docs/network-analysis.md", styles))
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(output)


if __name__ == "__main__":
    main()
