import os
import sys

# Setup environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from storage.postgres_bronze import SessionLocal
from storage.postgres_models import BronzeDocument

db = SessionLocal()
docs = db.query(BronzeDocument).filter(BronzeDocument.tenant_id == "hehe").all()
for d in docs:
    print(f"Doc: {d.filename}, Status: {d.status}, Type: {d.source_type}")
db.close()
