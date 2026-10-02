"""Build the Kota Aerospace Architecture Master Blueprint: HTML → PDF, standalone SVGs, page PNGs."""
import asyncio
import inspect
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import diagrams as D  # noqa: E402
from layout import CSS, font_faces, page  # noqa: E402
from pages import PAGES  # noqa: E402

OUT = os.path.abspath(os.path.join(HERE, "..", "out"))
PDF = os.path.join(OUT, "KOTA_AEROSPACE_ARCHITECTURE_MASTER_BLUEPRINT.pdf")


def build_html():
    nums = {k: i + 1 for i, (k, *_rest) in enumerate(PAGES)}
    parts = []
    for i, (key, sec, fn, dark) in enumerate(PAGES):
        body = fn()
        if key == "cover":
            parts.append(f'<section class="page dark" id="cover">{body}</section>')
        else:
            parts.append(page(i + 1, sec, body, dark=dark, pid=key))
    html = "\n".join(parts)

    def rep(m):
        k = m.group(1)
        if k.endswith(":n"):
            return f"{nums[k[:-2]]:02d}"
        return f'<a href="#{k}">p.{nums[k]:02d}</a>'
    html = re.sub(r"@@([a-z0-9]+(?::n)?)@@", rep, html)
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Kota Aerospace — Architecture Master Blueprint</title>'
           f'<style>{font_faces(True)}\n{CSS}</style></head><body>{html}</body></html>')
    return doc, len(PAGES)


def export_svgs():
    os.makedirs(os.path.join(OUT, "svg"), exist_ok=True)
    names = [n for n, f in inspect.getmembers(D, inspect.isfunction) if re.match(r"^(d\d\d|x\d\d)", n)]
    for n in names:
        d = getattr(D, n)()
        with open(os.path.join(OUT, "svg", f"{n}.svg"), "w") as fh:
            fh.write(d.svg(standalone=True))
    return names


async def render(doc):
    from playwright.async_api import async_playwright
    html_path = os.path.join(OUT, "blueprint.html")
    with open(html_path, "w") as fh:
        fh.write(doc)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto("file://" + html_path)
        await pg.wait_for_timeout(800)
        await pg.evaluate("document.fonts.ready")
        overflow = await pg.evaluate("""() => [...document.querySelectorAll('.page .inner')].map((el, i) => {
            const over = el.scrollHeight - el.clientHeight; return over > 2 ? [el.parentElement.id, over] : null }).filter(Boolean)""")
        await pg.pdf(path=PDF, width="297mm", height="210mm", print_background=True, outline=True, tagged=True,
                     margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        await b.close()
    return overflow


def pngs(scale=1.4, only=None):
    import pypdfium2 as pdfium
    os.makedirs(os.path.join(OUT, "pages"), exist_ok=True)
    pdf = pdfium.PdfDocument(PDF)
    for i in range(len(pdf)):
        if only and (i + 1) not in only:
            continue
        img = pdf[i].render(scale=scale).to_pil()
        img.save(os.path.join(OUT, "pages", f"p{i+1:02d}.png"))
    return len(pdf)


if __name__ == "__main__":
    doc, n = build_html()
    names = export_svgs()
    over = asyncio.run(render(doc))
    count = pngs()
    print(f"pages={n} pdf_pages={count} svgs={len(names)} overflow={over}")
