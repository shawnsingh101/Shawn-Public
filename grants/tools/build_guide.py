"""Build an updated grant guide (Word + review spreadsheet) from a content file.

Usage: python grants/tools/build_guide.py grants/guides/<guide>.json [out_dir]

The Word file starts from the office's own template (cover page, seal, page
border, fonts) and replaces the body with the content file. The spreadsheet
lists every entry with its status, what changed, sources, and an Approve column
for staff review. Convert the .docx to PDF with Word ("Save as PDF") for exact
fonts, or with LibreOffice for a preview.

Inline markup inside text: **bold** and [link text](https://url).
"""
import copy
import json
import os
import re
import sys

import docx
from docx.enum.text import WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

# Paragraph indexes in the template used as formatting prototypes.
PROTO = {"h1": 25, "h2": 33, "p": 34, "bullet": 68}
COVER_END = 25          # paragraphs [0, 25) are the cover page
YEAR_PARA = 13
TITLE_PARAS = (3, 4)
INLINE = re.compile(r"(\*\*.+?\*\*|\[[^\]]+\]\([^)]+\))")


def clear_runs(p):
    for r in list(p._p):
        if r.tag in (qn("w:r"), qn("w:hyperlink")):
            p._p.remove(r)


def add_hyperlink(p, text, url, bold=False, size=12):
    r_id = p.part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink")
    h.set(qn("r:id"), r_id)
    r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    for tag, attrs in (("w:color", {"w:val": "0563C1"}), ("w:u", {"w:val": "single"}),
                       ("w:sz", {"w:val": str(size * 2)})):
        el = OxmlElement(tag)
        for k, v in attrs.items():
            el.set(qn(k), v)
        rpr.append(el)
    if bold:
        rpr.append(OxmlElement("w:b"))
    r.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    h.append(r)
    p._p.append(h)


def fill(p, text, size=12, bold=False):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            run = p.add_run(part[2:-2]); run.bold = True; run.font.size = Pt(size)
        elif part.startswith("["):
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part).groups()
            add_hyperlink(p, label, url, bold=bold, size=size)
        else:
            run = p.add_run(part); run.font.size = Pt(size)
            if bold:
                run.bold = True


class Builder:
    def __init__(self, template):
        self.doc = docx.Document(template)
        paras = self.doc.paragraphs
        self.proto = {k: copy.deepcopy(paras[i]._p) for k, i in PROTO.items()}
        self.body = self.doc.element.body
        self.sect = self.body[-1] if self.body[-1].tag == qn("w:sectPr") else None
        for p in paras[COVER_END:]:
            self.body.remove(p._p)
        for t in self.doc.tables:
            self.body.remove(t._tbl)

    def _new(self, kind):
        el = copy.deepcopy(self.proto[kind])
        for ch in list(el):
            if ch.tag != qn("w:pPr"):
                el.remove(ch)
        if self.sect is not None:
            self.sect.addprevious(el)
        else:
            self.body.append(el)
        return docx.text.paragraph.Paragraph(el, self.doc.part)

    def cover(self, title_lines, year):
        paras = self.doc.paragraphs
        for i, line in zip(TITLE_PARAS, title_lines + [""] * 2):
            p = paras[i]; clear_runs(p); p.add_run(line)
        y = paras[YEAR_PARA]; clear_runs(y); y.add_run(str(year))

    def h1(self, text):
        p = self._new("h1"); fill(p, text, size=16, bold=True)
        p.paragraph_format.space_before = Pt(12); p.paragraph_format.keep_with_next = True

    def h2(self, text):
        p = self._new("h2"); fill(p, text, size=14, bold=True)
        p.paragraph_format.space_before = Pt(10); p.paragraph_format.keep_with_next = True

    def para(self, text, bold=False):
        p = self._new("p"); fill(p, text, bold=bold)

    def bullets(self, items):
        for it in items:
            p = self._new("bullet"); fill(p, it)

    def page_break(self):
        p = self._new("p"); p.add_run().add_break(WD_BREAK.PAGE)

    def offices(self, offices):
        """Two-column table of office addresses (replaces the old screenshot)."""
        tbl = self.doc.add_table(rows=0, cols=2)
        if self.sect is not None:
            self.sect.addprevious(tbl._tbl)
        cells = []
        for i in range(0, len(offices), 2):
            row = tbl.add_row().cells
            cells.extend(zip(row, offices[i:i + 2]))
        for cell, office in cells:
            p = cell.paragraphs[0]
            r = p.add_run(office["name"]); r.bold = True; r.font.size = Pt(11)
            for line in office["lines"]:
                q = cell.add_paragraph(); rr = q.add_run(line); rr.font.size = Pt(11)
            cell.add_paragraph()

    def block(self, b):
        t = b["type"]
        if t == "h1": self.h1(b["text"])
        elif t == "h2": self.h2(b["text"])
        elif t == "p": self.para(b["text"], b.get("bold", False))
        elif t == "bullets": self.bullets(b["items"])
        elif t == "pagebreak": self.page_break()
        elif t == "offices": self.offices(b["offices"])
        else: raise ValueError(f"unknown block type {t}")


def build(content_path, out_dir):
    c = json.load(open(content_path))
    tpl = os.path.join(os.path.dirname(content_path), "..", "templates", c["template"])
    b = Builder(tpl)
    b.cover(c["title_lines"], c["year"])
    # Contents page: section and entry names (no page numbers, so it never goes stale).
    b.page_break()
    b.h1("In This Guide")
    for sec in c["sections"]:
        b.para(f"**{sec['title']}**")
        b.bullets([e["title"] for e in sec["entries"] if e.get("status") != "Removed"])
    b.page_break()
    for blk in c.get("front", []):
        b.block(blk)
    for sec in c["sections"]:
        b.page_break()
        b.h1(sec["title"])
        for blk in sec.get("intro", []):
            b.block(blk)
        for e in sec["entries"]:
            if e.get("status") == "Removed":
                continue
            b.h2(e["title"])
            for blk in e["blocks"]:
                b.block(blk)
    for blk in c.get("back", []):
        b.block(blk)
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, c["file_name"])
    b.doc.core_properties.author = "Office of U.S. Senator Kirsten Gillibrand"
    b.doc.core_properties.title = " ".join(c["title_lines"])
    b.doc.save(base + ".docx")
    review_sheet(c, base + " - Review.xlsx")
    return base


def review_sheet(c, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook(); ws = wb.active; ws.title = "Review"
    head = ["Section", "Entry", "Status", "What changed", "Please double-check", "Sources (checked " + c["checked"] + ")", "Approve?", "Reviewer notes"]
    ws.append(head)
    fills = {"New": "E2EFDA", "Updated": "FFF2CC", "Kept": "FFFFFF", "Removed": "F8CBAD"}
    for sec in c["sections"]:
        for e in sec["entries"]:
            ws.append([sec["title"], e["title"], e.get("status", ""), e.get("changes", ""), e.get("verify", ""),
                       "\n".join(e.get("sources", [])), "", ""])
            ws.cell(ws.max_row, 3).fill = PatternFill("solid", fgColor=fills.get(e.get("status"), "FFFFFF"))
    for extra in c.get("review_extra", []):
        ws.append(["(Whole guide)", extra["title"], extra.get("status", "Updated"), extra.get("changes", ""), extra.get("verify", ""), "", "", ""])
    dv = DataValidation(type="list", formula1='"Approve,Approve with edits,Remove"', allow_blank=True)
    ws.add_data_validation(dv); dv.add(f"G2:G{ws.max_row}")
    for col, w in zip("ABCDEFGH", (22, 34, 11, 60, 40, 55, 16, 30)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=1):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "C2"
    wb.save(path)


if __name__ == "__main__":
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join("grants", "output")
    print(build(sys.argv[1], out))
