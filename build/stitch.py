import os, re, glob
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                 PageBreak, KeepTogether, ListFlowable, ListItem, HRFlowable, Image)
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import pymupdf

BUILD = r"c:\Users\bagma\OneDrive\Pictures\tools\build"
OUT = r"c:\Users\bagma\OneDrive\Pictures\tools\Markdown_Summary_Tool_Technical_Specification_v1.0.pdf"

# Collect parts in order
parts = sorted(glob.glob(os.path.join(BUILD, "part*.md")), key=lambda p: int(re.search(r"part(\d+)", p).group(1)))
print(f"Found {len(parts)} parts: {parts}")

# Concatenate markdown
full_md = ""
for p in parts:
    with open(p, encoding="utf-8") as f:
        full_md += f.read() + "\n\n"

# Save combined markdown for reference
with open(os.path.join(BUILD, "combined.md"), "w", encoding="utf-8") as f:
    f.write(full_md)
print(f"Combined markdown: {len(full_md)} chars, {len(full_md.splitlines())} lines")

# Now build PDF via reportlab
from reportlab.lib.pagesizes import A4
W, H = A4

NAVY = HexColor("#1a2744")
ACCENT = HexColor("#2e86ab")
LIGHT_BG = HexColor("#f0f4f8")
MID_BG = HexColor("#e8eef4")
BORDER = HexColor("#c5d1de")
CODE_BG = HexColor("#f6f8fa")
WARN_BG = HexColor("#fff8e1")
GREEN_BG = HexColor("#e8f5e9")

styles = getSampleStyleSheet()

sTitle = ParagraphStyle("Title2", parent=styles["Title"], fontSize=26, leading=30, textColor=NAVY, alignment=TA_CENTER, spaceAfter=12)
sSubtitle = ParagraphStyle("Subtitle2", parent=styles["Normal"], fontSize=10, leading=13, textColor=HexColor("#4a6582"), alignment=TA_CENTER, spaceAfter=10)
sH1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, leading=17, textColor=NAVY, spaceBefore=24, spaceAfter=12, keepWithNext=True, borderPadding=(0,0,4,0))
sH2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=10.5, leading=13, textColor=HexColor("#24344e"), spaceBefore=20, spaceAfter=10, keepWithNext=True)
sH3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=9, leading=11, textColor=HexColor("#2e4a66"), spaceBefore=16, spaceAfter=8, keepWithNext=True)
sBody = ParagraphStyle("Body2", parent=styles["Normal"], fontSize=8, leading=14.5, textColor=HexColor("#1e2a3a"), alignment=TA_JUSTIFY, spaceAfter=11)
sBullet = ParagraphStyle("Bullet2", parent=sBody, leftIndent=14, bulletIndent=4, spaceAfter=8, alignment=TA_LEFT)
sCode = ParagraphStyle("Code2", parent=styles["Code"], fontSize=7, leading=9, textColor=HexColor("#1a1a2e"), fontName="Courier", spaceAfter=4, leftIndent=4, rightIndent=4)
sCaption = ParagraphStyle("Caption2", parent=styles["Normal"], fontSize=7, leading=9, textColor=HexColor("#5a6d80"), alignment=TA_CENTER, spaceAfter=6, fontName="Helvetica-Oblique")
sTableCell = ParagraphStyle("TableCell", parent=styles["Normal"], fontSize=7, leading=9, textColor=HexColor("#1e2a3a"), alignment=TA_LEFT)
sTableHeader = ParagraphStyle("TableHeader", parent=sTableCell, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER)
sFooter = ParagraphStyle("Footer2", parent=styles["Normal"], fontSize=6, leading=7, textColor=HexColor("#8a9bb0"), alignment=TA_CENTER)

def header_footer(canvas, doc):
    canvas.saveState()
    # Header line
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(15*mm, H - 12*mm, W - 15*mm, H - 12*mm)
    canvas.setFont("Helvetica", 6)
    canvas.setFillColor(HexColor("#8a9bb0"))
    canvas.drawString(15*mm, H - 10*mm, "Markdown Summary Tool  --  Technical Specification  v1.0  --  Draft for Review")
    canvas.drawRightString(W - 15*mm, H - 10*mm, f"Page {doc.page}")
    # Footer line
    canvas.line(15*mm, 12*mm, W - 15*mm, 12*mm)
    canvas.drawCentredString(W/2, 9*mm, "Confidential  --  Do not distribute outside the project team  --  Generated 2026-10-14")
    canvas.restoreState()

def no_header_footer(canvas, doc):
    pass

story = []
# Helper to add styled table
def add_table(headers, rows, col_widths=None, caption=None):
    if caption:
        story.append(Paragraph(caption, sCaption))
    data = [[Paragraph(f"<b>{h}</b>", sTableHeader) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), sTableCell) for c in row])
    avail = W - 30*mm
    if col_widths:
        cw = [avail * w for w in col_widths]
    else:
        cw = [avail / len(headers)] * len(headers)
    t = Table(data, colWidths=cw, repeatRows=1)
    style = [
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("ALIGN", (0,0), (-1,0), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), 0.4, BORDER),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, HexColor("#f7f9fb")]),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
    ]
    t.setStyle(TableStyle(style))
    story.append(t)
    story.append(Spacer(1, 4*mm))

def code_block(text):
    # Render as table with code bg
    p = Paragraph(f'<font face="Courier" size="7">{text.replace(chr(10), chr(10))}</font>', sCode)
    t = Table([[p]], colWidths=[W - 30*mm - 8])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), CODE_BG),
        ("BOX", (0,0), (-1,-1), 0.4, BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 2*mm))

# -- Parse combined markdown and render --
# Simple markdown parser: headings, paragraphs, bullets, code blocks, tables
lines = full_md.splitlines()
i = 0
in_code = False
code_buf = []
# Track TOC entries
toc_entries = []

def flush_code():
    global code_buf
    if code_buf:
        text = "\n".join(code_buf)
        # Escape HTML
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace("\n", "<br/>").replace("  ", "&nbsp;&nbsp;")
        code_block(text)
        code_buf = []

while i < len(lines):
    line = lines[i]
    stripped = line.strip()

    # Code fence
    if stripped.startswith("```"):
        if in_code:
            flush_code()
            in_code = False
        else:
            in_code = True
            code_buf = []
        i += 1
        continue
    if in_code:
        code_buf.append(line)
        i += 1
        continue

    # Headings
    if stripped.startswith("# "):
        title = stripped[2:].strip()
        # Cover title handled specially
        story.append(Paragraph(title, sTitle))
        i += 1
        continue
    if stripped.startswith("## "):
        title = stripped[3:].strip()
        # Detect numbered sections for TOC
        toc_entries.append((1, title))
        story.append(Paragraph(title, sH1))
        i += 1
        continue
    if stripped.startswith("### "):
        title = stripped[4:].strip()
        toc_entries.append((2, title))
        story.append(Paragraph(title, sH2))
        i += 1
        continue
    if stripped.startswith("#### "):
        title = stripped[5:].strip()
        toc_entries.append((3, title))
        story.append(Paragraph(title, sH3))
        i += 1
        continue

    # Horizontal rule
    if stripped in ("---", "***", "___"):
        story.append(HRFlowable(width="100%", thickness=0.4, color=BORDER, spaceAfter=4, spaceBefore=4))
        i += 1
        continue

    # Table detection: line contains | and next line is separator
    if "|" in stripped and i+1 < len(lines) and re.match(r"^\s*\|?[\s\-\|:]+\|?\s*$", lines[i+1]):
        headers = [c.strip() for c in stripped.strip("|").split("|")]
        i += 2  # skip separator
        rows = []
        while i < len(lines) and "|" in lines[i] and lines[i].strip():
            rows.append([c.strip() for c in lines[i].strip("|").split("|")])
            i += 1
        add_table(headers, rows)
        continue

    # Bullet
    if stripped.startswith("- ") or stripped.startswith("* ") or stripped.startswith("• "):
        text = stripped[2:].strip()
        # Collect continuation lines
        j = i+1
        while j < len(lines) and lines[j].startswith("  ") and lines[j].strip() and not lines[j].strip().startswith("- "):
            text += " " + lines[j].strip()
            j += 1
        # Escape and render - extract code spans before escaping
        _bcodes = []
        def _bsv(m):
            _bcodes.append(m.group(1))
            return f"__BC{len(_bcodes)-1}__"
        text = re.sub(r"`(.+?)`", _bsv, text)
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        for _ci, _cc in enumerate(_bcodes):
            _sf = _cc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            text = text.replace(f"__BC{_ci}__", f'<font face="Courier">{_sf}</font>')
        story.append(Paragraph(text, sBullet, bulletText="•"))
        i = j
        continue

    # Numbered list
    if re.match(r"^\d+\.\s", stripped):
        text = re.sub(r"^\d+\.\s", "", stripped)
        _ncodes = []
        def _nsv(m):
            _ncodes.append(m.group(1))
            return f"__NC{len(_ncodes)-1}__"
        text = re.sub(r"`(.+?)`", _nsv, text)
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        for _ci, _cc in enumerate(_ncodes):
            _sf = _cc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            text = text.replace(f"__NC{_ci}__", f'<font face="Courier">{_sf}</font>')
        m = re.match(r"^(\d+)\.", stripped)
        num = m.group(1) if m else "1"
        story.append(Paragraph(text, sBullet, bulletText=f"{num}."))
        i += 1
        continue

    # Empty line
    if not stripped:
        i += 1
        continue

    # Regular paragraph - collect until blank or special
    para_lines = [line.strip()]
    j = i+1
    while j < len(lines):
        nxt = lines[j]
        ns = nxt.strip()
        if not ns:
            break
        if ns.startswith("#") or ns.startswith("- ") or ns.startswith("* ") or ns.startswith("```") or re.match(r"^\d+\.\s", ns) or "|" in ns and j+1 < len(lines) and re.match(r"^\s*\|?[\s\-\|:]+\|?\s*$", lines[j+1]):
            break
        if ns in ("---", "***"):
            break
        para_lines.append(ns)
        j += 1
    text = " ".join(para_lines)
    _codes = []
    def _sv(m):
        _codes.append(m.group(1))
        return f"__C{len(_codes)-1}__"
    text = re.sub(r"`(.+?)`", _sv, text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    for _ci, _cc in enumerate(_codes):
        _sf = _cc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        text = text.replace(f"__C{_ci}__", f'<font face="Courier">{_sf}</font>')
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    story.append(Paragraph(text, sBody))
    i = j

# Build PDF
doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm,
                        title="Markdown Summary Tool - Technical Specification v1.0",
                        author="Engineering")
doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
print(f"PDF written to {OUT}")
print(f"Pages: {pymupdf.open(OUT).__len__()}")





