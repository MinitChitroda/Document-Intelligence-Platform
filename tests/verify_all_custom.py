import os
import cv2
import pytesseract
from pytesseract import Output
import numpy as np
import time

# Make sure pytesseract knows where tesseract is
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Import our preprocess function
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from extraction.ocr.preprocess import preprocess_image

def get_ocr_data(image: np.ndarray):
    start_time = time.time()
    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    text = pytesseract.image_to_string(image)
    end_time = time.time()
    
    confidences = [int(c) for c in data['conf'] if c != '-1']
    conf = sum(confidences) / len(confidences) if confidences else 0.0
    return conf, text, end_time - start_time

def test_files():
    samples_dir = "samples"
    files_to_test = [
        "photographed_spreadsheet.jpg",
        "photographed_receipt_1.png",
        "photographed_receipt_2.jpeg"
    ]
    
    for filename in files_to_test:
        path = os.path.join(samples_dir, filename)
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue
            
        print(f"\n--- Processing {filename} ---")
        
        img = cv2.imread(path)
        if img is None:
            print(f"Failed to load image: {path}")
            continue
            
        # 1. Without preprocessing
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        conf_without, text_without, time_without = get_ocr_data(gray)
        cv2.imwrite(os.path.join(samples_dir, f"debug_{filename}_before.png"), gray)
        with open(os.path.join(samples_dir, f"ocr_{filename}_before.txt"), "w", encoding="utf-8") as f:
            f.write(text_without)
            
        # 2. With preprocessing
        processed = preprocess_image(img)
        conf_with, text_with, time_with = get_ocr_data(processed)
        cv2.imwrite(os.path.join(samples_dir, f"debug_{filename}_after.png"), processed)
        with open(os.path.join(samples_dir, f"ocr_{filename}_after.txt"), "w", encoding="utf-8") as f:
            f.write(text_with)
            
        print(f"Confidence WITHOUT preprocessing: {conf_without:.2f}%")
        print(f"Confidence WITH preprocessing:    {conf_with:.2f}%")
        print(f"Difference:                       {conf_with - conf_without:.2f}%")
        print(f"Execution Time:                   {time_without + time_with:.2f}s (Before: {time_without:.2f}s, After: {time_with:.2f}s)")

if __name__ == "__main__":
    test_files()
