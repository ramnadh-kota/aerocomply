"""Kota blueprint — tiny SVG diagram DSL.

Every diagram in the publication is produced from Python with this module so the
visual language (colours, status encoding, arrow semantics) is defined once.
Text is measured with the real font metrics (fontTools) so wrapping is exact.
"""
from __future__ import annotations

import html
import math
import os
from functools import lru_cache

from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "..", "fonts")

# ------------------------------------------------------------------ palette
C = {
    "navy": "#071A2E", "deep": "#0D2B49", "deep2": "#123A60", "blue": "#2475D0", "cyan": "#35C2D0",
    "teal": "#238A75", "mint": "#63D3B0", "amber": "#F2B84B", "amberd": "#B7791F", "coral": "#F07861",
    "corald": "#C4513C", "purple": "#7B61D9", "purpled": "#5B43B5", "ink": "#0B1B2B", "slate": "#5B6B7F",
    "slate2": "#8A99AB", "line": "#D3DCE6", "paper": "#F5F7FA", "white": "#FFFFFF", "mist": "#EAF0F6",
}

# semantic kinds -> (accent, light tint, dark tint)
KIND = {
    "infra":   (C["blue"],   "#EAF2FC", "#10345A"),
    "data":    (C["cyan"],   "#E6F8FA", "#0E3A4A"),
    "domain":  (C["teal"],   "#E7F4F1", "#0F3A3A"),
    "decision": (C["amber"], "#FDF4E1", "#3A3320"),
    "ai":      (C["purple"], "#EFEBFB", "#2A2550"),
    "risk":    (C["coral"],  "#FDECE8", "#46262A"),
    "ext":     (C["slate"],  "#EEF1F5", "#1C3047"),
    "user":    (C["navy"],   "#E8EDF3", "#1B3553"),
    "gov":     (C["mint"],   "#E9F9F3", "#123F3A"),
}

# status vocabulary used everywhere in the publication
STATUS = {
    "VERIFIED": {"label": "VERIFIED", "glyph": "✓", "color": C["teal"], "dash": None,
                 "long": "Verified implemented — code, migration and passing tests found in the repository"},
    "PARTIAL": {"label": "PARTIAL", "glyph": "◐", "color": C["amberd"], "dash": None,
                "long": "Partially implemented — works with documented limits or missing pieces"},
    "DESIGNED": {"label": "DESIGNED", "glyph": "◇", "color": C["blue"], "dash": "7 4",
                 "long": "Designed, not implemented — an ADR or spec exists; no code"},
    "PROPOSED": {"label": "PROPOSED", "glyph": "+", "color": C["purple"], "dash": "2 4",
                 "long": "Proposed — recommended by this blueprint; not yet decided"},
    "EXTERNAL": {"label": "EXTERNAL", "glyph": "⊘", "color": C["corald"], "dash": "10 3 2 3",
                 "long": "Blocked / external — needs hardware, credentials, provider or field validation"},
    "VERIFY": {"label": "VERIFY", "glyph": "?", "color": C["slate"], "dash": "1 3",
               "long": "Needs verification — claimed in documents, not confirmed in code during this audit"},
    "SUPERSEDED": {"label": "SUPERSEDED", "glyph": "✕", "color": C["slate2"], "dash": "4 4",
                   "long": "Superseded / deprecated — replaced by a later decision; kept for history"},
}

# arrow semantics
ARROW = {
    "sync":   {"color": C["ink"], "dark": "#DCE6F2", "width": 1.6, "dash": None, "head": "solid", "label": "Synchronous request / call"},
    "async":  {"color": C["cyan"], "dark": C["cyan"], "width": 1.6, "dash": "6 4", "head": "solid", "label": "Asynchronous job / event"},
    "data":   {"color": C["blue"], "dark": "#6FA8EA", "width": 2.2, "dash": None, "head": "open", "label": "Data persistence (write / read)"},
    "obs":    {"color": C["slate2"], "dark": "#7F92A8", "width": 1.2, "dash": "1.5 3", "head": "open", "label": "Observability (logs, metrics, health)"},
    "human":  {"color": C["amberd"], "dark": C["amber"], "width": 2.0, "dash": None, "head": "solid", "label": "Human review / approval step"},
    "feedback": {"color": C["teal"], "dark": C["mint"], "width": 1.6, "dash": "10 4", "head": "solid", "label": "Feedback / outcome loop"},
    "prohibited": {"color": C["coral"], "dark": C["coral"], "width": 1.6, "dash": "4 3", "head": "cross", "label": "Prohibited dependency"},
    "proposed": {"color": C["purple"], "dark": "#A996F0", "width": 1.6, "dash": "2 4", "head": "solid", "label": "Proposed path (not built)"},
}

FONTS = {
    "cond": ("IBM Plex Sans Condensed", {400: "ibm-plex-sans-condensed-latin-400-normal.woff2", 500: "ibm-plex-sans-condensed-latin-500-normal.woff2",
                                         600: "ibm-plex-sans-condensed-latin-600-normal.woff2", 700: "ibm-plex-sans-condensed-latin-700-normal.woff2"}),
    "sans": ("IBM Plex Sans", {300: "ibm-plex-sans-latin-300-normal.woff2", 400: "ibm-plex-sans-latin-400-normal.woff2", 500: "ibm-plex-sans-latin-500-normal.woff2",
                               600: "ibm-plex-sans-latin-600-normal.woff2", 700: "ibm-plex-sans-latin-700-normal.woff2"}),
    "mono": ("IBM Plex Mono", {400: "ibm-plex-mono-latin-400-normal.woff2", 500: "ibm-plex-mono-latin-500-normal.woff2"}),
    "disp": ("Space Grotesk", {400: "space-grotesk-latin-400-normal.woff2", 500: "space-grotesk-latin-500-normal.woff2",
                               600: "space-grotesk-latin-600-normal.woff2", 700: "space-grotesk-latin-700-normal.woff2"}),
}


@lru_cache(maxsize=None)
def _metrics(face: str, weight: int):
    fam, files = FONTS[face]
    w = weight if weight in files else min(files, key=lambda k: abs(k - weight))
    f = TTFont(os.path.join(FONT_DIR, files[w]))
    cmap = f.getBestCmap()
    hmtx = f["hmtx"].metrics
    upm = f["head"].unitsPerEm
    default = hmtx.get(cmap.get(ord("n"), ".notdef"), (500, 0))[0]
    return cmap, hmtx, upm, default


def text_width(s: str, size: float, face: str = "cond", weight: int = 400) -> float:
    cmap, hmtx, upm, default = _metrics(face, weight)
    total = 0
    for ch in s:
        g = cmap.get(ord(ch))
        total += hmtx[g][0] if g in hmtx else default
    return total * size / upm


def wrap(s: str, width: float, size: float, face: str = "cond", weight: int = 400) -> list[str]:
    out: list[str] = []
    for para in str(s).split("\n"):
        words = para.split(" ")
        line = ""
        for w in words:
            cand = (line + " " + w).strip()
            if text_width(cand, size, face, weight) <= width * 0.97 or not line:
                line = cand
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


def fit(s: str, width: float, size: float, face: str = "mono", weight: int = 400) -> str:
    """Truncate a single line with an ellipsis so it fits the width."""
    if text_width(s, size, face, weight) <= width:
        return s
    while s and text_width(s + "…", size, face, weight) > width:
        s = s[:-1]
    return s + "…"


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def fam(face: str) -> str:
    return f"'{FONTS[face][0]}', 'DejaVu Sans'"


def icon(status, cx, cy, r, col):
    """Status glyph drawn as vector shapes (no font dependency)."""
    sw = max(1.0, r * 0.32)
    if status == "VERIFIED":
        return (f'<path d="M{cx-r*0.85:.2f},{cy:.2f} L{cx-r*0.25:.2f},{cy+r*0.6:.2f} L{cx+r*0.9:.2f},{cy-r*0.65:.2f}" '
                f'fill="none" stroke="{col}" stroke-width="{sw:.2f}" stroke-linecap="round" stroke-linejoin="round"/>')
    if status == "PARTIAL":
        return (f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r*0.85:.2f}" fill="none" stroke="{col}" stroke-width="{sw*0.7:.2f}"/>'
                f'<path d="M{cx:.2f},{cy-r*0.85:.2f} A{r*0.85:.2f},{r*0.85:.2f} 0 0 1 {cx:.2f},{cy+r*0.85:.2f} Z" fill="{col}"/>')
    if status == "DESIGNED":
        return (f'<path d="M{cx:.2f},{cy-r:.2f} L{cx+r:.2f},{cy:.2f} L{cx:.2f},{cy+r:.2f} L{cx-r:.2f},{cy:.2f} Z" fill="none" '
                f'stroke="{col}" stroke-width="{sw*0.75:.2f}"/>')
    if status == "PROPOSED":
        return (f'<path d="M{cx-r*0.85:.2f},{cy:.2f} H{cx+r*0.85:.2f} M{cx:.2f},{cy-r*0.85:.2f} V{cy+r*0.85:.2f}" '
                f'stroke="{col}" stroke-width="{sw:.2f}" stroke-linecap="round"/>')
    if status == "EXTERNAL":
        return (f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r*0.85:.2f}" fill="none" stroke="{col}" stroke-width="{sw*0.75:.2f}"/>'
                f'<path d="M{cx-r*0.6:.2f},{cy+r*0.6:.2f} L{cx+r*0.6:.2f},{cy-r*0.6:.2f}" stroke="{col}" stroke-width="{sw*0.75:.2f}"/>')
    if status == "VERIFY":
        return (f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r*0.85:.2f}" fill="none" stroke="{col}" stroke-width="{sw*0.7:.2f}" stroke-dasharray="1.2 1.2"/>'
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r*0.28:.2f}" fill="{col}"/>')
    return (f'<path d="M{cx-r*0.7:.2f},{cy-r*0.7:.2f} L{cx+r*0.7:.2f},{cy+r*0.7:.2f} M{cx+r*0.7:.2f},{cy-r*0.7:.2f} '
            f'L{cx-r*0.7:.2f},{cy+r*0.7:.2f}" stroke="{col}" stroke-width="{sw:.2f}" stroke-linecap="round"/>')


class Diagram:
    def __init__(self, w: int, h: int, dark: bool = False, bg: str | None = None, title: str = ""):
        self.w, self.h, self.dark = w, h, dark
        self.bg = bg if bg is not None else (C["navy"] if dark else "none")
        self.title = title
        self.el: list[str] = []
        self.top: list[str] = []  # painted last (labels over arrows)

    # ---------------------------------------------------------- primitives
    def raw(self, s: str, top: bool = False):
        (self.top if top else self.el).append(s)

    def text(self, x, y, s, size=12, weight=400, color=None, anchor="start", face="cond", top=False,
             italic=False, ls=None, opacity=None):
        color = color or (C["white"] if self.dark else C["ink"])
        extra = ' font-style="italic"' if italic else ""
        if ls is not None:
            extra += f' letter-spacing="{ls}"'
        if opacity is not None:
            extra += f' opacity="{opacity}"'
        self.raw(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{fam(face)}" font-size="{size}" font-weight="{weight}" '
                 f'fill="{color}" text-anchor="{anchor}"{extra}>{esc(s)}</text>', top)

    def mtext(self, x, y, s, width, size=12, weight=400, color=None, anchor="start", face="cond", lh=1.25,
              top=False, max_lines=None):
        lines = wrap(s, width, size, face, weight)
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip(".,;") + "…"
        for i, ln in enumerate(lines):
            self.text(x, y + i * size * lh, ln, size, weight, color, anchor, face, top)
        return len(lines) * size * lh

    def rect(self, x, y, w, h, fill="none", stroke="none", sw=1, rx=6, dash=None, opacity=None, top=False):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o = f' opacity="{opacity}"' if opacity is not None else ""
        self.raw(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" '
                 f'stroke="{stroke}" stroke-width="{sw}"{d}{o}/>', top)

    def circle(self, cx, cy, r, fill="none", stroke="none", sw=1, dash=None, top=False, opacity=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o = f' opacity="{opacity}"' if opacity is not None else ""
        self.raw(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}{o}/>', top)

    def line(self, x1, y1, x2, y2, stroke=None, sw=1, dash=None, top=False, opacity=None):
        stroke = stroke or C["line"]
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o = f' opacity="{opacity}"' if opacity is not None else ""
        self.raw(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{sw}"{d}{o}/>', top)

    # ---------------------------------------------------------- semantic pieces
    def badge(self, x, y, status, anchor="end", size=8.5, top=True, solid=False):
        st = STATUS[status]
        label = st['label']
        tw = text_width(label, size, "mono", 500) + size + 2
        w = tw + 10
        h = size + 7
        bx = x - w if anchor == "end" else (x - w / 2 if anchor == "middle" else x)
        if solid:
            fill, tc = st["color"], C["white"]
        else:
            fill = (C["navy"] if self.dark else C["white"])
            tc = st["color"] if not self.dark else (C["mint"] if status == "VERIFIED" else (C["amber"] if status == "PARTIAL" else ("#9DB4CC" if status in ("VERIFY", "SUPERSEDED") else ("#8FB7EE" if status == "DESIGNED" else ("#B9A8F5" if status == "PROPOSED" else C["coral"])))))
        stroke = tc
        self.rect(bx, y, w, h, fill=fill, stroke=stroke, sw=0.9, rx=h / 2, top=top)
        gx, gy, gr = bx + 5 + size / 2, y + h / 2, size * 0.42
        self.raw(icon(status, gx, gy, gr, tc), top)
        self.text(bx + size + 7 + (w - size - 12) / 2, y + h - 4.6, label, size, 500, tc, "middle", "mono", top)
        return w

    def box(self, x, y, w, h, title, sub=None, kind="domain", status=None, note=None, tsize=12.5, ssize=8.6,
            center=False, fill=None, accent_side="left", rx=7, nsize=9.5, title_color=None, sw=1.2):
        acc, light, darkt = KIND[kind]
        fill = fill or (darkt if self.dark else C["white"])
        st = STATUS.get(status) if status else None
        dash = st["dash"] if st else None
        stroke = acc if (st is None or status in ("VERIFIED", "PARTIAL")) else st["color"]
        if self.dark and st and status not in ("VERIFIED", "PARTIAL"):
            stroke = {"DESIGNED": "#8FB7EE", "PROPOSED": "#B9A8F5", "EXTERNAL": C["coral"], "VERIFY": "#9DB4CC", "SUPERSEDED": "#71839A"}[status]
        self.rect(x, y, w, h, fill=fill, stroke=stroke, sw=sw, rx=rx, dash=dash)
        if accent_side == "left":
            self.raw(f'<path d="M{x+0.6:.1f},{y+rx:.1f} Q{x+0.6:.1f},{y+0.6:.1f} {x+rx:.1f},{y+0.6:.1f} L{x+rx:.1f},{y+h-0.6:.1f} '
                     f'Q{x+0.6:.1f},{y+h-0.6:.1f} {x+0.6:.1f},{y+h-rx:.1f} Z" fill="{acc}"/>')
            self.rect(x + 0.6, y + 0.6, 4.2, h - 1.2, fill=acc, rx=1.5)
        elif accent_side == "top":
            self.rect(x + 0.6, y + 0.6, w - 1.2, 4, fill=acc, rx=2)
        tc = title_color or (C["white"] if self.dark else C["ink"])
        pad = 12 if accent_side == "left" else 9
        bw = 0
        if status:
            bw = text_width(STATUS[status]['label'], 8, "mono", 500) + 8 + 2 + 14
        avail = w - pad - 8 - (bw if not center else 0)
        cy = y + 8 + tsize
        if center:
            lines = wrap(title, w - 16, tsize, "cond", 600)
            total = len(lines) * tsize * 1.15 + ((len(wrap(sub, w - 16, ssize, "mono")) * ssize * 1.3 + 3) if sub else 0)
            cy = y + (h - total) / 2 + tsize * 0.88
            for i, ln in enumerate(lines):
                self.text(x + w / 2, cy + i * tsize * 1.15, ln, tsize, 600, tc, "middle")
            yy = cy + len(lines) * tsize * 1.15 - tsize * 0.15
            if sub:
                for i, ln in enumerate(wrap(sub, w - 16, ssize, "mono")):
                    self.text(x + w / 2, yy + 3 + i * ssize * 1.3, ln, ssize, 400, C["slate2"] if self.dark else C["slate"], "middle", "mono")
            if status:
                self.badge(x + w / 2, y + h - 6 - 15.5, status, "middle", 8)
            return
        lines = wrap(title, avail, tsize, "cond", 600)
        badge_bottom = False
        if status and any(text_width(l, tsize, "cond", 600) > avail for l in lines):
            badge_bottom = True
            lines = wrap(title, w - pad - 8, tsize, "cond", 600)
        for i, ln in enumerate(lines):
            self.text(x + pad, cy + i * tsize * 1.15, ln, tsize, 600, tc)
        yy = cy + (len(lines) - 1) * tsize * 1.15 + 4
        if sub:
            sl = [fit(t, w - pad - 8, ssize) for t in wrap(sub, w - pad - 8, ssize, "mono")]
            for i, ln in enumerate(sl):
                self.text(x + pad, yy + ssize + 2 + i * ssize * 1.3, ln, ssize, 400, C["slate2"] if self.dark else C["slate"], "start", "mono")
            yy += len(sl) * ssize * 1.3 + 3
        if note:
            nl = wrap(note, w - pad - 8, nsize, "cond")
            room = int(max(0, (y + h - 6 - (yy + 4)) // (nsize * 1.28)))
            if len(nl) > room:
                nl = nl[:room]
                if nl:
                    nl[-1] = nl[-1].rstrip(".,;") + "…"
            for i, ln in enumerate(nl):
                self.text(x + pad, yy + 4 + nsize + i * nsize * 1.28, ln, nsize, 400, "#C9D6E4" if self.dark else "#3A4A5C")
        if status:
            if badge_bottom:
                self.badge(x + w - 6, y + h - 21, status, "end", 8)
            else:
                self.badge(x + w - 6, y + 6, status, "end", 8)

    def sicon(self, cx, cy, status, r=6.5, top=True):
        st = STATUS[status]
        col = st["color"]
        if self.dark:
            col = {"VERIFIED": C["mint"], "PARTIAL": C["amber"], "DESIGNED": "#8FB7EE", "PROPOSED": "#B9A8F5",
                   "EXTERNAL": C["coral"], "VERIFY": "#9DB4CC", "SUPERSEDED": "#71839A"}[status]
        self.circle(cx, cy, r, fill=(C["navy"] if self.dark else C["white"]), stroke=col, sw=1, top=top)
        self.raw(icon(status, cx, cy, r * 0.62, col), top)

    def chip(self, x, y, w, h, title, sub=None, kind="domain", status=None, tsize=10.5, ssize=7.6):
        """Compact component chip: title, optional mono sub-line, status icon."""
        acc, light, darkt = KIND[kind]
        st = STATUS.get(status) if status else None
        dash = st["dash"] if st else None
        fill = darkt if self.dark else C["white"]
        stroke = acc if (not st or status in ("VERIFIED", "PARTIAL")) else st["color"]
        if status == "SUPERSEDED":
            fill = "#0E2236" if self.dark else "#F1F3F6"
        self.rect(x, y, w, h, fill=fill, stroke=stroke, sw=1, rx=5, dash=dash)
        self.rect(x + 0.5, y + 0.5, 3, h - 1, fill=acc, rx=1.5)
        tc = (C["white"] if self.dark else C["ink"]) if status != "SUPERSEDED" else C["slate2"]
        lines = wrap(title, w - 26, tsize, "cond", 600)[:2]
        ty = y + (h - (len(lines) * tsize * 1.1 + ((ssize + 3) if sub else 0))) / 2 + tsize * 0.85
        for i, ln in enumerate(lines):
            self.text(x + 9, ty + i * tsize * 1.1, ln, tsize, 600, tc)
        if sub:
            sl = fit(wrap(sub, w - 14, ssize, "mono")[0], w - 14, ssize)
            self.text(x + 9, ty + len(lines) * tsize * 1.1 + 1.5, sl, ssize, 400, C["slate2"] if self.dark else C["slate"], face="mono")
        if status:
            self.sicon(x + w - 9, y + 9, status, 5.6)

    def zone(self, x, y, w, h, label, kind="ext", dash="5 4", fill=None, label_pos="tl", sw=1.1, lsize=9, rx=10,
             label_color=None, tag=None):
        acc = KIND[kind][0]
        if fill is None:
            fill = ("#0B2238" if self.dark else KIND[kind][1])
        self.rect(x, y, w, h, fill=fill, stroke=acc, sw=sw, rx=rx, dash=dash)
        lc = label_color or (acc if not self.dark else "#A9BDD3")
        tw = text_width(label.upper(), lsize, "mono", 500) + 1.2 * len(label)
        if label_pos == "tl":
            self.rect(x + 12, y - 7, tw + 14, 14, fill=(C["navy"] if self.dark else C["white"]), stroke=acc, sw=0.8, rx=7)
            self.text(x + 19, y + 3.2, label.upper(), lsize, 500, lc, "start", "mono", ls=1.2)
        elif label_pos == "inside":
            self.text(x + 12, y + 16, label.upper(), lsize, 500, lc, "start", "mono", ls=1.2)
        if tag:
            self.badge(x + w - 10, y - 7.5, tag, "end", 8)

    def num(self, cx, cy, n, r=10, color=None, top=True):
        color = color or C["amber"]
        self.circle(cx, cy, r, fill=color, stroke=(C["navy"] if self.dark else C["white"]), sw=1.6, top=top)
        self.text(cx, cy + r * 0.38, str(n), r * 1.05, 700, C["navy"], "middle", "sans", top)

    def pill(self, x, y, s, size=9, fill=None, color=None, stroke=None, anchor="middle", face="cond", weight=500, top=True, pad=6):
        fill = fill or (C["navy"] if self.dark else C["white"])
        color = color or (C["white"] if self.dark else C["ink"])
        tw = text_width(s, size, face, weight)
        w = tw + pad * 2
        h = size + 7
        bx = x - w / 2 if anchor == "middle" else (x - w if anchor == "end" else x)
        self.rect(bx, y - h / 2, w, h, fill=fill, stroke=stroke or "none", sw=0.8, rx=h / 2, top=top)
        self.text(bx + w / 2, y + size * 0.36, s, size, weight, color, "middle", face, top)
        return w

    def arrow(self, pts, kind="sync", label=None, lpos=None, lsize=8.6, both=False, r=8, lseg=None, label_fill=None,
              label_color=None, width=None):
        a = ARROW[kind]
        col = a["dark"] if self.dark else a["color"]
        sw = width or a["width"]
        d = f' stroke-dasharray="{a["dash"]}"' if a["dash"] else ""
        # rounded orthogonal path
        path = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
        for i in range(1, len(pts) - 1):
            (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
            l1 = math.hypot(x1 - x0, y1 - y0) or 1
            l2 = math.hypot(x2 - x1, y2 - y1) or 1
            rr = min(r, l1 / 2, l2 / 2)
            ax, ay = x1 - (x1 - x0) / l1 * rr, y1 - (y1 - y0) / l1 * rr
            bx, by = x1 + (x2 - x1) / l2 * rr, y1 + (y2 - y1) / l2 * rr
            path += f" L{ax:.1f},{ay:.1f} Q{x1:.1f},{y1:.1f} {bx:.1f},{by:.1f}"
        path += f" L{pts[-1][0]:.1f},{pts[-1][1]:.1f}"
        mid = f"{kind}{'D' if self.dark else 'L'}"
        ms = f' marker-start="url(#s-{mid})"' if both else ""
        self.raw(f'<path d="{path}" fill="none" stroke="{col}" stroke-width="{sw}"{d} stroke-linecap="round" '
                 f'marker-end="url(#e-{mid})"{ms}/>')
        if label:
            if lpos is None:
                segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
                if lseg is None:
                    lseg = max(range(len(segs)), key=lambda i: math.hypot(segs[i][1][0] - segs[i][0][0], segs[i][1][1] - segs[i][0][1]))
                (p, q) = segs[lseg]
                lpos = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            lf = label_fill or (C["navy"] if self.dark else C["white"])
            lc = label_color or col
            if kind == "sync" and not self.dark:
                lc = label_color or C["ink"]
            self.pill(lpos[0], lpos[1], label, lsize, lf, lc, stroke=col, face="cond", weight=500)

    # ---------------------------------------------------------- legends
    def status_legend(self, x, y, keys=None, cols=1, colw=150, size=8.2, title="STATUS"):
        keys = keys or ["VERIFIED", "PARTIAL", "DESIGNED", "PROPOSED", "EXTERNAL", "VERIFY"]
        self.text(x, y, title, 8, 500, C["slate2"] if self.dark else C["slate"], face="mono", ls=1.2)
        for i, k in enumerate(keys):
            cx = x + (i % cols) * colw
            cy = y + 8 + (i // cols) * 18
            self.badge(cx, cy, k, "start", size)

    def arrow_legend(self, x, y, keys, cols=1, colw=170, title="CONNECTORS", lab=None):
        self.text(x, y, title, 8, 500, C["slate2"] if self.dark else C["slate"], face="mono", ls=1.2)
        for i, k in enumerate(keys):
            cx = x + (i % cols) * colw
            cy = y + 14 + (i // cols) * 16
            self.arrow([(cx, cy), (cx + 30, cy)], k)
            self.text(cx + 38, cy + 3.2, (lab or {}).get(k, ARROW[k]["label"]), 8.6, 400, "#C9D6E4" if self.dark else C["slate"])

    # ---------------------------------------------------------- output
    def defs(self) -> str:
        out = []
        for k, a in ARROW.items():
            for dark in (False, True):
                col = a["dark"] if dark else a["color"]
                mid = f"{k}{'D' if dark else 'L'}"
                if a["head"] == "solid":
                    shape = f'<path d="M0,0 L10,5 L0,10 L2.5,5 Z" fill="{col}"/>'
                    shape_s = f'<path d="M10,0 L0,5 L10,10 L7.5,5 Z" fill="{col}"/>'
                elif a["head"] == "open":
                    shape = f'<path d="M1,1 L9,5 L1,9" fill="none" stroke="{col}" stroke-width="1.6"/>'
                    shape_s = f'<path d="M9,1 L1,5 L9,9" fill="none" stroke="{col}" stroke-width="1.6"/>'
                else:
                    shape = f'<path d="M1,1 L9,9 M9,1 L1,9" stroke="{col}" stroke-width="1.8"/>'
                    shape_s = shape
                out.append(f'<marker id="e-{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                           f'orient="auto" markerUnits="userSpaceOnUse">{shape}</marker>')
                out.append(f'<marker id="s-{mid}" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" '
                           f'orient="auto" markerUnits="userSpaceOnUse">{shape_s}</marker>')
        out.append('<pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
                   f'<line x1="0" y1="0" x2="0" y2="6" stroke="{C["coral"]}" stroke-width="1" opacity="0.35"/></pattern>')
        out.append('<pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">'
                   '<path d="M24,0 L0,0 0,24" fill="none" stroke="#1A3A5C" stroke-width="0.5" opacity="0.55"/></pattern>')
        return "<defs>" + "".join(out) + "</defs>"

    def svg(self, standalone: bool = False, crop: int = 0, cropb: int = 0) -> str:
        bg = ""
        if self.bg != "none":
            bg = f'<rect x="0" y="0" width="{self.w}" height="{self.h}" fill="{self.bg}"/>'
            if self.dark:
                bg += f'<rect x="0" y="0" width="{self.w}" height="{self.h}" fill="url(#grid)"/>'
        ns = 'xmlns="http://www.w3.org/2000/svg" ' if True else ""
        style = ""
        if standalone:
            faces = []
            for key, (family, files) in FONTS.items():
                for wgt, fn in files.items():
                    faces.append(f"@font-face{{font-family:'{family}';font-weight:{wgt};src:url('../fonts/{fn}') format('woff2');}}")
            style = "<style>" + "".join(faces) + "</style>"
        t = f"<title>{esc(self.title)}</title>" if self.title else ""
        return (f'<svg {ns}viewBox="0 {crop} {self.w} {self.h - crop - cropb}" width="100%" role="img" aria-label="{esc(self.title)}">{t}{style}'
                f'{self.defs()}{bg}{"".join(self.el)}{"".join(self.top)}</svg>')
