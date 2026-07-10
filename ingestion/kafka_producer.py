import json
import os
import logging
from kafka import KafkaProducer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC_NAME = "raw_documents"

_producer = None

def get_producer():
    global _producer
    if _producer is None:
        try:
            _producer = KafkaProducer(
                bootstrap_servers=[KAFKA_BROKER],
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None
            )
        except Exception as e:
            logger.error(f"Failed to connect to Kafka at {KAFKA_BROKER}: {e}")
            raise
    return _producer

def publish_raw_document(document_id: str, filename: str, file_hash: str, file_type: str, tenant_id: str):
    producer = get_producer()
    message = {
        "document_id": document_id,
        "filename": filename,
        "hash": file_hash,
        "file_type": file_type,
        "tenant_id": tenant_id
    }
    
    # Use document_id as the partition key
    producer.send(TOPIC_NAME, key=document_id, value=message)
    producer.flush()
    logger.info(f"Published document {document_id} with tenant_id {tenant_id} to {TOPIC_NAME}")

