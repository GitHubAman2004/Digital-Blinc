import sqlite3
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
import json
from config import Config

class DBManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBManager, cls).__new__(cls)
            cls._instance.engine_type = None  # 'postgres' or 'sqlite'
            cls._instance.test_connection()
        return cls._instance

    def test_connection(self):
        """Attempts to connect to PostgreSQL, otherwise falls back to SQLite."""
        if not HAS_POSTGRES:
            print("Database Status: psycopg2 driver not installed. Falling back to SQLite local database.")
            self.engine_type = 'sqlite'
            return

        try:
            # Try PostgreSQL
            conn = psycopg2.connect(
                dbname=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                connect_timeout=3
            )
            conn.close()
            self.engine_type = 'postgres'
            print("Database Status: Connected successfully to PostgreSQL server.")
        except Exception as e:
            print(f"Database Status: PostgreSQL connection failed ({e}). Falling back to SQLite local database.")
            self.engine_type = 'sqlite'

    def get_connection(self):
        """Returns an active database connection."""
        if self.engine_type == 'postgres' and HAS_POSTGRES:
            conn = psycopg2.connect(
                dbname=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                host=Config.DB_HOST,
                port=Config.DB_PORT
            )
            return conn
        else:
            conn = sqlite3.connect(Config.SQLITE_DB)
            # Enable dictionary-like access for SQLite
            conn.row_factory = sqlite3.Row
            return conn

    def execute_query(self, query, params=None):
        """Executes a non-returning query (INSERT, UPDATE, DELETE)."""
        conn = self.get_connection()
        try:
            if self.engine_type == 'sqlite':
                # Convert PostgreSQL placeholder %s to SQLite ?
                query = query.replace('%s', '?')
            
            cur = conn.cursor()
            cur.execute(query, params or ())
            conn.commit()
            cur.close()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def fetch_all(self, query, params=None):
        """Executes a query and returns all matching rows as dictionaries."""
        conn = self.get_connection()
        try:
            if self.engine_type == 'sqlite':
                query = query.replace('%s', '?')
                cur = conn.cursor()
                cur.execute(query, params or ())
                rows = cur.fetchall()
                # Convert SQLite Rows to Dict list
                result = [dict(row) for row in rows]
            else:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(query, params or ())
                result = cur.fetchall()
                # Convert RealDictRow to standard dict
                result = [dict(row) for row in result]
            cur.close()
            return result
        except Exception as e:
            raise e
        finally:
            conn.close()

    def fetch_one(self, query, params=None):
        """Executes a query and returns a single row as a dictionary."""
        conn = self.get_connection()
        try:
            if self.engine_type == 'sqlite':
                query = query.replace('%s', '?')
                cur = conn.cursor()
                cur.execute(query, params or ())
                row = cur.fetchone()
                result = dict(row) if row else None
            else:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(query, params or ())
                row = cur.fetchone()
                result = dict(row) if row else None
            cur.close()
            return result
        except Exception as e:
            raise e
        finally:
            conn.close()

    def init_db(self):
        """Creates the necessary schemas for HPE OneView and Cisco APIC."""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            if self.engine_type == 'postgres':
                # Enable pgvector if postgres is available
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                except Exception as ex:
                    print(f"Warning: Could not create pgvector extension: {ex}")
                
                # PostgreSQL Schema definition
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_enclosures (
                        id VARCHAR(100) PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        temp_c INT NOT NULL,
                        power_watts INT NOT NULL,
                        model VARCHAR(100),
                        serial_number VARCHAR(100)
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_server_hardware (
                        id VARCHAR(100) PRIMARY KEY,
                        enclosure_id VARCHAR(100) REFERENCES oneview_enclosures(id) ON DELETE CASCADE,
                        bay INT NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        model VARCHAR(100),
                        serial_number VARCHAR(100),
                        cpu_util_pct REAL NOT NULL,
                        power_watts INT NOT NULL,
                        temp_c INT NOT NULL,
                        profile_name VARCHAR(100),
                        memory_mb INT NOT NULL,
                        cpu_cores INT NOT NULL
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_interconnects (
                        id VARCHAR(100) PRIMARY KEY,
                        enclosure_id VARCHAR(100) REFERENCES oneview_enclosures(id) ON DELETE CASCADE,
                        bay INT NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        model VARCHAR(100),
                        type VARCHAR(50)
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_storage_pools (
                        id VARCHAR(100) PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        capacity_gb REAL NOT NULL,
                        free_space_gb REAL NOT NULL,
                        system_name VARCHAR(100)
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_fabric_nodes (
                        id VARCHAR(100) PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        role VARCHAR(20) NOT NULL,
                        ip_address VARCHAR(50) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        health_score INT NOT NULL
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_interfaces (
                        id VARCHAR(100) PRIMARY KEY,
                        node_id VARCHAR(100) REFERENCES apic_fabric_nodes(id) ON DELETE CASCADE,
                        name VARCHAR(100) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        usage_in_bps REAL NOT NULL,
                        usage_out_bps REAL NOT NULL
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_logical (
                        id SERIAL PRIMARY KEY,
                        tenant VARCHAR(100) NOT NULL,
                        vrf VARCHAR(100) NOT NULL,
                        bd_name VARCHAR(100) NOT NULL,
                        epg VARCHAR(100) NOT NULL
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id SERIAL PRIMARY KEY,
                        source VARCHAR(50) NOT NULL,
                        severity VARCHAR(20) NOT NULL,
                        entity_id VARCHAR(100) NOT NULL,
                        entity_name VARCHAR(100) NOT NULL,
                        message TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        resolved BOOLEAN DEFAULT FALSE
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS historical_metrics (
                        id SERIAL PRIMARY KEY,
                        entity_type VARCHAR(50) NOT NULL,
                        entity_id VARCHAR(100) NOT NULL,
                        metric_name VARCHAR(50) NOT NULL,
                        metric_value REAL NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS kb_documents (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(200) NOT NULL,
                        content TEXT NOT NULL,
                        category VARCHAR(50) NOT NULL,
                        embedding vector(1024)
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_server_profiles (
                        id VARCHAR(100) PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        server_hardware_id VARCHAR(100) REFERENCES oneview_server_hardware(id) ON DELETE SET NULL,
                        status VARCHAR(20) NOT NULL,
                        compliance_state VARCHAR(30) NOT NULL,
                        template_name VARCHAR(100),
                        firmware_baseline VARCHAR(100),
                        description TEXT
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_networks (
                        id VARCHAR(100) PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        type VARCHAR(20) NOT NULL,
                        vlan_id INT,
                        status VARCHAR(20) NOT NULL,
                        bandwidth_typical REAL,
                        subnet VARCHAR(50),
                        purpose VARCHAR(50)
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_firmware (
                        id VARCHAR(100) PRIMARY KEY,
                        name VARCHAR(200) NOT NULL,
                        version VARCHAR(50) NOT NULL,
                        release_date VARCHAR(30),
                        iso_file_name VARCHAR(200),
                        status VARCHAR(20) NOT NULL,
                        size_mb REAL
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_endpoints (
                        id VARCHAR(100) PRIMARY KEY,
                        mac VARCHAR(20) NOT NULL,
                        ip VARCHAR(50),
                        epg VARCHAR(100) NOT NULL,
                        interface VARCHAR(100),
                        encap VARCHAR(20),
                        node_id VARCHAR(100),
                        status VARCHAR(20) NOT NULL
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_contracts (
                        id VARCHAR(100) PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        tenant VARCHAR(100) NOT NULL,
                        scope VARCHAR(30) NOT NULL,
                        filter_name VARCHAR(100),
                        protocol VARCHAR(20),
                        dst_port VARCHAR(20),
                        action VARCHAR(20) NOT NULL
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_equipment (
                        id VARCHAR(100) PRIMARY KEY,
                        node_id VARCHAR(100) REFERENCES apic_fabric_nodes(id) ON DELETE CASCADE,
                        type VARCHAR(10) NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        model VARCHAR(100),
                        serial_number VARCHAR(100)
                    );
                """)
                
            else:
                # SQLite Schema definition
                cur.execute("PRAGMA foreign_keys = ON;")
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_enclosures (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        temp_c INTEGER NOT NULL,
                        power_watts INTEGER NOT NULL,
                        model TEXT,
                        serial_number TEXT
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_server_hardware (
                        id TEXT PRIMARY KEY,
                        enclosure_id TEXT,
                        bay INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        model TEXT,
                        serial_number TEXT,
                        cpu_util_pct REAL NOT NULL,
                        power_watts INTEGER NOT NULL,
                        temp_c INTEGER NOT NULL,
                        profile_name TEXT,
                        memory_mb INTEGER NOT NULL,
                        cpu_cores INTEGER NOT NULL,
                        FOREIGN KEY (enclosure_id) REFERENCES oneview_enclosures(id) ON DELETE CASCADE
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_interconnects (
                        id TEXT PRIMARY KEY,
                        enclosure_id TEXT,
                        bay INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        model TEXT,
                        type TEXT,
                        FOREIGN KEY (enclosure_id) REFERENCES oneview_enclosures(id) ON DELETE CASCADE
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_storage_pools (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        capacity_gb REAL NOT NULL,
                        free_space_gb REAL NOT NULL,
                        system_name TEXT
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_fabric_nodes (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        role TEXT NOT NULL,
                        ip_address TEXT NOT NULL,
                        status TEXT NOT NULL,
                        health_score INTEGER NOT NULL
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_interfaces (
                        id TEXT PRIMARY KEY,
                        node_id TEXT,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        usage_in_bps REAL NOT NULL,
                        usage_out_bps REAL NOT NULL,
                        FOREIGN KEY (node_id) REFERENCES apic_fabric_nodes(id) ON DELETE CASCADE
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_logical (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tenant TEXT NOT NULL,
                        vrf TEXT NOT NULL,
                        bd_name TEXT NOT NULL,
                        epg TEXT NOT NULL
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        entity_name TEXT NOT NULL,
                        message TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        resolved INTEGER DEFAULT 0
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS historical_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        entity_type TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        metric_name TEXT NOT NULL,
                        metric_value REAL NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS kb_documents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        category TEXT NOT NULL,
                        embedding TEXT
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_server_profiles (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        server_hardware_id TEXT,
                        status TEXT NOT NULL,
                        compliance_state TEXT NOT NULL,
                        template_name TEXT,
                        firmware_baseline TEXT,
                        description TEXT,
                        FOREIGN KEY (server_hardware_id) REFERENCES oneview_server_hardware(id) ON DELETE SET NULL
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_networks (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        type TEXT NOT NULL,
                        vlan_id INTEGER,
                        status TEXT NOT NULL,
                        bandwidth_typical REAL,
                        subnet TEXT,
                        purpose TEXT
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oneview_firmware (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        version TEXT NOT NULL,
                        release_date TEXT,
                        iso_file_name TEXT,
                        status TEXT NOT NULL,
                        size_mb REAL
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_endpoints (
                        id TEXT PRIMARY KEY,
                        mac TEXT NOT NULL,
                        ip TEXT,
                        epg TEXT NOT NULL,
                        interface TEXT,
                        encap TEXT,
                        node_id TEXT,
                        status TEXT NOT NULL
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_contracts (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        tenant TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        filter_name TEXT,
                        protocol TEXT,
                        dst_port TEXT,
                        action TEXT NOT NULL
                    );
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apic_equipment (
                        id TEXT PRIMARY KEY,
                        node_id TEXT,
                        type TEXT NOT NULL,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        model TEXT,
                        serial_number TEXT,
                        FOREIGN KEY (node_id) REFERENCES apic_fabric_nodes(id) ON DELETE CASCADE
                    );
                """)

            conn.commit()
            print("Database schemas initialized successfully.")
        except Exception as e:
            conn.rollback()
            print(f"Error during schema initialization: {e}")
            raise e
        finally:
            conn.close()

# Export a default singleton instance
db = DBManager()
