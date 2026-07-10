import fitz

file_path = r"d:\PYTHON PROJECTS\DATA ENGINEERING PROJECT\data\raw\hehe\hehe_99388ef54ea961d95d2c20fe8265a91035d6feba7b8a9e13f3499139d5f93dde.pdf"
doc = fitz.open(file_path)

count = 0
for page in doc:
    text = page.get_text("text", sort=True)
    count += text.count("@gmail.com") + text.count("@") # quick heuristic
    print(f"Page {page.number+1} has ~ {text.count('@')} emails")

print(f"Total estimated students: {count}")
