import os
import time
import random
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from google import genai
from google.genai import types

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

@dataclass
class ApiKey:
    key: str
    client: genai.Client
    status: str = "AVAILABLE"  # AVAILABLE, RATE_LIMITED, EXHAUSTED, DEAD
    cooldown_until: float = 0.0

class GeminiClientManager:
    def __init__(self, timeout: float = 300000.0):
        self._keys: list[ApiKey] = []
        
        # Load up to 10 indexed keys
        for i in range(10):
            key_val = os.environ.get(f"GEMINI_API_KEY_{i}")
            if key_val:
                try:
                    client = genai.Client(api_key=key_val, http_options={"timeout": timeout})
                    self._keys.append(ApiKey(key=key_val, client=client))
                except Exception as e:
                    logging.warning(f"Failed to initialize client for key {i}: {e}")
        
        # Fallback to standard key
        if not self._keys:
            key_val = os.environ.get("GEMINI_API_KEY")
            if key_val:
                client = genai.Client(api_key=key_val, http_options={"timeout": timeout})
                self._keys.append(ApiKey(key=key_val, client=client))
                
        if not self._keys:
            raise RuntimeError("No Gemini API keys found in .env.")
            
        self._current_index = 0

    def _get_next_available_key(self) -> Optional[ApiKey]:
        """Finds the next available key or a key whose cooldown has expired."""
        now = time.time()
        start_idx = self._current_index
        
        for _ in range(len(self._keys)):
            k = self._keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(self._keys)
            
            if k.status == "AVAILABLE":
                return k
            elif k.status in ("RATE_LIMITED", "EXHAUSTED"):
                if now > k.cooldown_until:
                    k.status = "AVAILABLE"
                    return k
                    
        return None  # All keys are currently exhausted or dead

    def call_with_fallback(self, messages: list, model: str = "gemini-flash-latest", temperature: float = 0.0, max_retries: int = 3) -> str:
        """
        Intelligent failover client with metrics collection, exponential backoff, and state-aware key rotation.
        """
        metrics = {
            "total_latency_ms": 0,
            "api_latency_ms": 0,
            "retry_count": 0,
            "failover_count": 0,
            "key_used": None,
            "error_type": None,
            "timeout_count": 0
        }
        
        start_time_total = time.perf_counter()
        
        system_instruction = None
        user_prompt_parts = []
        for msg in messages:
            if msg.get("role") == "system":
                system_instruction = msg.get("content", "")
            else:
                user_prompt_parts.append(f"{msg.get('role', '').upper()}: {msg.get('content', '')}")

        prompt = "\n\n".join(user_prompt_parts)
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
        )
        
        fallback_models = ["gemini-2.5-flash", "gemini-1.5-flash"]
        last_error = None
        
        for model_name in fallback_models:
            attempts = 0
            while attempts < max_retries:
                api_key_obj = self._get_next_available_key()
                
                if not api_key_obj:
                    # If all keys exhausted, wait 25 seconds to outlast the 60s cooldown, then retry
                    time.sleep(25)
                    attempts += 1
                    metrics["retry_count"] += 1
                    last_error = RuntimeError("All API keys are currently exhausted, rate limited, or dead.")
                    continue
                
                metrics["key_used"] = f"KEY_{self._keys.index(api_key_obj)}"
                start_time_api = time.perf_counter()
                
                try:
                    response = api_key_obj.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config,
                    )
                    end_time = time.perf_counter()
                    metrics["api_latency_ms"] = (end_time - start_time_api) * 1000
                    metrics["total_latency_ms"] = (end_time - start_time_total) * 1000
                    
                    # Optionally attach metrics to response (hacky but useful) if we wanted, 
                    # but signature demands a string return. We just log it for now.
                    logging.debug(f"Gemini Metrics: {metrics}")
                    return response.text
                    
                except Exception as e:
                    metrics["api_latency_ms"] = (time.perf_counter() - start_time_api) * 1000
                    error_msg = str(e).lower()
                    last_error = e
                    metrics["error_type"] = error_msg
                    
                    # 1. Quota Exceeded (429)
                    if "429" in error_msg and ("quota" in error_msg or "exhausted" in error_msg):
                        if "perprojectpermodel" in error_msg or "perday" in error_msg:
                            break # Skip to the next model immediately without locking the key
                        api_key_obj.status = "EXHAUSTED"
                        api_key_obj.cooldown_until = time.time() + 60.0
                        metrics["failover_count"] += 1
                        
                    # 2. Rate Limited (429)
                    elif "429" in error_msg:
                        api_key_obj.status = "RATE_LIMITED"
                        api_key_obj.cooldown_until = time.time() + 30.0  # 30s cooldown
                        metrics["failover_count"] += 1
                        
                    # 3. Invalid Key / Auth Failure (401, 403)
                    elif "401" in error_msg or "403" in error_msg:
                        api_key_obj.status = "DEAD"
                        metrics["failover_count"] += 1
                        
                    elif "400" in error_msg or "404" in error_msg:
                        break # Try next fallback model instead of retrying a potentially completely invalid model name
                        
                    # 4. Timeout / Network Error / 503 Service Unavailable
                    else:
                        metrics["timeout_count"] += 1
                        metrics["retry_count"] += 1
                        attempts += 1
                        
                        # Exponential backoff with jitter
                        backoff = min(10.0, 1.0 * (2 ** attempts)) + random.uniform(0.1, 0.5)
                        time.sleep(backoff)
                        continue
                        
                    # If we failover due to quota/dead key, we don't count it as a model retry, 
                    # we just immediately loop to get the next available key.
                    
        # If we exit the loops, we failed completely
        metrics["total_latency_ms"] = (time.perf_counter() - start_time_total) * 1000
        logging.error(f"Gemini Call Failed. Final Metrics: {metrics}. Last Error: {last_error}")
        raise last_error

    def stream_with_fallback(self, messages: list, model: str = "gemini-flash-latest", temperature: float = 0.0, max_retries: int = 5):
        """
        Intelligent failover client that streams the response.
        """
        system_instruction = None
        user_prompt_parts = []
        for msg in messages:
            if msg.get("role") == "system":
                system_instruction = msg.get("content", "")
            else:
                user_prompt_parts.append(f"{msg.get('role', '').upper()}: {msg.get('content', '')}")

        prompt = "\n\n".join(user_prompt_parts)
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
        )
        
        fallback_models = ["gemini-2.5-flash", "gemini-1.5-flash"]
        last_error = None
        
        for model_name in fallback_models:
            attempts = 0
            while attempts < max_retries:
                api_key_obj = self._get_next_available_key()
                
                if not api_key_obj:
                    time.sleep(25)
                    attempts += 1
                    last_error = RuntimeError("All API keys are currently exhausted, rate limited, or dead.")
                    continue
                
                try:
                    # Request the stream
                    response_stream = api_key_obj.client.models.generate_content_stream(
                        model=model_name,
                        contents=prompt,
                        config=config,
                    )
                    
                    # We start iterating. If an error like 429 happens, it will likely throw on the first chunk.
                    iterator = iter(response_stream)
                    try:
                        first_chunk = next(iterator)
                        yield first_chunk.text
                    except StopIteration:
                        return # Empty stream
                        
                    # If we got the first chunk, the request was accepted. Yield the rest.
                    for chunk in iterator:
                        yield chunk.text
                        
                    return # Successfully finished streaming!
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    last_error = e
                    
                    if "429" in error_msg and ("quota" in error_msg or "exhausted" in error_msg):
                        if "perprojectpermodel" in error_msg or "perday" in error_msg:
                            break # Skip to the next model immediately without locking the key
                        api_key_obj.status = "EXHAUSTED"
                        api_key_obj.cooldown_until = time.time() + 60.0  # Just lock for 60s, API usually resets quickly
                    elif "429" in error_msg:
                        api_key_obj.status = "RATE_LIMITED"
                        api_key_obj.cooldown_until = time.time() + 30.0
                    elif "401" in error_msg or "403" in error_msg:
                        api_key_obj.status = "DEAD"
                    elif "400" in error_msg or "404" in error_msg:
                        # Model name might be invalid or deprecated. Try next fallback model.
                        break
                    else:
                        # For timeouts, 500s, 503s, etc, retry the same model
                        attempts += 1
                        backoff = min(10.0, 1.0 * (2 ** attempts)) + random.uniform(0.1, 0.5)
                        time.sleep(backoff)
                        continue
                    
        raise last_error

_manager = GeminiClientManager()

def get_gemini_manager():
    return _manager
