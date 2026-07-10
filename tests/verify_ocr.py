from extraction.ocr.extract import extract_text_ocr
import sys
import json

def test_custom_image():
    # Change this to the path of your custom image!
    # For example: "samples/img_receipt_grocery.png"
    target_file =r"C:\Users\LENOVO\Downloads\WhatsApp Image 2026-06-17 at 3.15.25 PM.jpeg"
    
    print(f"Running OCR on: {target_file}...\n")
    
    try:
        result = extract_text_ocr(target_file)
        
        print(f"Overall Confidence: {result['average_confidence']:.2f}%")
        print("\n--- Extracted Text ---")
        print(result['text'])
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_custom_image()
