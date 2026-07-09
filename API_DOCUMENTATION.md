# AIOps Infrastructure API Documentation

This document describes the APIs used by the AIOps collection system to interface with **HPE OneView** and **Cisco APIC (ACI)**. It details both the mock simulator endpoints (implemented in `app.py`) and the production endpoints used by the telemetry collectors (`collectors/oneview.py` and `collectors/apic.py`), along with their respective database mappings.

---

## 1. HPE OneView REST API Integration

The HPE OneView collector pulls physical infrastructure status, power usage, server blade statistics, and storage pool allocations from the OneView appliance.

### 1.1 Authentication / Session Management
- **Method**: `POST`
- **Mock Endpoint**: `/mock/oneview/rest/login-sessions`
- **Production Endpoint**: `/rest/login-sessions`
- **Headers**:
  - `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "userName": "admin",
    "password": "password"
  }
  ```
  *(In production, credentials are loaded from `Config.ONEVIEW_USER` and `Config.ONEVIEW_PASS`)*
- **Response Body**:
  ```json
  {
    "sessionID": "mock-session-token-9988776655"
  }
  ```
- **Usage**: The returned `sessionID` is extracted and used as the `Auth` header in all subsequent GET requests.

---

### 1.2 Fetch Enclosures
- **Method**: `GET`
- **Mock Endpoint**: `/mock/oneview/rest/enclosures`
- **Production Endpoint**: `/rest/enclosures`
- **Headers**:
  - `Auth`: `<sessionID>`
  - `X-API-Version`: `2000`
- **Response Body**:
  ```json
  [
    {
      "id": "enc1",
      "name": "Enclosure-01",
      "status": "OK",
      "temp_c": 32,
      "power_watts": 1650,
      "model": "Synergy 12000",
      "serial_number": "SGH822X01"
    },
    {
      "id": "enc2",
      "name": "Enclosure-02",
      "status": "OK",
      "temp_c": 29,
      "power_watts": 1420,
      "model": "Synergy 12000",
      "serial_number": "SGH822X02"
    }
  ]
  ```
- **Local DB Mapping**: Saved to `oneview_enclosures` table.
- **Alert Trigger**: If `status` is not `'OK'`, `'NORMAL'`, or `'UP'`, a `CRITICAL` or `WARNING` alert is created in the `alerts` table.

---

### 1.3 Fetch Server Hardware (Blades)
- **Method**: `GET`
- **Mock Endpoint**: `/mock/oneview/rest/server-hardware`
- **Production Endpoint**: `/rest/server-hardware`
- **Headers**:
  - `Auth`: `<sessionID>`
  - `X-API-Version`: `2000`
- **Response Body**:
  ```json
  [
    {
      "id": "server1_1",
      "enclosure_id": "enc1",
      "bay": 1,
      "name": "Blade-01",
      "status": "OK",
      "model": "Synergy 480 Gen10",
      "serial_number": "SGH822X01A",
      "cpu_util_pct": 45.2,
      "power_watts": 180,
      "temp_c": 36,
      "profile_name": "ESXi-Prod-ClusterA",
      "memory_mb": 262144,
      "cpu_cores": 32
    }
  ]
  ```
- **Local DB Mapping**: Saved to `oneview_server_hardware` table.
- **Alert Trigger**: 
  - If `status` is not healthy, an alert is logged.
  - **Thermal Rule**: If a server's temperature `temp_c` exceeds `80°C`, a custom `CRITICAL` thermal alert is logged (e.g., during simulated thermal throttling).

---

### 1.4 Fetch Storage Pools
- **Method**: `GET`
- **Mock Endpoint**: `/mock/oneview/rest/storage-pools`
- **Production Endpoint**: `/rest/storage-pools`
- **Headers**:
  - `Auth`: `<sessionID>`
  - `X-API-Version`: `2000`
- **Response Body**:
  ```json
  [
    {
      "id": "pool1",
      "name": "SAN-Prod-Pool-01",
      "status": "OK",
      "capacity_gb": 81920.0,
      "free_space_gb": 24576.0,
      "system_name": "3PAR-StoreServ-8200"
    }
  ]
  ```
- **Local DB Mapping**: Saved to `oneview_storage_pools` table.
- **Alert Trigger**: If status is not healthy, an alert is logged against the storage pool ID.

---

## 2. Cisco APIC (ACI) REST API Integration

The Cisco APIC (Application Policy Infrastructure Controller) collector queries the network fabric node health, layer 1 physical interface usage, and active system faults.

### 2.1 AAA Login (Authentication)
- **Method**: `POST`
- **Production Endpoint**: `/api/aaaLogin.json`
- **Headers**:
  - `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "aaaUser": {
      "attributes": {
        "name": "admin",
        "pwd": "apic_password"
      }
    }
  }
  ```
  *(In production, credentials are loaded from `Config.APIC_USER` and `Config.APIC_PASS`)*
- **Response**: Returns a token or sets a session cookie (typically `APIC-cookie`) containing the token which must be attached to subsequent network requests.

---

### 2.2 Fetch Fabric Nodes
- **Method**: `GET`
- **Mock Endpoint**: `/mock/apic/api/node/class/fabricNode.json`
- **Production Endpoint**: `/api/node/class/fabricNode.json`
- **Headers**:
  - Session cookie / authorization headers.
- **Response Body**:
  ```json
  [
    {
      "id": "spine201",
      "name": "Spine-201",
      "role": "spine",
      "ip_address": "10.0.0.201",
      "status": "online",
      "health_score": 100
    },
    {
      "id": "leaf102",
      "name": "Leaf-102",
      "role": "leaf",
      "ip_address": "10.0.0.102",
      "status": "online",
      "health_score": 95
    }
  ]
  ```
- **Local DB Mapping**: Saved to `apic_fabric_nodes` table.
- **Alert Trigger**: Triggered when a switch node transitions to `offline` or its status is unhealthy.

---

### 2.3 Fetch Physical Interfaces (L1 Physical Interfaces)
- **Method**: `GET`
- **Mock Endpoint**: `/mock/apic/api/node/class/l1PhysIf.json`
- **Production Endpoint**: `/api/node/class/l1PhysIf.json`
- **Response Body**:
  ```json
  [
    {
      "id": "leaf101_1",
      "node_id": "leaf101",
      "node_name": "Leaf-101",
      "name": "ethernet 1/1",
      "status": "up",
      "usage_in_bps": 450000000.0,
      "usage_out_bps": 320000000.0
    }
  ]
  ```
- **Local DB Mapping**: Saved to `apic_interfaces` table.
- **Alert Trigger**: If an interface status is not `'up'` (e.g. `'down'`), a warning/critical alert is generated. Once the status returns to `'up'`, it is cleared.

---

### 2.4 Fetch Active System Faults
- **Method**: `GET`
- **Mock Endpoint**: `/mock/apic/api/node/class/faultInst.json`
- **Production Endpoint**: `/api/node/class/faultInst.json`
- **Response Body**:
  ```json
  [
    {
      "id": "fault_epg_1024",
      "code": "F1024",
      "entity_name": "Tenant:Production/VRF:Prod-VRF/EPG:Prod-DB-EPG",
      "message": "High packet drop rates detected on DB EPG cluster."
    }
  ]
  ```
- **Local DB Mapping**: Evaluated directly against the `alerts` table. Active faults are added as `CRITICAL` network incidents.
- **State Cleanup**: The collector cross-references current active alerts in the DB with the API response; any historical APIC logical alert (`fault_...`) that is *no longer reported* by the API is automatically marked as resolved (`resolved = True`).

---

## 3. Local Telemetry Storage Schemas

Data collected from the external APIs is normalized and stored locally (PostgreSQL or SQLite fallback).

### 3.1 HPE OneView Database Tables
```sql
CREATE TABLE oneview_enclosures (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    temp_c INT NOT NULL,
    power_watts INT NOT NULL,
    model VARCHAR(100),
    serial_number VARCHAR(100)
);

CREATE TABLE oneview_server_hardware (
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

CREATE TABLE oneview_storage_pools (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    capacity_gb REAL NOT NULL,
    free_space_gb REAL NOT NULL,
    system_name VARCHAR(100)
);
```

### 3.2 Cisco APIC Database Tables
```sql
CREATE TABLE apic_fabric_nodes (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL,
    ip_address VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    health_score INT NOT NULL
);

CREATE TABLE apic_interfaces (
    id VARCHAR(100) PRIMARY KEY,
    node_id VARCHAR(100) REFERENCES apic_fabric_nodes(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    usage_in_bps REAL NOT NULL,
    usage_out_bps REAL NOT NULL
);
```

### 3.3 Historical Metrics & Telemetry Aggregate Table
Every collection cycle, aggregate telemetry values are computed and recorded for time-series visualization:
```sql
CREATE TABLE historical_metrics (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,    -- 'enclosure', 'network'
    entity_id VARCHAR(100) NOT NULL,    -- 'all', 'fabric'
    metric_name VARCHAR(50) NOT NULL,    -- 'temp_c', 'power_watts', 'inbound_mbps', 'outbound_mbps'
    metric_value REAL NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
- **HPE OneView aggregates**:
  - `temp_c`: Average temperature across all active enclosures.
  - `power_watts`: Sum of enclosure power draw + server blade power draw.
- **Cisco APIC aggregates**:
  - `inbound_mbps`: Total input rate (converted from sum of `usage_in_bps` in bits to Megabits).
  - `outbound_mbps`: Total output rate (converted from sum of `usage_out_bps` in bits to Megabits).
