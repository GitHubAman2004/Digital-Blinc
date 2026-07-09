from flask import Flask, jsonify, request
from db import db
import seeder
from scheduler import aiops_scheduler
from chatbot.rag import rag_manager
from config import Config
from datetime import datetime, timedelta
import random
import threading, time, queue, json as json_module

app = Flask(__name__)

# Global in-memory simulation states
sim_states = {
    'fan_failure': False,
    'psu_failure': False,
    'storage_failure': False,
    'thermal_throttling': False,
    'leaf_down': False,
    'interface_flap': False,
    'epg_fault': False
}

scmb_events = []  # State-Change Message Bus events
msmb_events = []  # Metric Streaming Message Bus events
bus_lock = threading.Lock()

# ==================== MOCK HPE ONEVIEW API SIMULATOR ====================

@app.route('/mock/oneview/rest/login-sessions', methods=['POST'])
def mock_oneview_login():
    return jsonify({"sessionID": "mock-session-token-9988776655"})

@app.route('/mock/oneview/rest/enclosures', methods=['GET'])
def mock_oneview_enclosures():
    # Evaluate simulated faults
    enc1_status = 'OK'
    enc1_temp = 32
    enc1_power = 1650

    if sim_states['fan_failure']:
        enc1_status = 'Critical'
        enc1_temp = 48  # Chassis overheats due to fan failure
        enc1_power = 1950  # Fans drawing auxiliary power or struggling
    elif sim_states['psu_failure']:
        enc1_status = 'Warning'
        enc1_power = 950  # Lost half power redundancy

    return jsonify([
        {
            "id": "enc1",
            "name": "Enclosure-01",
            "status": enc1_status,
            "temp_c": enc1_temp,
            "power_watts": enc1_power,
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
    ])

@app.route('/mock/oneview/rest/server-hardware', methods=['GET'])
def mock_oneview_servers():
    # Base server list
    servers = [
        {"id": "server1_1", "enclosure_id": "enc1", "bay": 1, "name": "Blade-01", "status": "OK", "model": "Synergy 480 Gen10", "serial_number": "SGH822X01A", "cpu_util_pct": 45.2, "power_watts": 180, "temp_c": 36, "profile_name": "ESXi-Prod-ClusterA", "memory_mb": 262144, "cpu_cores": 32},
        {"id": "server1_2", "enclosure_id": "enc1", "bay": 2, "name": "Blade-02", "status": "OK", "model": "Synergy 480 Gen10", "serial_number": "SGH822X01B", "cpu_util_pct": 62.5, "power_watts": 210, "temp_c": 42, "profile_name": "ESXi-Prod-ClusterA", "memory_mb": 262144, "cpu_cores": 32},
        {"id": "server1_3", "enclosure_id": "enc1", "bay": 3, "name": "Blade-03", "status": "OK", "model": "Synergy 660 Gen10", "serial_number": "SGH822X01C", "cpu_util_pct": 82.1, "power_watts": 350, "temp_c": 48, "profile_name": "BareMetal-SAP-DB", "memory_mb": 524288, "cpu_cores": 64},
        {"id": "server1_4", "enclosure_id": "enc1", "bay": 4, "name": "Blade-04", "status": "OK", "model": "Synergy 480 Gen10", "serial_number": "SGH822X01D", "cpu_util_pct": 15.0, "power_watts": 140, "temp_c": 33, "profile_name": "K8s-Dev-Worker", "memory_mb": 131072, "cpu_cores": 16},
        {"id": "server2_1", "enclosure_id": "enc2", "bay": 1, "name": "Blade-05", "status": "OK", "model": "Synergy 480 Gen10", "serial_number": "SGH822X02A", "cpu_util_pct": 38.0, "power_watts": 175, "temp_c": 34, "profile_name": "ESXi-Stage-ClusterB", "memory_mb": 262144, "cpu_cores": 32},
        {"id": "server2_2", "enclosure_id": "enc2", "bay": 2, "name": "Blade-06", "status": "OK", "model": "Synergy 480 Gen10", "serial_number": "SGH822X02B", "cpu_util_pct": 12.4, "power_watts": 130, "temp_c": 31, "profile_name": "K8s-Dev-Worker", "memory_mb": 131072, "cpu_cores": 16}
    ]

    # Modify based on active simulated failures
    for s in servers:
        # Fan failure: All servers in enclosure 01 heat up slightly
        if sim_states['fan_failure'] and s['enclosure_id'] == 'enc1':
            s['temp_c'] += 15
            s['status'] = 'Warning'
        
        # Thermal Throttling: Blade-03 (SAP-DB) severely overheats
        if sim_states['thermal_throttling'] and s['id'] == 'server1_3':
            s['temp_c'] = 88
            s['cpu_util_pct'] = 99.5
            s['status'] = 'Critical'
            s['power_watts'] = 450
            
        # PSU failure: Blade-03 loses power feed redundancy
        if sim_states['psu_failure'] and s['id'] == 'server1_3':
            s['status'] = 'Warning'
            s['power_watts'] = 220  # Runs in low performance power state

    return jsonify(servers)

@app.route('/mock/oneview/rest/storage-pools', methods=['GET'])
def mock_oneview_storage():
    pools = [
        {"id": "pool1", "name": "SAN-Prod-Pool-01", "status": "OK", "capacity_gb": 81920.0, "free_space_gb": 24576.0, "system_name": "3PAR-StoreServ-8200"},
        {"id": "pool2", "name": "SAN-Backup-Pool-02", "status": "OK", "capacity_gb": 40960.0, "free_space_gb": 18432.0, "system_name": "3PAR-StoreServ-8200"},
        {"id": "pool3", "name": "SAN-Dev-Pool-03", "status": "OK", "capacity_gb": 20480.0, "free_space_gb": 14336.0, "system_name": "StoreOnce-VSA"}
    ]

    # Modify based on simulated storage failure
    if sim_states['storage_failure']:
        pools[0]['status'] = 'Critical'  # RAID Offline / Degraded
        pools[0]['free_space_gb'] = 2048.0  # Storage space shrinks because spindles went offline

    return jsonify(pools)


# ==================== MOCK CISCO APIC API SIMULATOR ====================

@app.route('/mock/apic/api/node/class/fabricNode.json', methods=['GET'])
def mock_apic_nodes():
    nodes = [
        {"id": "spine201", "name": "Spine-201", "role": "spine", "ip_address": "10.0.0.201", "status": "online", "health_score": 100},
        {"id": "spine202", "name": "Spine-202", "role": "spine", "ip_address": "10.0.0.202", "status": "online", "health_score": 98},
        {"id": "leaf101", "name": "Leaf-101", "role": "leaf", "ip_address": "10.0.0.101", "status": "online", "health_score": 100},
        {"id": "leaf102", "name": "Leaf-102", "role": "leaf", "ip_address": "10.0.0.102", "status": "online", "health_score": 95},
        {"id": "leaf103", "name": "Leaf-103", "role": "leaf", "ip_address": "10.0.0.103", "status": "online", "health_score": 100}
    ]

    # Leaf Down simulation
    if sim_states['leaf_down']:
        nodes[3]['status'] = 'offline'
        nodes[3]['health_score'] = 0

    return jsonify(nodes)

@app.route('/mock/apic/api/node/class/l1PhysIf.json', methods=['GET'])
def mock_apic_interfaces():
    interfaces = [
        {"id": "leaf101_1", "node_id": "leaf101", "node_name": "Leaf-101", "name": "ethernet 1/1", "status": "up", "usage_in_bps": 450000000.0, "usage_out_bps": 320000000.0},
        {"id": "leaf101_2", "node_id": "leaf101", "node_name": "Leaf-101", "name": "ethernet 1/2", "status": "up", "usage_in_bps": 890000000.0, "usage_out_bps": 640000000.0},
        {"id": "leaf102_1", "node_id": "leaf102", "node_name": "Leaf-102", "name": "ethernet 1/1", "status": "up", "usage_in_bps": 520000000.0, "usage_out_bps": 480000000.0},
        {"id": "leaf102_5", "node_id": "leaf102", "node_name": "Leaf-102", "name": "ethernet 1/5", "status": "up", "usage_in_bps": 150000000.0, "usage_out_bps": 90000000.0},
        {"id": "leaf103_1", "node_id": "leaf103", "node_name": "Leaf-103", "name": "ethernet 1/1", "status": "up", "usage_in_bps": 720000000.0, "usage_out_bps": 610000000.0}
    ]

    # Leaf Down forces its interfaces down
    if sim_states['leaf_down']:
        interfaces[2]['status'] = 'down'
        interfaces[2]['usage_in_bps'] = 0
        interfaces[2]['usage_out_bps'] = 0
        interfaces[3]['status'] = 'down'
        interfaces[3]['usage_in_bps'] = 0
        interfaces[3]['usage_out_bps'] = 0

    # Interface Link flap simulation
    if sim_states['interface_flap']:
        interfaces[1]['status'] = 'down'  # ethernet 1/2 on Leaf-101 goes down
        interfaces[1]['usage_in_bps'] = 0
        interfaces[1]['usage_out_bps'] = 0

    return jsonify(interfaces)

@app.route('/mock/apic/api/node/class/faultInst.json', methods=['GET'])
def mock_apic_faults():
    faults = []
    
    # Logical EPG Packet Drop alert
    if sim_states['epg_fault']:
        faults.append({
            "id": "fault_epg_1024",
            "code": "F1024",
            "entity_name": "Tenant:Production/VRF:Prod-VRF/EPG:Prod-DB-EPG",
            "message": "High packet drop rates detected on DB EPG cluster."
        })
        
    return jsonify(faults)


# ==================== CLIENT API ENDPOINTS ====================

@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    # Verify DB connectivity
    db_connected = False
    try:
        db.fetch_one("SELECT 1;")
        db_connected = True
    except:
        pass

    # Read from DB
    oneview_data = {}
    apic_data = {}

    if db_connected:
        try:
            # HPE OneView Database pull
            encs = db.fetch_all("SELECT * FROM oneview_enclosures;")
            servers = db.fetch_all("SELECT * FROM oneview_server_hardware;")
            pools = db.fetch_all("SELECT * FROM oneview_storage_pools;")
            
            # Calculate health index
            ov_unhealthy = len([e for e in encs if e['status'] != 'OK']) + len([s for s in servers if s['status'] != 'OK'])
            ov_health = max(0, 100 - (ov_unhealthy * 15))
            
            # Fetch historical telemetry averages (last 12 readings)
            ov_history = db.fetch_all("""
                SELECT timestamp, 
                       MAX(CASE WHEN metric_name = 'temp_c' THEN metric_value END) as temp_c,
                       MAX(CASE WHEN metric_name = 'power_watts' THEN metric_value END) as power_watts
                FROM historical_metrics
                WHERE entity_type = 'enclosure'
                GROUP BY timestamp
                ORDER BY timestamp DESC
                LIMIT 12;
            """)
            ov_history.reverse()  # chronological order
            
            # Transform enclosures: rename serial_number -> serial
            for e in encs:
                if 'serial_number' in e:
                    e['serial'] = e.pop('serial_number')

            # Transform servers -> blades: rename fields
            blades = []
            for s in servers:
                blade = dict(s)
                if 'temp_c' in blade:
                    blade['temperature'] = blade.pop('temp_c')
                if 'power_watts' in blade:
                    blade['power_draw'] = blade.pop('power_watts')
                if 'serial_number' in blade:
                    blade['serial'] = blade.pop('serial_number')
                blades.append(blade)

            # Transform storage pools: compute total_tb, used_tb, add raid
            for p in pools:
                cap = p.get('capacity_gb', 0)
                free = p.get('free_space_gb', 0)
                p['total_tb'] = round(cap / 1024, 2)
                p['used_tb'] = round((cap - free) / 1024, 2)
                p['raid'] = 'RAID-5'

            # Transform OV telemetry history
            for h in ov_history:
                if 'temp_c' in h:
                    h['avg_temp'] = h.pop('temp_c')
                if 'power_watts' in h:
                    h['avg_power'] = h.pop('power_watts')
                if 'timestamp' in h:
                    h['ts'] = h.pop('timestamp')

            oneview_data = {
                "enclosures": encs,
                "blades": blades,
                "storage_pools": pools,
                "health_index": ov_health,
                "telemetry_history": ov_history
            }

            # Cisco APIC Database pull
            nodes = db.fetch_all("SELECT * FROM apic_fabric_nodes;")
            interfaces = db.fetch_all("SELECT * FROM apic_interfaces;")
            logical = db.fetch_all("SELECT * FROM apic_logical;")
            
            # Fetch active endpoints count
            endpoints_count = 14 + len([f for f in interfaces if f.get('status') == 'up' or f.get('oper_state') == 'up']) * 3
            if sim_states['leaf_down']:
                endpoints_count -= 6

            # Compute APIC Health
            apic_health = int(sum(n['health_score'] for n in nodes) / len(nodes)) if nodes else 100
            if sim_states['epg_fault']:
                apic_health = max(0, apic_health - 15)

            # Cisco bandwidth history
            apic_history = db.fetch_all("""
                SELECT timestamp,
                       MAX(CASE WHEN metric_name = 'inbound_mbps' THEN metric_value END) as inbound_mbps,
                       MAX(CASE WHEN metric_name = 'outbound_mbps' THEN metric_value END) as outbound_mbps
                FROM historical_metrics
                WHERE entity_type = 'network'
                GROUP BY timestamp
                ORDER BY timestamp DESC
                LIMIT 12;
            """)
            apic_history.reverse()

            # Transform switches: rename serial_number -> serial, add model
            switches = []
            for n in nodes:
                sw = dict(n)
                if 'serial_number' in sw:
                    sw['serial'] = sw.pop('serial_number')
                sw['model'] = 'N9K-C9336C-FX2' if sw.get('role') == 'spine' else 'N9K-C93180YC-FX'
                switches.append(sw)

            # Transform interfaces: rename status -> oper_state, add speed/errors
            for iface in interfaces:
                if 'status' in iface:
                    iface['oper_state'] = iface.pop('status')
                iface['speed'] = '10G'
                iface['errors'] = 0

            # Transform tenants: rename bd_name -> bd
            tenants = []
            for l in logical:
                t = dict(l)
                if 'bd_name' in t:
                    t['bd'] = t.pop('bd_name')
                tenants.append(t)

            # Transform APIC telemetry history
            for h in apic_history:
                if 'inbound_mbps' in h:
                    h['ingress_mbps'] = h.pop('inbound_mbps')
                if 'outbound_mbps' in h:
                    h['egress_mbps'] = h.pop('outbound_mbps')
                if 'timestamp' in h:
                    h['ts'] = h.pop('timestamp')

            apic_data = {
                "switches": switches,
                "interfaces": interfaces,
                "tenants": tenants,
                "endpoints_count": endpoints_count,
                "health_index": apic_health,
                "telemetry_history": apic_history
            }

        except Exception as e:
            print(f"Flask API: Error compiling database metrics - {e}")
            db_connected = False

    return jsonify({
        "db_connected": db_connected,
        "oneview_connected": True,  # Mock endpoint is always online inside Flask
        "apic_connected": True,     # Mock endpoint is always online inside Flask
        "oneview": oneview_data,
        "apic": apic_data
    })

@app.route('/api/metrics/server/<id>', methods=['GET'])
def get_server_detail(id):
    server = db.fetch_one("SELECT * FROM oneview_server_hardware WHERE id = %s;", (id,))
    if server:
        return jsonify(server)
    return jsonify({"error": "Blade server not found"}), 404

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    rows = db.fetch_all("SELECT * FROM alerts ORDER BY timestamp DESC;")
    for r in rows:
        r['status'] = 'resolved' if r.get('resolved') else 'active'
    return jsonify(rows)

@app.route('/api/alerts/<id>/resolve', methods=['POST'])
def resolve_alert(id):
    db.execute_query("UPDATE alerts SET resolved = %s WHERE id = %s;", (True, id))
    return jsonify({"success": True})

@app.route('/api/alerts/resolve-all', methods=['POST'])
def resolve_all_alerts():
    db.execute_query("UPDATE alerts SET resolved = %s WHERE resolved = %s;", (True, False))
    return jsonify({"success": True})

@app.route('/api/sim/status', methods=['GET'])
def get_sim_status():
    return jsonify(sim_states)

@app.route('/api/sim/trigger', methods=['POST'])
def trigger_sim():
    data = request.json
    sim_type = data.get("scenario")
    if sim_type in sim_states:
        sim_states[sim_type] = data.get('active', not sim_states[sim_type])
        print(f"Simulator: Toggled simulation '{sim_type}' to {sim_states[sim_type]}")
        return jsonify({"type": sim_type, "active": sim_states[sim_type]})
    return jsonify({"error": "Invalid simulation type"}), 400

@app.route('/api/chat', methods=['POST'])
def chat():
    import requests
    data = request.json or {}
    message = data.get("message", "")
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "Message is required"}), 400

    system_prompt = (
        "You are an AIOps Assistant Chatbot for a cloud infrastructure dashboard.\n"
        "If the user asks you to generate a chart, plot a graph, compare metrics, or visualize telemetry, "
        "you MUST embed a JSON code block in your markdown response using the exact format below. "
        "For everything else, answer conversationally in markdown.\n\n"
        "Here is the exact JSON structure to use inside the ```json ... ``` code block for charts:\n"
        "{\n"
        '  "chartType": "line" | "bar" | "area" | "pie" | "radar" | "scatter",\n'
        '  "title": "A descriptive title for the chart",\n'
        '  "xAxisKey": "name",\n'
        '  "data": [\n'
        '    { "name": "Item 1", "metric1": 45, "metric2": 32 },\n'
        '    { "name": "Item 2", "metric1": 70, "metric2": 65 }\n'
        '  ],\n'
        '  "series": [\n'
        '    { "key": "metric1", "color": "#54a3ff", "name": "Label for Metric 1" },\n'
        '    { "key": "metric2", "color": "#ff453a", "name": "Label for Metric 2" }\n'
        '  ]\n'
        "}\n\n"
        "CRITICAL RULES FOR CHART JSON DATA:\n"
        "1. Allowed chartTypes: 'line', 'bar', 'area', 'pie', 'radar', 'scatter'.\n"
        "2. All metric values in the 'data' array MUST be raw numbers (e.g. 950 or 45.5). NEVER output strings with units (e.g. do NOT output '950 Mbps' or '35 C').\n"
        "3. When comparing different entities (like comparing Thor-Server and Loki-Server) on a single metric, use a single continuous metric key (e.g. 'speed') across all objects in the 'data' array. Do NOT create separate sparse keys for each entity (e.g. do NOT create keys like 'Thor-Server Speed' and 'Loki-Server Speed').\n"
        "   - Correct Comparison Format:\n"
        "     data: [{ \"name\": \"Thor-Server\", \"speed\": 950 }, { \"name\": \"Loki-Server\", \"speed\": 150 }]\n"
        "     series: [{ \"key\": \"speed\", \"color\": \"#54a3ff\", \"name\": \"Network Speed (Mbps)\" }]\n"
        "4. Ensure the 'xAxisKey' value matches the key name used for the X-axis labels in the 'data' array (typically 'name') exactly.\n"
        "5. Output valid JSON. Double check syntax and quotes before responding."
    )

    try:
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": message})

        res = requests.post(f"{Config.OLLAMA_HOST}/api/chat", json={
            "model": Config.CHAT_MODEL,
            "messages": messages,
            "stream": False
        }, timeout=90)

        if res.status_code == 200:
            ollama_res = res.json()
            reply = ollama_res.get("message", {}).get("content", "")
            return jsonify({"reply": reply})
        else:
            return jsonify({"reply": f"I'm sorry, I'm unable to connect to the local LLM engine at the moment. (Error code: {res.status_code})"})
    except Exception as e:
        print(f"Chatbot API: Error calling Ollama - {e}")
        return jsonify({"reply": "I'm sorry, I couldn't reach the local Qwen model. Make sure Ollama is running on your system."})

# ==================== KNOWLEDGE BASE (RAG) ENDPOINTS ====================

@app.route('/api/kb/list', methods=['GET'])
def get_kb_list():
    docs = db.fetch_all("SELECT title, content, category FROM kb_documents ORDER BY id DESC;")
    return jsonify(docs)

@app.route('/api/kb/index', methods=['POST'])
def index_runbook():
    data = request.json
    title = data.get("title")
    category = data.get("category")
    content = data.get("content")
    
    if not title or not content:
        return jsonify({"error": "Missing title or content"}), 400
        
    try:
        rag_manager.index_document(title, content, category)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to index document: {e}"}), 500

@app.route('/api/kb/search', methods=['GET'])
def search_kb():
    query = request.args.get("query")
    if not query:
        return jsonify([]), 400
        
    try:
        results = rag_manager.search_kb(query)
        # Convert any vector objects/scores to serializable types
        clean_results = []
        for r in results:
            clean_results.append({
                "title": r["title"],
                "content": r["content"],
                "category": r["category"]
            })
        return jsonify(clean_results)
    except Exception as e:
        print(f"RAG search error: {e}")
        return jsonify([]), 500


# ==================== MESSAGE BUS SIMULATION ====================

def message_bus_generator():
    """Background thread that simulates SCMB and MSMB events.
    
    ===========================================================================
    NOTE FOR LIVE INTEGRATION (HPE ONEVIEW MESSAGE BUS):
    ===========================================================================
    To replace this simulator with real events from a live HPE OneView appliance:
    
    1. OneView exposes its State-Change Message Bus (SCMB) and Metric Streaming 
       Message Bus (MSMB) as an AMQPS (RabbitMQ over SSL) broker on port 5671.
    2. Install the 'pika' package: pip install pika
    3. Download the AMQP client certificates from OneView via the REST endpoint:
       GET /rest/certificates/client/rabbitmq
    4. Save the key, certificate, and CA files locally.
    5. Connect to the message bus broker over SSL:
       
       import pika, ssl
       
       ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile="carabbitmq.pem")
       ssl_context.load_cert_chain(certfile="client.pem", keyfile="clientkey.pem")
       
       conn_params = pika.ConnectionParameters(
           host=Config.ONEVIEW_HOST,
           port=5671,
           virtual_host="/",
           credentials=pika.ExternalCredentials(),
           ssl_options=pika.SSLOptions(context=ssl_context)
       )
       connection = pika.BlockingConnection(conn_params)
       channel = connection.channel()
       
       # For SCMB events:
       def on_scmb_event(ch, method, properties, body):
           event = json_module.loads(body)
           with bus_lock:
               scmb_events.append(event)
               if len(scmb_events) > 200: scmb_events.pop(0)
               
       channel.basic_consume(queue='scmb', on_message_callback=on_scmb_event, auto_ack=True)
       channel.start_consuming()
    ===========================================================================
    """
    scmb_templates = [
        {'type': 'server-hardware', 'action': 'status-change', 'resource': 'Blade-{bay}', 'enclosure': 'Enclosure-0{enc}', 'from_state': 'OK', 'to_state': 'Warning', 'reason': 'Temperature threshold exceeded'},
        {'type': 'server-hardware', 'action': 'profile-applied', 'resource': 'Blade-{bay}', 'enclosure': 'Enclosure-0{enc}', 'profile': 'ESXi-Prod-ClusterA', 'reason': 'Server profile assignment completed'},
        {'type': 'enclosure', 'action': 'status-change', 'resource': 'Enclosure-0{enc}', 'from_state': 'OK', 'to_state': 'OK', 'reason': 'Fan module health check passed'},
        {'type': 'interconnect', 'action': 'link-state-change', 'resource': 'VC-FC-Module-{bay}', 'enclosure': 'Enclosure-0{enc}', 'port': 'Q1:1', 'from_state': 'Linked', 'to_state': 'Linked', 'reason': 'Uplink re-negotiation complete'},
        {'type': 'server-hardware', 'action': 'firmware-updated', 'resource': 'Blade-{bay}', 'enclosure': 'Enclosure-0{enc}', 'firmware': 'iLO 5 v2.81', 'reason': 'Firmware baseline compliance update'},
        {'type': 'storage', 'action': 'pool-threshold', 'resource': 'SAN-Prod-Pool-01', 'threshold': '75%', 'reason': 'Storage pool utilization monitoring'},
        {'type': 'alert', 'action': 'alert-raised', 'resource': 'Blade-{bay}', 'enclosure': 'Enclosure-0{enc}', 'severity': 'warning', 'reason': 'Predictive failure on DIMM slot 4A'},
        {'type': 'task', 'action': 'task-completed', 'resource': 'Firmware Update Task', 'taskId': 'TASK-{task}', 'reason': 'Scheduled firmware compliance scan finished'},
        {'type': 'enclosure', 'action': 'compliance-check', 'resource': 'Enclosure-0{enc}', 'from_state': 'Compliant', 'to_state': 'Compliant', 'reason': 'Logical enclosure compliance verified'},
        {'type': 'server-hardware', 'action': 'power-on', 'resource': 'Blade-{bay}', 'enclosure': 'Enclosure-0{enc}', 'reason': 'Server powered on via iLO'},
    ]

    last_scmb = time.time()
    last_msmb = time.time()

    while True:
        now = time.time()

        # SCMB: generate event every 8-12 seconds
        if now - last_scmb >= random.uniform(8, 12):
            template = random.choice(scmb_templates).copy()
            bay = random.randint(1, 6)
            enc = random.randint(1, 2)
            task = random.randint(1000, 9999)
            # Format all string values
            for k, v in template.items():
                if isinstance(v, str):
                    template[k] = v.format(bay=bay, enc=enc, task=task)
            event = {
                'bus': 'SCMB',
                'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                'changeType': template.get('action', 'unknown'),
                'resourceType': template.get('type', 'unknown'),
                'resourceName': template.get('resource', 'Unknown'),
                'details': template
            }
            with bus_lock:
                scmb_events.append(event)
                if len(scmb_events) > 200:
                    scmb_events.pop(0)
            last_scmb = now

        # MSMB: generate metrics every 3-5 seconds
        if now - last_msmb >= random.uniform(3, 5):
            blade_id = random.choice(['Blade-01', 'Blade-02', 'Blade-03', 'Blade-04', 'Blade-05', 'Blade-06'])
            enc_name = 'Enclosure-01' if blade_id in ['Blade-01','Blade-02','Blade-03','Blade-04'] else 'Enclosure-02'
            base_temp = random.uniform(30, 50)
            base_power = random.uniform(120, 380)
            base_cpu = random.uniform(8, 95)

            if sim_states.get('fan_failure') and enc_name == 'Enclosure-01':
                base_temp += 20
            if sim_states.get('thermal_throttling') and blade_id == 'Blade-03':
                base_temp = random.uniform(85, 92)
                base_cpu = random.uniform(95, 100)

            metric = {
                'bus': 'MSMB',
                'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                'resourceName': blade_id,
                'enclosure': enc_name,
                'metrics': {
                    'cpuUtilization': round(base_cpu, 1),
                    'cpuTemperature': round(base_temp, 1),
                    'powerConsumed': round(base_power, 0),
                    'memoryUtilization': round(random.uniform(20, 85), 1),
                    'fanSpeedRpm': random.randint(3200, 8500) if not sim_states.get('fan_failure') else random.randint(0, 500),
                    'ambientTemperature': round(base_temp - random.uniform(5, 12), 1),
                    'networkAdapterThroughputMbps': round(random.uniform(100, 9500), 0)
                }
            }
            with bus_lock:
                msmb_events.append(metric)
                if len(msmb_events) > 500:
                    msmb_events.pop(0)
            last_msmb = now

        time.sleep(0.5)


# ==================== MESSAGE BUS REST ENDPOINTS ====================

@app.route('/api/bus/scmb', methods=['GET'])
def get_scmb():
    limit = request.args.get('limit', 50, type=int)
    with bus_lock:
        return jsonify(scmb_events[-limit:])

@app.route('/api/bus/msmb', methods=['GET'])
def get_msmb():
    limit = request.args.get('limit', 50, type=int)
    with bus_lock:
        return jsonify(msmb_events[-limit:])

@app.route('/api/bus/msmb/latest', methods=['GET'])
def get_msmb_latest():
    """Returns latest metric reading per blade."""
    with bus_lock:
        latest = {}
        for m in msmb_events:
            latest[m['resourceName']] = m
        return jsonify(list(latest.values()))


# ==================== FLASK SERVER INITIALIZATION ====================

if __name__ == "__main__":
    print("Initializing AIOps platform components...")
    
    # 1. Initialize Tables
    db.init_db()
    
    # 2. Seed Baseline Data
    seeder.seed_database()
    
    # 3. Start Background Scheduler
    aiops_scheduler.start()
    
    # 4. Start Message Bus Simulator
    bus_thread = threading.Thread(target=message_bus_generator, daemon=True)
    bus_thread.start()
    print("OneView Message Bus Simulator: SCMB + MSMB threads active.")
    
    # 5. Start Flask REST API Server
    try:
        app.run(host="0.0.0.0", port=Config.PORT, debug=False)
    finally:
        # Stop background thread on exit
        aiops_scheduler.shutdown()
