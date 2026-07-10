import os
import shutil
from datetime import timedelta, datetime
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
import sys

# Ensure ddp is in PYTHONPATH (we mapped the project root to /opt/airflow/dags/ddp)
sys.path.append('/opt/airflow/dags/ddp')

from storage.postgres_bronze import SessionLocal, BronzeDocument
from extraction.text_extraction import extract_text_native
from extraction.ocr.extract import extract_text_ocr
from quality.quality_gate import evaluate_document

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=1),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=5),
}

def sense_pending_documents(ds, **kwargs):
    """Query postgres for pending documents on the given date (ds)."""
    # If this is a backfill, ds will be the logical execution date.
    db = SessionLocal()
    try:
        # We query for documents created on this date that are 'pending'
        # Airflow ds is a string 'YYYY-MM-DD'
        docs = db.query(BronzeDocument).filter(
            BronzeDocument.status == 'pending'
        ).all() # Simplification for backfill/run: process all pending or filter by date
        
        # Actually, let's filter by created_at matching the execution date to support true backfills
        date_obj = datetime.strptime(ds, "%Y-%m-%d").date()
        target_docs = [d for d in docs if d.created_at and d.created_at.date() == date_obj]
        
        doc_ids = [d.document_id for d in target_docs]
        kwargs['ti'].xcom_push(key='pending_doc_ids', value=doc_ids)
        
        if not doc_ids:
            print(f"No pending documents found for {ds}")
        else:
            print(f"Found {len(doc_ids)} pending documents for {ds}: {doc_ids}")
            
    finally:
        db.close()

def branch_by_source_type(**kwargs):
    doc_ids = kwargs['ti'].xcom_pull(key='pending_doc_ids', task_ids='sense_pending_documents')
    if not doc_ids:
        return 'no_docs_task'
    
    db = SessionLocal()
    try:
        branches = set()
        for doc_id in doc_ids:
            doc = db.query(BronzeDocument).filter(BronzeDocument.document_id == doc_id).first()
            if doc:
                if doc.source_type == 'text_native' or doc.source_type == 'text_pdf':
                    branches.add('extract_text_pdf')
                elif doc.source_type == 'scanned' or doc.source_type == 'scanned_pdf':
                    branches.add('extract_ocr')
                elif doc.source_type == 'csv':
                    branches.add('extract_csv')
                else:
                    print(f"Unknown source type: {doc.source_type} for doc {doc.id}")
                    
        return list(branches) if branches else 'no_docs_task'
    finally:
        db.close()

def process_documents(source_types, **kwargs):
    doc_ids = kwargs['ti'].xcom_pull(key='pending_doc_ids', task_ids='sense_pending_documents')
    if not doc_ids:
        return
        
    db = SessionLocal()
    try:
        docs = db.query(BronzeDocument).filter(BronzeDocument.document_id.in_(doc_ids)).all()
        for doc in docs:
            if doc.source_type not in source_types:
                continue
            
            print(f"Processing doc_id={doc.document_id}, file_hash={doc.file_hash}")
            
            raw_path = f"/opt/airflow/dags/ddp/data/raw/{doc.file_hash}"
            if not os.path.exists(raw_path):
                files = [f for f in os.listdir("/opt/airflow/dags/ddp/data/raw/") if f.startswith(doc.file_hash)]
                if files:
                    raw_path = f"/opt/airflow/dags/ddp/data/raw/{files[0]}"
                else:
                    doc.status = "failed"
                    db.commit()
                    continue
            
            try:
                text_content = ""
                confidence = 100.0
                extracted_page_count = None
                
                # 1. Extraction
                if doc.source_type == 'text_pdf' or doc.source_type == 'text_native':
                    result = extract_text_native(raw_path)
                    text_content = " ".join([c['content'] for c in result])
                    extracted_page_count = len(result)       # DB-02 Fix: capture page count
                    confidence = 100.0                       # Native PDFs → 100% confidence
                elif doc.source_type == 'scanned_pdf' or doc.source_type == 'scanned':
                    result = extract_text_ocr(raw_path) 
                    text_content = result.get('text', '')
                    confidence = result.get('average_confidence', 0.0)
                    extracted_page_count = result.get('page_count', None)  # DB-02 Fix
                elif doc.source_type == 'csv':
                    text_content = "CSV mock content"
                    
                doc.extracted_text = text_content
                
                # DB-02 Fix: Persist telemetry metrics before quality gate and commit
                doc.ocr_confidence = confidence if doc.source_type in ('scanned_pdf', 'scanned') else None
                doc.page_count = extracted_page_count
                
                # 2. Quality Gate
                evaluate_document(db, doc.document_id, raw_path, text_content, confidence, tenant_id=doc.tenant_id)
                
            except Exception as e:
                db.rollback()
                doc.status = "failed"
                print(f"Failed to process {doc.document_id}: {e}")
            
            db.commit()
    finally:
        db.close()

def no_docs():
    print("No documents to process.")

with DAG(
    'ingestion_dag',
    default_args=default_args,
    description='A simple ingestion DAG with branching',
    schedule_interval='@daily',
    catchup=False,
) as dag:

    sense_task = PythonOperator(
        task_id='sense_pending_documents',
        python_callable=sense_pending_documents,
        op_kwargs={'ds': '{{ ds }}'},
    )

    branch_task = BranchPythonOperator(
        task_id='branch_on_source_type',
        python_callable=branch_by_source_type,
    )

    extract_text_task = PythonOperator(
        task_id='extract_text_pdf',
        python_callable=process_documents,
        op_kwargs={'source_types': ['text_pdf', 'text_native']},
    )

    extract_ocr_task = PythonOperator(
        task_id='extract_ocr',
        python_callable=process_documents,
        op_kwargs={'source_types': ['scanned_pdf', 'scanned']},
    )

    extract_csv_task = PythonOperator(
        task_id='extract_csv',
        python_callable=process_documents,
        op_kwargs={'source_types': ['csv']},
    )
    
    no_docs_task = PythonOperator(
        task_id='no_docs_task',
        python_callable=no_docs,
    )

    sense_task >> branch_task
    branch_task >> [extract_text_task, extract_ocr_task, extract_csv_task, no_docs_task]
