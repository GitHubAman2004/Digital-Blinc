import os

class Config:
    # ==================== DATABASE CONFIGURATION ====================
    # Set these to connect to your production PostgreSQL server.
    # If psycopg2 is not installed or connection fails, the app automatically falls back to SQLite (aiops.db).
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
    DB_HOST = os.getenv("DB_HOST", "localhost")  # <-- Change this to your Postgres DB server IP/Hostname
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "aiops")
    
    # Primary PostgreSQL Connection URL
    POSTGRES_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    # SQLite fallback database name (used when running locally or during development offline)
    SQLITE_DB = "aiops.db"
    
    # ==================== AIOPS ENGINE SETTINGS ====================
    # Background Scheduler Config (how frequently the collector pulls from infrastructure APIs)
    COLLECTOR_INTERVAL = int(os.getenv("COLLECTOR_INTERVAL", "15"))
    
    # Flask backend server port
    PORT = int(os.getenv("PORT", "5000"))
    
    # ==================== OLLAMA / CHATBOT CONFIGURATION ====================
    # Change OLLAMA_HOST to point to the IP address of your offline LLM server.
    # Default is localhost (127.0.0.1:11434).
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "bge-m3:latest")
    CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen3:8b")  # <-- Match your local model name (e.g. qwen2.5:8b, llama3, etc.)

    # ==================== REAL INFRASTRUCTURE INTEGRATION ====================
    # INSERT YOUR LIVE INFRASTRUCTURE IP ADDRESSES AND CREDENTIALS HERE
    # These will be referenced in app.py when you transition from mock APIs to real hardware APIs.
    
    # HPE OneView Settings
    ONEVIEW_HOST = os.getenv("ONEVIEW_HOST", "192.168.1.100")       # <-- Insert HPE OneView Appliance IP/FQDN
    ONEVIEW_USER = os.getenv("ONEVIEW_USER", "Administrator")     # <-- Insert OneView Username
    ONEVIEW_PASS = os.getenv("ONEVIEW_PASS", "oneview_password")  # <-- Insert OneView Password
    
    # Cisco APIC Settings
    APIC_HOST = os.getenv("APIC_HOST", "192.168.1.200")           # <-- Insert Cisco ACI APIC controller IP/FQDN
    APIC_USER = os.getenv("APIC_USER", "admin")                  # <-- Insert APIC Username
    APIC_PASS = os.getenv("APIC_PASS", "apic_password")          # <-- Insert APIC Password

