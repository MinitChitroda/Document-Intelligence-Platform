import os
import sys

# Setup environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from rag import qdrant_store as qc
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

client = qc.get_client()
tenant_id = "hehe"

query_filter = Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))])

res, _ = client.scroll(
    collection_name=qc.COLLECTION_NAME,
    scroll_filter=query_filter,
    limit=100,
    with_payload=True
)

print(f"Total chunks for tenant 'hehe': {len(res)}")
for idx, hit in enumerate(res):
    print(f"Chunk {idx+1}: {hit.payload.get('chunk_text', '')[:50]}...")
