import os
import sys
import time
import subprocess

def main():
    print("=" * 65)
    print("  STARTING ALL PLATFORM SERVICES (FastAPI, Consumer, Streamlit)  ")
    print("=" * 65)
    
    # 1. Start Ingestion API (FastAPI)
    print("\n[1/3] Starting Ingestion FastAPI Server (port 8001)...")
    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "ingestion.api:app", "--host", "0.0.0.0", "--port", "8001"],
        env={**os.environ}
    )
    time.sleep(2)
    
    # 2. Start Kafka Consumer
    print("\n[2/3] Starting Ingestion Kafka Consumer...")
    consumer_proc = subprocess.Popen(
        [sys.executable, "ingestion/kafka_consumer.py"],
        env={**os.environ}
    )
    time.sleep(2)
    
    # 3. Start Streamlit App Dashboard
    print("\n[3/3] Starting Streamlit App (port 8501)...")
    streamlit_proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "dashboard/streamlit_app.py"],
        env={**os.environ}
    )
    
    print("\n" + "=" * 65)
    print("  All services are now active!")
    print("  - Streamlit Dashboard: http://localhost:8501")
    print("  - Ingestion API Docs : http://localhost:8001/docs")
    print("  - Press Ctrl+C in this terminal to stop all services.")
    print("=" * 65 + "\n")
    
    try:
        while True:
            # Check if any process exited
            if api_proc.poll() is not None:
                print(f"[ERROR] FastAPI server exited with code {api_proc.poll()}")
                break
            if consumer_proc.poll() is not None:
                print(f"[ERROR] Kafka consumer exited with code {consumer_proc.poll()}")
                break
            if streamlit_proc.poll() is not None:
                print(f"[ERROR] Streamlit app exited with code {streamlit_proc.poll()}")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping all services...")
    finally:
        print("Terminating background processes...")
        if consumer_proc:
            consumer_proc.terminate()
        if api_proc:
            api_proc.terminate()
        if streamlit_proc:
            streamlit_proc.terminate()
            
        if consumer_proc:
            consumer_proc.wait()
        if api_proc:
            api_proc.wait()
        if streamlit_proc:
            streamlit_proc.wait()
        print("All services stopped.")

if __name__ == "__main__":
    main()
