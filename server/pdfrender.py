"""Draw a PDF page onto a bitmap, for the PDFs that have no text to read.

Some statements are exported with every character converted to outlines. The
page looks like words to a human and to the file it is a few thousand filled
Bezier curves: no fonts, no text operators, nothing for a text extractor to
find, and no embedded image either, so there is also no scan to hand over. The
SBI account statement is one of these -- 49,876 curve operators and not a
single `Tj`.

The reading itself is not the problem. An engine that can look at a page can
read that page perfectly well. What is missing is a page to look at, and a PDF
carries the instructions to draw one. So this module follows them: it walks the
content stream, keeps the graphics state, flattens the curves and fills the
resulting polygons onto a grayscale canvas, which is then written out as a PNG
with `zlib` and handed over like any other page image.

It is a renderer for this one purpose, and it is honest about that. It draws
filled and stroked paths in grayscale and ignores clipping paths, shadings,
transparency groups, patterns and image XObjects, because what it is being
asked to make legible is black text on a white page. A document whose meaning
depends on any of those should be rendered by something else; a bank statement
does not.
"""

from __future__ import annotations

import math
import re

from . import pdfread

# 2x gives roughly 14 pixels of height to 7-point type, which is the size
# statements print their figures at and about where a reader stops guessing.
DEFAULT_SCALE = 2.0

# Vertical sub-samples per output row. Text this small lives or dies on its
# antialiasing: without it the thin strokes of a 4 and a 1 drop out entirely.
SUBSAMPLES = 4

MAX_PAGES = 40
US_LETTER = (0.0, 0.0, 612.0, 792.0)


# ---------------------------------------------------------------------------
# matrices
# ---------------------------------------------------------------------------
def _mul(m, n):
    """m applied first, then n -- the order the `cm` operator composes in."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + b * C, a * B + b * D,
            c * A + d * C, c * B + d * D,
            e * A + f * C + E, e * B + f * D + F)


def _apply(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _scale_of(m) -> float:
    """Roughly how much this matrix magnifies, for flattening and line width."""
    a, b, c, d = m[0], m[1], m[2], m[3]
    return max(1e-6, math.sqrt(abs(a * d - b * c)) or math.hypot(a, b))


# ---------------------------------------------------------------------------
# the canvas
# ---------------------------------------------------------------------------
class Canvas:
    """A grayscale page, filled by scanline with antialiased coverage.

    Coverage is accumulated per output row in a dict rather than a full-width
    array: a glyph touches a dozen pixels on a row and allocating a row of
    floats for each of several thousand paths costs more than the drawing.
    """

    def __init__(self, width: int, height: int) -> None:
        self.w, self.h = width, height
        self.px = bytearray(b"\xff" * (width * height))

    def fill(self, subpaths, gray: int, even_odd: bool) -> None:
        edges = []
        for pts in subpaths:
            if len(pts) < 2:
                continue
            closed = pts if pts[0] == pts[-1] else pts + [pts[0]]
            for i in range(len(closed) - 1):
                x0, y0 = closed[i]
                x1, y1 = closed[i + 1]
                if y0 != y1:
                    edges.append((x0, y0, x1, y1))
        if not edges:
            return

        top = max(0, int(math.floor(min(min(e[1], e[3]) for e in edges))))
        bottom = min(self.h - 1, int(math.ceil(max(max(e[1], e[3]) for e in edges))))
        if top > bottom:
            return

        w, px = self.w, self.px
        weight = 1.0 / SUBSAMPLES
        for row in range(top, bottom + 1):
            acc: dict[int, float] = {}
            for k in range(SUBSAMPLES):
                yy = row + (k + 0.5) * weight
                hits = []
                for x0, y0, x1, y1 in edges:
                    if (y0 <= yy < y1) or (y1 <= yy < y0):
                        hits.append((x0 + (yy - y0) * (x1 - x0) / (y1 - y0),
                                     1 if y1 > y0 else -1))
                if len(hits) < 2:
                    continue
                hits.sort()
                if even_odd:
                    spans = [(hits[i][0], hits[i + 1][0])
                             for i in range(0, len(hits) - 1, 2)]
                else:
                    spans, wind, start = [], 0, 0.0
                    for x, direction in hits:
                        if wind == 0:
                            start = x
                        wind += direction
                        if wind == 0:
                            spans.append((start, x))
                for xa, xb in spans:
                    self._span(acc, xa, xb, weight)
            if not acc:
                continue
            base = row * w
            for i, cov in acc.items():
                if cov <= 0.002:
                    continue
                cov = 1.0 if cov > 1.0 else cov
                here = px[base + i]
                px[base + i] = int(here + (gray - here) * cov)

    def _span(self, acc: dict, xa: float, xb: float, weight: float) -> None:
        if xb < xa:
            xa, xb = xb, xa
        if xb <= 0 or xa >= self.w:
            return
        xa = 0.0 if xa < 0 else xa
        xb = float(self.w) if xb > self.w else xb
        ia, ib = int(xa), int(xb)
        if ib >= self.w:
            ib = self.w - 1
        if ia == ib:
            acc[ia] = acc.get(ia, 0.0) + (xb - xa) * weight
            return
        acc[ia] = acc.get(ia, 0.0) + (ia + 1 - xa) * weight
        for i in range(ia + 1, ib):
            acc[i] = acc.get(i, 0.0) + weight
        acc[ib] = acc.get(ib, 0.0) + (xb - ib) * weight

    def png(self) -> bytes:
        return pdfread._png(self.w, self.h, 0, 8, bytes(self.px))


# ---------------------------------------------------------------------------
# the content stream
# ---------------------------------------------------------------------------
TOKEN = re.compile(rb"""
    (?P<num>[+-]?(?:\d+\.\d*|\.\d+|\d+))
  | (?P<name>/[^\s/\[\]<>(){}%]*)
  | (?P<op>[A-Za-z'"][A-Za-z0-9'"*]*)
  | (?P<punct>[\[\]]|<<|>>)
  | (?P<string>\()
  | (?P<hex><)
  | (?P<comment>%[^\r\n]*)
""", re.X)

PAINTS = {"f", "F", "f*", "B", "B*", "b", "b*", "S", "s", "n"}


def _skip_string(buf: bytes, pos: int) -> int:
    depth = 1
    while pos < len(buf) and depth:
        ch = buf[pos:pos + 1]
        if ch == b"\\":
            pos += 2
            continue
        if ch == b"(":
            depth += 1
        elif ch == b")":
            depth -= 1
        pos += 1
    return pos


def _gray_from(comps: list[float], space: str) -> int:
    """One 0-255 grey from whatever colour operator was used.

    Rec. 601 luminance, so that a dark blue header keeps its contrast against
    the white text printed on it instead of flattening to the same shade."""
    if space == "g" and comps:
        v = comps[-1]
    elif space == "rg" and len(comps) >= 3:
        r, g, b = comps[-3:]
        v = 0.299 * r + 0.587 * g + 0.114 * b
    elif space == "k" and len(comps) >= 4:
        c, m, y, k = comps[-4:]
        v = (1 - min(1.0, c + k)) * 0.299 + (1 - min(1.0, m + k)) * 0.587 \
            + (1 - min(1.0, y + k)) * 0.114
    elif comps:
        v = comps[-1]
    else:
        v = 0.0
    return max(0, min(255, int(round(v * 255))))


def render_page(doc: pdfread.Document, page: dict, scale: float = DEFAULT_SCALE) -> Canvas:
    """One page, drawn."""
    box = doc.resolve(page.get("MediaBox")) or list(US_LETTER)
    try:
        x0, y0, x1, y1 = (float(doc.resolve(v)) for v in box)
    except (TypeError, ValueError):
        x0, y0, x1, y1 = US_LETTER
    pw, ph = abs(x1 - x0), abs(y1 - y0)
    if not (10 < pw < 20000 and 10 < ph < 20000):
        x0, y0, pw, ph = 0.0, 0.0, 612.0, 792.0

    width = max(1, int(round(pw * scale)))
    height = max(1, int(round(ph * scale)))
    canvas = Canvas(width, height)

    # PDF user space has its origin at the bottom left and y increasing
    # upwards; a bitmap counts rows downwards from the top.
    base = (scale, 0.0, 0.0, -scale, -min(x0, x1) * scale, max(y0, y1) * scale)

    ctm = base
    stack: list[tuple] = []
    fill_gray, stroke_gray = 0, 0
    fill_space, stroke_space = "g", "g"
    line_width = 1.0
    nums: list[float] = []

    path: list[list[tuple]] = []     # subpaths, in device space
    current: list[tuple] = []
    start_pt = None
    here = (0.0, 0.0)                # in user space, for curve control points

    content = doc.content_of(page)
    pos, size = 0, len(content)
    while pos < size:
        m = TOKEN.search(content, pos)
        if not m:
            break
        pos = m.end()
        kind = m.lastgroup
        if kind == "num":
            nums.append(float(m.group()))
            continue
        if kind in ("name", "punct", "comment"):
            continue
        if kind == "string":
            pos = _skip_string(content, pos)
            continue
        if kind == "hex":
            end = content.find(b">", pos)
            pos = size if end < 0 else end + 1
            continue

        op = m.group().decode("latin-1")

        if op == "BI":                       # an inline image: skip its data
            end = content.find(b"EI", pos)
            pos = size if end < 0 else end + 2
            nums = []
            continue

        def dev(x, y):
            return _apply(ctm, x, y)

        if op == "q":
            stack.append((ctm, fill_gray, stroke_gray, fill_space, stroke_space, line_width))
        elif op == "Q":
            if stack:
                (ctm, fill_gray, stroke_gray,
                 fill_space, stroke_space, line_width) = stack.pop()
        elif op == "cm" and len(nums) >= 6:
            ctm = _mul(tuple(nums[-6:]), ctm)
        elif op == "w" and nums:
            line_width = abs(nums[-1])
        elif op in ("g", "rg", "k"):
            fill_space, fill_gray = op, _gray_from(nums, op)
        elif op in ("G", "RG", "K"):
            stroke_space, stroke_gray = op.lower(), _gray_from(nums, op.lower())
        elif op in ("sc", "scn"):
            fill_gray = _gray_from(nums, {1: "g", 3: "rg", 4: "k"}.get(len(nums), "g"))
        elif op in ("SC", "SCN"):
            stroke_gray = _gray_from(nums, {1: "g", 3: "rg", 4: "k"}.get(len(nums), "g"))
        elif op == "m" and len(nums) >= 2:
            if len(current) > 1:
                path.append(current)
            here = (nums[-2], nums[-1])
            start_pt = here
            current = [dev(*here)]
        elif op == "l" and len(nums) >= 2:
            here = (nums[-2], nums[-1])
            current.append(dev(*here))
        elif op in ("c", "v", "y") and current:
            if op == "c" and len(nums) >= 6:
                p1, p2, p3 = (nums[-6], nums[-5]), (nums[-4], nums[-3]), (nums[-2], nums[-1])
            elif op == "v" and len(nums) >= 4:
                p1, p2, p3 = here, (nums[-4], nums[-3]), (nums[-2], nums[-1])
            elif len(nums) >= 4:
                p1 = (nums[-4], nums[-3])
                p2 = p3 = (nums[-2], nums[-1])
            else:
                nums = []
                continue
            _flatten(current, dev(*here), dev(*p1), dev(*p2), dev(*p3))
            here = p3
        elif op == "h":
            if current and start_pt is not None:
                current.append(dev(*start_pt))
                here = start_pt
        elif op == "re" and len(nums) >= 4:
            if len(current) > 1:
                path.append(current)
            x, y, rw, rh = nums[-4:]
            current = [dev(x, y), dev(x + rw, y), dev(x + rw, y + rh), dev(x, y + rh),
                       dev(x, y)]
            path.append(current)
            here = start_pt = (x, y)
            current = []
        elif op in PAINTS:
            if len(current) > 1:
                path.append(current)
            current = []
            if op in ("f", "F", "f*", "B", "B*", "b", "b*"):
                canvas.fill(path, fill_gray, op.endswith("*"))
            if op in ("S", "s", "B", "B*", "b", "b*"):
                _stroke(canvas, path, stroke_gray,
                        max(0.7, line_width * _scale_of(ctm)))
            path = []
        elif op in ("W", "W*"):
            pass          # clipping is not modelled; see the module docstring

        nums = []

    return canvas


def _flatten(out: list, p0, p1, p2, p3) -> None:
    """A cubic in device space, as line segments fine enough not to show."""
    span = (math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3))
    steps = max(2, min(24, int(span / 2.5) + 2))
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * p1[0]
                    + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1]
                    + 3 * u * t * t * p2[1] + t * t * t * p3[1]))


def _stroke(canvas: Canvas, subpaths, gray: int, width: float) -> None:
    """Each segment as a filled quad. Good enough for rules and boxes."""
    half = max(0.35, width / 2.0)
    for pts in subpaths:
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            dx, dy = x1 - x0, y1 - y0
            length = math.hypot(dx, dy)
            if length < 1e-9:
                continue
            nx, ny = -dy / length * half, dx / length * half
            canvas.fill([[(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                          (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]], gray, False)


def pages_as_png(doc: pdfread.Document, limit: int = MAX_PAGES,
                 scale: float = DEFAULT_SCALE) -> list[tuple[int, bytes]]:
    """Every page drawn, as (page number, PNG bytes)."""
    out = []
    for number, page in enumerate(doc.pages(), 1):
        if number > limit:
            break
        try:
            out.append((number, render_page(doc, page, scale).png()))
        except Exception:  # noqa: BLE001
            continue
    return out


def has_drawing(doc: pdfread.Document, page: dict) -> bool:
    """Whether this page has paths worth drawing.

    A page with no fills is either blank or built from something this renderer
    does not follow, and a blank PNG is worse than saying so: it looks like a
    document that was read and found empty.
    """
    content = doc.content_of(page)
    return bool(re.search(rb"(?m)(?:^|\s)(?:f|f\*|F|B|B\*|re|S)(?=\s|$)", content))
