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
    'epg_fault': False,
    'firmware_mismatch': False,
    'interconnect_uplink_down': False,
    'apic_psu_failure': False,
    'contract_deny_log': False
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


# 2a. /mock/oneview/rest/server-profiles
@app.route('/mock/oneview/rest/server-profiles', methods=['GET'])
def mock_oneview_server_profiles():
    profiles = [
        {'uri': '/rest/server-profiles/prof-001', 'name': 'ESXi-Prod-ClusterA', 'serverHardwareUri': '/rest/server-hardware/server1_1', 'status': 'OK', 'templateCompliance': 'Compliant', 'serverProfileTemplateUri': '/rest/server-profile-templates/ESXi-Production-Template', 'firmware': {'firmwareBaselineUri': '/rest/firmware-drivers/fw-001'}, 'description': 'Production ESXi cluster profile'},
        {'uri': '/rest/server-profiles/prof-002', 'name': 'BareMetal-SAP-DB', 'serverHardwareUri': '/rest/server-hardware/server1_3', 'status': 'OK', 'templateCompliance': 'Compliant', 'serverProfileTemplateUri': '/rest/server-profile-templates/BareMetal-SAP-Template', 'firmware': {'firmwareBaselineUri': '/rest/firmware-drivers/fw-001'}, 'description': 'SAP HANA database server'},
        {'uri': '/rest/server-profiles/prof-003', 'name': 'K8s-Dev-Worker', 'serverHardwareUri': '/rest/server-hardware/server1_4', 'status': 'OK', 'templateCompliance': 'Compliant', 'serverProfileTemplateUri': '/rest/server-profile-templates/K8s-Worker-Template', 'firmware': {'firmwareBaselineUri': '/rest/firmware-drivers/fw-002'}, 'description': 'Kubernetes development worker node'},
        {'uri': '/rest/server-profiles/prof-004', 'name': 'ESXi-Stage-ClusterB', 'serverHardwareUri': '/rest/server-hardware/server2_1', 'status': 'OK', 'templateCompliance': 'Compliant', 'serverProfileTemplateUri': '/rest/server-profile-templates/ESXi-Staging-Template', 'firmware': {'firmwareBaselineUri': '/rest/firmware-drivers/fw-001'}, 'description': 'Staging ESXi cluster profile'},
        {'uri': '/rest/server-profiles/prof-005', 'name': 'GPU-ML-Training', 'serverHardwareUri': '/rest/server-hardware/server1_2', 'status': 'OK', 'templateCompliance': 'Compliant', 'serverProfileTemplateUri': '/rest/server-profile-templates/GPU-Compute-Template', 'firmware': {'firmwareBaselineUri': '/rest/firmware-drivers/fw-003'}, 'description': 'Machine learning training node'},
        {'uri': '/rest/server-profiles/prof-006', 'name': 'Docker-CI-Runner', 'serverHardwareUri': '/rest/server-hardware/server2_2', 'status': 'OK', 'templateCompliance': 'Compliant', 'serverProfileTemplateUri': '/rest/server-profile-templates/Container-Host-Template', 'firmware': {'firmwareBaselineUri': '/rest/firmware-drivers/fw-001'}, 'description': 'CI/CD Docker build runner'}
    ]
    if sim_states['firmware_mismatch']:
        profiles[2]['templateCompliance'] = 'NonCompliant'
        profiles[2]['status'] = 'Warning'
        profiles[4]['templateCompliance'] = 'NonCompliant'
        profiles[4]['status'] = 'Warning'
    return jsonify({"members": profiles, "count": len(profiles)})

# 2b. /mock/oneview/rest/server-hardware/<id>/utilization
@app.route('/mock/oneview/rest/server-hardware/<id>/utilization', methods=['GET'])
def mock_oneview_server_utilization(id):
    import random
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    samples_count = 24
    
    cpu_samples = []
    temp_samples = []
    power_samples = []
    
    cpu_base = 40.0
    temp_base = 35.0
    power_base = 180.0
    
    if id == 'server1_3':
        cpu_base = 80.0
        temp_base = 48.0
        power_base = 350.0
    
    if sim_states['thermal_throttling'] and id == 'server1_3':
        cpu_base = 95.0
        temp_base = 82.0
        power_base = 390.0

    for i in range(samples_count):
        ts = (now - timedelta(minutes=5 * (samples_count - i))).strftime('%Y-%m-%dT%H:%M:%SZ')
        cpu_samples.append([ts, round(cpu_base + random.uniform(-5.0, 5.0), 1)])
        temp_samples.append([ts, round(temp_base + random.uniform(-2.0, 2.0), 1)])
        power_samples.append([ts, int(power_base + random.uniform(-15.0, 15.0))])
        
    return jsonify({
        "metricList": [
            {"metricName": "CpuUtilization", "metricCapacity": 100.0, "metricSamples": cpu_samples},
            {"metricName": "CpuAverageFreq", "metricCapacity": 3000.0, "metricSamples": []},
            {"metricName": "AmbientTemperature", "metricCapacity": 40.0, "metricSamples": temp_samples},
            {"metricName": "PowerConsumed", "metricCapacity": 500.0, "metricSamples": power_samples}
        ]
    })

# 2c. /mock/oneview/rest/interconnects
@app.route('/mock/oneview/rest/interconnects', methods=['GET'])
def mock_oneview_interconnects():
    ports = []
    for p_num in range(1, 9):
        p_status = 'Linked'
        p_reason = 'None'
        p_speed = '40Gbps' if p_num <= 2 else '10Gbps'
        if p_num == 1 and sim_states['interconnect_uplink_down']:
            p_status = 'Unlinked'
            p_reason = 'No signal detected'
        ports.append({
            "portName": f"Port-{p_num}",
            "status": p_status,
            "portStatusReason": p_reason,
            "portType": "Uplink" if p_num <= 2 else "Downlink",
            "operationalSpeed": p_speed,
            "neighbor": "Core-Switch-A" if p_num == 1 else "Core-Switch-B" if p_num == 2 else f"Blade-{p_num-2}"
        })
        
    interconnects = [
        {"uri": "/rest/interconnects/ic1_3", "name": "VC-Module-3", "enclosureUri": "/rest/enclosures/enc1", "interconnectIP": "10.1.10.31", "model": "Virtual Connect SE 40Gb F8", "state": "Configured", "status": "Warning" if sim_states['interconnect_uplink_down'] else "OK", "portCount": 8, "ports": ports},
        {"uri": "/rest/interconnects/ic1_6", "name": "VC-Module-6", "enclosureUri": "/rest/enclosures/enc1", "interconnectIP": "10.1.10.32", "model": "Virtual Connect SE 40Gb F8", "state": "Configured", "status": "OK", "portCount": 8, "ports": [dict(p) for p in ports]},
        {"uri": "/rest/interconnects/ic2_3", "name": "VC-Module-3", "enclosureUri": "/rest/enclosures/enc2", "interconnectIP": "10.1.10.33", "model": "Virtual Connect SE 40Gb F8", "state": "Configured", "status": "OK", "portCount": 8, "ports": [dict(p) for p in ports]},
        {"uri": "/rest/interconnects/ic2_6", "name": "VC-Module-6", "enclosureUri": "/rest/enclosures/enc2", "interconnectIP": "10.1.10.34", "model": "Virtual Connect SE 40Gb F8", "state": "Configured", "status": "OK", "portCount": 8, "ports": [dict(p) for p in ports]}
    ]
    if sim_states['interconnect_uplink_down']:
        interconnects[1]['ports'][0]['status'] = 'Linked'
        
    return jsonify({"members": interconnects, "count": len(interconnects)})

# 2d. /mock/oneview/rest/interconnects/<id>/statistics
@app.route('/mock/oneview/rest/interconnects/<id>/statistics', methods=['GET'])
def mock_oneview_interconnect_statistics(id):
    import random
    port_stats = []
    for p_num in range(1, 9):
        rx_err = 0
        if p_num == 1 and id == 'ic1_3' and sim_states['interconnect_uplink_down']:
            rx_err = random.randint(1500, 5000)
        port_stats.append({
            "portName": f"Port-{p_num}",
            "commonStatistics": {
                "rfc": {
                    "rxBytes": random.randint(10000000, 50000000),
                    "txBytes": random.randint(10000000, 50000000),
                    "rxPackets": random.randint(50000, 250000),
                    "txPackets": random.randint(50000, 250000),
                    "rxErrors": rx_err,
                    "txErrors": 0
                }
            }
        })
    return jsonify({"portStatistics": port_stats})

# 2e. /mock/oneview/rest/ethernet-networks
@app.route('/mock/oneview/rest/ethernet-networks', methods=['GET'])
def mock_oneview_ethernet_networks():
    networks = [
        {'uri': '/rest/ethernet-networks/net-001', 'name': 'Production-VLAN100', 'vlanId': 100, 'status': 'Active', 'ethernetNetworkType': 'Tagged', 'bandwidth': {'typicalBandwidth': 10000.0}, 'subnetUri': '10.1.100.0/24', 'purpose': 'Production'},
        {'uri': '/rest/ethernet-networks/net-002', 'name': 'Management-VLAN10', 'vlanId': 10, 'status': 'Active', 'ethernetNetworkType': 'Tagged', 'bandwidth': {'typicalBandwidth': 1000.0}, 'subnetUri': '10.1.10.0/24', 'purpose': 'Management'},
        {'uri': '/rest/ethernet-networks/net-003', 'name': 'vMotion-VLAN200', 'vlanId': 200, 'status': 'Active', 'ethernetNetworkType': 'Tagged', 'bandwidth': {'typicalBandwidth': 25000.0}, 'subnetUri': '10.1.200.0/24', 'purpose': 'vMotion'},
        {'uri': '/rest/ethernet-networks/net-004', 'name': 'iSCSI-A-VLAN300', 'vlanId': 300, 'status': 'Active', 'ethernetNetworkType': 'Tagged', 'bandwidth': {'typicalBandwidth': 25000.0}, 'subnetUri': '10.1.300.0/24', 'purpose': 'iSCSI'},
        {'uri': '/rest/ethernet-networks/net-005', 'name': 'iSCSI-B-VLAN301', 'vlanId': 301, 'status': 'Active', 'ethernetNetworkType': 'Tagged', 'bandwidth': {'typicalBandwidth': 25000.0}, 'subnetUri': '10.1.301.0/24', 'purpose': 'iSCSI'},
        {'uri': '/rest/ethernet-networks/net-006', 'name': 'Dev-VLAN50', 'vlanId': 50, 'status': 'Active', 'ethernetNetworkType': 'Tagged', 'bandwidth': {'typicalBandwidth': 10000.0}, 'subnetUri': '10.1.50.0/24', 'purpose': 'Development'}
    ]
    return jsonify({"members": networks, "count": len(networks)})

# 2f. /mock/oneview/rest/firmware-drivers
@app.route('/mock/oneview/rest/firmware-drivers', methods=['GET'])
def mock_oneview_firmware_drivers():
    bundles = [
        {'uri': '/rest/firmware-drivers/fw-001', 'name': 'Service Pack for ProLiant', 'version': '2025.03.01', 'isoFileName': 'SPP2025.03.01.iso', 'state': 'Active', 'bundleSize': 8500.0, 'releaseDate': '2025-03-15'},
        {'uri': '/rest/firmware-drivers/fw-002', 'name': 'Service Pack for ProLiant', 'version': '2024.09.01', 'isoFileName': 'SPP2024.09.01.iso', 'state': 'Active', 'bundleSize': 8200.0, 'releaseDate': '2024-09-20'},
        {'uri': '/rest/firmware-drivers/fw-003', 'name': 'Service Pack for ProLiant', 'version': '2024.06.01', 'isoFileName': 'SPP2024.06.01.iso', 'state': 'Active', 'bundleSize': 7900.0, 'releaseDate': '2024-06-10'},
        {'uri': '/rest/firmware-drivers/fw-004', 'name': 'Service Pack for ProLiant', 'version': '2024.03.01', 'isoFileName': 'SPP2024.03.01.iso', 'state': 'Archived', 'bundleSize': 7600.0, 'releaseDate': '2024-03-05'}
    ]
    return jsonify({"members": bundles, "count": len(bundles)})

# 2g. /mock/oneview/rest/alerts
@app.route('/mock/oneview/rest/alerts', methods=['GET'])
def mock_oneview_alerts():
    try:
        alerts = db.fetch_all("SELECT * FROM alerts WHERE source = 'oneview';")
        return jsonify({"members": alerts, "count": len(alerts)})
    except:
        return jsonify({"members": [], "count": 0})


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


# 3a. /mock/apic/api/node/class/topSystem.json
@app.route('/mock/apic/api/node/class/topSystem.json', methods=['GET'])
def mock_apic_top_system():
    imdata = [
        {"topSystem": {"attributes": {"dn": "topology/pod-1/node-201/sys", "name": "Spine-201", "role": "spine", "serial": "PSU-SN-SP201-1", "version": "5.2(4d)", "systemUpTime": "120:14:32:05", "inbMgmtAddr": "10.0.0.201", "state": "in-service"}}},
        {"topSystem": {"attributes": {"dn": "topology/pod-1/node-202/sys", "name": "Spine-202", "role": "spine", "serial": "PSU-SN-SP202-1", "version": "5.2(4d)", "systemUpTime": "120:14:30:12", "inbMgmtAddr": "10.0.0.202", "state": "in-service"}}},
        {"topSystem": {"attributes": {"dn": "topology/pod-1/node-101/sys", "name": "Leaf-101", "role": "leaf", "serial": "PSU-SN-LF101-1", "version": "5.2(4d)", "systemUpTime": "45:02:11:54", "inbMgmtAddr": "10.0.0.101", "state": "in-service"}}},
        {"topSystem": {"attributes": {"dn": "topology/pod-1/node-102/sys", "name": "Leaf-102", "role": "leaf", "serial": "PSU-SN-LF102-1", "version": "5.2(4d)", "systemUpTime": "12:21:40:15" if not sim_states['leaf_down'] else "00:00:00:00", "inbMgmtAddr": "10.0.0.102", "state": "in-service" if not sim_states['leaf_down'] else "out-of-service"}}},
        {"topSystem": {"attributes": {"dn": "topology/pod-1/node-103/sys", "name": "Leaf-103", "role": "leaf", "serial": "PSU-SN-LF103-1", "version": "5.2(4d)", "systemUpTime": "45:02:10:44", "inbMgmtAddr": "10.0.0.103", "state": "in-service"}}}
    ]
    return jsonify({"imdata": imdata})

# 3b. /mock/apic/api/node/class/fvCEp.json
@app.route('/mock/apic/api/node/class/fvCEp.json', methods=['GET'])
def mock_apic_learned_endpoints():
    imdata = [
        {"fvCEp": {"attributes": {"dn": "uni/tn-Production/ap-Web-App/epg-Prod-App-EPG/cep-00:50:56:A1:B2:01", "mac": "00:50:56:A1:B2:01", "ip": "10.1.100.11", "epgDn": "uni/tn-Production/ap-Web-App/epg-Prod-App-EPG", "lcC": "learned", "encap": "vlan-100"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Production/ap-Web-App/epg-Prod-App-EPG/cep-00:50:56:A1:B2:02", "mac": "00:50:56:A1:B2:02", "ip": "10.1.100.12", "epgDn": "uni/tn-Production/ap-Web-App/epg-Prod-App-EPG", "lcC": "learned", "encap": "vlan-100"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Production/ap-Web-App/epg-Prod-App-EPG/cep-00:50:56:A1:B2:03", "mac": "00:50:56:A1:B2:03", "ip": "10.1.100.13", "epgDn": "uni/tn-Production/ap-Web-App/epg-Prod-App-EPG", "lcC": "learned", "encap": "vlan-100"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Production/ap-Web-App/epg-Prod-DB-EPG/cep-00:50:56:C3:D4:01", "mac": "00:50:56:C3:D4:01", "ip": "10.1.100.21", "epgDn": "uni/tn-Production/ap-Web-App/epg-Prod-DB-EPG", "lcC": "learned", "encap": "vlan-100"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Production/ap-Web-App/epg-Prod-DB-EPG/cep-00:50:56:C3:D4:02", "mac": "00:50:56:C3:D4:02", "ip": "10.1.100.22", "epgDn": "uni/tn-Production/ap-Web-App/epg-Prod-DB-EPG", "lcC": "learned", "encap": "vlan-100"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Production/ap-Web-App/epg-Prod-DB-EPG/cep-00:50:56:C3:D4:03", "mac": "00:50:56:C3:D4:03", "ip": "10.1.100.23", "epgDn": "uni/tn-Production/ap-Web-App/epg-Prod-DB-EPG", "lcC": "learned", "encap": "vlan-100"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Development/ap-Dev-App/epg-Dev-App-EPG/cep-00:50:56:E5:F6:01", "mac": "00:50:56:E5:F6:01", "ip": "10.1.50.11", "epgDn": "uni/tn-Development/ap-Dev-App/epg-Dev-App-EPG", "lcC": "learned", "encap": "vlan-50"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Development/ap-Dev-App/epg-Dev-App-EPG/cep-00:50:56:E5:F6:02", "mac": "00:50:56:E5:F6:02", "ip": "10.1.50.12", "epgDn": "uni/tn-Development/ap-Dev-App/epg-Dev-App-EPG", "lcC": "learned", "encap": "vlan-50"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Development/ap-Dev-App/epg-Dev-App-EPG/cep-00:50:56:E5:F6:03", "mac": "00:50:56:E5:F6:03", "ip": "10.1.50.13", "epgDn": "uni/tn-Development/ap-Dev-App/epg-Dev-App-EPG", "lcC": "learned", "encap": "vlan-50"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Shared-Services/ap-Services/epg-SharedSvc-DNS-EPG/cep-00:50:56:A7:B8:01", "mac": "00:50:56:A7:B8:01", "ip": "10.1.200.11", "epgDn": "uni/tn-Shared-Services/ap-Services/epg-SharedSvc-DNS-EPG", "lcC": "learned", "encap": "vlan-200"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Shared-Services/ap-Services/epg-SharedSvc-DNS-EPG/cep-00:50:56:A7:B8:02", "mac": "00:50:56:A7:B8:02", "ip": "10.1.200.12", "epgDn": "uni/tn-Shared-Services/ap-Services/epg-SharedSvc-DNS-EPG", "lcC": "learned", "encap": "vlan-200"}}},
        {"fvCEp": {"attributes": {"dn": "uni/tn-Shared-Services/ap-Services/epg-SharedSvc-DNS-EPG/cep-00:50:56:A7:B8:03", "mac": "00:50:56:A7:B8:03", "ip": "10.1.200.13", "epgDn": "uni/tn-Shared-Services/ap-Services/epg-SharedSvc-DNS-EPG", "lcC": "learned", "encap": "vlan-200"}}}
    ]
    if sim_states['leaf_down']:
        imdata = [e for e in imdata if "A1:B2:03" not in e['fvCEp']['attributes']['mac'] and 
                  "C3:D4:01" not in e['fvCEp']['attributes']['mac'] and 
                  "C3:D4:02" not in e['fvCEp']['attributes']['mac'] and 
                  "A7:B8:02" not in e['fvCEp']['attributes']['mac']]
    return jsonify({"imdata": imdata})

# 3c. /mock/apic/api/node/class/healthInst.json
@app.route('/mock/apic/api/node/class/healthInst.json', methods=['GET'])
def mock_apic_health_inst():
    h_spine1 = 100
    h_spine2 = 98
    h_leaf1 = 97
    h_leaf2 = 96
    h_leaf3 = 99
    
    if sim_states['leaf_down']:
        h_leaf2 = 0
    if sim_states['interface_flap']:
        h_leaf1 = 80
        
    imdata = [
        {"healthInst": {"attributes": {"dn": "topology/pod-1/node-201/sys/health", "cur": str(h_spine1)}}},
        {"healthInst": {"attributes": {"dn": "topology/pod-1/node-202/sys/health", "cur": str(h_spine2)}}},
        {"healthInst": {"attributes": {"dn": "topology/pod-1/node-101/sys/health", "cur": str(h_leaf1)}}},
        {"healthInst": {"attributes": {"dn": "topology/pod-1/node-102/sys/health", "cur": str(h_leaf2)}}},
        {"healthInst": {"attributes": {"dn": "topology/pod-1/node-103/sys/health", "cur": str(h_leaf3)}}},
        {"healthInst": {"attributes": {"dn": "uni/tn-Production/health", "cur": "85" if sim_states['epg_fault'] else "98"}}}
    ]
    return jsonify({"imdata": imdata})

# 3d. /mock/apic/api/node/class/fabricHealthTotal.json
@app.route('/mock/apic/api/node/class/fabricHealthTotal.json', methods=['GET'])
def mock_apic_fabric_health_total():
    score = 98
    if sim_states['leaf_down']:
        score = 78
    elif sim_states['interface_flap'] or sim_states['epg_fault']:
        score = 91
    return jsonify({"imdata": [{"fabricHealthTotal": {"attributes": {"dn": "fabric/health", "cur": str(score)}}}]})

# 3e. /mock/apic/api/node/class/ethpmPhysIf.json
@app.route('/mock/apic/api/node/class/ethpmPhysIf.json', methods=['GET'])
def mock_apic_ethpm_phys_if():
    import random
    st1 = 'up'
    st2 = 'up'
    
    if sim_states['leaf_down']:
        st2 = 'down'
    if sim_states['interface_flap']:
        st1 = 'up' if random.choice([True, False]) else 'down'
        
    imdata = [
        {"ethpmPhysIf": {"attributes": {"dn": "topology/pod-1/node-101/sys/phys-[eth1/1]/phys", "operSt": st1, "operSpeed": "10G", "operDuplex": "full", "operStQual": "none" if st1=='up' else "link-flap"}}},
        {"ethpmPhysIf": {"attributes": {"dn": "topology/pod-1/node-102/sys/phys-[eth1/1]/phys", "operSt": st2, "operSpeed": "10G", "operDuplex": "full", "operStQual": "none" if st2=='up' else "node-offline"}}},
        {"ethpmPhysIf": {"attributes": {"dn": "topology/pod-1/node-103/sys/phys-[eth1/1]/phys", "operSt": "up", "operSpeed": "10G", "operDuplex": "full", "operStQual": "none"}}},
        {"ethpmPhysIf": {"attributes": {"dn": "topology/pod-1/node-101/sys/phys-[eth1/2]/phys", "operSt": "up", "operSpeed": "40G", "operDuplex": "full", "operStQual": "none"}}},
        {"ethpmPhysIf": {"attributes": {"dn": "topology/pod-1/node-102/sys/phys-[eth1/2]/phys", "operSt": st2, "operSpeed": "40G", "operDuplex": "full", "operStQual": "none" if st2=='up' else "node-offline"}}}
    ]
    return jsonify({"imdata": imdata})

# 3f. /mock/apic/api/node/class/eqptPsu.json
@app.route('/mock/apic/api/node/class/eqptPsu.json', methods=['GET'])
def mock_apic_psu():
    imdata = []
    nodes = [201, 202, 101, 102, 103]
    for n in nodes:
        for psu_id in [1, 2]:
            st = 'ok'
            if sim_states['apic_psu_failure'] and n == 102 and psu_id == 2:
                st = 'fail'
            if sim_states['leaf_down'] and n == 102:
                st = 'fail'
            p_model = 'N9K-PAC-1200W' if n >= 200 else 'N9K-PAC-650W'
            imdata.append({
                "eqptPsu": {
                    "attributes": {
                        "dn": f"topology/pod-1/node-{n}/sys/ch/psu-{psu_id}",
                        "id": f"PSU-{psu_id}",
                        "operSt": st,
                        "model": p_model,
                        "ser": f"PSU-SN-{'SP' if n>=200 else 'LF'}{n}-{psu_id}"
                    }
                }
            })
    return jsonify({"imdata": imdata})

# 3g. /mock/apic/api/node/class/eqptFan.json
@app.route('/mock/apic/api/node/class/eqptFan.json', methods=['GET'])
def mock_apic_fan():
    imdata = []
    nodes = [201, 202, 101, 102, 103]
    for n in nodes:
        for fan_id in [1, 2]:
            st = 'ok'
            if sim_states['leaf_down'] and n == 102:
                st = 'unknown'
            f_model = 'N9K-C9508-FAN' if n >= 200 else 'N9K-C93180-FAN'
            imdata.append({
                "eqptFan": {
                    "attributes": {
                        "dn": f"topology/pod-1/node-{n}/sys/ch/fan-{fan_id}",
                        "id": f"FanTray-{fan_id}",
                        "operSt": st,
                        "model": f_model,
                        "ser": f"FAN-SN-{'SP' if n>=200 else 'LF'}{n}-{fan_id}"
                    }
                }
            })
    return jsonify({"imdata": imdata})

# 3h. /mock/apic/api/node/class/vzBrCP.json
@app.route('/mock/apic/api/node/class/vzBrCP.json', methods=['GET'])
def mock_apic_contracts():
    imdata = [
        {"vzBrCP": {"attributes": {"dn": "uni/tn-Production/brc-Web-to-App", "name": "Web-to-App", "scope": "tenant", "status": "active"}}},
        {"vzBrCP": {"attributes": {"dn": "uni/tn-Production/brc-App-to-DB", "name": "App-to-DB", "scope": "tenant", "status": "active"}}},
        {"vzBrCP": {"attributes": {"dn": "uni/tn-Shared-Services/brc-ICMP-Allow", "name": "ICMP-Allow", "scope": "global", "status": "active"}}},
        {"vzBrCP": {"attributes": {"dn": "uni/tn-Shared-Services/brc-DNS-Allow", "name": "DNS-Allow", "scope": "global", "status": "active"}}}
    ]
    return jsonify({"imdata": imdata})


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
            
            try:
                profiles = db.fetch_all("SELECT * FROM oneview_server_profiles;")
            except Exception:
                profiles = []
            try:
                networks = db.fetch_all("SELECT * FROM oneview_networks;")
            except Exception:
                networks = []
            try:
                firmware = db.fetch_all("SELECT * FROM oneview_firmware;")
            except Exception:
                firmware = []
            
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

            profiles_compliant = len([p for p in profiles if p.get('compliance_state') == 'Compliant'])

            oneview_data = {
                "enclosures": encs,
                "blades": blades,
                "storage_pools": pools,
                "health_index": ov_health,
                "telemetry_history": ov_history,
                "profiles": profiles,
                "profiles_compliant": profiles_compliant,
                "profiles_total": len(profiles),
                "networks": networks,
                "firmware": firmware
            }

            # Cisco APIC Database pull
            nodes = db.fetch_all("SELECT * FROM apic_fabric_nodes;")
            interfaces = db.fetch_all("SELECT * FROM apic_interfaces;")
            logical = db.fetch_all("SELECT * FROM apic_logical;")
            
            try:
                endpoints = db.fetch_all("SELECT * FROM apic_endpoints;")
            except Exception:
                endpoints = []
            try:
                contracts = db.fetch_all("SELECT * FROM apic_contracts;")
            except Exception:
                contracts = []
            try:
                equipment = db.fetch_all("SELECT * FROM apic_equipment;")
            except Exception:
                equipment = []

            # Fetch active endpoints count
            endpoints_count = len(endpoints) if endpoints else (14 + len([f for f in interfaces if f.get('status') == 'up' or f.get('oper_state') == 'up']) * 3)
            if sim_states['leaf_down'] and not endpoints:
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

            equipment_ok = len([e for e in equipment if e.get('status') == 'ok'])

            apic_data = {
                "switches": switches,
                "interfaces": interfaces,
                "tenants": tenants,
                "endpoints_count": endpoints_count,
                "endpoints": endpoints[:10],
                "health_index": apic_health,
                "telemetry_history": apic_history,
                "contracts": contracts,
                "equipment": equipment,
                "equipment_ok": equipment_ok,
                "equipment_total": len(equipment)
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

# ==================== ADDITIONAL CLIENT API ENDPOINTS ====================

@app.route('/api/oneview/profiles', methods=['GET'])
def get_oneview_profiles():
    try:
        profiles = db.fetch_all("SELECT * FROM oneview_server_profiles;")
        return jsonify(profiles)
    except Exception as e:
        return jsonify([])

@app.route('/api/oneview/interconnects', methods=['GET'])
def get_oneview_interconnects():
    try:
        interconnects = db.fetch_all("SELECT * FROM oneview_interconnects;")
        return jsonify(interconnects)
    except Exception as e:
        return jsonify([])

@app.route('/api/oneview/networks', methods=['GET'])
def get_oneview_networks():
    try:
        networks = db.fetch_all("SELECT * FROM oneview_networks;")
        return jsonify(networks)
    except Exception as e:
        return jsonify([])

@app.route('/api/oneview/firmware', methods=['GET'])
def get_oneview_firmware():
    try:
        firmware = db.fetch_all("SELECT * FROM oneview_firmware;")
        return jsonify(firmware)
    except Exception as e:
        return jsonify([])

@app.route('/api/apic/endpoints', methods=['GET'])
def get_apic_endpoints():
    try:
        epg = request.args.get('epg')
        if epg:
            endpoints = db.fetch_all("SELECT * FROM apic_endpoints WHERE epg = %s;", (epg,))
        else:
            endpoints = db.fetch_all("SELECT * FROM apic_endpoints;")
        return jsonify(endpoints)
    except Exception as e:
        return jsonify([])

@app.route('/api/apic/health', methods=['GET'])
def get_apic_health():
    try:
        nodes = db.fetch_all("SELECT id, name, role, health_score FROM apic_fabric_nodes;")
        fabric_health = int(sum(n['health_score'] for n in nodes) / len(nodes)) if nodes else 100
        return jsonify({"nodes": nodes, "fabric_health": fabric_health})
    except Exception as e:
        return jsonify({"nodes": [], "fabric_health": 100})

@app.route('/api/apic/contracts', methods=['GET'])
def get_apic_contracts():
    try:
        contracts = db.fetch_all("SELECT * FROM apic_contracts;")
        return jsonify(contracts)
    except Exception as e:
        return jsonify([])

@app.route('/api/apic/equipment', methods=['GET'])
def get_apic_equipment():
    try:
        node_id = request.args.get('node_id')
        if node_id:
            equipment = db.fetch_all("SELECT * FROM apic_equipment WHERE node_id = %s;", (node_id,))
        else:
            equipment = db.fetch_all("SELECT * FROM apic_equipment;")
        return jsonify(equipment)
    except Exception as e:
        return jsonify([])


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
