"""
extraction/verify_preprocessing_impact.py

Controlled side-by-side OCR test to measure the impact of the preprocessing
pipeline on Tesseract OCR confidence and text quality.

Test Subject: samples/photographed_receipt_1.png
  - Run 1: Raw image directly through Tesseract
  - Run 2: Image after full preprocess_image() pipeline (preprocess.py)

Outputs:
  - samples/verified_preprocessed.png   : the preprocessed image
  - samples/ocr_comparison_results.txt  : side-by-side text comparison
  - Prints before/after report to terminal
  - Appends result to metrics.md
"""

import sys
import os
import cv2
import numpy as np
import pytesseract
from datetime import date

# Allow running from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from extraction.ocr.preprocess import preprocess_image

# ── Tesseract path (Windows) ──────────────────────────────────────────────────
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR        = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAMPLE_IMAGE    = os.path.join(BASE_DIR, "samples", "photographed_receipt_1.png")
OUTPUT_IMG      = os.path.join(BASE_DIR, "samples", "verified_preprocessed.png")
OUTPUT_TXT      = os.path.join(BASE_DIR, "samples", "ocr_comparison_results.txt")
METRICS_FILE    = os.path.join(BASE_DIR, "metrics.md")


def run_tesseract(img: np.ndarray) -> tuple[str, float]:
    """Run Tesseract on a numpy image array, return (text, avg_confidence)."""
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    words, conf_sum, word_count = [], 0.0, 0
    for i in range(len(data["text"])):
        word = data["text"][i].strip()
        conf = int(data["conf"][i])
        if conf > -1 and word:
            words.append(word)
            conf_sum += conf
            word_count += 1
    text = " ".join(words)
    avg_conf = conf_sum / word_count if word_count > 0 else 0.0
    return text, avg_conf


def main():
    print("=" * 60)
    print("  OCR PREPROCESSING IMPACT VERIFICATION")
    print("=" * 60)
    print(f"  Image : {SAMPLE_IMAGE}")
    print()

    # ── Load image ─────────────────────────────────────────────────────────────
    if not os.path.exists(SAMPLE_IMAGE):
        print(f"[ERROR] Sample image not found: {SAMPLE_IMAGE}")
        sys.exit(1)

    raw_bgr = cv2.imread(SAMPLE_IMAGE)
    if raw_bgr is None:
        print("[ERROR] cv2.imread returned None — check the file path.")
        sys.exit(1)

    # ── RUN 1: Raw image (greyscale for Tesseract, but NO preprocessing) ───────
    print(">> RUN 1 -- Raw image (no preprocessing) ...")
    raw_gray = cv2.cvtColor(raw_bgr, cv2.COLOR_BGR2GRAY)
    raw_text, raw_conf = run_tesseract(raw_gray)
    print(f"   Confidence : {raw_conf:.2f}%")
    print(f"   Words found: {len(raw_text.split())}")

    # ── RUN 2: Full preprocessing pipeline ────────────────────────────────────
    print()
    print(">> RUN 2 -- Preprocessed image (preprocess.py pipeline) ...")
    preprocessed = preprocess_image(raw_bgr)          # returns binary np array
    cv2.imwrite(OUTPUT_IMG, preprocessed)
    print(f"   Preprocessed image saved -> {OUTPUT_IMG}")
    pre_text, pre_conf = run_tesseract(preprocessed)
    print(f"   Confidence : {pre_conf:.2f}%")
    print(f"   Words found: {len(pre_text.split())}")

    # ── Compute delta ──────────────────────────────────────────────────────────
    delta = pre_conf - raw_conf
    pct_change = (delta / raw_conf * 100) if raw_conf > 0 else 0.0

    print()
    print("=" * 60)
    print("  SIDE-BY-SIDE COMPARISON")
    print("=" * 60)
    print(f"  Raw confidence         : {raw_conf:.2f}%")
    print(f"  Preprocessed confidence: {pre_conf:.2f}%")
    print(f"  Delta                  : {delta:+.2f} pp  ({pct_change:+.1f}%)")
    print()

    if delta >= 0:
        verdict = f"preprocessing MATCHES or IMPROVES confidence by {abs(pct_change):.1f}%"
        print(f"  [PASS] {verdict.upper()}")
        print()
        flag_note = ""
    else:
        params_to_tune = [
            "GaussianBlur kernel size (currently 5x5) — may over-blur fine text",
            "Canny thresholds (75, 200) — may mis-detect document edges",
            "adaptiveThreshold blockSize (21) / C (10) — may binarise poorly under bright spots",
            "medianBlur ksize (3) — try 1 (disable) for cleaner receipts",
        ]
        verdict = (f"preprocessing DEGRADES confidence by {abs(pct_change):.1f}% -- tuning needed")
        print(f"  [WARN] {verdict.upper()}")
        print()
        print("  OpenCV parameters that need adjustment:")
        for p in params_to_tune:
            print(f"    • {p}")
        flag_note = "\n  **Flagged parameters:** " + ", ".join(params_to_tune)

    # ── Write text comparison file ─────────────────────────────────────────────
    report = f"""OCR PREPROCESSING IMPACT — {SAMPLE_IMAGE}
Generated: {date.today()}
{'='*60}

RAW IMAGE
---------
Confidence : {raw_conf:.2f}%
Text       :
{raw_text}

PREPROCESSED IMAGE (preprocess.py)
-----------------------------------
Confidence : {pre_conf:.2f}%
Text       :
{pre_text}

{'='*60}
VERDICT: {verdict}{flag_note}
"""
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  Full comparison saved -> {OUTPUT_TXT}")
    print()

    # -- Append to metrics.md
    today = str(date.today())
    if delta >= 0:
        metrics_line = (
            f"| {today} | OCR Preprocessing (simplified) | Confidence Impact | "
            f"+{abs(pct_change):.1f}% | "
            f"Raw: {raw_conf:.1f}% -> Preprocessed: {pre_conf:.1f}%. "
            f"preprocessing MATCHES or IMPROVES confidence — no degradation |\n"
        )
    else:
        metrics_line = (
            f"| {today} | OCR Preprocessing | Confidence Impact | "
            f"{pct_change:.1f}% | "
            f"Raw: {raw_conf:.1f}% -> Preprocessed: {pre_conf:.1f}%. "
            f"preprocessing DEGRADES confidence by {abs(pct_change):.1f}% -- tuning needed |\n"
        )

    with open(METRICS_FILE, "a", encoding="utf-8") as f:
        f.write(metrics_line)
    print(f"  metrics.md updated -> {METRICS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
