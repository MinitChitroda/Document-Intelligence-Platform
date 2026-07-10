import os
import pandas as pd
from rag.query_classifier import classify_query
from rag.groq_client import get_groq_manager

def handle_csv_aggregation(query: str, csv_file_path: str, document_id: str) -> dict or None:
    classification = classify_query(query)
    if classification["type"] != "aggregation":
        return None
        
    try:
        df = pd.read_csv(csv_file_path)
        df = df.dropna(how='all')
        
        # Clean column names (strip trailing spaces)
        df.columns = [col.strip() for col in df.columns]
        
        # Prepare schema details for the LLM
        columns = list(df.columns)
        head_sample = df.head(3).to_dict(orient="records")
        
        system_prompt = (
            "You are a precise data engineering code generator. "
            "You are given a Pandas DataFrame named 'df'. "
            "Your job is to generate a single-line Python expression that can be evaluated using eval() to answer the user's question. "
            "The columns are: " + str(columns) + "\n"
            "Example data:\n" + str(head_sample) + "\n"
            "Rules:\n"
            "1. Output ONLY the raw Python expression. No markdown blocks, no 'python' syntax tags, no explanation.\n"
            "2. Always clean string values in filters (e.g., use `.str.strip()` or `.str.lower()` where appropriate to match values, or exact matches if safe).\n"
            "3. Ensure the return value of your expression is a single number (like df.shape[0]), a string, a list of strings, or a pandas Series/DataFrame.\n"
            "4. If the question asks for multiple metrics, return them combined using an f-string (e.g., f'{len(df.columns)} columns, {df[\"Branch\"].nunique()} unique branches'). Never add integers directly to strings.\n"
            "5. If asked for columns count, use len(df.columns) or df.shape[1]. If asked for unique names, use df['Branch'].unique().tolist().\n"
            "Example: df[df['Branch'].str.strip() == 'Information Technology'].shape[0]\n"
            "Example: df[df['Branch'].str.strip() == 'Information Technology']['Full Name'].tolist()"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User Question: {query}"}
        ]
        
        groq_manager = get_groq_manager()
        raw_code = groq_manager.call_with_fallback(messages, "llama-3.1-8b-instant", 0.0)
        
        # Clean up any potential markdown wraps
        code = raw_code.strip().replace("`", "")
        if code.startswith("python"):
            code = code[6:].strip()
            
        # Execute the pandas expression
        print(f"Generated Pandas Code: {code}")
        local_dict = {"df": df, "pd": pd}
        result = eval(code, {}, local_dict)
        
        # Convert result to clean string representation
        if isinstance(result, list):
            result_text = ", ".join([str(x) for x in result])
        elif isinstance(result, (int, float)):
            result_text = str(result)
        elif isinstance(result, pd.Series):
            result_text = ", ".join([str(x) for x in result.tolist()])
        elif isinstance(result, pd.DataFrame):
            result_text = result.to_string()
        else:
            result_text = str(result)
            
        return {
            "type": "structured",
            "data": f"Aggregation result for '{query}': {result_text}",
            "document_id": document_id
        }
    except Exception as e:
        # Fallback to semantic search on error
        return None
