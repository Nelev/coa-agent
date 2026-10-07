"""Lay the guide out as an A4 PDF with ReportLab, from the same HTML the web
page is made of, so the two cannot drift apart.

    cd docs/build
    uv run --with reportlab --with beautifulsoup4 python html-to-pdf.py ../coa-agent-guide.html ../coa-agent-guide.pdf
"""

import re
import sys
from xml.sax.saxutils import escape

from bs4 import BeautifulSoup, NavigableString, Tag
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SRC, OUT = sys.argv[1], sys.argv[2]

INK = colors.HexColor("#14212B")
MUTED = colors.HexColor("#51606B")
LINE = colors.HexColor("#D6DFE5")
ACCENT = colors.HexColor("#1B5E78")
SOFT = colors.HexColor("#E2EFF4")
PAPER = colors.HexColor("#F5F8FA")
TINT = {
    "pass": ("#1E7A4F", "#E2F3EA"),
    "review": ("#8F5F00", "#FDF0C8"),
    "fail": ("#B3261E", "#FBE3E1"),
    "error": ("#51606B", "#EEF1F3"),
}
WHO = {"ai": ("#1B5E78", "#E2EFF4"), "rule": ("#14212B", "#EEF1F3"), "person": ("#8F5F00", "#FDF0C8")}

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.8, leading=14, textColor=INK, alignment=TA_LEFT, spaceAfter=6)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.8, leading=12, spaceAfter=3)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.8, leading=12, spaceAfter=3)
MUTED_S = ParagraphStyle("muted", parent=BODY, textColor=MUTED)
EYEBROW = ParagraphStyle("eyebrow", parent=BODY, fontName="Helvetica-Bold", fontSize=7.8, textColor=MUTED, spaceAfter=4)
TITLE = ParagraphStyle("title", fontName="Times-Bold", fontSize=30, leading=34, textColor=ACCENT, spaceAfter=10)
LEDE = ParagraphStyle("lede", parent=BODY, fontSize=12, leading=17.5, spaceAfter=10)
H2 = ParagraphStyle("h2", fontName="Times-Bold", fontSize=18, leading=22, textColor=ACCENT, spaceBefore=14, spaceAfter=2, keepWithNext=1)
H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=INK, spaceBefore=10, spaceAfter=4, keepWithNext=1)
STEP_H = ParagraphStyle("steph", parent=H3, spaceBefore=0, spaceAfter=4)
BIG = ParagraphStyle("big", fontName="Times-Bold", fontSize=17, leading=20, textColor=INK, spaceAfter=2)
LABEL = ParagraphStyle("label", parent=BODY, fontName="Helvetica-Bold", fontSize=7.4, textColor=MUTED, spaceAfter=3)


def classes(tag: Tag) -> list[str]:
    return tag.get("class") or []


def inline(node) -> str:
    """The text of a node's contents as ReportLab paragraph markup."""
    return "".join(inline_el(child) for child in node.children).strip()


def inline_el(child) -> str:
    """One node (text, or a tag with its styling) as paragraph markup."""
    out = []
    if True:
        if isinstance(child, NavigableString):
            return escape(re.sub(r"\s+", " ", str(child)))
        cls = classes(child)
        inner = inline(child)
        if child.name in ("strong", "b"):
            out.append(f"<b>{inner}</b>")
        elif child.name == "em":
            out.append(f"<i>{inner}</i>")
        elif child.name == "br":
            out.append("<br/>")
        elif child.name == "code" or "val" in cls:
            out.append(f'<span fontName="Courier" backColor="#E2EFF4">&nbsp;{inner.strip().replace(" ", "&nbsp;")}&nbsp;</span>')
        elif "status" in cls:
            kind = next(c for c in cls if c in TINT)
            fg, bg = TINT[kind]
            out.append(f'<span fontName="Courier-Bold" color="{fg}" backColor="{bg}">&nbsp;{inner.strip()}&nbsp;</span>')
        elif "who" in cls:
            kind = next(c for c in cls if c in WHO)
            fg, bg = WHO[kind]
            out.append(f'<span fontName="Helvetica-Bold" fontSize="6.6" color="{fg}" backColor="{bg}">&nbsp;{inner.strip().upper()}&nbsp;</span>')
        else:
            out.append(inner)
    return "".join(out)


def para(node, style=BODY) -> Paragraph:
    return Paragraph(inline(node), style)


def boxed(flowables, fill=None, bar=None, border=LINE, dashed=False, pad=8, width=CONTENT_W):
    """A single-cell table around some flowables."""
    t = Table([[flowables]], colWidths=[width])
    cmds = [
        ("LEFTPADDING", (0, 0), (-1, -1), pad + (3 if bar else 0)),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if fill is not None:
        cmds.append(("BACKGROUND", (0, 0), (-1, -1), fill))
    if bar is not None:
        cmds.append(("LINEBEFORE", (0, 0), (0, -1), 3, bar))
    elif border is not None:
        cmds.append(("BOX", (0, 0), (-1, -1), 0.6, border, None, (3, 2) if dashed else None))
    t.setStyle(TableStyle(cmds))
    return t


def bullets(items, style=BODY, width=None):
    rows = [[Paragraph("&bull;", style), Paragraph(inline(li), style)] for li in items]
    t = Table(rows, colWidths=[12, (width or CONTENT_W) - 12])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def data_table(table: Tag) -> Table:
    head = [c for c in table.find("thead").find_all("th")]
    body = [[c for c in r.find_all("td")] for r in table.find("tbody").find_all("tr")]
    ncols = len(head)
    # Column share follows how much text each holds, with a floor and a ceiling.
    weights = []
    for i in range(ncols):
        longest = max(len(c[i].get_text(" ", strip=True)) for c in body)
        weights.append(min(max(longest, 14), 70))
    total = sum(weights)
    widths = [CONTENT_W * w / total for w in weights]
    rows = [[Paragraph(f"<b>{inline(h).upper()}</b>", ParagraphStyle("th", parent=CELL, fontSize=7.2, textColor=MUTED)) for h in head]]
    for r in body:
        rows.append([Paragraph(inline(c), CELL) for c in r])
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF3F6")),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def grid(cells, ncols):
    """Equal-width boxes in rows of ncols, each a list of flowables."""
    w = CONTENT_W / ncols
    rows = [cells[i:i + ncols] for i in range(0, len(cells), ncols)]
    for r in rows:
        r += [[Spacer(1, 1)]] * (ncols - len(r))
    t = Table(rows, colWidths=[w] * ncols)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


state: dict = {}


def render_block(el: Tag, story: list) -> None:
    cls = classes(el)
    if el.name != "p" and el.name != "h2":
        state.pop("after_h2", None)
    if el.name == "h2":
        rule = HRFlowable(width="100%", thickness=0.6, color=LINE, spaceAfter=8)
        rule.keepWithNext = 1
        story += [Paragraph(inline(el), H2), rule]
        state["after_h2"] = True
        return
    elif el.name == "h3":
        story.append(Paragraph(inline(el), H3))
    elif el.name == "p":
        p = para(el, MUTED_S if "muted" in cls else (SMALL if "legend" in cls else BODY))
        if state.pop("after_h2", False):
            p.keepWithNext = 1  # the opening paragraph stays with its heading and what follows
        story.append(p)
    elif el.name == "ul":
        story += [bullets(el.find_all("li", recursive=False)), Spacer(1, 6)]
    elif el.name == "dl":
        rows = [[Paragraph(f"<b>{inline(dt)}</b>", CELL), Paragraph(inline(dd), ParagraphStyle("dd", parent=CELL, textColor=MUTED))] for dt, dd in zip(el.find_all("dt"), el.find_all("dd"))]
        t = Table(rows, colWidths=[CONTENT_W * 0.3, CONTENT_W * 0.7])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(t)
    elif "callout" in cls:
        warn = "warn" in cls
        paras = [para(p, ParagraphStyle("c", parent=BODY, spaceAfter=4)) for p in el.find_all("p")]
        story += [boxed(paras, fill=colors.HexColor("#FDF0C8" if warn else "#E2EFF4"), bar=colors.HexColor("#8F5F00" if warn else "#1B5E78")), Spacer(1, 8)]
    elif "letter" in cls:
        label = Paragraph(inline(el.find(class_="label")).upper(), LABEL)
        story += [boxed([label, para(el.find("p"), SMALL)], fill=colors.white, dashed=True, border=MUTED), Spacer(1, 8)]
    elif "tablewrap" in cls:
        story += [data_table(el.find("table")), Spacer(1, 8)]
    elif "flow" in cls:
        cells = []
        for li in el.find_all("li", recursive=False):
            cells.append([Paragraph(inline_el(li.find(class_="who")), SMALL), Paragraph(f"<b>{inline(li.find('strong'))}</b>", ParagraphStyle("fs", parent=BODY, fontName="Times-Bold", fontSize=11, spaceAfter=2)), Paragraph(inline(li.find(class_="t")), ParagraphStyle("ft", parent=SMALL, textColor=MUTED))])
        story += [KeepTogether([grid(cells, 5)]), Spacer(1, 8)]
    elif "cards" in cls:
        cells = []
        for card in el.find_all(class_="card", recursive=False):
            items = card.find("ul").find_all("li")
            cells.append([Paragraph(inline_el(card.find(class_="status")), BODY), bullets(items, SMALL, width=CONTENT_W / 3 - 14)])
        story += [KeepTogether([grid(cells, 3)]), Spacer(1, 8)]
    elif "numbers" in cls:
        cells = [[Paragraph(inline(d.find(class_="big")), BIG), Paragraph(inline(d.find(class_="small")), ParagraphStyle("ns", parent=SMALL, textColor=MUTED))] for d in el.find_all("div", recursive=False)]
        story += [KeepTogether([grid(cells, 3)]), Spacer(1, 8)]
    elif "steps" in cls:
        for n, li in enumerate(el.find_all("li", recursive=False), 1):
            head = li.find(class_="head")
            title = head.find("h3").get_text(strip=True)
            chips = " ".join(inline_el(w) for w in head.find_all(class_="who"))
            inner = [Paragraph(f"{n}. {escape(title)} &nbsp; {chips}", STEP_H)]
            for p in li.find_all("p", recursive=False):
                inner.append(para(p, ParagraphStyle("w", parent=SMALL, textColor=MUTED) if "what" in classes(p) else ParagraphStyle("sb", parent=BODY, fontSize=9.6, leading=13.5, spaceAfter=4)))
            story += [KeepTogether([boxed(inner, fill=colors.white)]), Spacer(1, 6)]
    elif el.name == "footer":
        story += [Spacer(1, 10), HRFlowable(width="100%", thickness=0.5, color=LINE, spaceAfter=6), para(el, ParagraphStyle("f", parent=SMALL, textColor=MUTED))]


class Numbered(canvas.Canvas):
    """Page x of y: the total is known only after the last page."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7.5)
            self.setFillColor(MUTED)
            self.drawCentredString(PAGE_W / 2, 10 * mm, f"The CoA agent  ·  proof of concept on synthetic data  ·  page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def background(c, doc):
    c.saveState()
    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    c.restoreState()


def main():
    soup = BeautifulSoup(open(SRC, encoding="utf-8").read(), "html.parser")
    page = soup.find(class_="page")
    story = []
    header = page.find("header")
    story += [Paragraph(inline(header.find(class_="eyebrow")).upper(), EYEBROW), Paragraph(inline(header.find("h1")), TITLE), Paragraph(inline(header.find(class_="lede")), LEDE), HRFlowable(width="100%", thickness=0.6, color=LINE, spaceAfter=4)]
    for section in page.find_all("section", recursive=False):
        for child in section.children:
            if isinstance(child, Tag):
                render_block(child, story)
    render_block(page.find("footer"), story)

    doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=16 * mm, bottomMargin=18 * mm, title="The CoA agent", author="CoA agent project")
    doc.build(story, onFirstPage=background, onLaterPages=background, canvasmaker=Numbered)
    print("wrote", OUT)


main()
