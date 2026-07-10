"""
generate_samples.py
===================
Generates all sample documents for the Document Data Platform.

Generation methods
------------------
Text-native PDFs  : reportlab (100% programmatically generated — no licensing concerns)
Scanned PDFs      : reportlab text-PDF → PyMuPDF rasterise → Pillow degrade
                    (rotate + noise + blur) → save as image-only PDF via Pillow.
                    Result is a genuine image-only PDF with zero extractable text.
Messy CSVs        : hand-crafted rows with deliberate data-quality flaws
                    (duplicates, missing values, inconsistent casing/formats).

Run from the project root:
    .venv\\Scripts\\python samples/generate_samples.py
"""

import os
import csv
import random

import fitz                          # PyMuPDF
import numpy as np
from PIL import Image, ImageFilter

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

random.seed(42)
np.random.seed(42)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = SCRIPT_DIR          # write everything into samples/

styles = getSampleStyleSheet()


# ---------------------------------------------------------------------------
# helpers — paragraph style factory
# ---------------------------------------------------------------------------

def _h1(color="#1a237e"):
    return ParagraphStyle("h1", parent=styles["Heading1"], fontSize=13,
                          textColor=colors.HexColor(color),
                          spaceBefore=12, spaceAfter=4)


def _body():
    return ParagraphStyle("body", parent=styles["Normal"], fontSize=10,
                          leading=15, alignment=TA_JUSTIFY)


def _title_style(color="#1a237e", size=18):
    return ParagraphStyle("title", parent=styles["Title"], fontSize=size,
                          textColor=colors.HexColor(color), spaceAfter=6)


# ===========================================================================
# SECTION 1 — TEXT-NATIVE PDFs (reportlab)
# ===========================================================================

def make_text_financial_report():
    path = os.path.join(OUT, "text_financial_report.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)
    h1 = _h1("#1a237e")
    body = _body()
    story = [
        Paragraph("Acme Corporation — Q3 2024 Financial Report", _title_style("#1a237e", 18)),
        Paragraph("For the quarter ended September 30, 2024 (UNAUDITED)", styles["Normal"]),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a237e"), spaceAfter=12),
        Paragraph("Executive Summary", h1),
        Paragraph(
            "Acme Corporation delivered strong performance in Q3 2024, with total revenue growing "
            "18.4% year-over-year to $142.7 million, driven primarily by expansion in our cloud "
            "services division (+34%) and international markets (+22%). Net income of $21.3 million "
            "represents a 14.9% net margin compared to 12.1% in Q3 2023. Operating cash flow of "
            "$38.9 million provides ample liquidity for planned capital expenditures of $15 million "
            "in Q4.", body),
        Spacer(1, 8),
        Paragraph("Revenue Breakdown by Segment", h1),
        Table(
            [["Segment",         "Q3 2024 ($M)", "Q3 2023 ($M)", "YoY"],
             ["Cloud Services",   "54.2",  "40.4", "+34.2%"],
             ["Enterprise SaaS",  "48.9",  "41.7", "+17.3%"],
             ["Professional Svcs","23.1",  "22.0",  "+5.0%"],
             ["Hardware/Other",   "16.5",  "16.3",  "+1.2%"],
             ["Total",           "142.7", "120.4", "+18.4%"]],
            colWidths=[6.5*cm, 3.5*cm, 3.5*cm, 3*cm],
            style=TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#283593")),
                ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
                ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",   (0,0), (-1,-1), 9),
                ("ROWBACKGROUNDS", (0,1), (-1,-2),
                 [colors.HexColor("#e8eaf6"), colors.white]),
                ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#c5cae9")),
                ("FONTNAME",   (0,-1), (-1,-1), "Helvetica-Bold"),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#9fa8da")),
                ("ALIGN",   (1,0), (-1,-1), "CENTER"),
                ("VALIGN",  (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING",    (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ])),
        Spacer(1, 10),
        Paragraph("Outlook", h1),
        Paragraph(
            "For Q4 2024, management guides to total revenue of $148–153 million and net income "
            "of $22–24 million, reflecting continued investment in R&D (+$3M) and sales headcount "
            "expansion into three new geographies. Full-year 2024 revenue guidance is maintained "
            "at $555–565 million.", body),
    ]
    doc.build(story)
    print(f"  [OK] {os.path.basename(path)}")
    return path


def make_text_research_summary():
    path = os.path.join(OUT, "text_research_summary.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)
    h1 = _h1("#1b5e20")
    body = _body()
    abstract_box = ParagraphStyle(
        "ab", parent=styles["Normal"], fontSize=9, leading=14,
        leftIndent=20, rightIndent=20,
        backColor=colors.HexColor("#f1f8e9"),
        borderPad=8, borderColor=colors.HexColor("#a5d6a7"),
        borderWidth=1)
    story = [
        Paragraph("Urban Air Quality and Respiratory Health: A Five-Year Cohort Study",
                  _title_style("#1b5e20", 16)),
        Paragraph("J. Anderson¹, M. Chen² | ¹City University | ²Regional Medical Centre",
                  styles["Normal"]),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2e7d32"), spaceAfter=8),
        Paragraph("Abstract", h1),
        Paragraph(
            "Background: Chronic PM2.5 exposure is linked to elevated asthma and COPD rates. "
            "This study examines PM2.5 concentrations and emergency-department (ED) visit rates "
            "across 48 urban census tracts over five years (2018–2022). A 10 μg/m³ increase in "
            "annual mean PM2.5 was associated with a 12.4% increase (95% CI: 8.7–16.2%, p<0.001) "
            "in respiratory ED visits. Low-income tracts showed 1.8× greater effect size.",
            abstract_box),
        Spacer(1, 10),
        Paragraph("1. Introduction", h1),
        Paragraph(
            "Ambient air pollution causes ~4.2 million premature deaths annually (WHO, 2021). "
            "PM2.5 is the most harmful component. Urban environments concentrate emission sources "
            "including vehicular traffic, industrial activity, and domestic heating.", body),
        Spacer(1, 6),
        Paragraph("2. Methods", h1),
        Paragraph(
            "Study population: 48 census tracts, population 2,100–8,900. Air quality data from "
            "12 EPA-certified monitoring stations interpolated by inverse distance weighting. "
            "Panel fixed-effects regression with heteroskedasticity-robust standard errors "
            "clustered at tract level. All analyses in R 4.2.1 (plm package).", body),
        Spacer(1, 6),
        Paragraph("3. Results", h1),
        Paragraph(
            "Mean annual PM2.5 ranged 6.2–28.7 μg/m³ (grand mean 14.3). ED visit rates: "
            "87–412 per 10,000 person-years. Stratified analysis: 9.1% effect in high-income "
            "tracts vs 17.6% in low-income tracts.", body),
        Spacer(1, 6),
        Paragraph("4. Conclusions", h1),
        Paragraph(
            "Targeted air quality interventions in high-exposure, low-income tracts may yield "
            "disproportionate health benefits. Estimated cost saving: $2.7M/year against an "
            "intervention cost of $800K–$1.2M for a 5 μg/m³ PM2.5 reduction.", body),
    ]
    doc.build(story)
    print(f"  [OK] {os.path.basename(path)}")
    return path


def make_text_onboarding_handbook():
    path = os.path.join(OUT, "text_onboarding_handbook.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)
    h1 = _h1("#4a148c")
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11,
                        textColor=colors.HexColor("#6a1b9a"), spaceBefore=8, spaceAfter=3)
    body = _body()
    bullet = ParagraphStyle("bullet", parent=styles["Normal"], fontSize=10,
                            leading=14, leftIndent=20)
    story = [
        Paragraph("Employee Onboarding Handbook",
                  _title_style("#4a148c", 18)),
        Paragraph("Human Resources | Effective: January 1, 2024", styles["Normal"]),
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#7b1fa2"), spaceAfter=12),
        Paragraph("Welcome", h1),
        Paragraph("We are delighted to welcome you. This handbook covers policies, "
                  "your first week, and key benefits.", body),
        Spacer(1, 6),
        Paragraph("1. Your First Week", h1),
        Paragraph("Day 1 — Orientation", h2),
        Paragraph("• IT equipment setup and system access provisioning", bullet),
        Paragraph("• Security badge and building access", bullet),
        Paragraph("• Introduction to your team and assigned buddy", bullet),
        Paragraph("• HR documentation: I-9, direct deposit, benefits enrolment", bullet),
        Paragraph("Days 2–5", h2),
        Paragraph("• Mandatory compliance training (4 modules, ~3 hours)", bullet),
        Paragraph("• Shadow team members across key functional areas", bullet),
        Paragraph("• 30-60-90 day goal alignment with your manager", bullet),
        Spacer(1, 6),
        Paragraph("2. Core Policies", h1),
        Paragraph("2.1 Code of Conduct", h2),
        Paragraph("All employees must act with integrity and professionalism. "
                  "Harassment or discrimination of any kind will not be tolerated.", body),
        Paragraph("2.2 Information Security", h2),
        Paragraph("All company data is Confidential by default. Never share credentials; "
                  "encrypt sensitive files; report suspected breaches within one hour to "
                  "security@company.com.", body),
        Paragraph("2.3 Remote Work", h2),
        Paragraph("Up to 3 remote days/week with manager approval. Core hours 10am–3pm "
                  "local time. VPN required at all times on company systems.", body),
        Spacer(1, 6),
        Paragraph("3. Benefits Summary", h1),
        Table(
            [["Benefit",          "Eligibility",     "Detail"],
             ["Health Insurance", "Day 1",           "Medical, Dental, Vision"],
             ["401(k)",          "Day 90",           "4% company match (2-yr vest)"],
             ["PTO",             "Day 1",            "20 days/year accrued"],
             ["Parental Leave",  "12 months svc",    "16 weeks paid (primary carer)"],
             ["Learning Budget", "Day 90",           "$2,500/year approved courses"]],
            colWidths=[5*cm, 4*cm, 7*cm],
            style=TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#6a1b9a")),
                ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
                ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",   (0,0), (-1,-1), 9),
                ("ROWBACKGROUNDS", (0,1), (-1,-1),
                 [colors.HexColor("#f3e5f5"), colors.white]),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#ce93d8")),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING",    (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ])),
    ]
    doc.build(story)
    print(f"  [OK] {os.path.basename(path)}")
    return path


def make_text_incident_report():
    path = os.path.join(OUT, "text_incident_report.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)
    h1 = _h1("#b71c1c")
    body = _body()
    code_style = ParagraphStyle(
        "code", parent=styles["Code"], fontSize=8,
        backColor=colors.HexColor("#fafafa"),
        borderPad=6, borderColor=colors.HexColor("#ef9a9a"),
        borderWidth=1, leftIndent=10)
    story = [
        Paragraph("Post-Incident Review — DB Outage INC-20240915",
                  _title_style("#b71c1c", 16)),
        Paragraph("Severity: P1 | Duration: 47 min | Impact: All production API endpoints",
                  ParagraphStyle("sub", parent=styles["Normal"], fontSize=10,
                                 textColor=colors.HexColor("#c62828"))),
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#c62828"), spaceAfter=12),
        Paragraph("1. Summary", h1),
        Paragraph(
            "On 2024-09-15 at 14:23 UTC, the primary PostgreSQL cluster suffered a 47-minute "
            "complete outage. Root cause: a schema migration acquired an EXCLUSIVE lock on a "
            "220M-row table, causing connection pool exhaustion and universal HTTP 503 responses.",
            body),
        Spacer(1, 6),
        Paragraph("2. Timeline", h1),
        Table(
            [["UTC Time", "Event"],
             ["14:18", "Migration v2.14.1 initiated by automated deploy pipeline"],
             ["14:19", "EXCLUSIVE lock acquired on users table (220M rows)"],
             ["14:23", "Connection pool saturated; HTTP 503 on all endpoints"],
             ["14:24", "PagerDuty fires; on-call SRE paged"],
             ["14:31", "SRE identifies blocker via pg_stat_activity"],
             ["14:33", "Migration terminated; lock released"],
             ["14:37", "Connection pool recovers; APIs restored"],
             ["14:45", "Migration v2.14.1 rolled back"],
             ["15:10", "Post-incident review initiated"]],
            colWidths=[3*cm, 13*cm],
            style=TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#c62828")),
                ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
                ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",   (0,0), (-1,-1), 9),
                ("ROWBACKGROUNDS", (0,1), (-1,-1),
                 [colors.HexColor("#ffebee"), colors.white]),
                ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#ef9a9a")),
                ("VALIGN",  (0,0), (-1,-1), "TOP"),
                ("TOPPADDING",    (0,0), (-1,-1), 4),
                ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ])),
        Spacer(1, 8),
        Paragraph("3. Root Cause", h1),
        Paragraph(
            "ALTER TABLE on a 220M-row table with NOT NULL DEFAULT rewrites the entire "
            "table under ACCESS EXCLUSIVE lock. No lock_timeout guard was in place.", body),
        Spacer(1, 4),
        Paragraph("ALTER TABLE users\n  ADD COLUMN last_login_ip INET NOT NULL DEFAULT '0.0.0.0';",
                  code_style),
        Spacer(1, 8),
        Paragraph("4. Remediation", h1),
        Paragraph(
            "Immediate: terminate migration, rollback, drain pool. "
            "Long-term: (1) mandatory zero-downtime review for tables >1M rows; "
            "(2) lock_timeout=5s on all prod migrations; (3) integrate pg_repack.", body),
    ]
    doc.build(story)
    print(f"  [OK] {os.path.basename(path)}")
    return path


def make_text_supply_chain_audit():
    path = os.path.join(OUT, "text_supply_chain_audit.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)
    h1 = _h1("#e65100")
    body = _body()
    rows = [
        ["#",  "Audit Item",                                        "Status", "Notes"],
        ["1",  "Supplier ISO 9001 certification current (<3 yrs)",  "PASS",   "Cert #ISO-2024-4471"],
        ["2",  "On-time delivery rate ≥95% (trailing 12 months)",   "PASS",   "97.3% actual"],
        ["3",  "Sub-supplier disclosure — 2 tiers documented",      "FAIL",   "Tier-2 list incomplete"],
        ["4",  "Conflict minerals (3TG) RCOI filed",                "PASS",   "Filed 2024-03-15"],
        ["5",  "Modern slavery policy signed",                      "PASS",   "Version 3.1"],
        ["6",  "Environmental: wastewater discharge permit",        "WARN",   "Renewal due 2024-12-01"],
        ["7",  "Cybersecurity: SOC 2 Type II or equivalent",        "FAIL",   "Audit pending Q4"],
        ["8",  "BCP tested <12 months",                            "PASS",   "Test date 2024-06-14"],
        ["9",  "Product liability insurance ≥$5M",                 "PASS",   "Policy #PLI-882341"],
        ["10", "Packaging: EU Directive 94/62/EC",                  "WARN",   "Review needed for new SKUs"],
    ]
    status_bg = {"PASS": colors.HexColor("#e8f5e9"),
                 "FAIL": colors.HexColor("#ffebee"),
                 "WARN": colors.HexColor("#fff8e1")}
    ts = [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e65100")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#ffccbc")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]
    for i, row in enumerate(rows[1:], 1):
        ts.append(("BACKGROUND", (0,i), (-1,i), status_bg.get(row[2], colors.white)))
    story = [
        Paragraph("Supply Chain Compliance Audit — Veridian Manufacturing Ltd.",
                  _title_style("#e65100", 15)),
        Paragraph("Date: 2024-10-08 | Ref: SCA-2024-117 | Auditor: SC Risk Team",
                  styles["Normal"]),
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#f4511e"), spaceAfter=12),
        Paragraph("Audit Scope", h1),
        Paragraph("Quality management, environmental compliance, social responsibility, "
                  "and cybersecurity posture for Supplier ID VMU-4491, Leeds UK.", body),
        Spacer(1, 8),
        Paragraph("Results", h1),
        Table(rows, colWidths=[1*cm, 7.5*cm, 2*cm, 5.5*cm],
              style=TableStyle(ts)),
        Spacer(1, 10),
        Paragraph("Summary: 6 PASS · 2 WARN · 2 FAIL. Supplier placed on Conditional "
                  "Approved status. FAIL items must be remediated within 90 days.", body),
    ]
    doc.build(story)
    print(f"  [OK] {os.path.basename(path)}")
    return path


# ===========================================================================
# SECTION 2 — SCANNED (image-only) PDFs
# ===========================================================================

def _render_page_to_image(pdf_path: str, page_index: int = 0,
                           dpi: int = 150) -> Image.Image:
    """Render one PDF page to a PIL RGB image."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def _degrade(img: Image.Image, rotation_deg: float = 0.9,
             noise_std: int = 14, blur_radius: float = 0.7) -> Image.Image:
    """
    Simulate physical scan degradation:
      1. Gaussian noise  — scanner sensor noise
      2. Gaussian blur   — slight scanner-platen defocus
      3. Slight rotation — paper mis-feed
    Result is converted to greyscale (typical scanner output) then back to RGB
    so Pillow can save it as a single-layer colour PDF page.
    """
    arr = np.array(img, dtype=np.float32)

    # brightness gradient (uneven lamp)
    w = arr.shape[1]
    grad = np.linspace(0.96, 1.04, w, dtype=np.float32)
    arr *= grad[np.newaxis, :, np.newaxis]

    # Gaussian noise
    arr = np.clip(arr + np.random.normal(0, noise_std, arr.shape), 0, 255).astype(np.uint8)

    result = Image.fromarray(arr, "RGB")

    # blur
    result = result.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # rotation with white fill
    rotated = result.rotate(rotation_deg, expand=True, fillcolor=(245, 245, 245))

    # crop back to original dimensions (centre crop)
    dw, dh = rotated.size
    left = (dw - img.width)  // 2
    top  = (dh - img.height) // 2
    rotated = rotated.crop((max(0, left), max(0, top),
                            max(0, left) + img.width,
                            max(0, top)  + img.height))

    # convert to greyscale → RGB (mirrors a real scanner's output)
    return rotated.convert("L").convert("RGB")


def make_scanned_pdf(source_pdf_path: str, out_path: str,
                     rotation: float = 0.9, noise: int = 14,
                     max_pages: int = 2):
    """
    Produce a genuinely image-only PDF:
      source text PDF → rasterise each page → degrade → save as image PDF.
    No text layer is embedded; PyMuPDF will extract 0 characters.
    """
    doc = fitz.open(source_pdf_path)
    n_pages = min(len(doc), max_pages)
    doc.close()

    images = []
    for i in range(n_pages):
        raw = _render_page_to_image(source_pdf_path, page_index=i, dpi=150)
        images.append(_degrade(raw, rotation_deg=rotation, noise_std=noise))

    # Pillow saves multi-page image PDFs with no text layer
    rgb = [img.convert("RGB") for img in images]
    rgb[0].save(out_path, save_all=True, append_images=rgb[1:], format="PDF")
    print(f"  [OK] {os.path.basename(out_path)}  ({n_pages} page(s), image-only)")
    return out_path


# ===========================================================================
# SECTION 3 — MESSY CSVs
# ===========================================================================

def make_csv_customer_orders():
    path = os.path.join(OUT, "csv_customer_orders.csv")
    rows = [
        ["order_id","customer_name","customer_email","order_date",
         "product_sku","quantity","unit_price_usd","status","region"],
        # clean
        ["ORD-1001","Alice Johnson","alice@example.com","2024-01-15","SKU-A001","2","29.99","completed","North America"],
        ["ORD-1002","Bob Smith","bob.smith@corp.io","2024/01/16","SKU-B002","1","149.00","shipped","Europe"],
        # CASING inconsistency
        ["ORD-1003","CAROL WILLIAMS","","2024-01-17","SKU-A001","5","29.99","Completed","APAC"],
        # missing quantity
        ["ORD-1004","dave O'Brien","dave@startup.co","01-18-2024","SKU-C003","","89.50","pending","north america"],
        ["ORD-1005","Eve Nakamura","eve.n@jpmail.jp","2024-01-18","SKU-B002","3","149.00","completed","APAC"],
        # missing price
        ["ORD-1006","Frank Müller","f.muller@de.com","2024-01-19","SKU-D004","10","","cancelled","Europe"],
        # DUPLICATE of ORD-1002
        ["ORD-1002","Bob Smith","bob.smith@corp.io","2024/01/16","SKU-B002","1","149.00","shipped","Europe"],
        # missing name
        ["ORD-1007","","grace@example.org","2024-01-20","SKU-A001","1","29.99","completed","North America"],
        ["ORD-1008","Henry Park","henry@parkco.kr","2024-01-21","SKU-E005","2","200.00","SHIPPED","APAC"],
        ["ORD-1009","Isabel Ferreira","isabel.f@pt.net","2024-01-22","SKU-C003","4","89.50","completed","Europe"],
        # missing region
        ["ORD-1010","Jack Li","jack.li@cn.example","2024-01-23","SKU-F006","7","15.00","pending",""],
        # non-numeric quantity
        ["ORD-1011","Kate Brown","kate@example.com","2024-01-24","SKU-A001","N/A","29.99","completed","North America"],
        ["ORD-1012","Liam Murphy","liam@ie.example","2024-01-25","SKU-B002","2","149.00","Shipped","Europe"],
        # DUPLICATE of ORD-1001
        ["ORD-1001","Alice Johnson","alice@example.com","2024-01-15","SKU-A001","2","29.99","completed","North America"],
        ["ORD-1013","Mia Santos","mia.santos@br.net","2024-01-26","SKU-G007","3","55.00","completed","South America"],
        # different date format
        ["ORD-1014","Noah Kim","noah@kr.example","26/01/2024","SKU-C003","1","89.50","pending","APAC"],
        # price with currency symbol
        ["ORD-1015","Olivia Chen","olivia@sg.example","2024-01-27","SKU-H008","6","$44.99","completed","APAC"],
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    print(f"  [OK] {os.path.basename(path)}  ({len(rows)-1} rows, flaws: 2 dupes, missing values, format inconsistency)")
    return path


def make_csv_pipeline_runs():
    path = os.path.join(OUT, "csv_pipeline_runs.csv")
    rows = [
        ["run_id","dag_name","run_date","start_time","end_time","status",
         "docs_processed","docs_failed","duration_sec","triggered_by"],
        ["RUN-001","ingestion_dag","2024-01-10","02:00:01","02:14:33","success","142","3","812","schedule"],
        # status casing
        ["RUN-002","nightly_batch","2024-01-10","03:00:00","03:47:22","SUCCESS","850","0","2842","Schedule"],
        # missing doc counts (dbt doesn't process docs)
        ["RUN-003","dbt_run_dag","2024-01-10","04:00:00","04:08:11","success","","","491","schedule"],
        ["RUN-004","ingestion_dag","2024-01-11","02:00:03","02:19:44","success","198","7","1181","schedule"],
        # crashed — missing end_time and duration
        ["RUN-005","nightly_batch","2024-01-11","03:00:00","","failed","400","400","","schedule"],
        ["RUN-006","dbt_run_dag","2024-01-11","04:00:00","04:09:02","success","","","542","schedule"],
        ["RUN-007","ingestion_dag","2024-01-12","02:00:01","02:15:50","success","163","1","949","schedule"],
        # DUPLICATE of RUN-004
        ["RUN-004","ingestion_dag","2024-01-11","02:00:03","02:19:44","success","198","7","1181","schedule"],
        ["RUN-008","nightly_batch","2024-01-12","03:00:00","03:51:09","success","920","2","3069","schedule"],
        # missing start_time
        ["RUN-009","dbt_run_dag","2024-01-12","","04:07:44","success","","","457","manual"],
        # different date format
        ["RUN-010","ingestion_dag","01/13/2024","02:00:02","02:22:10","success","211","4","1328","schedule"],
        # dag name capitalised differently
        ["RUN-011","NIGHTLY_BATCH","2024-01-13","03:00:00","04:01:14","success","1003","0","3674","schedule"],
        # non-standard status
        ["RUN-012","dbt_run_dag","2024-01-13","04:00:00","04:10:33","warning","","","633","schedule"],
        # N/A counts
        ["RUN-013","ingestion_dag","2024-01-14","02:00:00","02:13:01","success","N/A","N/A","781","backfill"],
        ["RUN-014","nightly_batch","2024-01-14","03:00:00","03:44:55","success","788","1","2695","schedule"],
        ["RUN-015","dbt_run_dag","2024-01-14","04:00:00","04:07:18","success","","","438","schedule"],
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    print(f"  [OK] {os.path.basename(path)}  ({len(rows)-1} rows, flaws: 1 dupe, missing fields, case/format issues)")
    return path


def make_csv_document_inventory():
    path = os.path.join(OUT, "csv_document_inventory.csv")
    rows = [
        ["doc_id","filename","source_type","upload_date","uploader",
         "page_count","file_size_kb","ocr_required","tags"],
        ["DOC-0001","annual_report_2023.pdf","text_pdf","2024-01-05","john.doe","42","1840","false","finance|annual|2023"],
        ["DOC-0002","scanned_invoice_jan.pdf","scanned_pdf","2024-01-06","jane.smith","3","2210","TRUE","invoice|accounts_payable"],
        # uploader casing inconsistent, N/A for page_count
        ["DOC-0003","customer_data_q4.csv","csv","2024-01-06","JANE.SMITH","N/A","88","false","customer|q4|2023"],
        # source_type casing
        ["DOC-0004","board_minutes_dec2023.pdf","TEXT_PDF","2024-01-07","admin","8","310","false","board|governance|minutes"],
        # different date format, missing page_count
        ["DOC-0005","scanned_contract_vendor_a.pdf","scanned_pdf","07/01/2024","procurement","","4502","True","contract|vendor"],
        ["DOC-0006","sales_pipeline.csv","CSV","2024-01-08","sales.ops","N/A","215","false","sales|pipeline|crm"],
        ["DOC-0007","tax_filing_2023.pdf","text_pdf","2024-01-09","john.doe","24","980","false","tax|finance|2023"],
        # DUPLICATE
        ["DOC-0002","scanned_invoice_jan.pdf","scanned_pdf","2024-01-06","jane.smith","3","2210","TRUE","invoice|accounts_payable"],
        # missing uploader
        ["DOC-0008","hr_policy_v3.pdf","text_pdf","2024-01-10","","18","720","false","hr|policy"],
        # ocr_required = 'yes' instead of bool
        ["DOC-0009","scanned_receipt_bundle.pdf","scanned_pdf","2024-01-10","finance.team","47","8830","yes","receipts|expense"],
        # different date format, missing tags
        ["DOC-0010","vendor_sla_terms.pdf","text_pdf","10-01-2024","legal","12","445","FALSE",""],
        ["DOC-0011","returns_jan.csv","csv","2024-01-12","warehouse","N/A","134","false","returns|warehouse|jan"],
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    print(f"  [OK] {os.path.basename(path)}  ({len(rows)-1} rows, flaws: 1 dupe, missing fields, type/format issues)")
    return path


# ===========================================================================
# SECTION 4 — VERIFICATION
# ===========================================================================

def verify_text_pdf(path: str) -> dict:
    doc = fitz.open(path)
    chars = sum(len(p.get_text("text").strip()) for p in doc)
    doc.close()
    return {"file": os.path.basename(path), "chars": chars, "has_text": chars > 0}


def verify_scanned_pdf(path: str) -> dict:
    doc = fitz.open(path)
    chars = sum(len(p.get_text("text").strip()) for p in doc)
    doc.close()
    return {"file": os.path.basename(path), "chars": chars, "is_image_only": chars == 0}


# ===========================================================================
# SECTION 5 — SAMPLE PNG IMAGES (Pillow-generated, scan-degraded)
# ===========================================================================
#
# Each image is drawn programmatically with ImageDraw, then the same
# scan-degradation pipeline used for scanned PDFs is applied:
#   - brightness gradient, Gaussian noise, slight blur, slight rotation.
# All text is rendered with a bundled or system monospace/sans font.
# No third-party content is used — 100% original generated data.

from PIL import ImageDraw, ImageFont
import textwrap


def _load_font(size: int, bold: bool = False):
    """
    Try common Windows / Linux monospace system fonts; fall back to
    Pillow's built-in bitmap font if none are found.
    """
    candidates = [
        # Windows
        "cour.ttf" if not bold else "courbd.ttf",
        "consola.ttf",
        "lucon.ttf",
        # Linux / macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Courier.ttc",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (IOError, OSError):
            continue
    # fallback – no sizing control, but always available
    return ImageFont.load_default()


def _apply_scan_look(img: Image.Image,
                     rotation_deg: float = 0.6,
                     noise_std: int = 10,
                     blur_radius: float = 0.5) -> Image.Image:
    """Apply scan-like degradation to a PIL Image."""
    arr = np.array(img.convert("RGB"), dtype=np.float32)
    w = arr.shape[1]
    grad = np.linspace(0.97, 1.03, w, dtype=np.float32)
    arr *= grad[np.newaxis, :, np.newaxis]
    arr = np.clip(arr + np.random.normal(0, noise_std, arr.shape), 0, 255).astype(np.uint8)
    result = Image.fromarray(arr, "RGB")
    result = result.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    result = result.rotate(rotation_deg, expand=False, fillcolor=(250, 250, 250))
    return result


def make_img_receipt():
    """
    img_receipt_grocery.png
    A greyscale scanned grocery store receipt.
    ~80 mm wide (receipt-proportioned), white background, monospace font.
    """
    W, H = 480, 820
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    fn  = _load_font(18)
    fn_s = _load_font(15)
    fn_b = _load_font(20, bold=True)

    y = 30
    def line(text, font=None, center=False, gap=6):
        nonlocal y
        font = font or fn
        if center:
            try:
                bbox = d.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
            except AttributeError:
                tw = len(text) * 10
            d.text(((W - tw) // 2, y), text, fill=(20, 20, 20), font=font)
        else:
            d.text((30, y), text, fill=(20, 20, 20), font=font)
        y += (bbox[3] - bbox[0] if False else 24) + gap

    def separator(char="-", gap=4):
        nonlocal y
        d.text((30, y), char * 36, fill=(120, 120, 120), font=fn_s)
        y += 20 + gap

    line("FRESHMART SUPERSTORE", fn_b, center=True)
    line("14 Orchard Lane, Springfield", fn_s, center=True)
    line("Tel: (555) 204-8812", fn_s, center=True)
    separator("=")
    line("Date: 2024-01-18    Time: 14:32")
    line("Cashier: Emma T.    Reg: 04")
    line("Member: **** 7741")
    separator()
    items = [
        ("Organic Whole Milk 2L",     "3.49"),
        ("Sourdough Bread 800g",       "4.25"),
        ("Free Range Eggs x12",        "5.10"),
        ("Cheddar Cheese 400g",        "4.80"),
        ("Cherry Tomatoes 250g",       "2.99"),
        ("Chicken Breast 500g",        "7.45"),
        ("Greek Yoghurt 500g",         "3.20"),
        ("Orange Juice 1L",            "3.79"),
        ("Mixed Salad Leaves",         "2.50"),
        ("Olive Oil Extra Virgin",     "6.99"),
        ("Pasta Penne 500g",           "1.89"),
        ("Tomato Pasta Sauce",         "2.45"),
    ]
    for name, price in items:
        pad = 36 - len(name) - len(price)
        d.text((30, y), f"{name}{' '*max(1,pad)}${price}",
               fill=(20,20,20), font=fn)
        y += 28
    separator()
    subtotal = 48.90
    tax      =  4.89
    total    = 53.79
    d.text((30, y), f"{'Subtotal':<28}${subtotal:.2f}", fill=(20,20,20), font=fn); y+=28
    d.text((30, y), f"{'Tax (10%)':<28}${tax:.2f}",     fill=(20,20,20), font=fn); y+=28
    separator("=")
    d.text((30, y), f"{'TOTAL':<28}${total:.2f}",       fill=(20,20,20), font=fn_b); y+=34
    separator("=")
    d.text((30, y), f"{'Cash Tendered':<28}$60.00",    fill=(20,20,20), font=fn); y+=28
    d.text((30, y), f"{'Change':<28}${60-total:.2f}",   fill=(20,20,20), font=fn); y+=28
    separator()
    line("Thank you for shopping!", fn_s, center=True)
    line("Loyalty pts earned: 54", fn_s, center=True)
    line("Ref: TXN-20240118-00441", fn_s, center=True)

    # convert to greyscale then degrade
    grey = img.convert("L").convert("RGB")
    out  = _apply_scan_look(grey, rotation_deg=0.5, noise_std=9)
    path = os.path.join(OUT, "img_receipt_grocery.png")
    out.save(path)
    print(f"  [OK] {os.path.basename(path)}  ({W}x{H} px, greyscale, scan-degraded)")
    return path


def make_img_invoice():
    """
    img_invoice_b2b.png
    A B2B invoice on a light-cream background — company header, line-item
    table, totals block. Rendered entirely with Pillow ImageDraw.
    """
    W, H = 900, 1100
    bg = (252, 250, 245)
    img = Image.new("RGB", (W, H), bg)
    d   = ImageDraw.Draw(img)

    fn   = _load_font(17)
    fn_s = _load_font(14)
    fn_b = _load_font(20, bold=True)
    fn_h = _load_font(28, bold=True)

    # header bar
    d.rectangle([0, 0, W, 90], fill=(30, 80, 160))
    d.text((40, 22), "NEXATECH SOLUTIONS LTD.", fill=(255,255,255), font=fn_h)
    d.text((40, 60), "VAT No: GB 342 8812 01  |  Reg: 09812347",
           fill=(200, 220, 255), font=fn_s)

    y = 110
    # invoice meta block
    d.text((40,  y), "INVOICE",              fill=(30,80,160), font=fn_h);  y+=40
    d.text((40,  y), "Invoice No: INV-2024-0892", fill=(40,40,40), font=fn_b)
    d.text((500, y), "Date: 2024-01-22",     fill=(40,40,40), font=fn_b);   y+=30
    d.text((40,  y), "Due Date:  2024-02-22", fill=(40,40,40), font=fn)
    d.text((500, y), "PO Ref:   PO-88441",   fill=(40,40,40), font=fn);     y+=30
    d.line([(40, y), (W-40, y)], fill=(180,180,200), width=1);              y+=14

    # bill-to / ship-to
    d.text((40,  y), "Bill To:",             fill=(80,80,80),  font=fn_s)
    d.text((400, y), "Ship To:",             fill=(80,80,80),  font=fn_s);  y+=22
    bill = ["Omni Retail Group", "Attn: Accounts Payable",
            "22 Commerce Park, Leeds", "LS1 4AP, United Kingdom"]
    ship = ["Omni Retail — Warehouse", "Unit 7, Logistics Hub",
            "Wakefield Road, Bradford", "BD3 9AB, United Kingdom"]
    for b, s in zip(bill, ship):
        d.text((40,  y), b, fill=(30,30,30), font=fn)
        d.text((400, y), s, fill=(30,30,30), font=fn);                      y+=24
    y += 14
    d.line([(40, y), (W-40, y)], fill=(180,180,200), width=1);              y+=10

    # table header
    cols = [40, 320, 480, 580, 700, 820]
    hdrs = ["Description", "SKU", "Qty", "Unit Price", "VAT", "Line Total"]
    d.rectangle([40, y, W-40, y+30], fill=(230, 235, 250))
    for i, h in enumerate(hdrs):
        d.text((cols[i]+4, y+6), h, fill=(30,60,140), font=fn_s)
    y += 32

    rows = [
        ("Cloud Infra Licence (annual)",  "LIC-CLOUD-01",  "1",  "4,200.00",  "840.00",  "5,040.00"),
        ("Pro Support — Tier 2",          "SUP-PRO-T2",    "12", "  250.00",  "600.00",  "3,600.00"),
        ("Implementation Services",       "SVC-IMPL-2024", "8",  "  195.00",  "312.00",  "1,872.00"),
        ("Data Migration (one-off)",       "SVC-MIGR-01",   "1",  "1,100.00",  "220.00",  "1,320.00"),
        ("Training — Remote (2 days)",    "TRN-REM-2D",    "1",  "  800.00",  "160.00",  "  960.00"),
    ]
    for i, row in enumerate(rows):
        fill = (245, 247, 255) if i % 2 == 0 else bg
        d.rectangle([40, y, W-40, y+28], fill=fill)
        for j, val in enumerate(row):
            d.text((cols[j]+4, y+5), val, fill=(30,30,30), font=fn_s)
        y += 28

    y += 10
    d.line([(40, y), (W-40, y)], fill=(30,80,160), width=2); y += 14
    # totals
    def total_row(label, value, bold=False):
        nonlocal y
        fnt = fn_b if bold else fn
        d.text((580, y), label, fill=(40,40,40), font=fnt)
        d.text((820, y), value, fill=(40,40,40), font=fnt)
        y += 28
    total_row("Subtotal (ex VAT):",  "11,350.00")
    total_row("VAT (20%):",          " 2,132.00")
    total_row("TOTAL DUE (GBP):",   "13,482.00", bold=True)
    y += 10
    d.line([(40, y), (W-40, y)], fill=(30,80,160), width=2); y += 20

    # payment terms
    d.text((40, y), "Payment Terms: 30 days net. Bank transfer to:", fill=(60,60,60), font=fn_s); y+=22
    d.text((40, y), "NexaTech Solutions Ltd — Sort: 40-22-18 — Acct: 81447722 — SWIFT: HBUKGB4B",
           fill=(60,60,60), font=fn_s); y+=22
    d.text((40, y), "Queries: billing@nexatech.example.com  |  +44 113 555 0192",
           fill=(60,60,60), font=fn_s)

    out  = _apply_scan_look(img, rotation_deg=-0.4, noise_std=7, blur_radius=0.4)
    path = os.path.join(OUT, "img_invoice_b2b.png")
    out.save(path)
    print(f"  [OK] {os.path.basename(path)}  ({W}x{H} px, colour, scan-degraded)")
    return path


def make_img_whiteboard():
    """
    img_whiteboard_notes.png
    A whiteboard photo with handwriting-style meeting notes.
    Off-white background with simulated camera/perspective noise and vignette.
    """
    W, H = 1000, 720
    img = Image.new("RGB", (W, H), (245, 243, 235))
    d   = ImageDraw.Draw(img)

    # faint ruled lines
    for row_y in range(60, H, 55):
        d.line([(30, row_y), (W-30, row_y)], fill=(210, 208, 200), width=1)

    fn  = _load_font(22)
    fn_b = _load_font(26, bold=True)
    fn_s = _load_font(17)

    y = 30
    d.text((W//2 - 160, y), "SPRINT PLANNING — 2024-01-22",
           fill=(20, 20, 80), font=fn_b); y += 50

    sections = [
        ("Attendees:", ["- Priya (PM), James (BE), Sofia (FE), Kwame (QA), Dan (DevOps)"]),
        ("Goals this sprint:", [
            "1. Ship ingestion API v1 (FastAPI endpoint + Kafka producer)",
            "2. OCR pipeline: OpenCV preprocess + Tesseract confidence scoring",
            "3. Postgres bronze schema migration (docs table + hash index)",
            "4. S3 lifecycle rules: raw/ -> curated/ -> failed/ prefixes",
        ]),
        ("Blockers:", [
            "- Tesseract win32 binary path not in CI env (James to fix)",
            "- RDS free-tier instance still pending AWS approval (Dan)",
            "- Need sample scanned PDFs for OCR testing (Sofia)",
        ]),
        ("Action items:", [
            "[ ] Priya  -> update Jira board by EOD",
            "[ ] James  -> Dockerfile for Tesseract",
            "[ ] Dan    -> EC2 + RDS provisioning script",
            "[ ] Sofia  -> generate sample corpus (text + scanned PDFs)",
            "[ ] Kwame  -> draft test plan for quality gate",
        ]),
        ("Next standup: 2024-01-23 09:30 UTC", []),
    ]
    for header, lines in sections:
        d.text((40, y), header, fill=(180, 30, 30), font=fn_b); y += 34
        for l in lines:
            d.text((60, y), l, fill=(30, 30, 30), font=fn);     y += 30
        y += 10

    # vignette overlay — darken edges to simulate camera
    vignette = Image.new("RGBA", (W, H), (0,0,0,0))
    vd = ImageDraw.Draw(vignette)
    for step in range(60):
        alpha = int(step * 1.5)
        vd.rectangle([step, step, W-step, H-step],
                     outline=(0, 0, 0, alpha), width=1)
    img_rgba = img.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, vignette)
    img = img_rgba.convert("RGB")

    out  = _apply_scan_look(img, rotation_deg=1.1, noise_std=14, blur_radius=0.6)
    path = os.path.join(OUT, "img_whiteboard_notes.png")
    out.save(path)
    print(f"  [OK] {os.path.basename(path)}  ({W}x{H} px, whiteboard-style, vignette+noise)")
    return path


def make_img_filled_form():
    """
    img_form_patient_intake.png
    A filled patient intake form — printed fields with typed-looking values.
    Tests the pipeline's ability to extract structured text from a form image.
    """
    W, H = 850, 1100
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d   = ImageDraw.Draw(img)

    fn   = _load_font(17)
    fn_s = _load_font(14)
    fn_b = _load_font(19, bold=True)
    fn_h = _load_font(24, bold=True)

    # top border
    d.rectangle([0, 0, W, 8], fill=(0, 90, 160))

    y = 24
    d.text((W//2 - 200, y), "SPRINGFIELD MEDICAL CENTRE",
           fill=(0, 90, 160), font=fn_h); y += 36
    d.text((W//2 - 130, y), "Patient Intake Form",
           fill=(60, 60, 60),  font=fn_b); y += 30
    d.line([(40, y), (W-40, y)], fill=(0, 90, 160), width=2); y += 18

    def field(label, value, label_w=230, gap=10):
        nonlocal y
        d.text((40, y),        label + ":", fill=(80, 80, 80),  font=fn_s)
        d.text((40+label_w, y), value,      fill=(10, 10, 10),  font=fn)
        # underline for the value
        try:
            bb = d.textbbox((40+label_w, y), value, font=fn)
            uw = bb[2] - bb[0]
        except AttributeError:
            uw = len(value) * 9
        d.line([(40+label_w, y+22), (40+label_w+max(uw, 200), y+22)],
               fill=(180, 180, 180), width=1)
        y += 34 + gap

    def section(title):
        nonlocal y
        y += 8
        d.rectangle([40, y, W-40, y+26], fill=(230, 240, 255))
        d.text((48, y+4), title, fill=(0, 60, 140), font=fn_b)
        y += 34

    section("Personal Information")
    field("Full Name",        "Johnson, Margaret A.")
    field("Date of Birth",    "14 / 03 / 1978")
    field("Gender",           "Female")
    field("NHS Number",       "485 777 3301")
    field("Phone",            "+44 7700 900 442")
    field("Email",            "m.johnson@email.example")
    field("Address",          "18 Birch Close, Sheffield, S3 7LN")
    field("Emergency Contact","Robert Johnson — +44 7700 900 111")

    section("Medical History")
    field("GP / Referring Doctor", "Dr. T. Patel (Sheffield Central Surgery)")
    field("Known Allergies",   "Penicillin, Ibuprofen")
    field("Current Medications","Lisinopril 10mg, Levothyroxine 50mcg")
    field("Previous Surgeries","Appendectomy 2009, Tonsillectomy 1995")
    field("Chronic Conditions", "Hypertension (diagnosed 2015), Hypothyroidism")
    field("Smoking Status",    "Non-smoker")
    field("Alcohol Use",       "Occasional (<5 units/week)")

    section("Presenting Complaint")
    field("Chief Complaint",   "Persistent headache and dizziness x 5 days")
    field("Pain Score (0-10)", "6")
    field("Onset",             "Gradual — worse in morning")
    field("Associated Symptoms","Mild nausea, photosensitivity")

    y += 10
    d.line([(40, y), (W-40, y)], fill=(180,180,180), width=1); y+=14
    d.text((40, y), "Patient signature: ___________________________    Date: ________ / ________ / 2024",
           fill=(60,60,60), font=fn_s)

    # bottom border
    d.rectangle([0, H-8, W, H], fill=(0, 90, 160))

    out  = _apply_scan_look(img, rotation_deg=0.3, noise_std=8, blur_radius=0.45)
    path = os.path.join(OUT, "img_form_patient_intake.png")
    out.save(path)
    print(f"  [OK] {os.path.basename(path)}  ({W}x{H} px, form layout, scan-degraded)")
    return path


def verify_png(path: str) -> dict:
    """Confirm the PNG opens correctly and has the expected dimensions."""
    img = Image.open(path)
    w, h = img.size
    mode = img.mode
    return {"file": os.path.basename(path), "size": f"{w}x{h}",
            "mode": mode, "ok": w > 0 and h > 0}


# ===========================================================================
# MAIN
# ===========================================================================

if __name__ == "__main__":
    print("\n=== Generating TEXT-NATIVE PDFs ===")
    t1 = make_text_financial_report()
    t2 = make_text_research_summary()
    t3 = make_text_onboarding_handbook()
    t4 = make_text_incident_report()
    t5 = make_text_supply_chain_audit()

    print("\n=== Generating SCANNED (image-only) PDFs ===")
    s1 = make_scanned_pdf(t1, os.path.join(OUT, "scanned_financial_report.pdf"),   rotation= 1.2, noise=15)
    s2 = make_scanned_pdf(t3, os.path.join(OUT, "scanned_onboarding_handbook.pdf"), rotation=-0.7, noise=18)
    s3 = make_scanned_pdf(t4, os.path.join(OUT, "scanned_incident_report.pdf"),     rotation= 0.4, noise=20)
    s4 = make_scanned_pdf(t5, os.path.join(OUT, "scanned_supply_chain_audit.pdf"),  rotation=-1.1, noise=12)

    print("\n=== Generating SAMPLE PNG IMAGES ===")
    p1 = make_img_receipt()
    p2 = make_img_invoice()
    p3 = make_img_whiteboard()
    p4 = make_img_filled_form()

    print("\n=== Generating MESSY CSVs ===")
    c1 = make_csv_customer_orders()
    c2 = make_csv_pipeline_runs()
    c3 = make_csv_document_inventory()

    # ── Verification ────────────────────────────────────────────────────────
    print("\n=== VERIFICATION ===")

    print("\n  Text-native PDFs (expect chars > 0):")
    text_pass = True
    for p in [t1, t2, t3, t4, t5]:
        r = verify_text_pdf(p)
        ok = "PASS" if r["has_text"] else "FAIL"
        if not r["has_text"]: text_pass = False
        print(f"    [{ok}] {r['file']:<45s}  chars={r['chars']:>6,}")

    print("\n  Scanned PDFs (expect chars == 0):")
    scan_pass = True
    for p in [s1, s2, s3, s4]:
        r = verify_scanned_pdf(p)
        ok = "PASS" if r["is_image_only"] else "FAIL"
        if not r["is_image_only"]: scan_pass = False
        print(f"    [{ok}] {r['file']:<45s}  chars={r['chars']:>6,}")

    print("\n  PNG images (expect valid dimensions):")
    png_pass = True
    for p in [p1, p2, p3, p4]:
        r = verify_png(p)
        ok = "PASS" if r["ok"] else "FAIL"
        if not r["ok"]: png_pass = False
        print(f"    [{ok}] {r['file']:<45s}  {r['size']}  mode={r['mode']}")

    print()
    if text_pass and scan_pass and png_pass:
        print("  ALL VERIFICATION CHECKS PASSED (PASS)")
        exit(0)
    else:
        print("  SOME CHECKS FAILED -- see above (FAIL)")
        exit(1)
