# Kota Aerospace — Architecture Master Blueprint (sources)

| File | Purpose |
|---|---|
| `KOTA_AEROSPACE_ARCHITECTURE_MASTER_BLUEPRINT.pdf` | The publication (42 pages, A4 landscape) |
| `ARCHITECTURE_SOURCE_OF_TRUTH.md` | Maintainable architecture reference — generated from `src/model.py` |
| `KOTA_AEROSPACE_ARCHITECTURE_DOCUMENT_QA.md` | Audit and quality report |
| `src/model.py` | **Single source** for modules, statuses, findings, ADRs, roadmap, glossary |
| `src/diagrams.py` + `src/svg.py` | Every diagram, as code (Python → SVG); one visual language |
| `src/pages.py`, `src/layout.py` | Page content and layout |
| `svg/*.svg` | Standalone vector diagrams (open in a browser, Figma, Illustrator, Inkscape) |
| `mermaid/*.mmd` | Mermaid versions of the flows suited to text diagrams |
| `fonts/` | IBM Plex Sans / Condensed / Mono and Space Grotesk (SIL Open Font License) |

## Regenerate

```bash
pip install playwright fonttools brotli pypdfium2 pillow
python -m playwright install chromium   # skip if Chromium is already available
cd docs/architecture-blueprint
python src/build.py        # PDF → out/, standalone SVGs, page PNGs
python src/gen_docs.py 42  # source-of-truth + QA markdown + mermaid
```

`build.py` writes to `out/` beside `src/`; copy results up a level when publishing a new edition.

## Editing rules

1. Change facts in `src/model.py` only — the PDF and the Markdown reference both read it.
2. A status may be `VERIFIED` only with code + migration + passing test as evidence.
3. Bump `VERSION` in `src/layout.py` and add a change-history row in `pages.py::p_gloss`.
