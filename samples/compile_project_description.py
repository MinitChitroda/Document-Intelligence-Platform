import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# ── Exhaustive Technical Case Study & System Reference Manual ──────────────

MARKDOWN_CONTENT = """# Technical Case Study: Document Data Platform
**A Production-Grade, Idempotent Document Ingestion, Analytical Warehousing, and Retrieval System**

---

## 1. Executive Summary
This platform is a fault-tolerant, idempotent document data platform designed to process multi-format files (text PDFs, scanned PDFs, images, plain text) at scale. It ingests documents asynchronously, runs them through custom computer vision and text extraction pipelines, subjects them to explicit quality validations, compiles a multi-layer SQL warehouse with Slowly Changing Dimensions (SCD Type 2), and indexes them into Qdrant for semantic search (RAG) queries.

To keep hosting overhead low, the system is designed to run in Docker on a single t3.medium EC2 instance ($30/month) rather than using expensive AWS managed services (which run $400-500/month). It splits functionalities into **75% Data Engineering** and **25% AI/RAG** so that database integrity, lineage tracking, and warehouse operations are fully decoupled from downstream AI models.

---

## 2. Technical Architecture & End-to-End System Flow

The diagram below maps a document's lifecycle from initial API upload through extraction branches, quality gate validations, warehouse compilations, and downstream retrieval indexing:

![System Architecture Flowchart](samples/flow_diagram.png)

---

## 3. Tech Stack & Trade-Off Analysis

| Layer | Chosen Technology | Alternatives Considered | Trade-Off Rationale |
|---|---|---|---|
| **Ingestion API** | FastAPI | Flask / Express.js | FastAPI provides native asynchronous execution, automatic OpenAPI schema generation, and lightweight background task execution. |
| **Event Broker** | Apache Kafka (KRaft) | AWS MSK / ZooKeeper-managed Kafka | Self-hosting Kafka in KRaft (Raft Metadata) mode removes ZooKeeper. This saves significant JVM container RAM overhead on our single EC2 instance, uses the modern industry-standard consensus protocol, and consolidates monitoring to native Kafka metrics. |
| **Database Layer** | PostgreSQL | MySQL / SQLite | PostgreSQL is used for both transactional operations (idempotency checking) and as our analytical data warehouse, offering advanced window functions and compatibility with dbt. |
| **Data Warehousing** | dbt (data build tool) | Raw SQL / Stored Procedures | dbt enables version-controlled, modular SQL transformations with automated testing (not-null, uniqueness, relationships) and auto-generated data lineage. |
| **Batch Reprocessing**| Apache Spark (Local Mode) | AWS EMR / Pandas | Spark parallelizes reprocessing across host CPU cores via RDD transformations. This provides a scalable template for distributed clustering without the cost of AWS EMR. |
| **Orchestration** | Apache Airflow | Prefect / Cron | Airflow manages complex DAG dependencies with native support for task retries, backfilling historic data, and conditional execution branching. |
| **Vector Database** | Qdrant | Pinecone / Milvus | Qdrant provides a fast, self-hosted vector database with a clean REST API and payload filtering capabilities, running with a low memory footprint. |
| **LLM Inference** | Groq API (Llama 3.1 8B) | Local LLM / OpenAI | Groq provides sub-second LLM inference latency via their LPU inference engine, keeping API execution times low. |

---

## 4. In-Depth Working: What, How, and Why

### 4.1 Ingestion & Idempotency Check
* **What**: Validates and accepts file uploads.
* **How**: The FastAPI server reads raw file bytes, computes a SHA-256 hash checksum, and queries the transactional `documents` database table. If the hash exists, it returns a `skipped_duplicate` status. If new, it saves the file as `data/raw/<hash><ext>` and commits a metadata row with status `pending`.
* **Why**: Content-addressed deduplication avoids using filenames (which are easily changed). Doing this synchronously at the gateway prevents duplicate storage, compute, and database writes.

### 4.2 Kafka Broker Queueing
* **What**: Buffers ingestion events for asynchronous worker execution.
* **How**: A FastAPI background task publishes a JSON event (containing Document ID, filename, and content hash) to the Kafka topic `raw_documents`, partitioning the message by using the `document_id` as the key.
* **Why**: Using a queue decouples the API from slow extraction workers. Key-based partitioning guarantees that all state updates for a single document are processed in order by the same partition handler. KRaft mode is used to remove ZooKeeper, saving JVM container RAM on our single host.

### 4.3 Classification & Extraction
* **What**: Classifies files and extracts text.
* **How**: The Kafka consumer classifies PDFs by character density using PyMuPDF: if the average character count per page is less than 50, it is classified as a scanned image PDF; otherwise, it is a text-native PDF.
  * **Text-Native Branch**: PyMuPDF extracts text directly, cleans running headers and page numbers, and chunks the text into 400-word segments with a 50-word overlap.
  * **Scanned/Image Branch**: PDF pages are rendered to images at 2x resolution (300 DPI equivalent). OpenCV converts them to grayscale and corrects skew via image moments. PyTesseract OCR processes the image, returning extracted text and a word-level average confidence score.
* **Why**: Scanned PDFs are just images inside a PDF wrapper; direct extraction returns empty strings. Preprocessing improves OCR accuracy, while a 50-word chunk overlap preserves context across boundaries.

### 4.4 The Quality Gate & Dead Letter Queue (DLQ)
* **What**: Governs extraction quality before warehousing and vector indexing.
* **How**: The engine validates extracted text: (1) text length must be at least 50 characters, and (2) OCR average confidence must be 60% or higher.
  * **Pass**: File is copied to `data/curated/` and marked as `curated` in the database.
  * **Fail**: File is copied to `data/failed/` and marked as `failed`.
* **Why**: Prevents dirty data (unreadable OCR, empty PDFs) from corrupting the warehouse or Qdrant search indices. The failed directory functions as a Dead Letter Queue (DLQ) for operator review.

---

## 5. Detailed Database & Storage Architecture

### 5.1 The Medallion Architecture (Bronze, Silver, Gold)
In data engineering, Bronze, Silver, and Gold refer to layers of the **Medallion Architecture**. This is a design pattern used to clean, organize, and structure data step-by-step as it flows through a pipeline:
* **🥉 The Bronze Layer (Raw Landing)**: The raw landing zone where data is stored exactly as it arrives from Kafka. We keep a raw, unchanged copy of our data so that if our extraction rules change in the future, we can reprocess the original files from scratch without losing anything. In our database, this is the `public.bronze_documents` table.
* **🥈 The Silver Layer (Cleaned & Validated)**: The layer where data is cleaned, conformed, and validated. In our project, this is represented by our **Quality Gate** rules (checking if text length > 50 and OCR confidence > 60%). Only conformed, healthy documents pass this gate.
* **🥇 The Gold Layer (Analytical Warehouse)**: The final reporting layer. The conformed data is modeled into a **Star Schema** (Dimension and Fact tables) optimized for dashboards, metrics, and BI tools. Dashboards shouldn't query raw, messy tables directly because it slows down performance. The Gold layer provides pre-modeled, fast-querying tables (like `gold.dim_document` and `gold.fact_document_processing`).

### 5.2 Physical Storage: Decoupling Database from Data Lake
A key architectural feature of this platform is the complete separation between **structural metadata** and **raw document text**:
* **The Data Lake (File-System / S3)**: Massive raw texts and physical files are stored inside a structured folder hierarchy (S3 buckets or Docker-mounted volumes):
  * `data/raw/` (or AWS S3 prefix `raw/`): Immutable storage of raw uploaded files, named using their SHA-256 hash.
  * `data/curated/` (or AWS S3 prefix `curated/`): Cleaned files that successfully passed the Quality Gate.
  * `data/failed/` (or AWS S3 prefix `failed/`): Quarantined files (DLQ) that failed validation.
* **The Relational Catalog (PostgreSQL)**: The PostgreSQL instance (`document_platform`) does **not** store raw text contents. It only hosts structural metadata, extraction logs, OCR confidence scores, and status flags.
* **Why this design matters**: Storing millions of raw document texts directly inside relation tables causes index bloat, increases query latencies, complicates SQL migrations, and inflates relational database backup sizes. By offloading files to an object-storage data lake (S3) and indexing metadata in PostgreSQL, we optimize both performance and cost.

### 5.3 Transactional Layer (Idempotency Table)
This table acts as the gatekeeper, ensuring write safety and deduplication.

#### Table: `public.documents`
* **`document_id`** (VARCHAR, Primary Key): Unique UUIDv4 assigned to the document on ingestion.
* **`file_hash`** (VARCHAR, Unique Index): SHA-256 hash of the raw content bytes. Used to perform instant synchronous lookup.
* **`status`** (VARCHAR): Processing state (`pending`, `curated`, `failed`).
* **`failure_reason`** (VARCHAR, Nullable): Explains Quality Gate failures (e.g. `insufficient_text_length`).
* **`created_at`** (TIMESTAMP WITH TIME ZONE): Ingestion timestamp.

### 5.3 Staging Layer (Bronze Table)
This table stores raw metadata and extraction metrics for dbt ingestion.

#### Table: `public.bronze_documents`
* **`id`** (INTEGER, Primary Key, Autoincrement): Staging surrogate key.
* **`document_id`** (VARCHAR, Index): Link back to the transactional table.
* **`file_hash`** (VARCHAR, Index): SHA-256 hash.
* **`version`** (INTEGER): Tracking version (starts at 1, bumped on reprocessing).
* **`status`** (VARCHAR): State of the document (`curated`, `failed`, `pending`).
* **`source_type`** (VARCHAR): Classified type (`text_native`, `scanned_pdf`, `csv`, `image`).
* **`ocr_confidence`** (FLOAT, Nullable): Tesseract confidence average.
* **`page_count`** (INTEGER, Nullable): Total pages extracted.
* **`created_at`** (TIMESTAMP WITH TIME ZONE): Database landing timestamp.

### 5.4 Analytical Layer (Gold Schema - dbt Marts)
These tables are compiled by dbt under the `gold` schema:

#### Table: `gold.dim_document` (SCD Type 2 Dimension)
Tracks every historical version of a document:
* **`document_id`** (VARCHAR): Links processing events to the document.
* **`file_hash`** (VARCHAR): SHA-256 hash.
* **`version`** (INTEGER): Incremental version number.
* **`status`** (VARCHAR): Quality gate outcome.
* **`source_type`** (VARCHAR): Document classification.
* **`valid_from`** (TIMESTAMP): When this version became active.
* **`valid_to`** (TIMESTAMP): When this version was superseded (defaults to `9999-12-31`).
* **`is_current`** (BOOLEAN): True if this is the active, latest version.

#### Table: `gold.fact_document_processing` (Fact Table)
Stores numeric processing metrics for analytical charts:
* **`processing_id`** (VARCHAR, Primary Key): MD5 hash of staging load keys.
* **`document_id`** (VARCHAR): Reference to the document dimension.
* **`ocr_confidence`** (FLOAT): Average OCR confidence.
* **`page_count`** (INTEGER): Page count.
* **`processing_timestamp`** (TIMESTAMP): Timestamp of the run.

---

## 6. Slowly Changing Dimensions (SCD Type 2) & Window Functions

### Concept
When a document is updated (e.g. Spark re-runs OCR with a better model), we do not overwrite the existing record in the analytical warehouse. Instead, we close the active period of the old record and insert a new active record.

### The dbt SQL Logic
dbt builds `dim_document` using PostgreSQL window functions:
* **`LEAD()`** partition by `document_id` order by `version` ASC: evaluates if a subsequent version exists. If found, its `created_at` timestamp becomes the `valid_to` date of the current row; otherwise, it is left open-ended (`9999-12-31`).
* **`ROW_NUMBER()`** partition by `document_id` order by `version` DESC: ranks rows. The rank `1` indicates the newest version, setting `is_current = True`.

### Example Transition Table
1. **Initial Upload (Version 1)**:
   A user uploads a scanned invoice. The OCR reads the text with a **61.2%** average confidence score.
   
   | document_id | file_hash | version | status | valid_from | valid_to | is_current |
   |---|---|---|---|---|---|---|
   | `inv_1` | `hash_abc` | 1 | `curated` | `12:00:00` | `9999-12-31` | `True` |

2. **Reprocessing Run (Version 2)**:
   A nightly Spark job reprocesses the document. The OCR confidence increases to **81.0%**. A new metadata row is committed.
   * Staging views update, and the warehouse dimensions close out Version 1:
   
   | document_id | file_hash | version | status | valid_from | valid_to | is_current |
   |---|---|---|---|---|---|---|
   | `inv_1` | `hash_abc` | 1 | `curated` | `12:00:00` | `03:00:00` | `False` |
   | `inv_1` | `hash_abc` | 2 | `curated` | `03:00:00` | `9999-12-31` | `True` |

---

## 7. Downstream RAG Query & Citation Flow

### 7.1 Embedding & Vector Storage
* **Embedding Model**: Text chunks from curated documents are encoded using the `all-MiniLM-L6-v2` transformer model, producing 384-dimensional dense vectors.
* **Vector DB**: Chunks are stored in a Qdrant collection named `document_chunks`.
* **Cosine Similarity**: Vector matching uses Cosine Similarity (from -1.0 to 1.0) to evaluate semantic overlap.
* **Deterministic Point IDs**: To prevent duplicate chunks in Qdrant, point IDs are generated using a deterministic UUID5 hash of the Document ID, page number, and chunk index:
  `uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}-{page_number}-{chunk_index}")`. Re-running the pipeline updates the existing vector points instead of inserting duplicates.

### 7.2 Generation Flow
1. **Search**: The user's query is converted into a 384-dimensional vector and compared against the stored vectors in Qdrant. The top 5 matching text segments are retrieved.
2. **Context Compilation**: The retrieved text segments are formatted into a structured prompt, labeling each with its Document ID, page number, and source type.
3. **LLM Generation**: The prompt is sent to the **Groq API (Llama 3.1 8B)** with strict instructions: *“Answer the query using only the provided context. Cite the document ID and page number for every fact. If the answer is not present, state that you cannot find it.”*
4. **Citations UI**: The Streamlit interface displays the generated answer and lists the cited sources in collapsible cards.
"""

# ── ReportLab PDF Builder ────────────────────────────────────────────────────

def create_project_description_pdf(filename="PROJECT_DESCRIPTION.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=45, leftMargin=45,
        topMargin=50, bottomMargin=50
    )
    
    styles = getSampleStyleSheet()
    
    # Premium Palette
    primary_color = colors.HexColor("#1e293b") # Slate 800
    accent_color = colors.HexColor("#0369a1")  # Sky 700 Accent
    text_color = colors.HexColor("#334155")    # Slate 700 text
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=primary_color,
        spaceAfter=12
    )
    
    h1_style = ParagraphStyle(
        'DocH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=accent_color,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'DocH2',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=primary_color,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=text_color,
        spaceAfter=5
    )

    code_style = ParagraphStyle(
        'DocCode',
        parent=styles['Code'],
        fontName='Courier',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0f766e"),
        spaceAfter=4
    )
    
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=body_style,
        fontName='Helvetica-Bold',
        textColor=colors.white
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
    
    lines = MARKDOWN_CONTENT.split("\n")
    in_code_block = False
    code_lines = []
    
    in_table = False
    table_data = []
    
    for line in lines:
        stripped = line.strip()
        
        # Handle code block toggles
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
            
        # Handle tables
        if stripped.startswith("|"):
            in_table = True
            cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
            # Skip delimiter line
            if all(c.startswith("-") for c in cells if c):
                continue
            table_data.append(cells)
            continue
        elif in_table:
            # End of table, compile Table flowable
            t_rows = []
            for row_idx, row in enumerate(table_data):
                t_row = []
                for col_idx, cell in enumerate(row):
                    if row_idx == 0:
                        t_row.append(Paragraph(md_to_html(cell), table_header_style))
                    else:
                        t_row.append(Paragraph(md_to_html(cell), body_style))
                t_rows.append(t_row)
            
            # Determine correct columns count for spacing
            if len(t_rows[0]) == 4:
                col_widths = [100, 110, 110, 200]
            else: # Transition Table layout
                col_widths = [75, 75, 55, 65, 80, 80, 90]
                
            t = Table(t_rows, colWidths=col_widths)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), accent_color),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ]))
            story.append(t)
            story.append(Spacer(1, 8))
            table_data = []
            in_table = False
            
        if stripped.startswith("# "):
            story.append(Spacer(1, 10))
            story.append(Paragraph(md_to_html(stripped[2:]), title_style))
        elif stripped.startswith("## "):
            story.append(Paragraph(md_to_html(stripped[3:]), h1_style))
        elif stripped.startswith("### "):
            story.append(Paragraph(md_to_html(stripped[4:]), h2_style))
        elif stripped.startswith("!["):
            # Embed high-res visual flowchart directly in PDF
            img_path = "samples/flow_diagram.png"
            if os.path.exists(img_path):
                story.append(Image(img_path, width=500, height=333))
                story.append(Spacer(1, 8))
            continue
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
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#e2e8f0")),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ])))
            story.append(Spacer(1, 8))
        elif stripped:
            story.append(Paragraph(md_to_html(stripped), body_style))
            
    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        page_num = canvas.getPageNumber()
        canvas.drawRightString(612 - 45, 30, f"Page {page_num}")
        canvas.drawString(45, 30, "Technical Case Study: Document Data Platform")
        canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
        canvas.setLineWidth(0.5)
        canvas.line(45, 742, 612 - 45, 742)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"Successfully generated {filename}")

if __name__ == "__main__":
    # Write the markdown file version
    with open("PROJECT_DESCRIPTION.md", "w", encoding="utf-8") as f:
        f.write(MARKDOWN_CONTENT)
    print("Successfully generated PROJECT_DESCRIPTION.md")
    create_project_description_pdf()
