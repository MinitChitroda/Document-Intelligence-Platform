import os
import sys
import time

# Ensure project root is in PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyspark.sql import SparkSession
from storage.postgres_bronze import SessionLocal, BronzeDocument
from sqlalchemy import func

def reprocess_document(row):
    """
    Simulated UDF for PySpark to re-apply chunking/quality rules.
    In a real scenario, this would call `extract_text_and_chunk(path)`
    and return new metadata. We will simulate an OCR confidence bump
    or a metadata change to trigger SCD2.
    """
    import random
    doc_id = row['document_id']
    file_hash = row['file_hash']
    current_version = row['version']
    current_conf = row['ocr_confidence']
    
    # Simulate a reprocessing event that changes a metric (e.g., better OCR model)
    new_conf = (current_conf or 70.0) + random.uniform(1.0, 5.0)
    if new_conf > 100:
        new_conf = 100.0
        
    return {
        'id': row['id'],
        'document_id': doc_id,
        'file_hash': file_hash,
        'version': current_version,
        'new_version': current_version + 1,
        'new_ocr_confidence': round(new_conf, 2),
        'source_type': row['source_type'],
        'status': row['status']
    }

def main():
    print("Starting PySpark Batch Reprocessing Job (local mode)...")
    start_time = time.time()
    
    # Initialize Spark
    spark = SparkSession.builder \
        .appName("BronzeReprocessing") \
        .master("local[*]") \
        .config("spark.driver.memory", "1g") \
        .getOrCreate()
        
    db = SessionLocal()
    try:
        # Load all latest versions of documents from postgres using SQLAlchemy
        # We find the max version for each document_id
        subq = db.query(
            BronzeDocument.document_id,
            func.max(BronzeDocument.version).label('max_version')
        ).group_by(BronzeDocument.document_id).subquery()
        
        latest_docs = db.query(BronzeDocument).join(
            subq,
            (BronzeDocument.document_id == subq.c.document_id) &
            (BronzeDocument.version == subq.c.max_version)
        ).filter(BronzeDocument.status == 'curated').all()
        
        if not latest_docs:
            print("No curated documents found in Bronze to reprocess.")
            return
            
        print(f"Loaded {len(latest_docs)} documents from Bronze.")
        
        # Convert to a list of dicts for Spark
        data = [{
            'id': d.id,
            'document_id': d.document_id,
            'file_hash': d.file_hash,
            'version': d.version,
            'ocr_confidence': d.ocr_confidence,
            'source_type': d.source_type,
            'status': d.status
        } for d in latest_docs]
        
        # Parallelize and map
        rdd = spark.sparkContext.parallelize(data)
        reprocessed_rdd = rdd.map(reprocess_document)
        results = reprocessed_rdd.collect()
        
        updates_count = 0
        for res in results:
            # We only insert a new version if something meaningfully changed
            # (e.g. OCR confidence changed by > 0.5)
            old_conf = next((d['ocr_confidence'] for d in data if d['document_id'] == res['document_id']), 0) or 0
            if abs(res['new_ocr_confidence'] - old_conf) > 0.5:
                # Insert new version triggering SCD2 when dbt runs
                new_doc = BronzeDocument(
                    document_id=res['document_id'],
                    file_hash=res['file_hash'],
                    version=res['new_version'],
                    status=res['status'],
                    source_type=res['source_type'],
                    ocr_confidence=res['new_ocr_confidence'],
                    page_count=None # Just inherit or calculate
                )
                db.add(new_doc)
                updates_count += 1
                
        db.commit()
        
        elapsed = time.time() - start_time
        print(f"Successfully reprocessed {len(results)} documents.")
        print(f"Inserted {updates_count} new versions into bronze_documents (triggering SCD2 on next dbt run).")
        print(f"Time taken: {elapsed:.2f} seconds.")
        
    finally:
        db.close()
        spark.stop()

if __name__ == "__main__":
    main()
