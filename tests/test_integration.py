import os
import requests
import time

def upload_samples():
    samples_dir = "samples"
    files = [
        "text_financial_report.pdf",
        "scanned_financial_report.pdf",
        "photographed_spreadsheet.jpg",
        "photographed_receipt_1.png",
        "photographed_receipt_2.jpeg",
        "corrupted_mock.pdf"
    ]
    
    url = "http://localhost:8000/upload"
    
    print("Uploading samples to API...")
    for file in files:
        path = os.path.join(samples_dir, file)
        if not os.path.exists(path):
            print(f"Skipping {file} - not found")
            continue
            
        with open(path, "rb") as f:
            files_dict = {"file": (file, f, "application/pdf" if file.endswith(".pdf") else "image/jpeg")}
            try:
                response = requests.post(url, files=files_dict)
                print(f"{file}: {response.status_code} - {response.json()}")
            except Exception as e:
                print(f"Failed to upload {file}: {e}")

if __name__ == "__main__":
    upload_samples()
