import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# ── Exhaustive Master Study Guide Content ────────────────────────────────────

MARKDOWN_CONTENT = """# Document Data Platform: Comprehensive System Explainer & Interview Guide

This guide is an exhaustive, production-grade study manual for the entire Document Data Platform. It details the system mechanics, mathematical principles, database schemas, parallel processing logic, and failure modes. Use this manual to master every technical detail and clear any architect-level interview.

---

## 1. Architectural Philosophy & Core Design

The platform is designed around a **75/25 functional split**: 75% Data Engineering (scalable ingestion, quality control, data warehousing, workflow orchestration, batch processing) and 25% AI Retrieval (vector databases, semantic similarity, and large language models). The primary design goals are:

* **Separation of Concerns**: Ingestion, processing, warehousing, and retrieval exist as separate micro-layers. Removing the vector store (RAG) layer leaves a complete, production-grade transactional and analytical data pipeline intact.
* **Cost-Efficient Self-Hosting**: To support deployment on a single `t3.medium` EC2 instance, all heavy infrastructure (Kafka, Airflow, Spark, Postgres, Qdrant) is self-hosted in Docker containers with strict memory limits and a host-level Swap configuration.
* **Lineage & Auditability**: Raw, processed, curated, and failed documents are stored in structured directories. Data is never deleted; changes are tracked historically using Slowly Changing Dimensions (SCD Type 2).

---

## 2. Ingestion & Duplicate Prevention (Idempotency)

The ingestion system ensures that duplicate files are rejected before consuming resources.

### 2.1 File Fingerprinting
When a user uploads a file, the platform does not trust the filename or upload timestamp. Instead, it reads the raw bytes of the file and calculates a **SHA-256 checksum**:
1. The file bytes are streamed into `hashlib.sha256()`.
2. The resulting hexadecimal digest (hash string) acts as a unique fingerprint.
3. This fingerprint is compared against the database. If the hash exists, the API skips processing and returns the existing Document ID.

### 2.2 Double-Layer Idempotency Guard
To ensure absolute safety, duplicate detection is implemented at two distinct boundary layers:
* **Layer 1 (FastAPI API)**: Dedupes synchronously at upload time. This saves storage and network overhead.
* **Layer 2 (Kafka Consumer)**: Before inserting a raw record into the Bronze landing tables, the consumer queries the transactional database using the Document ID. This protects the database from duplicate writes if Kafka offsets are replayed or reset.

---

## 3. Asynchronous Messaging (Kafka Broker)

* **Broker Configuration**: Kafka runs in self-hosted **KRaft mode** (no Zookeeper dependency) to reduce container overhead.
* **Topic Design**: Raw files are published to the `raw_documents` topic.
* **Partition Alignment**: The message key is set to the unique `document_id`. Kafka uses this key to compute the partition destination. This guarantees that all state updates for a specific document are processed in order by the same partition handler.
* **Decoupled API**: The FastAPI server handles the upload, saves the file to raw storage, commits a metadata record as `pending`, and offloads event publishing to a FastAPI `BackgroundTask`. This ensures the API response is returned immediately without waiting for Kafka.

---

## 4. Document Classification & Text Extraction

Once the consumer pulls an event, the system determines the document classification and routes it to the appropriate extraction pipeline:

### 4.1 Native vs. Scanned Classification
The system inspects the file extension and runs a density check:
1. If the file is an image (`.png/.jpg/.jpeg`), it is classified as a scanned image.
2. If the file is a PDF, the system opens it using PyMuPDF and extracts text characters per page.
3. If the average character count per page is **less than 50**, it is classified as a **Scanned PDF** (scanned/image-only).
4. If it contains 50 or more characters per page, it is classified as a **Text-Native PDF**.

### 4.2 Text-Native Extraction & Chunking
For Text-Native PDFs, text is extracted page-by-page. A cleaner utility normalizes whitespace, removes trailing page indicators, and extracts text content.
* **Chunking Algorithm**: The text is split into chunks of **400 words with a 50-word overlap**. 
* **Overlapping Rationale**: The 50-word overlap preserves semantic context. If a key fact is split across page or block boundaries, the overlap ensures that the semantic meaning is captured in the vector database.

### 4.3 Advanced OCR Image Preprocessing (OpenCV & Tesseract)
For Scanned PDFs and images, the platform uses an advanced computer vision pipeline:
1. **Resolution Scaling**: PyMuPDF renders each PDF page to an image pixmap at a `2.0` zoom matrix, producing a high-resolution image (~300 DPI equivalent) to ensure small text remains legible.
2. **Grayscale Conversion**: The RGB image is converted to grayscale to reduce channels and isolate text intensity.
3. **Moment-Based Deskewing**: The system detects text skew using image moments via `cv2.minAreaRect()`. It calculates the skew angle and corrects it using rotation matrices.
   * *Safe Rotation Guard*: Rotation is only applied if the detected skew is between 0.5° and 20° to avoid corrupting vertical text layouts.
4. **Tesseract OCR Output**: PyTesseract runs OCR and returns word coordinates, text, and confidence scores. It calculates the page's average confidence, ignoring layout blocks (marked as `-1` by Tesseract).

---

## 5. The Quality Gate & Dead Letter Queue (DLQ)

Every document must pass the Quality Gate rules before entering the curated collection:

* **Rule 1 (Length check)**: The extracted text length must be at least 50 characters.
* **Rule 2 (Confidence check)**: If the document went through OCR, the average word confidence must be at least 60%.

### Ingestion Status Mapping
* **Curated (Success)**: The file is copied to `data/curated/` and its database status is updated to `curated`.
* **Failed (Dead Letter Queue)**: The file is moved to `data/failed/` and marked as `failed` with the error reason recorded. This acts as a Dead Letter Queue (DLQ), allowing operators to inspect and fix failed uploads without disrupting the active pipeline.

---

## 6. Database Architecture & Data Warehousing

The database uses a multi-layer schema architecture:

### 6.1 Transactional Gatekeeper Table (`documents`)
Lives in the `idempotency` schema. It acts as the gateway to the pipeline:
* `document_id` (VARCHAR, PK): Unique Document UUID.
* `file_hash` (VARCHAR, UNIQUE INDEX): SHA-256 hash.
* `status` (VARCHAR): Ingestion state (`pending`, `curated`, `failed`).
* `failure_reason` (VARCHAR, Nullable): Reason for Quality Gate failure.
* `created_at` (TIMESTAMP): Upload timestamp.

### 6.2 Landing/Staging Table (`bronze_documents`)
Lives in the landing schema. Tracks metadata versions:
* `id` (INTEGER, PK, Autoincrement): Internal record ID.
* `document_id` (VARCHAR, Index): Business UUID.
* `file_hash` (VARCHAR, Index): SHA-256 hash.
* `version` (INTEGER): Version number (starts at 1).
* `status` (VARCHAR): Quality status (`pending`, `curated`, `failed`).
* `source_type` (VARCHAR): Classified type (`text_native`, `scanned_pdf`, `csv`, `image`).
* `ocr_confidence` (FLOAT, Nullable): Word-confidence average.
* `page_count` (INTEGER, Nullable): Pages count.
* `created_at` (TIMESTAMP): Record creation timestamp.

### 6.3 Warehouse Gold Layer (dbt Models)
Transformations run in the analytical database schema:

#### Table: `dim_document` (SCD Type 2 Dimension)
Tracks the historical versions of documents. Uses SQL window functions to manage active states:
* `document_id` (VARCHAR): Business UUID.
* `file_hash` (VARCHAR): SHA-256 hash.
* `version` (INTEGER): Version number.
* `status` (VARCHAR): Current quality status.
* `source_type` (VARCHAR): Document classification.
* `valid_from` (TIMESTAMP): When this version became active.
* `valid_to` (TIMESTAMP): When this version was superseded (defaults to `9999-12-31`).
* `is_current` (BOOLEAN): True if this is the active, latest version.

#### Table: `fact_document_processing` (Fact Table)
Stores numeric metrics for pipeline analytics:
* `processing_id` (VARCHAR, PK): MD5 hash of staging load keys.
* `document_id` (VARCHAR): Links to the document dimension.
* `ocr_confidence` (FLOAT): Average OCR confidence.
* `page_count` (INTEGER): Page count.
* `processing_timestamp` (TIMESTAMP): Recording timestamp.

---

## 7. Slowly Changing Dimensions (SCD Type 2) & Reprocessing

### Concept
SCD Type 2 dimensions do not overwrite old data when a record changes. Instead, they close the old record by setting a termination date (`valid_to`) and insert a new active record (where `is_current = True`).

### Detailed SQL Query Analysis
dbt compiles the history from the Bronze landing table using window functions:
* **`LEAD()`**: Inspects the next record version's creation timestamp and sets it as the `valid_to` of the current record. If no next version exists, it defaults to the open-ended date `9999-12-31`.
* **`ROW_NUMBER()`**: Orders the versions of each document in descending order. The row with rank `1` is marked as the active version (`is_current = True`).

### Concrete Example Walkthrough
1. **Initial Upload (Version 1)**:
   A user uploads a scanned invoice. The OCR reads the text with a **61.2%** average confidence score.
   * `dim_document` row:
     ```text
     doc_id: inv_99 | version: 1 | ocr_conf: 61.2% | valid_from: 12:00:00 | valid_to: 9999-12-31 | is_current: True
     ```
2. **Reprocessing Run (Version 2)**:
   A nightly Spark job reprocesses the document. The OCR confidence increases to **81.0%**. A new metadata row is committed.
   * The dbt staging views compile the changes. The warehouse updates to:
     ```text
     [Row 1] doc_id: inv_99 | version: 1 | ocr_conf: 61.2% | valid_from: 12:00:00 | valid_to: 03:00:00 | is_current: False
     [Row 2] doc_id: inv_99 | version: 2 | ocr_conf: 81.0% | valid_from: 03:00:00 | valid_to: 9999-12-31 | is_current: True
     ```

---

## 8. Batch Reprocessing (PySpark Engine)

When extraction rules or OCR models are updated, we must re-evaluate the historical corpus. A nightly batch job runs in PySpark (local mode):
1. **Fetch Active Rows**: Spark queries PostgreSQL for the latest active versions of curated documents (`is_current = True`).
2. **Parallelize**: The list of documents is parallelized across Spark executor partitions via `sparkContext.parallelize(data)`.
3. **Map Transformation**: A mapping function, `reprocess_document()`, runs on the executors. It recalculates the document's metrics (e.g. simulating a new OCR version).
4. **Version Bumping**: If the new metric differs from the old by more than a threshold (>0.5% difference), the driver inserts a new version row into the landing table. The next dbt run automatically updates the SCD Type 2 tables.

---

## 9. Orchestration & Workflow DAGs (Airflow)

The ingestion pipeline is managed by Airflow:

### Ingestion DAG (`ingestion_dag`)
* **`sense_pending_documents`**: Queries the Bronze database for documents in a `pending` state, filtering by execution date to support backfilling.
* **`branch_on_source_type`**: Evaluates the source types of pending documents. It returns the task IDs of the matching branches: `extract_text_pdf`, `extract_ocr`, or `extract_csv`.
* **Execution Branches**: The tasks run the extraction and Quality Gate logic in parallel based on source type.
* **Error Tolerances**: Tasks are configured with `retries=3`, `retry_delay=1 minute`, and `retry_exponential_backoff=True` to handle transient network or resource errors.

---

## 10. Vector Embeddings, Storage, & RAG Query Flow

### 10.1 Vector Embeddings & Similarity Metric
* **Embedding Model**: Chunks are processed using the `all-MiniLM-L6-v2` SentenceTransformer model, converting text into a **384-dimensional dense vector**.
* **Similarity Metric**: Stored in a Qdrant collection using **Cosine Distance**. The similarity score ranges from -1.0 to 1.0, where 1.0 represents identical semantic alignment.

### 10.2 Deterministic Indexing
To prevent duplicate points, Qdrant point IDs are generated deterministically using a UUID5 namespace hash of the document ID, page number, and chunk index:
`uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}-{page_number}-{chunk_index}")`
This ensures that re-running the embedding script updates the vector points rather than creating duplicates.

### 10.3 Query & LLM Generation Flow
1. **Search**: The user's text question is converted into a 384-dimensional vector and compared against stored vectors in Qdrant. The top 5 matching text segments are retrieved.
2. **Context Formatting**: The retrieved segments are compiled into a structured context prompt:
   ```text
   --- Context Chunk 1 ---
   Document ID: 222baa3b-029d-49a1-afb0-01eb5fdd1de8
   Page: 0
   Text: "Standard Shipping: Takes 3 to 5 business days..."
   ```
3. **Generation**: The prompt is sent to the **Groq API (Llama 3.1 8B)** with strict instructions to answer *only* using the provided context and to cite the document ID and page number for every fact.
4. **Citations UI**: The Streamlit interface displays the generated answer and lists the cited sources in collapsible cards.

---

## 11. Interview Masterclass & Failure Scenarios

### Q1: How does your pipeline prevent duplicate processing if a user re-uploads a renamed file?
> "We use content-addressed idempotency. When a file is uploaded, the API computes a SHA-256 hash of its binary data. This hash is compared against the database. If it exists, the upload is rejected immediately. Renaming the file does not change its binary content, so the hash remains identical and the duplicate is skipped."

### Q2: Why did you self-host the stack on a single EC2 instance instead of using managed services?
> "A managed services stack on AWS (such as MWAA, MSK, and EMR) would cost around $400-500/month. Because this is a prototype, I designed a Docker Compose stack configured with strict memory limits on a single t3.medium EC2 instance, supplemented by a 2GB swap space to handle memory spikes. This approach replicates the production architecture at a fraction of the cost, making it a cost-conscious engineering decision."

### Q3: What happens if a document fails during extraction or quality gating?
> "If a document fails validation (e.g. low OCR confidence or short text length), the database status is marked as 'failed' with the error reason recorded. The physical file is moved to a quarantine directory, which functions as a Dead Letter Queue (DLQ). The pipeline continues running gracefully without raising a crash, allowing operators to inspect and fix failed uploads."

### Q4: Explain the difference between your transactional DB and your analytical warehouse.
> "The transactional database is optimized for quick writes and transaction safety. It acts as the gateway to the pipeline. The analytical warehouse is a star-schema model built in PostgreSQL using dbt. It normalizes dimensions (dim_document, dim_source_type, dim_pipeline_run) and maps processing events to a central fact table (fact_document_processing), using SCD Type 2 windowing to preserve history."

### Q5: How does your system support backfilling and scheduling?
> "The pipeline is managed by Airflow. The ingestion DAG uses execution dates to filter pending documents. This allows us to re-run the pipeline for past dates (backfilling) without reprocessing newer data. It is scheduled to run daily, but can be triggered manually for batch runs."
"""

# ── ReportLab PDF Builder ────────────────────────────────────────────────────

def create_study_guide_pdf(filename="STUDY_GUIDE.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=45, leftMargin=45,
        topMargin=50, bottomMargin=50
    )
    
    styles = getSampleStyleSheet()
    
    # Premium Palette
    primary_color = colors.HexColor("#111827") # Dark slate
    accent_color = colors.HexColor("#0f766e")  # Teal Accent
    text_color = colors.HexColor("#374151")    # Charcoal body text
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=primary_color,
        spaceAfter=15
    )
    
    h1_style = ParagraphStyle(
        'DocH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=accent_color,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'DocH2',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=13,
        textColor=primary_color,
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=text_color,
        spaceAfter=6
    )

    code_style = ParagraphStyle(
        'DocCode',
        parent=styles['Code'],
        fontName='Courier',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#7c2d12"),
        spaceAfter=6
    )
    
    def md_to_html(text):
        escaped = text.replace("<", "&lt;").replace(">", "&gt;")
        parts = escaped.split("**")
        new_parts = []
        for idx, part in enumerate(parts):
            if idx % 2 == 1:
                new_parts.append(f"<b>{part}</b>")
            else:
                new_parts.append(part)
        return "".join(new_parts)
        
    story = []
    
    story.append(Paragraph("📖 DOCUMENT DATA PLATFORM: SYSTEM EXPLAINER", title_style))
    story.append(Paragraph("A study guide for understanding end-to-end data ingestion, database schemas, and RAG query flows.", body_style))
    story.append(Spacer(1, 10))
    
    lines = MARKDOWN_CONTENT.split("\n")
    in_code_block = False
    code_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith("```"):
            if in_code_block:
                code_text = "\n".join(code_lines)
                code_text = code_text.replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(f"<pre>{code_text}</pre>", code_style))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue
            
        if in_code_block:
            code_lines.append(line)
            continue
            
        if stripped.startswith("# "):
            story.append(Spacer(1, 15))
            story.append(Paragraph(md_to_html(stripped[2:]), title_style))
        elif stripped.startswith("## "):
            story.append(Paragraph(md_to_html(stripped[3:]), h1_style))
        elif stripped.startswith("### "):
            story.append(Paragraph(md_to_html(stripped[4:]), h2_style))
        elif stripped.startswith("* **") or stripped.startswith("- **") or stripped.startswith("* ") or stripped.startswith("- "):
            bullet_content = stripped[2:]
            story.append(Paragraph(f"• {md_to_html(bullet_content)}", body_style))
        elif stripped.startswith("1. ") or stripped.startswith("2. ") or stripped.startswith("3. ") or stripped.startswith("4. ") or stripped.startswith("5. "):
            story.append(Paragraph(md_to_html(stripped), body_style))
        elif stripped.startswith("> "):
            quote_text = stripped[2:].replace('"', '')
            quote_style = ParagraphStyle(
                'QuoteStyle',
                parent=body_style,
                leftIndent=15,
                textColor=colors.HexColor("#4b5563"),
                fontName='Helvetica-Oblique'
            )
            story.append(Paragraph(md_to_html(quote_text), quote_style))
        elif stripped == "---":
            story.append(Spacer(1, 5))
            story.append(Table([[""]], colWidths=[520], rowHeights=[1], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#e5e7eb")),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ])))
            story.append(Spacer(1, 10))
        elif stripped:
            story.append(Paragraph(md_to_html(stripped), body_style))
            
    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor("#9ca3af"))
        page_num = canvas.getPageNumber()
        canvas.drawRightString(612 - 45, 30, f"Page {page_num}")
        canvas.drawString(45, 30, "Document Data Platform — System Explainer & Study Guide")
        canvas.setStrokeColor(colors.HexColor("#e5e7eb"))
        canvas.setLineWidth(0.5)
        canvas.line(45, 742, 612 - 45, 742)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"Successfully generated {filename}")

if __name__ == "__main__":
    # Write the markdown file version as well
    with open("STUDY_GUIDE.md", "w", encoding="utf-8") as f:
        f.write(MARKDOWN_CONTENT)
    print("Successfully generated STUDY_GUIDE.md")
    create_study_guide_pdf()
