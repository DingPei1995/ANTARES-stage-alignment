"""Markdown memo (Chinese) -> PDF with reportlab: headings, paragraphs, bullet / numbered lists, tables, **bold**,
`code`. Usage: python memo_to_pdf.py <memo.md> [out.pdf]"""
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

pdfmetrics.registerFont(TTFont("YaHei", r"C:\Windows\Fonts\msyh.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("YaHeiB", r"C:\Windows\Fonts\msyhbd.ttc", subfontIndex=0))
pdfmetrics.registerFontFamily("YaHei", normal="YaHei", bold="YaHeiB", italic="YaHei", boldItalic="YaHeiB")

BLUE = colors.HexColor("#1a3a5c")
S = {
    "h1": ParagraphStyle("h1", fontName="YaHeiB", fontSize=15, leading=20, textColor=BLUE, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="YaHeiB", fontSize=12, leading=16, textColor=BLUE, spaceBefore=9,
                         spaceAfter=4, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName="YaHeiB", fontSize=10, leading=14, textColor=BLUE, spaceBefore=6,
                         spaceAfter=3, keepWithNext=1),
    "p": ParagraphStyle("p", fontName="YaHei", fontSize=9, leading=13.5, spaceAfter=3, wordWrap="CJK"),
    "li": ParagraphStyle("li", fontName="YaHei", fontSize=9, leading=13.5, leftIndent=12, bulletIndent=2,
                         spaceAfter=1.5, wordWrap="CJK"),
    "td": ParagraphStyle("td", fontName="YaHei", fontSize=7.8, leading=10, wordWrap="CJK"),
    "th": ParagraphStyle("th", fontName="YaHeiB", fontSize=7.8, leading=10, wordWrap="CJK"),
}


def inline(text: str) -> str:
    t = escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"`([^`]+)`", r"<font name='Courier' size='8'>\1</font>", t)
    return t


def table(lines):
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    rows = [r for i, r in enumerate(rows) if i != 1]  # drop the |---| line
    data = [[Paragraph(inline(c), S["th"] if i == 0 else S["td"]) for c in r] for i, r in enumerate(rows)]
    n = len(rows[0])
    width = 174 * mm
    first = min(0.34, 1.6 / n) * width if n > 2 else width / n
    widths = [first] + [(width - first) / (n - 1)] * (n - 1) if n > 1 else [width]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce6f0")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa9b8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return [t, Spacer(1, 4)]


def build(md: Path, pdf: Path, figures: dict | None = None):
    lines = md.read_text(encoding="utf-8").splitlines()
    story, para, i = [], [], 0

    def flush():
        if para:
            story.append(Paragraph(inline(" ".join(para)), S["p"]))
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            flush()
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(lines[i])
                i += 1
            story += table(block)
            continue
        m = re.match(r"^(#{1,3}) (.*)", ln)
        if m:
            flush()
            story.append(Paragraph(inline(m.group(2)), S["h" + str(len(m.group(1)))]))
            for key, (path, w) in (figures or {}).items():
                if m.group(2).startswith(key):
                    story.append(Image(str(path), width=w * mm, height=w * mm * _ratio(path)))
        elif re.match(r"^\s*- ", ln):
            flush()
            ind = len(ln) - len(ln.lstrip())
            st = ParagraphStyle("li2", parent=S["li"], leftIndent=12 + ind * 4, bulletIndent=2 + ind * 4)
            story.append(Paragraph(inline(ln.strip()[2:]), st, bulletText="•"))
        elif re.match(r"^\s*\d+\. ", ln):
            flush()
            num, txt = ln.strip().split(". ", 1)
            story.append(Paragraph(inline(txt), S["li"], bulletText=num + "."))
        elif not ln.strip():
            flush()
        else:
            para.append(ln.strip())
        i += 1
    flush()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("YaHei", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(18 * mm, 10 * mm, md.stem)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm,
                            bottomMargin=16 * mm, title=md.stem, author="ANTARES stage alignment")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def _ratio(path):
    from PIL import Image as PI
    with PI.open(path) as im:
        return im.height / im.width


if __name__ == "__main__":
    md = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else md.with_suffix(".pdf")
    figs = Path(__file__).parent / "cav_2026-11-20"
    build(md, out, {"3.3": (figs / "cav_summary.png", 165)} if "cav_zp" in md.stem else None)
    print(out)
