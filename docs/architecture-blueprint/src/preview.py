"""Render a diagram SVG to PNG for visual inspection (uses the same fonts as the PDF)."""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.abspath(os.path.join(HERE, "..", "fonts"))


def font_css():
    from svg import FONTS
    out = []
    for _, (family, files) in FONTS.items():
        for w, fn in files.items():
            import base64
            b64 = base64.b64encode(open(os.path.join(FONT_DIR, fn), "rb").read()).decode()
            out.append(f"@font-face{{font-family:'{family}';font-weight:{w};src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    return "".join(out)


async def shot(svg: str, out: str, width=1400, bg="#F5F7FA"):
    html = f"<html><head><style>{font_css()} body{{margin:0;background:{bg}}} .w{{padding:20px}}</style></head><body><div class='w'>{svg}</div></body></html>"
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": width, "height": 800}, device_scale_factor=1.5)
        await pg.set_content(html)
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=out, full_page=True)
        await b.close()


def run(name):
    sys.path.insert(0, HERE)
    import diagrams
    fn = getattr(diagrams, name)
    d = fn()
    asyncio.run(shot(d.svg(), f"/home/claude/bp/out/prev_{name}.png"))
    print("ok", name)


if __name__ == "__main__":
    for n in sys.argv[1:]:
        run(n)
