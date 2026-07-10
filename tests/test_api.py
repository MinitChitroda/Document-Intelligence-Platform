import pytest
from fastapi.testclient import TestClient
from ingestion.api import app
from ingestion.idempotency import Base, engine, SessionLocal, Document

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    """
    Drops and recreates the database tables before each test.
    This ensures each test runs in a clean environment.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # Clean up after the test completes
    Base.metadata.drop_all(bind=engine)

def test_duplicate_upload():
    file_content = b"Hello, this is a test document."
    
    # 1. First upload should be accepted
    response1 = client.post(
        "/upload",
        files={"file": ("test.txt", file_content, "text/plain")}
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["status"] == "accepted"
    assert "document_id" in data1
    
    # Verify the document was actually stored in the DB
    db = SessionLocal()
    doc_in_db = db.query(Document).filter(Document.document_id == data1["document_id"]).first()
    assert doc_in_db is not None
    assert doc_in_db.status == "pending"
    db.close()
    
    # 2. Second upload of the exact same content should be skipped
    response2 = client.post(
        "/upload",
        files={"file": ("test.txt", file_content, "text/plain")}
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["status"] == "skipped_duplicate"
    
    # The duplicate should return the ID of the original document
    assert data2["document_id"] == data1["document_id"]
