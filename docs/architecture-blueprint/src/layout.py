"""HTML page shell, CSS and small building blocks for the publication."""
import base64
import os

from svg import C, FONTS, STATUS, icon

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.abspath(os.path.join(HERE, "..", "fonts"))

DOC = "KOTA AEROSPACE · ARCHITECTURE MASTER BLUEPRINT"
VERSION = "v1.0 · 1 Oct 2026"
EVIDENCE = "Evidence: Aerocomply @ 6bd38ce"


def font_faces(embed=True):
    out = []
    for _, (family, files) in FONTS.items():
        for w, fn in files.items():
            if embed:
                b64 = base64.b64encode(open(os.path.join(FONT_DIR, fn), "rb").read()).decode()
                src = f"url(data:font/woff2;base64,{b64}) format('woff2')"
            else:
                src = f"url('fonts/{fn}') format('woff2')"
            out.append(f"@font-face{{font-family:'{family}';font-weight:{w};font-style:normal;src:{src};}}")
    return "\n".join(out)


CSS = f"""
@page {{ size: 297mm 210mm; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #DDE3EA; }}
body {{ font-family: 'IBM Plex Sans', 'DejaVu Sans', sans-serif; color: {C['ink']}; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.page {{ width: 297mm; height: 210mm; position: relative; overflow: hidden; background: {C['paper']}; page-break-after: always; break-after: page; }}
.page.dark {{ background: {C['navy']}; color: #fff; }}
.inner {{ position: absolute; left: 13mm; right: 13mm; top: 19mm; bottom: 13mm; display: flex; flex-direction: column; }}
.rh {{ position: absolute; top: 7mm; left: 13mm; right: 13mm; display: flex; justify-content: space-between; align-items: center;
       font-family: 'IBM Plex Mono'; font-size: 7.4pt; letter-spacing: .12em; color: {C['slate']}; border-bottom: 0.6pt solid {C['line']}; padding-bottom: 2.2mm; }}
.dark .rh {{ color: #8FA6BF; border-color: #1E3D5C; }}
.rh .sec b {{ color: {C['amberd']}; font-weight: 500; margin-right: 6px; }}
.dark .rh .sec b {{ color: {C['amber']}; }}
.ft {{ position: absolute; bottom: 5.5mm; left: 13mm; right: 13mm; display: flex; justify-content: space-between; font-family: 'IBM Plex Mono';
       font-size: 6.8pt; letter-spacing: .08em; color: {C['slate2']}; }}
.ft .pn {{ color: {C['ink']}; font-weight: 500; }}
.dark .ft .pn {{ color: #fff; }}
h1, h2, h3 {{ font-family: 'Space Grotesk', sans-serif; margin: 0; letter-spacing: -0.01em; }}
h2 {{ font-size: 21pt; font-weight: 600; line-height: 1.08; }}
h2 .num {{ color: {C['teal']}; font-weight: 500; margin-right: 8px; }}
.dark h2 .num {{ color: {C['cyan']}; }}
h3 {{ font-size: 11.5pt; font-weight: 600; margin-bottom: 2mm; }}
.kicker {{ font-family: 'IBM Plex Mono'; font-size: 7.6pt; letter-spacing: .14em; text-transform: uppercase; color: {C['teal']}; margin-bottom: 1.6mm; }}
.dark .kicker {{ color: {C['cyan']}; }}
.purpose {{ font-size: 9.6pt; line-height: 1.42; color: #33475C; max-width: 205mm; margin-top: 2mm; }}
.dark .purpose {{ color: #B9CADB; }}
.titlerow {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 8mm; margin-bottom: 3.5mm; }}
.tag {{ font-family: 'IBM Plex Mono'; font-size: 7pt; letter-spacing: .1em; padding: 1.2mm 2.6mm; border-radius: 10px; border: 0.8pt solid; white-space: nowrap; }}
.tag.cur {{ color: {C['teal']}; border-color: {C['teal']}; }}
.tag.hyb {{ color: {C['blue']}; border-color: {C['blue']}; }}
.tag.tgt {{ color: {C['purple']}; border-color: {C['purple']}; }}
.dark .tag.hyb {{ color: #8FB7EE; border-color: #8FB7EE; }}
.fig {{ flex: 1; display: flex; align-items: center; justify-content: center; min-height: 0; }}
.fig svg {{ max-height: 100%; width: 100%; height: auto; display: block; }}
.figcap {{ font-size: 8pt; color: {C['slate']}; margin-top: 1.5mm; }}
p {{ margin: 0 0 2.2mm; font-size: 9.3pt; line-height: 1.45; }}
.small {{ font-size: 8.2pt; line-height: 1.4; }}
.cols {{ display: grid; gap: 6mm; align-items: start; }}
.c2 {{ grid-template-columns: 1fr 1fr; }} .c3 {{ grid-template-columns: 1fr 1fr 1fr; }} .c4 {{ grid-template-columns: repeat(4, 1fr); }}
.c12 {{ grid-template-columns: 1fr 2fr; }} .c21 {{ grid-template-columns: 2fr 1fr; }} .c31 {{ grid-template-columns: 3fr 1.15fr; }}
.card {{ background: #fff; border: 0.7pt solid {C['line']}; border-radius: 3mm; padding: 3.6mm 4mm; }}
.dark .card {{ background: #0D2B49; border-color: #1E4468; }}
.card.acc {{ border-top: 2.2pt solid {C['teal']}; }}
.card.amber {{ border-top: 2.2pt solid {C['amber']}; }}
.card.coral {{ border-top: 2.2pt solid {C['coral']}; }}
.card.purple {{ border-top: 2.2pt solid {C['purple']}; }}
.card.blue {{ border-top: 2.2pt solid {C['blue']}; }}
.card.cyan {{ border-top: 2.2pt solid {C['cyan']}; }}
table {{ border-collapse: collapse; width: 100%; font-family: 'IBM Plex Sans Condensed', sans-serif; font-size: 8.3pt; line-height: 1.32; }}
th {{ text-align: left; font-family: 'IBM Plex Mono'; font-weight: 500; font-size: 6.7pt; letter-spacing: .08em; text-transform: uppercase; color: {C['slate']};
      border-bottom: 1pt solid {C['ink']}; padding: 1.3mm 1.6mm; vertical-align: bottom; }}
td {{ border-bottom: 0.5pt solid {C['line']}; padding: 1.25mm 1.6mm; vertical-align: top; }}
td.mono, span.mono {{ font-family: 'IBM Plex Mono'; font-size: 7.1pt; color: #3A4A5C; }}
td b {{ font-weight: 600; }}
tr.zebra:nth-child(even) td {{ background: rgba(255,255,255,.65); }}
.st {{ display: inline-flex; align-items: center; gap: 3px; font-family: 'IBM Plex Mono'; font-size: 6.6pt; letter-spacing: .03em; padding: 0.4mm 1.8mm 0.4mm 1.2mm;
       border-radius: 8px; border: 0.7pt solid; white-space: nowrap; background: #fff; }}
.st svg {{ width: 8px; height: 8px; }}
.stat {{ background: #fff; border-radius: 3mm; padding: 3.2mm 4mm; border: 0.7pt solid {C['line']}; }}
.stat .v {{ font-family: 'Space Grotesk'; font-size: 22pt; font-weight: 600; line-height: 1; }}
.stat .l {{ font-size: 7.8pt; color: {C['slate']}; margin-top: 1.4mm; line-height: 1.3; }}
.dark .stat {{ background: #0D2B49; border-color: #1E4468; }} .dark .stat .l {{ color: #A9BDD3; }}
.callouts {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 2.4mm 6mm; }}
.co {{ display: grid; grid-template-columns: 7mm 1fr; gap: 2mm; align-items: start; font-size: 8.4pt; line-height: 1.38; }}
.co .n {{ width: 6mm; height: 6mm; border-radius: 50%; background: {C['amber']}; color: {C['navy']}; font: 700 8pt 'IBM Plex Sans'; display: flex; align-items: center; justify-content: center; }}
.co .n.cy {{ background: {C['cyan']}; }} .co .n.mi {{ background: {C['mint']}; }}
.co b {{ font-weight: 600; }}
.ref {{ font-family: 'IBM Plex Mono'; font-size: 7pt; color: {C['blue']}; text-decoration: none; }}
a {{ color: inherit; }}
.interp {{ display: grid; grid-template-columns: 34mm 1fr; gap: 4mm; border-top: 0.7pt solid {C['line']}; padding-top: 2.4mm; margin-top: 2mm; font-size: 8.4pt; line-height: 1.4; }}
.dark .interp {{ border-color: #1E3D5C; color: #C9D6E4; }}
.interp .k {{ font-family: 'IBM Plex Mono'; font-size: 7pt; letter-spacing: .1em; color: {C['slate']}; text-transform: uppercase; }}
.dark .interp .k {{ color: #8FA6BF; }}
ul.tight {{ margin: 0; padding-left: 4mm; font-size: 8.8pt; line-height: 1.45; }} ul.tight li {{ margin-bottom: 1mm; }}
.sev {{ font-family: 'IBM Plex Mono'; font-size: 6.6pt; padding: 0.4mm 1.6mm; border-radius: 6px; color: #fff; }}
.sev.High {{ background: {C['corald']}; }} .sev.Medium {{ background: {C['amberd']}; }} .sev.Low {{ background: {C['slate']}; }}
.heat td {{ text-align: center; font-family: 'IBM Plex Mono'; font-size: 7pt; padding: 1mm 0.6mm; }}
.heat th.rot {{ height: 26mm; white-space: nowrap; vertical-align: bottom; padding: 0 0 1mm; }}
.heat th.rot div {{ transform: rotate(-60deg); transform-origin: left bottom; width: 6mm; margin-left: 3.2mm; }}
.toc a {{ text-decoration: none; display: grid; grid-template-columns: 9mm 1fr 12mm; align-items: baseline; padding: 0.85mm 0; border-bottom: 0.5pt solid {C['line']}; font-size: 9.2pt; }}
.toc .tn {{ font-family: 'IBM Plex Mono'; font-size: 7.6pt; color: {C['teal']}; }}
.toc .tp {{ font-family: 'IBM Plex Mono'; font-size: 7.6pt; text-align: right; color: {C['slate']}; }}
.toc .part {{ font-family: 'IBM Plex Mono'; font-size: 7pt; letter-spacing: .14em; color: {C['amberd']}; margin: 2.6mm 0 0.6mm; }}
.fs72 table {{ font-size: 7.2pt; }} .fs76 table {{ font-size: 7.6pt; }} .fs72 td, .fs76 td {{ padding-top: 1mm; padding-bottom: 1mm; }}
.sr {{ position: absolute; left: 2mm; top: 2mm; font-size: 2px; color: #071A2E; margin: 0; }}
.quote {{ font-family: 'Space Grotesk'; font-size: 13pt; line-height: 1.3; font-weight: 500; }}
"""


def chip(status, label=None):
    st = STATUS[status]
    col = st["color"]
    ic = f'<svg viewBox="0 0 10 10">{icon(status, 5, 5, 4.2, col)}</svg>'
    return f'<span class="st" style="color:{col};border-color:{col}">{ic}{label or st["label"]}</span>'


def page(num, section, body, dark=False, pid=None, total="{TOTAL}"):
    sec = f'<span class="sec"><b>{section[0]}</b>{section[1]}</span>' if section else '<span></span>'
    return (f'<section class="page{" dark" if dark else ""}" id="{pid or f"p{num}"}">'
            f'<div class="rh"><span>{DOC}</span>{sec}</div>'
            f'<div class="inner">{body}</div>'
            f'<div class="ft"><span class="pn">{num:02d}</span><span>{VERSION} · {EVIDENCE}</span><span>Status vocabulary: VERIFIED · PARTIAL · DESIGNED · PROPOSED · EXTERNAL · VERIFY</span></div>'
            f'</section>')


def ctitle(num, text, kicker, purpose, tag=None, tagcls="hyb"):
    """Compact title for full-diagram pages."""
    t = f'<span class="tag {tagcls}">{tag}</span>' if tag else ""
    return (f'<div class="titlerow" style="margin-bottom:2mm;align-items:center"><div style="flex:0 0 auto"><div class="kicker">{kicker}</div>'
            f'<h2 style="font-size:17pt"><span class="num">{num} </span>{text}</h2></div>'
            f'<div class="purpose" style="flex:1;margin:0;font-size:8.8pt;max-width:none">{purpose}</div>{t}</div>')


def title(num, text, kicker, purpose, tag=None, tagcls="hyb"):
    t = f'<span class="tag {tagcls}">{tag}</span>' if tag else ""
    return (f'<div class="titlerow"><div><div class="kicker">{kicker}</div><h2>{f"<span class=num>{num} </span>" if num else ""}{text}</h2>'
            f'<div class="purpose">{purpose}</div></div>{t}</div>')


def table(headers, rows, widths=None, cls="zebra"):
    cg = ""
    if widths:
        cg = "<colgroup>" + "".join(f'<col style="width:{w}">' for w in widths) + "</colgroup>"
    h = "".join(f"<th>{x}</th>" for x in headers)
    body = "".join(f'<tr class="{cls}">' + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table>{cg}<thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>"
