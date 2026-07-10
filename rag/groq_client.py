import os
from groq import Groq, RateLimitError

def load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ[k] = v.strip("'\"")

load_dotenv()

class GroqClientManager:
    def __init__(self):
        self._keys = []
        for i in range(10):  # Scan up to 10 keys (GROQ_API_KEY_0 to GROQ_API_KEY_9)
            key = os.environ.get(f"GROQ_API_KEY_{i}")
            if key:
                self._keys.append(key)
        
        # If no indexed keys, fallback to standard key
        if not self._keys:
            key = os.environ.get("GROQ_API_KEY")
            if key:
                self._keys.append(key)
                
        self._current_index = 0
        self._clients = [Groq(api_key=k) for k in self._keys]

    def call_with_fallback(self, messages: list, model: str, temperature: float) -> str:
        if not self._clients:
            raise RuntimeError("No Groq API clients available")
            
        num_keys = len(self._clients)
        last_error = None
        
        for _ in range(num_keys):
            # Advance index on EVERY request for true Round-Robin load balancing
            self._current_index = (self._current_index + 1) % num_keys
            client = self._clients[self._current_index]
            
            try:
                chat_completion = client.chat.completions.create(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                )
                return chat_completion.choices[0].message.content
            except Exception as e:
                last_error = e
                continue
                
        raise RuntimeError(f"Service temporarily unavailable (All configured keys failed. Last error: {last_error})")

    def stream_with_fallback(self, messages: list, model: str, temperature: float):
        if not self._clients:
            raise RuntimeError("No Groq API clients available")
            
        num_keys = len(self._clients)
        last_error = None
        
        for _ in range(num_keys):
            self._current_index = (self._current_index + 1) % num_keys
            client = self._clients[self._current_index]
            
            try:
                stream = client.chat.completions.create(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    stream=True,
                )
                
                iterator = iter(stream)
                try:
                    first_chunk = next(iterator)
                    if first_chunk.choices[0].delta.content:
                        yield first_chunk.choices[0].delta.content
                except StopIteration:
                    return
                    
                for chunk in iterator:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return # Success
                
            except Exception as e:
                last_error = e
                continue
                
        yield f"\n\n[API Error: Fallback provider also failed. Last error: {last_error}]"

_manager_instance = None

def get_groq_manager() -> GroqClientManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = GroqClientManager()
    return _manager_instance
