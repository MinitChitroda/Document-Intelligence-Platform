from PIL import Image, ImageDraw

def draw_flow_diagram():
    # Setup canvas size (high resolution for printing)
    width, height = 1200, 800
    img = Image.new("RGB", (width, height), color="#f8fafc") # Light Slate Slate 50
    draw = ImageDraw.Draw(img)

    # Theme Colors (Modern Slate & Teal)
    c_slate_800 = "#1e293b" # Primary dark
    c_teal_600  = "#0d9488" # Accent
    c_teal_500  = "#14b8a6"
    c_red_500   = "#ef4444" # Fail DLQ
    c_gray_400  = "#94a3b8" # Line color
    c_text_dark = "#0f172a"
    c_text_light= "#ffffff"

    # Define Node positions (x_center, y_center, width, height, label, color)
    nodes = {
        "upload":     (200, 100, 180, 60, "FastAPI Ingestion Gateway\n(SHA-256 Dedup)", c_slate_800),
        "kafka":      (200, 240, 180, 60, "Apache Kafka Queue\n(raw_documents topic)", c_slate_800),
        "consumer":   (200, 380, 180, 60, "Kafka Consumer\n(Classification)", c_slate_800),
        
        # Split Branches
        "native":     (500, 310, 180, 60, "Native Text Parser\n(PyMuPDF / Chunking)", c_teal_600),
        "ocr":        (500, 450, 180, 60, "OpenCV & Tesseract OCR\n(300 DPI Rendering)", c_teal_600),
        
        "qgate":      (800, 380, 180, 60, "Explicit Quality Gate\n(Rule Engine Check)", c_slate_800),
        
        "dlq":        (800, 520, 180, 60, "Dead Letter Queue\n(data/failed/ folder)", c_red_500),
        
        "postgres":   (1100, 240, 180, 60, "Bronze Landing DB\n(PostgreSQL status)", c_slate_800),
        "dbt":        (1100, 380, 180, 60, "dbt Gold Warehouse\n(SCD Type 2 Dimension)", c_slate_800),
        
        "qdrant":     (1100, 520, 180, 60, "Qdrant Vector DB\n(SentenceTransformers)", c_teal_600),
        "rag":        (1100, 660, 180, 60, "Groq LLM Generation\n(Llama 3.1 & Citations)", c_slate_800),
    }

    # Helper function to draw rounded rectangles
    def rounded_rect(draw, center_x, center_y, w, h, label, bg_color):
        left = center_x - w // 2
        top = center_y - h // 2
        right = center_x + w // 2
        bottom = center_y + h // 2
        
        # Draw box
        draw.rounded_rectangle([left, top, right, bottom], radius=8, fill=bg_color)
        
        # Calculate text position (approximate centering)
        lines = label.split("\n")
        total_h = len(lines) * 16
        start_y = center_y - total_h // 2
        
        for idx, line in enumerate(lines):
            line_w = len(line) * 6.5 # Approx char width
            draw.text((center_x - line_w // 2, start_y + idx * 16), line, fill=c_text_light)

    # Draw Connections (Lines & Arrows)
    def arrow(x1, y1, x2, y2):
        # Draw line
        draw.line([x1, y1, x2, y2], fill=c_gray_400, width=3)
        # Draw arrowhead
        if x1 == x2: # Vertical arrow
            if y2 > y1:
                draw.polygon([(x2-6, y2-8), (x2+6, y2-8), (x2, y2)], fill=c_gray_400)
            else:
                draw.polygon([(x2-6, y2+8), (x2+6, y2+8), (x2, y2)], fill=c_gray_400)
        elif y1 == y2: # Horizontal arrow
            if x2 > x1:
                draw.polygon([(x2-8, y2-6), (x2-8, y2+6), (x2, y2)], fill=c_gray_400)
            else:
                draw.polygon([(x2+8, y2-6), (x2+8, y2+6), (x2, y2)], fill=c_gray_400)

    # Ingestion flow connections
    arrow(200, 130, 200, 210) # API -> Kafka
    arrow(200, 270, 200, 350) # Kafka -> Consumer

    # Consumer splits to native/OCR
    draw.line([200, 410, 200, 450, 380, 450], fill=c_gray_400, width=3)
    arrow(380, 450, 410, 450) # To OCR
    
    draw.line([200, 410, 200, 310, 380, 310], fill=c_gray_400, width=3)
    arrow(380, 310, 410, 310) # To Native

    # Native/OCR to Quality Gate
    draw.line([590, 310, 680, 310, 680, 380], fill=c_gray_400, width=3)
    draw.line([590, 450, 680, 450, 680, 380], fill=c_gray_400, width=3)
    arrow(680, 380, 710, 380) # To Quality Gate

    # Quality Gate to DLQ / Curated Pipeline
    arrow(800, 410, 800, 490) # QGate -> DLQ (Fail)
    
    # QGate to Warehouse/Qdrant
    draw.line([890, 380, 980, 380, 980, 240], fill=c_gray_400, width=3)
    arrow(980, 240, 1010, 240) # To Bronze DB
    
    draw.line([890, 380, 980, 380, 980, 380], fill=c_gray_400, width=3)
    arrow(980, 380, 1010, 380) # To dbt Gold
    
    draw.line([890, 380, 980, 380, 980, 520], fill=c_gray_400, width=3)
    arrow(980, 520, 1010, 520) # To Qdrant Vector

    # Qdrant to RAG Generation
    arrow(1100, 550, 1100, 630) # Qdrant -> Groq

    # Draw Nodes
    for k, v in nodes.items():
        rounded_rect(draw, v[0], v[1], v[2], v[3], v[4], v[5])

    # Text annotations on arrows
    draw.text((215, 155), "Publish event", fill=c_text_dark)
    draw.text((215, 295), "Read event", fill=c_text_dark)
    draw.text((230, 320), "Text Native PDF", fill=c_text_dark)
    draw.text((230, 460), "Scanned PDF / Image", fill=c_text_dark)
    draw.text((815, 435), "[ FAIL ]", fill=c_red_500)
    draw.text((895, 360), "[ PASS ]", fill=c_teal_600)

    # Save PNG
    img.save("samples/flow_diagram.png")
    print("Successfully generated samples/flow_diagram.png")

if __name__ == "__main__":
    draw_flow_diagram()
