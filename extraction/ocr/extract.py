import fitz
import numpy as np
import cv2
import pytesseract
import os
from extraction.ocr.preprocess import preprocess_image

# Explicitly set path for Windows winget installations (fallback if not in PATH)
tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(tesseract_path):
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

def extract_text_ocr(pdf_path: str) -> dict:
    """
    Extracts text from a scanned PDF using Tesseract OCR.
    Converts PDF pages to images using PyMuPDF, preprocesses them with OpenCV,
    and runs OCR.
    
    Returns a dictionary with:
        - 'text': combined extracted text
        - 'average_confidence': average OCR confidence across all words
        - 'pages': list of dicts with page-level text and confidence
    """
    doc = fitz.open(pdf_path)
    
    total_confidence = 0.0
    total_words = 0
    pages_data = []
    
    for i, page in enumerate(doc):
        # Render page to an image pixmap
        # matrix = fitz.Matrix(2.0, 2.0) for 2x zoom (300dpi equivalent) if better quality is needed
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        
        # Convert pixmap to numpy array (RGB)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        
        # Preprocess the image
        processed_img = preprocess_image(img)
        
        # We can optionally save the image here for debugging/verification
        if i == 0:
            cv2.imwrite("debug_preprocessed_page0.png", processed_img)
            
        # Run Tesseract OCR and get data (includes confidence per word)
        # Output dict includes 'text', 'conf' (confidence from 0 to 100)
        data = pytesseract.image_to_data(processed_img, output_type=pytesseract.Output.DICT)
        
        page_text = ""
        page_conf_sum = 0.0
        page_words = 0
        
        for j in range(len(data['text'])):
            word = data['text'][j].strip()
            conf = int(data['conf'][j])
            
            # Tesseract uses -1 for layout blocks; only count actual text words > 0
            if conf > -1 and word:
                page_text += word + " "
                page_conf_sum += conf
                page_words += 1
                
        # Calculate average confidence for the page
        page_avg_conf = (page_conf_sum / page_words) if page_words > 0 else 0.0
        
        pages_data.append({
            "page_num": i + 1,
            "text": page_text.strip(),
            "confidence": page_avg_conf
        })
        
        total_confidence += page_conf_sum
        total_words += page_words
        
    overall_avg_conf = (total_confidence / total_words) if total_words > 0 else 0.0
    
    # Combine text from all pages
    full_text = "\n".join([p["text"] for p in pages_data])
    
    return {
        "text": full_text,
        "average_confidence": overall_avg_conf,
        "pages": pages_data
    }
