import os
import sys

# Setup environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from rag.query_router import route_query

tenant_id = "hehe"
query = "from which specialization majority of the students are selected?"

result = route_query(query=query, tenant_id=tenant_id)
print("Query:", query)
print("Query Type:", result.get("query_type"))
print("Chunks Retrieved:", result.get("chunks_used", 0))
print("Answer:", result.get("answer"))
