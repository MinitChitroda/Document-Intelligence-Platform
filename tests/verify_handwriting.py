from extraction.ocr.extract import extract_text_ocr
import cv2
import os

def test():
    # Path to the image
    target = r"C:\Users\LENOVO\Downloads\fees a.jpeg"
    
    if not os.path.exists(target):
        print(f"File not found: {target}")
        return
        
    print(f"Running Tesseract OCR on: {target}")
    
    # Run the standard OCR pipeline
    result = extract_text_ocr(target)
    
    print("\n--- OCR Extraction Result ---")
    print(result['text'])
    print(f"\nModel Confidence Score: {result['average_confidence']:.2f}%")

if __name__ == "__main__":
    test()
