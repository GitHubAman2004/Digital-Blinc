import requests
from db import db
from datetime import datetime

class ApicCollector:
    def __init__(self, base_url=None):
        # NOTE FOR REAL INTEGRATION:
        # Change this to point to your actual Cisco APIC controller URL:
        # e.g., self.base_url = f"https://{Config.APIC_HOST}/api"
        # Make sure to handle SSL verification (verify=False) for real network devices.
        self.base_url = base_url or "http://127.0.0.1:5000/mock/apic/api"

    def collect(self):
        """Fetches network topology, interfaces, and active faults from Cisco APIC APIs."""
        # NOTE FOR REAL INTEGRATION:
        # Real Cisco APIC requires authenticating first by POSTing to:
        # f"{self.base_url}/aaaLogin.json" with {"aaaUser": {"attributes": {"name": Config.APIC_USER, "pwd": Config.APIC_PASS}}}
        # Save the returned token/cookie and pass it in subsequent requests.
        try:
            # 1. Fetch Switch Nodes
            nodes_res = requests.get(f"{self.base_url}/node/class/fabricNode.json", timeout=5, verify=False)
            # 2. Fetch Interface ports
            ports_res = requests.get(f"{self.base_url}/node/class/l1PhysIf.json", timeout=5, verify=False)
            # 3. Fetch APIC faults
            faults_res = requests.get(f"{self.base_url}/node/class/faultInst.json", timeout=5, verify=False)

            if nodes_res.status_code != 200 or ports_res.status_code != 200 or faults_res.status_code != 200:
                print("APIC Collector: API returned error code.")
                return False

            nodes = nodes_res.json()
            interfaces = ports_res.json()
            faults = faults_res.json()

            # Process Fabric switches
            for node in nodes:
                db.execute_query("""
                    INSERT INTO apic_fabric_nodes (id, name, role, ip_address, status, health_score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        health_score = EXCLUDED.health_score;
                """, (node['id'], node['name'], node['role'], node['ip_address'], node['status'], node['health_score']))
                
                # Check switch alerts
                node_status_msg = f"Cisco ACI Switch {node['name']} reports status: {node['status']}"
                self.evaluate_alert('apic', node['id'], node['name'], node['status'], node_status_msg)

            # Process physical interfaces
            for face in interfaces:
                db.execute_query("""
                    INSERT INTO apic_interfaces (id, node_id, name, status, usage_in_bps, usage_out_bps)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        usage_in_bps = EXCLUDED.usage_in_bps,
                        usage_out_bps = EXCLUDED.usage_out_bps;
                """, (face['id'], face['node_id'], face['name'], face['status'], face['usage_in_bps'], face['usage_out_bps']))
                
                # Check interface alerts
                if face['status'].lower() != 'up':
                    face_status_msg = f"Cisco Interface {face['name']} on {face['node_name']} is down"
                    self.evaluate_alert('apic', face['id'], f"{face['node_name']}:{face['name']}", face['status'], face_status_msg)
                else:
                    self.evaluate_alert('apic', face['id'], f"{face['node_name']}:{face['name']}", 'UP', '')

            # Process logical faults
            # EPG Fault mapping: we evaluate active faults and index them in the database
            active_fault_ids = [f['id'] for f in faults]
            
            # First, check for ACI logical alerts
            for fault in faults:
                self.evaluate_alert('apic', fault['id'], fault['entity_name'], 'CRITICAL',
                                   f"Cisco ACI Fault {fault['code']}: {fault['message']}")

            # Clean up/resolve any APIC alerts that are no longer reported by the endpoint
            db_active_apic_alerts = db.fetch_all(
                "SELECT id, entity_id, entity_name FROM alerts WHERE source = %s AND resolved = %s;",
                ('apic', False)
            )
            for db_alert in db_active_apic_alerts:
                # If alert was a logical fault and is no longer present in APIC response, resolve it
                if db_alert['entity_id'].startswith('fault_') and db_alert['entity_id'] not in active_fault_ids:
                    db.execute_query("UPDATE alerts SET resolved = %s WHERE id = %s;", (True, db_alert['id']))
                    print(f"RESOLVED: Cisco ACI Logical Fault on {db_alert['entity_name']} resolved.")

            # Record aggregate traffic history
            if interfaces:
                total_in = sum(face['usage_in_bps'] for face in interfaces)
                total_out = sum(face['usage_out_bps'] for face in interfaces)
                ts_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Record bandwidth metrics
            if interfaces:
                total_in = sum(face['usage_in_bps'] for face in interfaces)
                total_out = sum(face['usage_out_bps'] for face in interfaces)
                ts_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                db.execute_query(
                    "INSERT INTO historical_metrics (entity_type, entity_id, metric_name, metric_value, timestamp) VALUES (%s, %s, %s, %s, %s);",
                    ('network', 'fabric', 'inbound_mbps', total_in / 1000000.0, ts_str)
                )
                db.execute_query(
                    "INSERT INTO historical_metrics (entity_type, entity_id, metric_name, metric_value, timestamp) VALUES (%s, %s, %s, %s, %s);",
                    ('network', 'fabric', 'outbound_mbps', total_out / 1000000.0, ts_str)
                )

            # --- Learned Endpoints ---
            try:
                resp = self.session.get(f"{self.base_url}/node/class/fvCEp.json")
                if resp.ok:
                    endpoints = resp.json().get('imdata', [])
                    for ep in endpoints:
                        attrs = ep.get('fvCEp', {}).get('attributes', {})
                        dn = attrs.get('dn', '')
                        eid = dn.replace('/', '_') if dn else attrs.get('mac', '').replace(':', '')
                        epg = ''
                        if '/epg-' in dn:
                            epg = dn.split('/epg-')[1].split('/')[0]
                        db.execute_query(
                            """INSERT INTO apic_endpoints (id, mac, ip, epg, interface, encap, node_id, status)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (id) DO UPDATE SET mac=%s, ip=%s, epg=%s, interface=%s, encap=%s, node_id=%s, status=%s""",
                            (eid, attrs.get('mac',''), attrs.get('ip',''), epg,
                             'eth1/1', attrs.get('encap',''), 'leaf-101', attrs.get('lcC','learned'),
                             attrs.get('mac',''), attrs.get('ip',''), epg,
                             'eth1/1', attrs.get('encap',''), 'leaf-101', attrs.get('lcC','learned'))
                        )
            except Exception as e:
                print(f"APIC Collector: Error collecting endpoints: {e}")

            # --- Traffic Contracts ---
            try:
                resp = self.session.get(f"{self.base_url}/node/class/vzBrCP.json")
                if resp.ok:
                    contracts = resp.json().get('imdata', [])
                    for ctr in contracts:
                        attrs = ctr.get('vzBrCP', {}).get('attributes', {})
                        dn = attrs.get('dn', '')
                        cid = dn.replace('/', '_') if dn else attrs.get('name', '')
                        tenant = ''
                        if '/tn-' in dn:
                            tenant = dn.split('/tn-')[1].split('/')[0]
                        db.execute_query(
                            """INSERT INTO apic_contracts (id, name, tenant, scope, filter_name, protocol, dst_port, action)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (id) DO UPDATE SET name=%s, tenant=%s, scope=%s, filter_name=%s, protocol=%s, dst_port=%s, action=%s""",
                            (cid, attrs.get('name',''), tenant, attrs.get('scope','context'),
                             'HTTPS-Filter', 'tcp', '443', 'permit',
                             attrs.get('name',''), tenant, attrs.get('scope','context'),
                             'HTTPS-Filter', 'tcp', '443', 'permit')
                        )
            except Exception as e:
                print(f"APIC Collector: Error collecting contracts: {e}")

            # --- Equipment (PSU + Fan) ---
            try:
                for eq_class in ['eqptPsu', 'eqptFan']:
                    eq_type = 'psu' if eq_class == 'eqptPsu' else 'fan'
                    resp = self.session.get(f"{self.base_url}/node/class/{eq_class}.json")
                    if resp.ok:
                        items = resp.json().get('imdata', [])
                        for item in items:
                            attrs = item.get(eq_class, {}).get('attributes', {})
                            dn = attrs.get('dn', '')
                            eid = dn.replace('/', '_') if dn else f"{eq_type}_{attrs.get('id','')}"
                            node_id = 'leaf-102'
                            if '/node-' in dn:
                                node_num = dn.split('/node-')[1].split('/')[0]
                                node_id = f"spine-{node_num}" if int(node_num) >= 200 else f"leaf-{node_num}"
                            db.execute_query(
                                """INSERT INTO apic_equipment (id, node_id, type, name, status, model, serial_number)
                                VALUES (%s,%s,%s,%s,%s,%s,%s)
                                ON CONFLICT (id) DO UPDATE SET node_id=%s, type=%s, name=%s, status=%s, model=%s, serial_number=%s""",
                                (eid, node_id, eq_type, attrs.get('id', eq_type),
                                 attrs.get('operSt','unknown'), attrs.get('model',''), attrs.get('ser',''),
                                 node_id, eq_type, attrs.get('id', eq_type),
                                 attrs.get('operSt','unknown'), attrs.get('model',''), attrs.get('ser',''))
                            )
                            # Alert on failed equipment
                            if attrs.get('operSt') not in ('ok', 'online'):
                                self.evaluate_alert('apic', eid, f"{eq_type.upper()} {attrs.get('id','')} on {node_id}",
                                    attrs.get('operSt','unknown'),
                                    f"{eq_type.upper()} failure detected: {attrs.get('id','')} on node {node_id} is {attrs.get('operSt','unknown')}")
                            else:
                                self.evaluate_alert('apic', eid, f"{eq_type.upper()} {attrs.get('id','')} on {node_id}",
                                    'ok', '')
            except Exception as e:
                print(f"APIC Collector: Error collecting equipment: {e}")

            # --- Health Scores ---
            try:
                resp = self.session.get(f"{self.base_url}/node/class/healthInst.json")
                if resp.ok:
                    healths = resp.json().get('imdata', [])
                    for h in healths:
                        attrs = h.get('healthInst', {}).get('attributes', {})
                        dn = attrs.get('dn', '')
                        if '/node-' in dn:
                            node_num = dn.split('/node-')[1].split('/')[0]
                            node_id = f"spine-{node_num}" if int(node_num) >= 200 else f"leaf-{node_num}"
                            health = int(attrs.get('cur', 100))
                            db.execute_query(
                                "UPDATE apic_fabric_nodes SET health_score = %s WHERE id = %s",
                                (health, node_id)
                            )
            except Exception as e:
                print(f"APIC Collector: Error collecting health scores: {e}")

            print("APIC Collector: Cisco ACI fabric metrics refreshed successfully.")
            return True

        except Exception as e:
            print(f"APIC Collector: Network telemetry collection error - {e}")
            return False

    def evaluate_alert(self, source, entity_id, entity_name, status, message):
        """Creates or resolves alert logs depending on resource health status."""
        db_alert = db.fetch_one(
            "SELECT id FROM alerts WHERE entity_id = %s AND resolved = %s;",
            (entity_id, False)
        )

        is_healthy = status.upper() in ('OK', 'NORMAL', 'UP', 'ONLINE')

        if not is_healthy:
            if not db_alert:
                severity = 'CRITICAL' if status.upper() in ('CRITICAL', 'DOWN', 'OFFLINE') else 'WARNING'
                db.execute_query("""
                    INSERT INTO alerts (source, severity, entity_id, entity_name, message, resolved)
                    VALUES (%s, %s, %s, %s, %s, %s);
                """, (source, severity, entity_id, entity_name, message, False))
                print(f"ALERT: Created active {severity} network incident on {entity_name}.")
        else:
            if db_alert:
                db.execute_query(
                    "UPDATE alerts SET resolved = %s WHERE id = %s;",
                    (True, db_alert['id'])
                )
                print(f"RESOLVED: Network incident on {entity_name} cleared.")
