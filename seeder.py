from db import db
from datetime import datetime, timedelta
import random

def seed_database():
    print("Database seeding started...")
    
    # 1. Seed HPE OneView Enclosures
    existing_encs = db.fetch_all("SELECT id FROM oneview_enclosures;")
    if not existing_encs:
        db.execute_query("""
            INSERT INTO oneview_enclosures (id, name, status, temp_c, power_watts, model, serial_number) VALUES
            ('enc1', 'Enclosure-01', 'OK', 32, 1650, 'Synergy 12000', 'SGH822X01'),
            ('enc2', 'Enclosure-02', 'OK', 29, 1420, 'Synergy 12000', 'SGH822X02');
        """)
        print("Seeded: 2 HPE Synergy Enclosures.")
    
    # 2. Seed HPE Blade Servers
    existing_servers = db.fetch_all("SELECT id FROM oneview_server_hardware;")
    if not existing_servers:
        db.execute_query("""
            INSERT INTO oneview_server_hardware (id, enclosure_id, bay, name, status, model, serial_number, cpu_util_pct, power_watts, temp_c, profile_name, memory_mb, cpu_cores) VALUES
            ('server1_1', 'enc1', 1, 'Blade-01', 'OK', 'Synergy 480 Gen10', 'SGH822X01A', 45.2, 180, 36, 'ESXi-Prod-ClusterA', 262144, 32),
            ('server1_2', 'enc1', 2, 'Blade-02', 'OK', 'Synergy 480 Gen10', 'SGH822X01B', 62.5, 210, 42, 'ESXi-Prod-ClusterA', 262144, 32),
            ('server1_3', 'enc1', 3, 'Blade-03', 'OK', 'Synergy 660 Gen10', 'SGH822X01C', 82.1, 350, 48, 'BareMetal-SAP-DB', 524288, 64),
            ('server1_4', 'enc1', 4, 'Blade-04', 'OK', 'Synergy 480 Gen10', 'SGH822X01D', 15.0, 140, 33, 'K8s-Dev-Worker', 131072, 16),
            ('server2_1', 'enc2', 1, 'Blade-05', 'OK', 'Synergy 480 Gen10', 'SGH822X02A', 38.0, 175, 34, 'ESXi-Stage-ClusterB', 262144, 32),
            ('server2_2', 'enc2', 2, 'Blade-06', 'OK', 'Synergy 480 Gen10', 'SGH822X02B', 12.4, 130, 31, 'K8s-Dev-Worker', 131072, 16);
        """)
        print("Seeded: 6 HPE Synergy Blade Servers in chassis bays.")

    # 3. Seed HPE Interconnect Modules
    existing_connects = db.fetch_all("SELECT id FROM oneview_interconnects;")
    if not existing_connects:
        db.execute_query("""
            INSERT INTO oneview_interconnects (id, enclosure_id, bay, name, status, model, type) VALUES
            ('ic1_3', 'enc1', 3, 'VC-Module-3', 'OK', 'Virtual Connect SE 40Gb F8', 'Ethernet'),
            ('ic1_6', 'enc1', 6, 'VC-Module-6', 'OK', 'Virtual Connect SE 40Gb F8', 'Ethernet'),
            ('ic2_3', 'enc2', 3, 'VC-Module-3', 'OK', 'Virtual Connect SE 40Gb F8', 'Ethernet'),
            ('ic2_6', 'enc2', 6, 'VC-Module-6', 'OK', 'Virtual Connect SE 40Gb F8', 'Ethernet');
        """)
        print("Seeded: 4 Virtual Connect Interconnect Modules.")

    # 4. Seed Storage Pools
    existing_pools = db.fetch_all("SELECT id FROM oneview_storage_pools;")
    if not existing_pools:
        db.execute_query("""
            INSERT INTO oneview_storage_pools (id, name, status, capacity_gb, free_space_gb, system_name) VALUES
            ('pool1', 'SAN-Prod-Pool-01', 'OK', 81920.0, 24576.0, '3PAR-StoreServ-8200'),
            ('pool2', 'SAN-Backup-Pool-02', 'OK', 40960.0, 18432.0, '3PAR-StoreServ-8200'),
            ('pool3', 'SAN-Dev-Pool-03', 'OK', 20480.0, 14336.0, 'StoreOnce-VSA');
        """)
        print("Seeded: 3 HPE SAN Storage Pools.")

    # 5. Seed Cisco APIC Fabric Nodes
    existing_nodes = db.fetch_all("SELECT id FROM apic_fabric_nodes;")
    if not existing_nodes:
        db.execute_query("""
            INSERT INTO apic_fabric_nodes (id, name, role, ip_address, status, health_score) VALUES
            ('spine201', 'Spine-201', 'spine', '10.0.0.201', 'online', 100),
            ('spine202', 'Spine-202', 'spine', '10.0.0.202', 'online', 98),
            ('leaf101', 'Leaf-101', 'leaf', '10.0.0.101', 'online', 100),
            ('leaf102', 'Leaf-102', 'leaf', '10.0.0.102', 'online', 95),
            ('leaf103', 'Leaf-103', 'leaf', '10.0.0.103', 'online', 100);
        """)
        print("Seeded: 5 Cisco ACI Switches (2 Spine, 3 Leaf).")

    # 6. Seed Cisco APIC Interfaces
    existing_interfaces = db.fetch_all("SELECT id FROM apic_interfaces;")
    if not existing_interfaces:
        db.execute_query("""
            INSERT INTO apic_interfaces (id, node_id, name, status, usage_in_bps, usage_out_bps) VALUES
            ('leaf101_1', 'leaf101', 'ethernet 1/1', 'up', 450000000.0, 320000000.0),
            ('leaf101_2', 'leaf101', 'ethernet 1/2', 'up', 890000000.0, 640000000.0),
            ('leaf102_1', 'leaf102', 'ethernet 1/1', 'up', 520000000.0, 480000000.0),
            ('leaf102_5', 'leaf102', 'ethernet 1/5', 'up', 150000000.0, 90000000.0),
            ('leaf103_1', 'leaf103', 'ethernet 1/1', 'up', 720000000.0, 610000000.0);
        """)
        print("Seeded: 5 Active Fabric Interface Ports.")

    # 7. Seed Cisco APIC Logical Layer (Tenants/VRFs/BDs/EPGs)
    existing_logical = db.fetch_all("SELECT id FROM apic_logical;")
    if not existing_logical:
        db.execute_query("""
            INSERT INTO apic_logical (tenant, vrf, bd_name, epg) VALUES
            ('Production', 'Prod-VRF', 'Prod-BD', 'Prod-App-EPG'),
            ('Production', 'Prod-VRF', 'Prod-BD', 'Prod-DB-EPG'),
            ('Development', 'Dev-VRF', 'Dev-BD', 'Dev-Web-EPG'),
            ('Shared-Services', 'Common-VRF', 'DNS-BD', 'Common-DNS-EPG');
        """)
        print("Seeded: 4 Cisco ACI Logical Architecture Paths.")

    # 8. Seed Historical Telemetry Data
    existing_metrics = db.fetch_all("SELECT id FROM historical_metrics;")
    if not existing_metrics:
        print("Generating historical metrics for the past 12 hours...")
        now = datetime.now()
        queries = []
        for hour in range(24, 0, -1):
            ts = now - timedelta(hours=hour)
            # Format timestamp for postgres or sqlite
            ts_str = ts.strftime('%Y-%m-%d %H:%M:%S')
            
            # Simulated telemetry metrics
            avg_temp = 32.0 + random.uniform(-2.0, 3.0)
            tot_power = 3000.0 + random.uniform(-150.0, 200.0)
            inbound = 2.5 + random.uniform(-0.5, 0.8) # Gbps
            outbound = 2.1 + random.uniform(-0.4, 0.6) # Gbps
            
            db.execute_query(
                "INSERT INTO historical_metrics (entity_type, entity_id, metric_name, metric_value, timestamp) VALUES (%s, %s, %s, %s, %s);",
                ('enclosure', 'all', 'temp_c', avg_temp, ts_str)
            )
            db.execute_query(
                "INSERT INTO historical_metrics (entity_type, entity_id, metric_name, metric_value, timestamp) VALUES (%s, %s, %s, %s, %s);",
                ('enclosure', 'all', 'power_watts', tot_power, ts_str)
            )
            db.execute_query(
                "INSERT INTO historical_metrics (entity_type, entity_id, metric_name, metric_value, timestamp) VALUES (%s, %s, %s, %s, %s);",
                ('network', 'fabric', 'inbound_mbps', inbound * 1000.0, ts_str)
            )
            db.execute_query(
                "INSERT INTO historical_metrics (entity_type, entity_id, metric_name, metric_value, timestamp) VALUES (%s, %s, %s, %s, %s);",
                ('network', 'fabric', 'outbound_mbps', outbound * 1000.0, ts_str)
            )
        print("Seeded: 24 hours of telemetry history.")

    # 9. Seed Knowledge Base SOPs (standard text columns for sqlite/postgres)
    existing_docs = db.fetch_all("SELECT id FROM kb_documents;")
    if not existing_docs:
        db.execute_query("""
            INSERT INTO kb_documents (title, content, category) VALUES
            (
                'SOP: HPE Synergy Enclosure Thermal Fault Recovery',
                '### Symptom
An HPE Synergy chassis reports high temperature alarms (> 45°C) or thermal throttling on installed server blade modules.

### Resolution Steps
1. Verify the status of the enclosure fan assembly. Open HPE OneView and navigate to Hardware -> Enclosures -> Fans.
2. If a fan module is in a Failed state, request immediate physical replacement. Synergy fans are hot-pluggable.
3. If all fans are active, check air vents for obstruction.
4. Check if any workload on the blades has spiked CPU usage beyond limits.
5. In extreme scenarios, migrate workloads away from the overheating blades to other cabinets or VM hosts, and gracefully shut down the chassis server blade.',
                'sop'
            ),
            (
                'SOP: HPE Synergy Storage Pool Capacity Overflow',
                '### Symptom
HPE StoreServ pool reports usage above 80% capacity limit.

### Resolution Steps
1. Identify high-consuming storage volumes.
2. Check for unused virtual machine templates, active snapshots, or old backups.
3. Delete snapshots older than 7 days using HPE OneView storage console.
4. Enable thin-provisioning deduplication features if supported by the storage engine.
5. Plan storage expansion by physical disk additions to the 3PAR chassis.',
                'sop'
            ),
            (
                'SOP: Cisco ACI EPG Packet Loss Troubleshooting',
                '### Symptom
EPG report traffic drops or active faults (e.g., ACI fault F1024).

### Resolution Steps
1. Identify source Endpoints in the EPG and check physical Leaf interface status.
2. Verify VRF routing table. Ensure there are no overlapping subnet ranges.
3. Verify Bridge Domain binding. Ensure the BD is active and associated with the correct tenant.
4. Execute endpoint traceroute via APIC CLI: "show endpoint ip <IP>" to locate network interfaces.
5. Check and clear mac-address tables on leaf switches if endpoint learning is flapping.',
                'runbook'
            ),
            (
                'Guide: HPE OneView Server Profile Mismatch',
                '### Symptom
Blade Server reports Profile Mismatch or Firmware Mismatch.

### Resolution Steps
1. Open server hardware details and inspect firmware baseline configurations.
2. Ensure the server profile baseline matches the physical Synergy chassis firmware repository.
3. Re-apply the server profile via HPE OneView REST API or interface.
4. If a reboot is required, schedule downtime and power-cycle the blade server.',
                'oneview'
            );
        """)
        print("Seeded: 4 Operational SOPs and Guides.")
    
    # 10. Seed Server Profiles
    existing_profiles = db.fetch_all("SELECT id FROM oneview_server_profiles;")
    if not existing_profiles:
        db.execute_query("""
            INSERT INTO oneview_server_profiles (id, name, server_hardware_id, status, compliance_state, template_name, firmware_baseline, description) VALUES
            ('prof-001', 'ESXi-Prod-ClusterA', 'server1_1', 'OK', 'Compliant', 'ESXi-Production-Template', 'SPP-2025.03.01', 'Production ESXi cluster profile'),
            ('prof-002', 'BareMetal-SAP-DB', 'server1_3', 'OK', 'Compliant', 'BareMetal-SAP-Template', 'SPP-2025.03.01', 'SAP HANA database server'),
            ('prof-003', 'K8s-Dev-Worker', 'server1_4', 'OK', 'NonCompliant', 'K8s-Worker-Template', 'SPP-2024.09.01', 'Kubernetes development worker node'),
            ('prof-004', 'ESXi-Stage-ClusterB', 'server2_1', 'OK', 'Compliant', 'ESXi-Staging-Template', 'SPP-2025.03.01', 'Staging ESXi cluster profile'),
            ('prof-005', 'GPU-ML-Training', 'server1_2', 'OK', 'NonCompliant', 'GPU-Compute-Template', 'SPP-2024.06.01', 'Machine learning training node'),
            ('prof-006', 'Docker-CI-Runner', 'server2_2', 'OK', 'Compliant', 'Container-Host-Template', 'SPP-2025.03.01', 'CI/CD Docker build runner');
        """)
        print("Seeded: 6 Server Profiles.")

    # 11. Seed Ethernet Networks
    existing_networks = db.fetch_all("SELECT id FROM oneview_networks;")
    if not existing_networks:
        db.execute_query("""
            INSERT INTO oneview_networks (id, name, type, vlan_id, status, bandwidth_typical, subnet, purpose) VALUES
            ('net-001', 'Production-VLAN100', 'Ethernet', 100, 'Active', 10000.0, '10.1.100.0/24', 'Production'),
            ('net-002', 'Management-VLAN10', 'Ethernet', 10, 'Active', 1000.0, '10.1.10.0/24', 'Management'),
            ('net-003', 'vMotion-VLAN200', 'Ethernet', 200, 'Active', 25000.0, '10.1.200.0/24', 'vMotion'),
            ('net-004', 'iSCSI-A-VLAN300', 'Ethernet', 300, 'Active', 25000.0, '10.1.300.0/24', 'iSCSI'),
            ('net-005', 'iSCSI-B-VLAN301', 'Ethernet', 301, 'Active', 25000.0, '10.1.301.0/24', 'iSCSI'),
            ('net-006', 'Dev-VLAN50', 'Ethernet', 50, 'Active', 10000.0, '10.1.50.0/24', 'Development');
        """)
        print("Seeded: 6 Ethernet Networks.")

    # 12. Seed Firmware SPPs
    existing_fw = db.fetch_all("SELECT id FROM oneview_firmware;")
    if not existing_fw:
        db.execute_query("""
            INSERT INTO oneview_firmware (id, name, version, release_date, iso_file_name, status, size_mb) VALUES
            ('fw-001', 'Service Pack for ProLiant', '2025.03.01', '2025-03-15', 'SPP2025.03.01.iso', 'Active', 8500.0),
            ('fw-002', 'Service Pack for ProLiant', '2024.09.01', '2024-09-20', 'SPP2024.09.01.iso', 'Active', 8200.0),
            ('fw-003', 'Service Pack for ProLiant', '2024.06.01', '2024-06-10', 'SPP2024.06.01.iso', 'Active', 7900.0),
            ('fw-004', 'Service Pack for ProLiant', '2024.03.01', '2024-03-05', 'SPP2024.03.01.iso', 'Archived', 7600.0);
        """)
        print("Seeded: 4 Firmware Bundles.")

    # 13. Seed Learned Endpoints
    existing_eps = db.fetch_all("SELECT id FROM apic_endpoints;")
    if not existing_eps:
        db.execute_query("""
            INSERT INTO apic_endpoints (id, mac, ip, epg, interface, encap, node_id, status) VALUES
            ('ep-001', '00:50:56:A1:B2:01', '10.1.100.11', 'Prod-App-EPG', 'eth1/1', 'vlan-100', 'leaf-101', 'learned'),
            ('ep-002', '00:50:56:A1:B2:02', '10.1.100.12', 'Prod-App-EPG', 'eth1/2', 'vlan-100', 'leaf-101', 'learned'),
            ('ep-003', '00:50:56:A1:B2:03', '10.1.100.13', 'Prod-App-EPG', 'eth1/3', 'vlan-100', 'leaf-102', 'learned'),
            ('ep-004', '00:50:56:C3:D4:01', '10.1.100.21', 'Prod-DB-EPG', 'eth1/4', 'vlan-100', 'leaf-102', 'learned'),
            ('ep-005', '00:50:56:C3:D4:02', '10.1.100.22', 'Prod-DB-EPG', 'eth1/5', 'vlan-100', 'leaf-102', 'learned'),
            ('ep-006', '00:50:56:C3:D4:03', '10.1.100.23', 'Prod-DB-EPG', 'eth1/6', 'vlan-100', 'leaf-103', 'learned'),
            ('ep-007', '00:50:56:E5:F6:01', '10.1.50.11', 'Dev-App-EPG', 'eth1/7', 'vlan-50', 'leaf-103', 'learned'),
            ('ep-008', '00:50:56:E5:F6:02', '10.1.50.12', 'Dev-App-EPG', 'eth1/8', 'vlan-50', 'leaf-103', 'learned'),
            ('ep-009', '00:50:56:E5:F6:03', '10.1.50.13', 'Dev-App-EPG', 'eth1/1', 'vlan-50', 'leaf-101', 'learned'),
            ('ep-010', '00:50:56:A7:B8:01', '10.1.200.11', 'SharedSvc-DNS-EPG', 'eth1/9', 'vlan-200', 'leaf-101', 'learned'),
            ('ep-011', '00:50:56:A7:B8:02', '10.1.200.12', 'SharedSvc-DNS-EPG', 'eth1/10', 'vlan-200', 'leaf-102', 'learned'),
            ('ep-012', '00:50:56:A7:B8:03', '10.1.200.13', 'SharedSvc-DNS-EPG', 'eth1/11', 'vlan-200', 'leaf-103', 'learned');
        """)
        print("Seeded: 12 Cisco ACI Learned Endpoints.")

    # 14. Seed Traffic Contracts
    existing_contracts = db.fetch_all("SELECT id FROM apic_contracts;")
    if not existing_contracts:
        db.execute_query("""
            INSERT INTO apic_contracts (id, name, tenant, scope, filter_name, protocol, dst_port, action) VALUES
            ('ctr-001', 'Web-to-App', 'Production', 'tenant', 'HTTPS-Filter', 'tcp', '443', 'permit'),
            ('ctr-002', 'Web-to-App', 'Production', 'tenant', 'HTTP-Alt-Filter', 'tcp', '8080', 'permit'),
            ('ctr-003', 'App-to-DB', 'Production', 'tenant', 'MySQL-Filter', 'tcp', '3306', 'permit'),
            ('ctr-004', 'App-to-DB', 'Production', 'tenant', 'PostgreSQL-Filter', 'tcp', '5432', 'permit'),
            ('ctr-005', 'ICMP-Allow', 'Shared-Services', 'global', 'ICMP-Filter', 'icmp', 'unspecified', 'permit'),
            ('ctr-006', 'DNS-Allow', 'Shared-Services', 'global', 'DNS-Filter', 'udp', '53', 'permit');
        """)
        print("Seeded: 6 Cisco ACI Traffic Contracts.")

    # 15. Seed Equipment (PSU and Fan)
    existing_eq = db.fetch_all("SELECT id FROM apic_equipment;")
    if not existing_eq:
        db.execute_query("""
            INSERT INTO apic_equipment (id, node_id, type, name, status, model, serial_number) VALUES
            ('eqp-001', 'spine-201', 'psu', 'PSU-1', 'ok', 'N9K-PAC-1200W', 'PSU-SN-SP201-1'),
            ('eqp-002', 'spine-201', 'psu', 'PSU-2', 'ok', 'N9K-PAC-1200W', 'PSU-SN-SP201-2'),
            ('eqp-003', 'spine-201', 'fan', 'FanTray-1', 'ok', 'N9K-C9508-FAN', 'FAN-SN-SP201-1'),
            ('eqp-004', 'spine-201', 'fan', 'FanTray-2', 'ok', 'N9K-C9508-FAN', 'FAN-SN-SP201-2'),
            ('eqp-005', 'spine-202', 'psu', 'PSU-1', 'ok', 'N9K-PAC-1200W', 'PSU-SN-SP202-1'),
            ('eqp-006', 'spine-202', 'psu', 'PSU-2', 'ok', 'N9K-PAC-1200W', 'PSU-SN-SP202-2'),
            ('eqp-007', 'spine-202', 'fan', 'FanTray-1', 'ok', 'N9K-C9508-FAN', 'FAN-SN-SP202-1'),
            ('eqp-008', 'spine-202', 'fan', 'FanTray-2', 'ok', 'N9K-C9508-FAN', 'FAN-SN-SP202-2'),
            ('eqp-009', 'leaf-101', 'psu', 'PSU-1', 'ok', 'N9K-PAC-650W', 'PSU-SN-LF101-1'),
            ('eqp-010', 'leaf-101', 'psu', 'PSU-2', 'ok', 'N9K-PAC-650W', 'PSU-SN-LF101-2'),
            ('eqp-011', 'leaf-101', 'fan', 'FanTray-1', 'ok', 'N9K-C93180-FAN', 'FAN-SN-LF101-1'),
            ('eqp-012', 'leaf-101', 'fan', 'FanTray-2', 'ok', 'N9K-C93180-FAN', 'FAN-SN-LF101-2'),
            ('eqp-013', 'leaf-102', 'psu', 'PSU-1', 'ok', 'N9K-PAC-650W', 'PSU-SN-LF102-1'),
            ('eqp-014', 'leaf-102', 'psu', 'PSU-2', 'ok', 'N9K-PAC-650W', 'PSU-SN-LF102-2'),
            ('eqp-015', 'leaf-102', 'fan', 'FanTray-1', 'ok', 'N9K-C93180-FAN', 'FAN-SN-LF102-1'),
            ('eqp-016', 'leaf-102', 'fan', 'FanTray-2', 'ok', 'N9K-C93180-FAN', 'FAN-SN-LF102-2'),
            ('eqp-017', 'leaf-103', 'psu', 'PSU-1', 'ok', 'N9K-PAC-650W', 'PSU-SN-LF103-1'),
            ('eqp-018', 'leaf-103', 'psu', 'PSU-2', 'ok', 'N9K-PAC-650W', 'PSU-SN-LF103-2'),
            ('eqp-019', 'leaf-103', 'fan', 'FanTray-1', 'ok', 'N9K-C93180-FAN', 'FAN-SN-LF103-1'),
            ('eqp-020', 'leaf-103', 'fan', 'FanTray-2', 'ok', 'N9K-C93180-FAN', 'FAN-SN-LF103-2');
        """)
        print("Seeded: 20 PSU and Fan Equipment items.")

    print("Database seeding completed successfully.")

if __name__ == "__main__":
    db.init_db()
    seed_database()
