# samples/ — Document Corpus

This directory contains the sample documents used to exercise all three ingestion
branches of the Document Data Platform:
**text-native PDFs**, **scanned (image-only) PDFs**, and **messy CSVs**.

All files are **programmatically generated** — no third-party content, no
licensing concerns.

---

## Generation

Run from the project root:

```bash
.venv\Scripts\python samples\generate_samples.py   # Windows
# or
.venv/bin/python samples/generate_samples.py        # macOS / Linux
```

The script produces every file listed below and then self-verifies that:
* Text-native PDFs have `chars > 0` (PyMuPDF extraction succeeds).
* Scanned PDFs have `chars == 0` (truly image-only — naive extraction yields nothing).

---

## File Inventory

### Text-native PDFs (5 files)

| File | Content | Generation method |
|---|---|---|
| `text_financial_report.pdf` | Acme Corp Q3 2024 quarterly financial report — revenue table, executive summary, outlook | `reportlab` — `SimpleDocTemplate` with `Table`, `Paragraph`, `HRFlowable` |
| `text_research_summary.pdf` | Academic public-health paper: urban PM2.5 vs respiratory ED visits | `reportlab` — multi-section layout with abstract box |
| `text_onboarding_handbook.pdf` | HR employee onboarding handbook: first-week checklist, policies, benefits table | `reportlab` — mixed list + table layout |
| `text_incident_report.pdf` | Post-incident review: 47-min PostgreSQL P1 outage with timeline & RCA | `reportlab` — timeline table, code-style block |
| `text_supply_chain_audit.pdf` | Supplier compliance audit checklist: 10 items, PASS/WARN/FAIL colour coding | `reportlab` — colour-coded table |

All five PDFs have a full embedded text layer. PyMuPDF `page.get_text()` returns
≥1 000 characters per document.

---

### Scanned (image-only) PDFs (4 files)

| File | Source document | Degradation applied |
|---|---|---|
| `scanned_financial_report.pdf` | `text_financial_report.pdf` | rotation +1.2°, noise σ=15, greyscale |
| `scanned_onboarding_handbook.pdf` | `text_onboarding_handbook.pdf` | rotation −0.7°, noise σ=18, greyscale |
| `scanned_incident_report.pdf` | `text_incident_report.pdf` | rotation +0.4°, noise σ=20, greyscale |
| `scanned_supply_chain_audit.pdf` | `text_supply_chain_audit.pdf` | rotation −1.1°, noise σ=12, greyscale |

**Generation pipeline for each scanned PDF:**

1. **Rasterise** — PyMuPDF renders the source text PDF page to a PIL RGB image at 150 DPI.
2. **Degrade** — Pillow applies:
   - Brightness gradient (uneven scanner lamp simulation)
   - Gaussian pixel noise (`numpy`, σ configurable per file)
   - `GaussianBlur` (radius 0.7 — slight platen defocus)
   - Slight rotation with white fill (paper mis-feed)
3. **Greyscale conversion** — `img.convert("L").convert("RGB")` — mirrors a typical
   flatbed scanner output and strips any remaining colour information.
4. **Save as image PDF** — `Pillow.Image.save(..., format="PDF")` writes a PDF whose
   pages contain only an embedded raster image with **no text layer**.

**Verification:** PyMuPDF `page.get_text("text")` returns `""` (0 chars) for every
page of every scanned PDF. This confirms they are genuine image-only files that will
force the OCR branch of the pipeline.

---

### Messy CSVs (3 files)

| File | Rows (excl. header) | Deliberate data-quality flaws |
|---|---|---|
| `csv_customer_orders.csv` | 17 | 2 exact duplicate rows (ORD-1001, ORD-1002); missing `quantity`, `price`, `name`, `region`; mixed date formats (`YYYY-MM-DD`, `YYYY/MM/DD`, `DD-MM-YYYY`, `DD/MM/YYYY`); price with `$` prefix; non-numeric `"N/A"` in numeric column; inconsistent `status` casing (`completed` / `Completed` / `SHIPPED`) |
| `csv_pipeline_runs.csv` | 16 | 1 exact duplicate (RUN-004); missing `end_time` and `duration_sec` for crashed run; missing `start_time`; mixed date formats; DAG name casing inconsistency (`nightly_batch` / `NIGHTLY_BATCH`); non-standard status `"warning"`; `"N/A"` doc counts |
| `csv_document_inventory.csv` | 12 | 1 exact duplicate (DOC-0002); missing `page_count` and `uploader`; `source_type` casing inconsistency (`text_pdf` / `TEXT_PDF` / `csv` / `CSV`); `ocr_required` mixed types (`false` / `TRUE` / `True` / `yes`); mixed date formats; empty `tags` field |

These files are designed to exercise the CSV validation branch of the quality gate
(Week 2) — schema validation, type coercion, deduplication, and normalisation.

---

### Sample PNG Images (4 files)

All images are programmatically generated with Pillow `ImageDraw` — no third-party
content, no licensing concerns. The same scan-degradation pipeline used for scanned
PDFs is applied to each (brightness gradient, Gaussian noise, Gaussian blur, slight
rotation). Images are designed to test the OCR/image ingestion branch directly,
without wrapping them in a PDF container.

| File | Content | Dimensions | Degradation |
|---|---|---|---|
| `img_receipt_grocery.png` | Grocery store receipt — 12 line items, subtotal/tax/total block, cashier/date/ref metadata | 480×820 px | Greyscale, rotation +0.5°, noise σ=9 |
| `img_invoice_b2b.png` | B2B invoice — company header bar, bill-to/ship-to blocks, 5-row line-item table, totals, payment terms | 900×1100 px | Colour, rotation −0.4°, noise σ=7 |
| `img_whiteboard_notes.png` | Sprint planning whiteboard — attendees, sprint goals, blockers, action items with checkboxes, camera vignette effect | 1000×720 px | Colour+vignette, rotation +1.1°, noise σ=14 |
| `img_form_patient_intake.png` | Patient intake form — personal info, medical history, presenting complaint, signature line | 850×1100 px | Colour, rotation +0.3°, noise σ=8 |

**Generation pipeline for each PNG:**

1. **Draw** — Pillow `Image.new()` + `ImageDraw.Draw()` renders text, tables, borders,
   and decorative elements onto a blank canvas. System fonts (`Courier New`, `Consolas`,
   `Lucida Console`) are tried first; Pillow's built-in bitmap font is the fallback.
2. **Degrade** — `_apply_scan_look()` applies:
   - Brightness gradient (left-to-right lamp variation)
   - Gaussian pixel noise (`numpy`, σ configurable per image)
   - `GaussianBlur` (slight defocus)
   - Slight rotation with white fill
3. **Save** — written as `PNG` (lossless), `RGB` mode.

These images are suitable for feeding directly into an OCR engine (Tesseract) or
as inputs to the image extraction branch of the Week 2 pipeline.

---

### User-Provided Photographed Samples (3 files)

These files were provided directly by the user to test the real-world performance of the OCR pipeline's preprocessing steps (Adaptive Thresholding and Perspective Transform) on messy mobile photos.

| File | Content | Source/Provenance |
|---|---|---|
| `photographed_spreadsheet.jpg` | Screen photo of a tabular spreadsheet | User-uploaded artifact |
| `photographed_receipt_1.png` | Digital receipt / form screenshot (formerly `image.png`) | User-provided download |
| `photographed_receipt_2.jpeg` | Invoice / fees receipt photo (formerly `fees a.jpeg`) | User-provided download |

---

## Verification Results (from last run)

```
Text-native PDFs (expect chars > 0):
  [PASS] text_financial_report.pdf        chars= 1,050
  [PASS] text_research_summary.pdf        chars= 1,564
  [PASS] text_onboarding_handbook.pdf     chars= 1,344
  [PASS] text_incident_report.pdf         chars= 1,270
  [PASS] text_supply_chain_audit.pdf      chars= 1,069

Scanned PDFs (expect chars == 0):
  [PASS] scanned_financial_report.pdf     chars=     0
  [PASS] scanned_onboarding_handbook.pdf  chars=     0
  [PASS] scanned_incident_report.pdf      chars=     0
  [PASS] scanned_supply_chain_audit.pdf   chars=     0

PNG images (expect valid dimensions):
  [PASS] img_receipt_grocery.png          480x820    mode=RGB
  [PASS] img_invoice_b2b.png             900x1100   mode=RGB
  [PASS] img_whiteboard_notes.png        1000x720   mode=RGB
  [PASS] img_form_patient_intake.png      850x1100   mode=RGB

ALL VERIFICATION CHECKS PASSED (PASS)
```
