import requests
from db import db
from datetime import datetime

class OneViewCollector:
    def __init__(self, base_url=None):
        # NOTE FOR REAL INTEGRATION:
        # Change this to point to your actual HPE OneView appliance URL:
        # e.g., self.base_url = f"https://{Config.ONEVIEW_HOST}/rest"
        # Make sure to handle SSL verification (verify=False or verify="/path/to/cert") for real devices.
        self.base_url = base_url or "http://127.0.0.1:5000/mock/oneview"
        self.token = None

    def login(self):
        """Authenticates with the HPE OneView appliance to fetch a session token."""
        try:
            # NOTE FOR REAL INTEGRATION:
            # Change "userName" and "password" values below to use your Config object:
            # "userName": Config.ONEVIEW_USER
            # "password": Config.ONEVIEW_PASS
            res = requests.post(f"{self.base_url}/rest/login-sessions", json={
                "userName": "admin",
                "password": "password"
            }, timeout=5, verify=False)  # verify=False ignores SSL warnings on internal IP/FQDN
            if res.status_code == 200:
                self.token = res.json().get("sessionID")
                return True
        except Exception as e:
            print(f"OneView Collector: Login failed - {e}")
        return False

    def collect(self):
        """Performs HTTP REST collection, database storage, and alert evaluation."""
        if not self.token and not self.login():
            print("OneView Collector: Skip collection due to auth failure.")
            return False

        headers = {
            "Auth": self.token,
            "X-API-Version": "2000"
        }

        try:
            # 1. Fetch Enclosures
            enc_res = requests.get(f"{self.base_url}/rest/enclosures", headers=headers, timeout=2)
            # 2. Fetch Server Blades
            server_res = requests.get(f"{self.base_url}/rest/server-hardware", headers=headers, timeout=2)
            # 3. Fetch Storage Pools
            storage_res = requests.get(f"{self.base_url}/rest/storage-pools", headers=headers, timeout=2)

            if enc_res.status_code != 200 or server_res.status_code != 200 or storage_res.status_code != 200:
                print("OneView Collector: API returned error code.")
                return False

            enclosures = enc_res.json()
            servers = server_res.json()
            storage_pools = storage_res.json()

            # Process & Save Enclosures
            for enc in enclosures:
                db.execute_query("""
                    INSERT INTO oneview_enclosures (id, name, status, temp_c, power_watts, model, serial_number)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        temp_c = EXCLUDED.temp_c,
                        power_watts = EXCLUDED.power_watts;
                """, (enc['id'], enc['name'], enc['status'], enc['temp_c'], enc['power_watts'], enc['model'], enc['serial_number']))
                
                # Check Enclosure Alerts
                self.evaluate_alert('oneview', enc['id'], enc['name'], enc['status'], 
                                   f"Enclosure {enc['name']} reports status: {enc['status']}")

            # Process & Save Server Blades
            for s in servers:
                db.execute_query("""
                    INSERT INTO oneview_server_hardware (id, enclosure_id, bay, name, status, model, serial_number, cpu_util_pct, power_watts, temp_c, profile_name, memory_mb, cpu_cores)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        cpu_util_pct = EXCLUDED.cpu_util_pct,
                        power_watts = EXCLUDED.power_watts,
                        temp_c = EXCLUDED.temp_c,
                        profile_name = EXCLUDED.profile_name;
                """, (s['id'], s['enclosure_id'], s['bay'], s['name'], s['status'], s['model'], s['serial_number'], s['cpu_util_pct'], s['power_watts'], s['temp_c'], s['profile_name'], s['memory_mb'], s['cpu_cores']))
                
                # Evaluate Server Alerts
                server_status_msg = f"Server Blade {s['name']} (Bay {s['bay']}) reports status: {s['status']}"
                self.evaluate_alert('oneview', s['id'], s['name'], s['status'], server_status_msg)

                # Custom thermal evaluation
                if s['temp_c'] > 80:
                    self.evaluate_alert('oneview', f"{s['id']}_temp", s['name'], 'CRITICAL',
                                       f"Server Blade {s['name']} CPU temperature is critical: {s['temp_c']}°C")
                else:
                    self.evaluate_alert('oneview', f"{s['id']}_temp", s['name'], 'OK', '')

            # Process & Save Storage Pools
            for p in storage_pools:
                db.execute_query("""
                    INSERT INTO oneview_storage_pools (id, name, status, capacity_gb, free_space_gb, system_name)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        capacity_gb = EXCLUDED.capacity_gb,
                        free_space_gb = EXCLUDED.free_space_gb;
                """, (p['id'], p['name'], p['status'], p['capacity_gb'], p['free_space_gb'], p['system_name']))
                
                # Evaluate Storage Pool Alerts
                storage_status_msg = f"SAN Storage Pool {p['name']} reports status: {p['status']}"
                self.evaluate_alert('oneview', p['id'], p['name'], p['status'], storage_status_msg)

            # Record telemetry average history
            if enclosures:
                avg_temp = sum(e['temp_c'] for e in enclosures) / len(enclosures)
                total_power = sum(e['power_watts'] for e in enclosures) + sum(s['power_watts'] for s in servers)
                ts_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                db.execute_query(
                    "INSERT INTO historical_metrics (entity_type, entity_id, metric_name, metric_value, timestamp) VALUES (%s, %s, %s, %s, %s);",
                    ('enclosure', 'all', 'temp_c', avg_temp, ts_str)
                )
                db.execute_query(
                    "INSERT INTO historical_metrics (entity_type, entity_id, metric_name, metric_value, timestamp) VALUES (%s, %s, %s, %s, %s);",
                    ('enclosure', 'all', 'power_watts', total_power, ts_str)
                )

            # --- Server Profiles ---
            try:
                resp = self.session.get(f"{self.base_url}/rest/server-profiles")
                profiles = resp.json().get('members', resp.json()) if resp.ok else []
                if isinstance(profiles, dict): profiles = profiles.get('members', [])
                for p in profiles:
                    pid = p.get('uri', '').split('/')[-1] or p.get('name', '').replace(' ', '-').lower()
                    hw_id = (p.get('serverHardwareUri') or '').split('/')[-1] or None
                    db.execute_query(
                        """INSERT INTO oneview_server_profiles (id, name, server_hardware_id, status, compliance_state, template_name, firmware_baseline, description)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (id) DO UPDATE SET name=%s, server_hardware_id=%s, status=%s, compliance_state=%s, template_name=%s, firmware_baseline=%s, description=%s""",
                        (pid, p.get('name',''), hw_id, p.get('status','Unknown'),
                         p.get('templateCompliance','Unknown'),
                         (p.get('serverProfileTemplateUri') or '').split('/')[-1],
                         (p.get('firmware',{}).get('firmwareBaselineUri') or '').split('/')[-1],
                         p.get('description',''),
                         p.get('name',''), hw_id, p.get('status','Unknown'),
                         p.get('templateCompliance','Unknown'),
                         (p.get('serverProfileTemplateUri') or '').split('/')[-1],
                         (p.get('firmware',{}).get('firmwareBaselineUri') or '').split('/')[-1],
                         p.get('description',''))
                    )
                    if p.get('templateCompliance') == 'NonCompliant':
                        self.evaluate_alert('oneview', pid, p.get('name',''), 'Warning',
                            f"Server profile '{p.get('name','')}' is non-compliant with its template")
                    else:
                        self.evaluate_alert('oneview', pid, p.get('name',''), 'OK', '')
            except Exception as e:
                print(f"OneView Collector: Error collecting server profiles: {e}")

            # --- Ethernet Networks ---
            try:
                resp = self.session.get(f"{self.base_url}/rest/ethernet-networks")
                networks = resp.json().get('members', resp.json()) if resp.ok else []
                if isinstance(networks, dict): networks = networks.get('members', [])
                for n in networks:
                    nid = n.get('uri', '').split('/')[-1] or n.get('name', '').replace(' ', '-').lower()
                    db.execute_query(
                        """INSERT INTO oneview_networks (id, name, type, vlan_id, status, bandwidth_typical, subnet, purpose)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (id) DO UPDATE SET name=%s, type=%s, vlan_id=%s, status=%s, bandwidth_typical=%s, subnet=%s, purpose=%s""",
                        (nid, n.get('name',''), n.get('ethernetNetworkType','Ethernet'),
                         n.get('vlanId', 0), n.get('status','Unknown'),
                         n.get('bandwidth',{}).get('typicalBandwidth', 0),
                         n.get('subnetUri',''), n.get('purpose','General'),
                         n.get('name',''), n.get('ethernetNetworkType','Ethernet'),
                         n.get('vlanId', 0), n.get('status','Unknown'),
                         n.get('bandwidth',{}).get('typicalBandwidth', 0),
                         n.get('subnetUri',''), n.get('purpose','General'))
                    )
            except Exception as e:
                print(f"OneView Collector: Error collecting networks: {e}")

            # --- Firmware Drivers ---
            try:
                resp = self.session.get(f"{self.base_url}/rest/firmware-drivers")
                firmware = resp.json().get('members', resp.json()) if resp.ok else []
                if isinstance(firmware, dict): firmware = firmware.get('members', [])
                for f_item in firmware:
                    fid = f_item.get('uri', '').split('/')[-1] or f_item.get('version', 'unknown')
                    db.execute_query(
                        """INSERT INTO oneview_firmware (id, name, version, release_date, iso_file_name, status, size_mb)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (id) DO UPDATE SET name=%s, version=%s, release_date=%s, iso_file_name=%s, status=%s, size_mb=%s""",
                        (fid, f_item.get('name',''), f_item.get('version',''),
                         f_item.get('releaseDate',''), f_item.get('isoFileName',''),
                         f_item.get('state','Unknown'), f_item.get('bundleSize', 0),
                         f_item.get('name',''), f_item.get('version',''),
                         f_item.get('releaseDate',''), f_item.get('isoFileName',''),
                         f_item.get('state','Unknown'), f_item.get('bundleSize', 0))
                    )
            except Exception as e:
                print(f"OneView Collector: Error collecting firmware: {e}")

            print("OneView Collector: Infrastructure metrics refreshed successfully.")
            return True

        except Exception as e:
            print(f"OneView Collector: Telemetry fetch error - {e}")
            return False

    def evaluate_alert(self, source, entity_id, entity_name, status, message):
        """Creates or resolves alert logs depending on resource health status."""
        # Find active unresolved alert for this entity
        db_alert = db.fetch_one(
            "SELECT id FROM alerts WHERE entity_id = %s AND resolved = %s;",
            (entity_id, False)
        )

        is_healthy = status.upper() in ('OK', 'NORMAL', 'UP')

        if not is_healthy:
            # We have an anomaly. If alert doesn't exist, create it.
            if not db_alert:
                severity = 'CRITICAL' if status.upper() in ('CRITICAL', 'DOWN') else 'WARNING'
                db.execute_query("""
                    INSERT INTO alerts (source, severity, entity_id, entity_name, message, resolved)
                    VALUES (%s, %s, %s, %s, %s, %s);
                """, (source, severity, entity_id, entity_name, message, False))
                print(f"ALERT: Created active {severity} incident on {entity_name}.")
        else:
            # Resource is healthy. If there was an active alert, resolve it.
            if db_alert:
                db.execute_query(
                    "UPDATE alerts SET resolved = %s WHERE id = %s;",
                    (True, db_alert['id'])
                )
                print(f"RESOLVED: Incident on {entity_name} cleared.")
