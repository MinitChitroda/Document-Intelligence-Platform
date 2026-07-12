# Document Data Platform

> A production-grade, multi-tenant document ingestion and RAG (Retrieval-Augmented Generation) platform. Upload any document — PDF, scanned image, or CSV — and instantly query it with evidence-backed, cited answers.

<br>

Most RAG pipelines are simple: you chuck a PDF into a vector database and ask questions. This platform is different.
It is a **fully automated data engineering pipeline** that handles the messy real world — scanned documents with poor quality, multi-tenant user isolation, tabular spreadsheets that trip up vector search — and delivers trustworthy, cited answers. Every single claim made by the LLM is backed by a retrieved document chunk, and the system is architecturally **gated from hallucinating**.

---

## Architecture Overview

The platform is composed of 6 distinct layers that work in sequence:

![Architecture Diagram](img.png)

---


### Layer 1 — Ingestion (`ingestion/`)

| Component | File | What it does |
|---|---|---|
| REST API | `api.py` | Accepts `multipart/form-data` uploads via FastAPI. Reads the `X-Tenant-ID` header for tenant isolation. |
| Idempotency | `idempotency.py` | Computes a SHA-256 hash of the uploaded file and checks PostgreSQL. If the file has already been seen **by that tenant**, it is silently discarded. |
| Document Classifier | `classifier.py` | Determines the document type: `text_native`, `scanned`, `csv`, or `image` — before it is even queued. |
| Kafka Producer | `kafka_producer.py` | Publishes a JSON event to the `raw_documents` topic. The event includes the file path, tenant ID, document ID, and source type. |

### Layer 2 — Extraction (`extraction/`)

The **Kafka Consumer** (`ingestion/kafka_consumer.py`) picks up events from the `raw_documents` topic and branches into one of three extraction paths:

| Document Type | Extraction Method | Library |
|---|---|---|
| `text_native` PDF | Direct text extraction | **PyMuPDF** (`fitz`) |
| `scanned` PDF / image | OCR pipeline | **OpenCV** (preprocessing) + **Tesseract** |
| `csv` | Structured parsing | **Pandas** |

**OCR Preprocessing Pipeline (for scanned documents):**
```
Raw Image
    │
    ├── Grayscale conversion
    ├── Deskewing (perspective correction)
    ├── Adaptive thresholding
    └── Median blur (noise reduction)
         │
         ▼
   Tesseract OCR → (text + confidence %)
```

### Layer 3 — Quality Gate (`quality/`)

Every extracted document is scored before it is accepted. The gate enforces:
- **Minimum text length** — rejects corrupted or near-empty documents.
- **Minimum OCR confidence** — rejects images that Tesseract could not read reliably.
- **CSV structural validation** — rejects files that don't parse into valid columns/rows.

Documents that **PASS** are written to `bronze_documents` in PostgreSQL (AWS RDS) with status `curated`. Documents that **FAIL** are written with status `failed`. The original raw files in AWS S3 are moved to `curated/` or `failed/` prefixes accordingly.

### Layer 4 — Embedding & Vector Storage (`rag/`)

| Component | Detail |
|---|---|
| Embedding Model | `all-MiniLM-L6-v2` via `sentence-transformers` |
| Vector DB | **Qdrant** (self-hosted, Docker) |
| Collection | `document_chunks` |
| Tenant Isolation | Every vector payload stores `tenant_id`; all queries apply a `MatchValue` filter |
| Chunking Strategy | Sliding-window text chunking for prose; row-level chunking for CSV |
| AI Summary | Gemini generates a document-level summary stored alongside each chunk |

### Layer 5 — Gold Warehouse (`warehouse/`)

After embedding, **dbt** is triggered to rebuild the Gold analytical layer on PostgreSQL:

| dbt Model | Type | Description |
|---|---|---|
| `stg_bronze_documents` | Staging | Cleans and standardizes raw Bronze records |
| `dim_document` | SCD Type 2 | Tracks document version history (`valid_from`, `valid_to`, `is_current`) |
| `dim_source_type` | Dimension | Normalises source type labels (`text_native`, `scanned`, `csv`, `image`) |
| `dim_pipeline_run` | Dimension | Records every pipeline execution with timestamps and statuses |
| `fact_document_processing` | Fact | Joins documents to pipeline runs for full audit traceability |

All 13 dbt tests (unique, not_null, relationship constraints) run green.

### Layer 6 — RAG Query Engine (`rag/`)

This is the most sophisticated component. Every user query is intelligently routed:

![RAG Query Engine Architecture](rag.png)

**Key RAG components:**

| File | Role |
|---|---|
| `query_classifier.py` | Classifies query intent: `aggregation`, `table_lookup`, `comparison`, `descriptive` |
| `structured_query_handler.py` | Executes Pandas queries against in-memory CSV DataFrames for tabular questions |
| `retrieval_v2.py` | Fetches top-k chunks from Qdrant, applies confidence scoring and re-ranking |
| `context_optimizer.py` | Deduplicates and trims chunks to fit the LLM context window |
| `generation_v2.py` | Calls Gemini with a strict evidence-only system prompt; abstains if confidence is below threshold |
| `semantic_cache.py` | Caches query results per tenant; invalidates when the tenant's document collection changes |
| `gemini_client.py` | Manages multiple Gemini API keys with automatic failover and rate-limit handling |

---

## Hallucination Prevention

The LLM operates under a mathematically strict rule set:
1. **Pre-generation gate** — if the best retrieved chunk scores below `0.30`, the system abstains entirely rather than guessing.
2. **Evidence-only system prompt** — the LLM is explicitly instructed that every single claim must be backed by a retrieved chunk.
3. **Citation enforcement** — every statement must include `(Document: <filename>, Page: <number>)`.
4. **Abstention detection** — if the generated answer contains "cannot find sufficient evidence", the system flags it as `abstained=True` and surfaces the abstention to the user.

---

## Multi-Tenant Architecture

Every resource in the system is partitioned by `tenant_id`:

| Layer | Isolation Mechanism |
|---|---|
| PostgreSQL | `WHERE tenant_id = ?` on all queries; composite unique index on `(file_hash, tenant_id)` |
| Qdrant | `MatchValue(tenant_id)` filter on every vector search |
| FastAPI | `X-Tenant-ID` HTTP header propagated through the entire pipeline |
| Streamlit | Per-tenant login; all uploads and queries scoped to the authenticated tenant |

Zero data bleed between tenants has been verified via explicit cross-tenant isolation tests.

---

## Cloud Deployment (AWS) & CI/CD

This project is architected for deployment on AWS using managed services (AWS RDS, AWS S3, Qdrant Cloud) and a fully automated CI/CD pipeline.

### Architectural Changes for the Cloud
1. **Unified Dockerization**: The FastAPI, Kafka Consumer, and Streamlit apps are packaged into optimized Docker containers via `infra/docker-compose-free.yml`.
2. **Managed Infrastructure**: Stateful services were decoupled from Docker. PostgreSQL runs on AWS RDS, Vector Storage uses Qdrant Cloud, and File Storage uses AWS S3 (`boto3`).
3. **CORS & Networking**: FastAPI is configured with restrictive CORS middleware, and Streamlit disables XSRF/CORS to allow the UI to communicate over the public internet seamlessly.
4. **CI/CD Pipeline**: GitHub Actions (`.github/workflows/deploy.yml`) is configured to automatically SSH into the EC2 instance, pull the latest `main` branch, rebuild images, and restart containers with zero downtime on every push.

### AWS Setup Prerequisites
- AWS EC2 Instance with Docker and Docker Compose installed.
- AWS RDS (PostgreSQL) and AWS S3 Bucket created.
- Qdrant Cloud Cluster running.

To deploy manually on EC2:
```bash
docker compose -f infra/docker-compose-free.yml up -d --build
```
Open `http://<YOUR_EC2_PUBLIC_IP>:80` in your browser.

---

## Project Structure

```
.
├── ingestion/              # FastAPI API, Kafka producer, idempotency, document classifier
├── extraction/             # Text extraction (PyMuPDF), OCR pipeline (OpenCV + Tesseract), CSV parser
│   └── ocr/                # OCR preprocessing and extraction logic
├── quality/                # Quality gate rule engine (confidence scoring, rejection routing)
├── storage/                # PostgreSQL models, Bronze layer writer, SCD2 migration utilities
├── rag/                    # Full RAG pipeline
│   ├── query_classifier.py # Intent classification
│   ├── retrieval_v2.py     # Qdrant vector search with confidence scoring
│   ├── generation_v2.py    # Evidence-only Gemini generation
│   ├── structured_query_handler.py  # Pandas SQL executor for tabular queries
│   ├── semantic_cache.py   # Tenant-aware result cache
│   ├── context_optimizer.py # Chunk dedup and ranking
│   ├── gemini_client.py    # Multi-key Gemini manager with failover
│   └── embed.py            # Chunking, embedding, Qdrant upsert, AI summary
├── warehouse/              # dbt project (staging + gold star schema)
│   └── models/
│       ├── staging/        # stg_bronze_documents
│       └── marts/          # dim_document, dim_source_type, dim_pipeline_run, fact_document_processing
├── orchestration/          # Airflow DAGs (ingestion + nightly batch)
├── dashboard/              # Streamlit frontend (upload, catalog, RAG chat)
├── batch/                  # PySpark nightly reprocessing job
├── evaluation/             # Precision@5 evaluation harness
├── tests/                  # Test scripts and verification utilities
├── samples/                # Sample PDFs, images, CSVs for testing
├── infra/                  # docker-compose.yml (dev) + docker-compose-ec2.yml (prod)
├── run_app.py              # Single-command launcher (FastAPI + Kafka Consumer + Streamlit)
└── requirements.txt
```

---

<div align="center">
  <b>Developed by <a href="mailto:minitchitroda@gmail.com">Minit Chitroda</a></b>
</div>
