"""Writing an Excel workbook with nothing but the standard library.

An .xlsx file is a zip of a few XML parts. This writes the small subset a
return needs -- text, whole and decimal numbers, bold headings, column widths,
a frozen header row, wrapped text -- and nothing else, which is what keeps the
program free of anything to install.

Amounts are written as numbers, never as text, so the workbook can be summed
and compared. They are shown with Indian digit grouping (12,34,567) by a number
format, which changes how a figure looks and not what it is.

    book = Workbook()
    sheet = book.sheet("Summary", widths=[40, 16])
    sheet.row(["Line", "Amount"], style="head")
    sheet.row(["Total income", 8605720])
    book.save(path)
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

# Lakhs and crores, with a negative shown by a minus sign.
INDIAN = ("[>=10000000]##\\,##\\,##\\,##0;[>=100000]##\\,##\\,##0;##,##0")
INDIAN_NEG = ("[<=-10000000]-##\\,##\\,##\\,##0;[<=-100000]-##\\,##\\,##0;##,##0")

# name -> (font, fill, number format, wrap, horizontal). Fonts and fills are
# indexes into the lists written in _styles(); 164 and 165 are the two formats.
STYLES = {
    "text":   (0, 0, 0, True, None),
    "money":  (0, 0, 164, False, None),
    "neg":    (0, 0, 165, False, None),
    "num":    (0, 0, 2, False, None),
    "head":   (1, 2, 0, True, None),
    "headr":  (1, 2, 0, True, "right"),
    "bold":   (1, 0, 0, True, None),
    "boldm":  (1, 0, 164, False, None),
    "boldn":  (1, 0, 165, False, None),
    "title":  (2, 0, 0, False, None),
    "muted":  (3, 0, 0, True, None),
    "sub":    (3, 0, 0, True, None),
}
ORDER = list(STYLES)

# Characters XML 1.0 will not carry; a stray one makes Excel refuse the file.
ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
SHEET_NAME_BAD = re.compile(r"[\[\]:*?/\\]")


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


class Sheet:
    def __init__(self, name: str, widths: list[float] | None = None, freeze: int = 0):
        self.name = name
        self.widths = widths or []
        self.freeze = freeze
        self.rows: list[str] = []

    def row(self, values, style: str | None = None, styles: list[str | None] | None = None) -> None:
        """One row. `style` applies to every cell; `styles` names one per cell.
        Without either, a number is an amount and anything else is text."""
        n = len(self.rows) + 1
        cells = []
        for i, value in enumerate(values):
            if value is None or value == "":
                continue
            ref = f"{column_letter(i)}{n}"
            chosen = (styles[i] if styles and i < len(styles) and styles[i] else style)
            if isinstance(value, bool):
                value = "yes" if value else "no"
            if isinstance(value, (int, float)):
                if chosen in (None, "money"):
                    chosen = ("neg" if value < 0 else "money") if float(value).is_integer() else "num"
                elif chosen in ("bold", "boldm"):
                    chosen = "boldn" if value < 0 else "boldm"
                elif chosen in ("head", "headr", "muted", "sub", "title", "text"):
                    chosen = "neg" if value < 0 else "money"
                cells.append(f'<c r="{ref}" s="{ORDER.index(chosen)}"><v>{value!r}</v></c>')
            else:
                text = escape(ILLEGAL.sub("", str(value)))
                cells.append(f'<c r="{ref}" s="{ORDER.index(chosen or "text")}" t="inlineStr">'
                             f'<is><t xml:space="preserve">{text}</t></is></c>')
        self.rows.append(f'<row r="{n}">{"".join(cells)}</row>')

    def blank(self) -> None:
        self.rows.append(f'<row r="{len(self.rows) + 1}"/>')

    def xml(self) -> str:
        pane = ""
        if self.freeze:
            pane = (f'<pane ySplit="{self.freeze}" topLeftCell="A{self.freeze + 1}" '
                    f'activePane="bottomLeft" state="frozen"/>')
        cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>'
                       for i, w in enumerate(self.widths))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetViews><sheetView workbookViewId="0">{pane}</sheetView></sheetViews>'
                + (f"<cols>{cols}</cols>" if cols else "")
                + f'<sheetData>{"".join(self.rows)}</sheetData></worksheet>')


class Workbook:
    def __init__(self):
        self.sheets: list[Sheet] = []

    def sheet(self, name: str, widths: list[float] | None = None, freeze: int = 0) -> Sheet:
        sheet = Sheet(self._name(name), widths, freeze)
        self.sheets.append(sheet)
        return sheet

    def _name(self, wanted: str) -> str:
        """Excel allows 31 characters, none of []:*?/\\, and no two alike."""
        base = SHEET_NAME_BAD.sub(" ", wanted).strip().strip("'")[:31] or "Sheet"
        taken = {s.name.lower() for s in self.sheets}
        name, n = base, 2
        while name.lower() in taken:
            tail = f" {n}"
            name, n = base[:31 - len(tail)] + tail, n + 1
        return name

    def save(self, path: Path) -> Path:
        """Written beside the target and renamed over it, so a failed write
        never leaves half a workbook. A workbook open in Excel is locked on
        Windows; that raises PermissionError for the caller to report."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", self._content_types())
            z.writestr("_rels/.rels", _RELS)
            z.writestr("xl/workbook.xml", self._workbook())
            z.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels())
            z.writestr("xl/styles.xml", _styles())
            for i, sheet in enumerate(self.sheets, 1):
                z.writestr(f"xl/worksheets/sheet{i}.xml", sheet.xml())
        try:
            tmp.replace(path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
        return path

    def _content_types(self) -> str:
        sheets = "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.'
            f'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(self.sheets) + 1))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
                'officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-'
                'officedocument.spreadsheetml.styles+xml"/>'
                f'{sheets}</Types>')

    def _workbook(self) -> str:
        sheets = "".join(f'<sheet name="{escape(s.name, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
                         for i, s in enumerate(self.sheets, 1))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets>{sheets}</sheets></workbook>')

    def _workbook_rels(self) -> str:
        rels = "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            f'relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(self.sheets) + 1))
        n = len(self.sheets) + 1
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'{rels}<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/officeDocument/'
                f'2006/relationships/styles" Target="styles.xml"/></Relationships>')


_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
         'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')


def _styles() -> str:
    xfs = []
    for font, fill, fmt, wrap, align in (STYLES[name] for name in ORDER):
        alignment = ""
        if wrap or align:
            alignment = ("<alignment vertical=\"top\""
                         + (' wrapText="1"' if wrap else "")
                         + (f' horizontal="{align}"' if align else "") + "/>")
        xfs.append(f'<xf numFmtId="{fmt}" fontId="{font}" fillId="{fill}" borderId="0" xfId="0" '
                   f'applyNumberFormat="1" applyFont="1" applyFill="1" applyAlignment="1">{alignment}</xf>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<numFmts count="2"><numFmt numFmtId="164" formatCode="{escape(INDIAN)}"/>'
            f'<numFmt numFmtId="165" formatCode="{escape(INDIAN_NEG)}"/></numFmts>'
            '<fonts count="4">'
            '<font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="14"/><name val="Calibri"/></font>'
            '<font><sz val="10"/><color rgb="FF5F6368"/><name val="Calibri"/></font>'
            '</fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFEDEFF2"/></patternFill></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>')
