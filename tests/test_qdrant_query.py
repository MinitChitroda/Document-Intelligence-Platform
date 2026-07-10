import os
import sys

# Setup environment to import project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from rag import qdrant_store as qc
from sentence_transformers import SentenceTransformer
from qdrant_client.http.models import SearchRequest, Filter, FieldCondition, MatchValue

model = SentenceTransformer("all-MiniLM-L6-v2")
client = qc.get_client()

query = "What is the email of Minit Chitroda"
query_vector = model.encode(query, normalize_embeddings=True).tolist()

tenant_id = "hehe"
query_filter = Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))])

res = client.http.search_api.search_points(
    collection_name=qc.COLLECTION_NAME,
    search_request=SearchRequest(
        vector=query_vector,
        limit=5,
        filter=query_filter,
        with_payload=True,
    )
)

print(f"Results for query '{query}':")
for hit in res.result:
    print(f"Score: {hit.score:.4f}, Payload chunk text snippet: {hit.payload.get('chunk_text', '')[:100]}")
