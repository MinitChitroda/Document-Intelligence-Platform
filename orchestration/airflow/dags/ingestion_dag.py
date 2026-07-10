"""
orchestration/airflow/dags/ingestion_dag.py
Airflow DAG: document ingestion pipeline.
Triggers FastAPI -> Kafka -> extraction -> quality gate -> S3/Postgres.
Week 4 — not yet implemented.
"""
