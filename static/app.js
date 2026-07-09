// AIOps Platform Frontend Javascript Control Logic

// State variables
let activeTab = 'dashboard';
let echartsInstances = {};
let pollingInterval = null;
let activeSimulations = {};

// Theme colors
const colors = {
  blue: '#3b82f6',
  emerald: '#10b981',
  amber: '#f59e0b',
  red: '#ef4444',
  purple: '#8b5cf6',
  slateDark: '#131a26',
  slateBorder: '#243049',
  textSecondary: '#94a3b8',
  textPrimary: '#f1f5f9'
};

// Initial setup on page load
document.addEventListener('DOMContentLoaded', () => {
  initCharts();
  switchTab('dashboard');
  
  // Start polling metrics and alerts every 3 seconds
  fetchData();
  pollingInterval = setInterval(fetchData, 3000);

  // Resize charts on window resize
  window.addEventListener('resize', () => {
    Object.values(echartsInstances).forEach(chart => {
      if (chart) chart.resize();
    });
  });
});

// Tab navigation handler
function switchTab(tabId) {
  activeTab = tabId;
  
  // Hide all tab views and remove active state from nav items
  document.querySelectorAll('.tab-view').forEach(view => {
    view.classList.remove('active');
  });
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });
  
  // Show active tab view and add active class to nav
  const activeView = document.getElementById(`${tabId}-view`);
  if (activeView) activeView.classList.add('active');
  
  const activeNav = document.getElementById(`nav-${tabId}`);
  if (activeNav) activeNav.classList.add('active');
  
  // Update Header Title
  const titleEl = document.getElementById('view-title');
  if (tabId === 'dashboard') titleEl.textContent = 'Unified Infrastructure Status';
  if (tabId === 'oneview') titleEl.textContent = 'HPE OneView Compute & Storage';
  if (tabId === 'apic') titleEl.textContent = 'Cisco APIC ACI Networking';
  if (tabId === 'alerts') titleEl.textContent = 'AIOps Alerts Center';
  if (tabId === 'sim') titleEl.textContent = 'Operations Simulation & Fault Injection';

  // Force chart resize since their containers might have changed from display: none
  setTimeout(() => {
    Object.values(echartsInstances).forEach(chart => {
      if (chart) chart.resize();
    });
  }, 100);
}

// Initialize ECharts instances
function initCharts() {
  // 1. Dashboard OneView Health Dial
  echartsInstances.dashOneViewHealth = echarts.init(document.getElementById('dash-oneview-health-chart'));
  
  // 2. Dashboard APIC Health Dial
  echartsInstances.dashApicHealth = echarts.init(document.getElementById('dash-apic-health-chart'));
  
  // 3. HPE OneView Power & Thermal Chart
  echartsInstances.ovTelemetry = echarts.init(document.getElementById('ov-telemetry-chart'));
  
  // 4. Cisco APIC Traffic Rate Chart
  echartsInstances.apicTraffic = echarts.init(document.getElementById('apic-traffic-chart'));
}

// Fetch metrics, alerts, and simulation status from Flask Backend
async function fetchData() {
  try {
    const [metricsRes, alertsRes, simRes] = await Promise.all([
      fetch('/api/metrics'),
      fetch('/api/alerts'),
      fetch('/api/sim/status')
    ]);
    
    if (!metricsRes.ok || !alertsRes.ok || !simRes.ok) {
      console.warn("Backend endpoints returning error, using placeholder simulator client-side");
      updatePulseDots(false, false, false);
      return;
    }
    
    const metrics = await metricsRes.json();
    const alerts = await alertsRes.json();
    const simulations = await simRes.json();
    
    activeSimulations = simulations;
    
    // Update Connection indicators
    updatePulseDots(metrics.db_connected, metrics.oneview_connected, metrics.apic_connected);
    
    // Update Header Counts
    updateHeaderAlerts(alerts);
    
    // Update Active simulations UI state
    updateSimulatorsUI(simulations);
    
    // Render specific tabs based on active view
    updateDashboardOverview(metrics, alerts);
    updateOneViewTab(metrics.oneview);
    updateApicTab(metrics.apic);
    updateAlertsCenter(alerts);
    
  } catch (err) {
    console.error("Connection to Flask API failed", err);
    updatePulseDots(false, false, false);
  }
}

// Helper to update status lights in sidebar
function updatePulseDots(db, oneview, apic) {
  const dbDot = document.getElementById('status-db');
  dbDot.className = db ? 'pulse-dot' : 'pulse-dot error';
  
  const ovDot = document.getElementById('status-oneview');
  ovDot.className = oneview ? 'pulse-dot' : 'pulse-dot error';
  
  const apicDot = document.getElementById('status-apic');
  apicDot.className = apic ? 'pulse-dot' : 'pulse-dot error';
}

// Helper to update header warning/critical counters
function updateHeaderAlerts(alerts) {
  const critical = alerts.filter(a => a.severity.toLowerCase() === 'critical' && !a.resolved).length;
  const warning = alerts.filter(a => a.severity.toLowerCase() === 'warning' && !a.resolved).length;
  
  document.getElementById('header-critical-count').textContent = `${critical} Critical`;
  document.getElementById('header-warning-count').textContent = `${warning} Warning`;
}

// Helper to update simulator button visual states
function updateSimulatorsUI(simulations) {
  Object.keys(simulations).forEach(key => {
    const btn = document.getElementById(`sim-${key}-btn`);
    if (btn) {
      if (simulations[key]) {
        btn.classList.add('active');
        btn.textContent = 'Clear Failure';
      } else {
        btn.classList.remove('active');
        btn.textContent = 'Inject Failure';
      }
    }
  });
}

// 1. ==================== Render Tab 1: Dashboard Overview ====================
function updateDashboardOverview(metrics, alerts) {
  if (activeTab !== 'dashboard') return;
  
  const ov = metrics.oneview || {};
  const apic = metrics.apic || {};
  
  // Enclosure count
  document.getElementById('kpi-dash-enclosures').textContent = ov.enclosures ? ov.enclosures.length : '0';
  document.getElementById('kpi-dash-enclosures-status').textContent = ov.health_index > 80 ? 'OK' : 'DEGRADED';
  document.getElementById('kpi-dash-enclosures-status').className = `kpi-badge ${ov.health_index > 80 ? 'success' : 'warning'}`;
  
  // Blade count
  document.getElementById('kpi-dash-servers').textContent = ov.servers ? ov.servers.length : '0';
  document.getElementById('kpi-dash-servers-status').textContent = ov.health_index > 90 ? 'OK' : 'ALERT';
  document.getElementById('kpi-dash-servers-status').className = `kpi-badge ${ov.health_index > 90 ? 'success' : 'warning'}`;
  
  // Cisco Switches
  document.getElementById('kpi-dash-switches').textContent = apic.nodes ? apic.nodes.length : '0';
  document.getElementById('kpi-dash-switches-status').textContent = apic.health_index > 85 ? 'OK' : 'DEGRADED';
  document.getElementById('kpi-dash-switches-status').className = `kpi-badge ${apic.health_index > 85 ? 'success' : 'warning'}`;
  
  // Cisco Tenants
  document.getElementById('kpi-dash-tenants').textContent = apic.logical ? [...new Set(apic.logical.map(l => l.tenant))].length : '0';

  // Render Gauge Charts
  renderHealthGauge(echartsInstances.dashOneViewHealth, 'HPE Synergy Health', ov.health_index || 0, colors.blue);
  renderHealthGauge(echartsInstances.dashApicHealth, 'Cisco ACI Health', apic.health_index || 0, colors.purple);

  // Render High Priority Alert lists
  const activeAlerts = alerts.filter(a => !a.resolved).slice(0, 5);
  const container = document.getElementById('dash-active-alerts-list');
  
  if (activeAlerts.length === 0) {
    container.innerHTML = `<p class="text-secondary" style="font-size: 0.8rem; text-align: center; margin-top: 2rem;">No active high priority alerts</p>`;
  } else {
    container.innerHTML = activeAlerts.map(alert => `
      <div class="alert-item ${alert.severity.toLowerCase()}">
        <div class="alert-item-header">
          <span>${alert.source.toUpperCase()} &bull; ${alert.entity_name}</span>
          <span class="alert-time">${formatTimestamp(alert.timestamp)}</span>
        </div>
        <div class="alert-msg">${alert.message}</div>
      </div>
    `).join('');
  }
}

// 2. ==================== Render Tab 2: HPE OneView Tab ====================
function updateOneViewTab(ov) {
  if (activeTab !== 'oneview' || !ov) return;
  
  // Power KPIs
  const totalPower = ov.servers ? ov.servers.reduce((sum, s) => sum + s.power_watts, 0) + ov.enclosures.reduce((sum, e) => sum + e.power_watts, 0) : 0;
  document.getElementById('kpi-ov-power').textContent = `${totalPower} W`;
  
  // Temperature KPIs
  const avgTemp = ov.servers && ov.servers.length ? Math.round(ov.servers.reduce((sum, s) => sum + s.temp_c, 0) / ov.servers.length) : 0;
  document.getElementById('kpi-ov-temp').textContent = `${avgTemp} °C`;
  const tempStatus = document.getElementById('kpi-ov-temp-status');
  tempStatus.textContent = avgTemp < 40 ? 'Normal' : avgTemp < 60 ? 'Warm' : 'Critical';
  tempStatus.className = `kpi-badge ${avgTemp < 40 ? 'success' : avgTemp < 60 ? 'warning' : 'danger'}`;
  
  // Storage pools total capacity
  const totalCapacity = ov.storage_pools ? ov.storage_pools.reduce((sum, p) => sum + p.capacity_gb, 0) / 1024 : 0;
  const freeCapacity = ov.storage_pools ? ov.storage_pools.reduce((sum, p) => sum + p.free_space_gb, 0) / 1024 : 0;
  document.getElementById('kpi-ov-storage').textContent = `${Math.round(totalCapacity - freeCapacity)} / ${Math.round(totalCapacity)} TB`;
  
  // Profiles configured
  document.getElementById('kpi-ov-profiles').textContent = ov.servers ? ov.servers.filter(s => s.profile_name).length : '0';

  // Render Enclosure grids
  const rackContainer = document.getElementById('ov-enclosures-rack');
  if (ov.enclosures && ov.enclosures.length) {
    rackContainer.innerHTML = ov.enclosures.map(enc => {
      const blades = ov.servers.filter(s => s.enclosure_id === enc.id).sort((a, b) => a.bay - b.bay);
      
      // Render bays (HPE Synergy frame holds up to 12 half-height or 6 full-height. Let's represent 8 bays for simplicity)
      let bayHTML = '';
      for (let i = 1; i <= 8; i++) {
        const blade = blades.find(b => b.bay === i);
        if (blade) {
          const statusClass = blade.status.toLowerCase() === 'critical' ? 'critical' : blade.status.toLowerCase() === 'warning' ? 'warning' : 'healthy';
          bayHTML += `
            <div class="blade-bay ${statusClass}" onclick="openBladeDetails('${blade.id}', '${escapeHtml(blade.name)}')">
              <span class="blade-label">Bay ${i}</span>
              <span style="font-size: 0.65rem; color: var(--text-primary); text-align: center;">${blade.name.replace('Blade-', 'B')}</span>
              <div class="blade-status-indicator ${statusClass}"></div>
            </div>
          `;
        } else {
          bayHTML += `
            <div class="blade-bay empty">
              <span class="blade-label">Bay ${i}</span>
              <span style="font-size: 0.55rem; color: var(--text-muted);">Empty</span>
              <div></div>
            </div>
          `;
        }
      }
      
      const encStatusClass = enc.status.toLowerCase() === 'critical' ? 'danger' : enc.status.toLowerCase() === 'warning' ? 'warning' : 'success';
      
      return `
        <div class="enclosure-wrapper">
          <div class="enclosure-header">
            <span><i class="fa-solid fa-cube"></i> ${enc.name} (${enc.model})</span>
            <div style="display: flex; gap: 1rem; font-size: 0.75rem;">
              <span>Power: <strong style="color: var(--text-primary);">${enc.power_watts} W</strong></span>
              <span>Temp: <strong style="color: var(--text-primary);">${enc.temp_c} °C</strong></span>
              <span class="kpi-badge ${encStatusClass}">${enc.status.toUpperCase()}</span>
            </div>
          </div>
          <div class="enclosure-bays">
            ${bayHTML}
          </div>
        </div>
      `;
    }).join('');
  } else {
    rackContainer.innerHTML = '<p class="text-secondary" style="font-size: 0.8rem; text-align: center; padding: 2rem;">No chassis configured</p>';
  }

  // Render Storage Pools
  const poolContainer = document.getElementById('ov-storage-pools-list');
  if (ov.storage_pools && ov.storage_pools.length) {
    poolContainer.innerHTML = ov.storage_pools.map(pool => {
      const usedPercent = Math.round(((pool.capacity_gb - pool.free_space_gb) / pool.capacity_gb) * 100);
      const isWarn = usedPercent > 75;
      const isCrit = usedPercent > 90;
      const progressClass = isCrit ? 'critical' : isWarn ? 'warning' : '';
      
      return `
        <div class="storage-pool-card">
          <div style="display: flex; justify-content: space-between; font-size: 0.8rem; font-weight: 600;">
            <span>${pool.name}</span>
            <span>${usedPercent}% Used</span>
          </div>
          <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: var(--text-secondary); margin-top: 0.25rem;">
            <span>System: ${pool.system_name}</span>
            <span>${Math.round(pool.free_space_gb/1024)} TB Free of ${Math.round(pool.capacity_gb/1024)} TB</span>
          </div>
          <div class="progress-bar-container">
            <div class="progress-bar ${progressClass}" style="width: ${usedPercent}%;"></div>
          </div>
        </div>
      `;
    }).join('');
  } else {
    poolContainer.innerHTML = '<p class="text-secondary" style="font-size: 0.8rem;">No storage pools configured</p>';
  }

  // Render Telemetry Line Chart
  renderTelemetryChart(echartsInstances.ovTelemetry, ov.telemetry_history);
}

// 3. ==================== Render Tab 3: Cisco APIC Tab ====================
function updateApicTab(apic) {
  if (activeTab !== 'apic' || !apic) return;
  
  // APIC switch counts
  document.getElementById('kpi-apic-spines').textContent = apic.nodes ? apic.nodes.filter(n => n.role === 'spine').length : '0';
  document.getElementById('kpi-apic-leafs').textContent = apic.nodes ? apic.nodes.filter(n => n.role === 'leaf').length : '0';
  document.getElementById('kpi-apic-endpoints').textContent = apic.endpoints_count || '0';
  document.getElementById('kpi-apic-epgs').textContent = apic.logical ? apic.logical.length : '0';

  // Populate Switches Table
  const tableBody = document.getElementById('apic-nodes-table-body');
  if (apic.nodes && apic.nodes.length) {
    tableBody.innerHTML = apic.nodes.map(node => {
      const isCrit = node.health_score < 70;
      const isWarn = node.health_score < 90;
      const scoreColor = isCrit ? colors.red : isWarn ? colors.amber : colors.emerald;
      const statusBadge = node.status.toLowerCase() === 'online' ? 'success' : 'danger';
      
      return `
        <tr>
          <td style="font-weight: 600;">${node.name}</td>
          <td><span style="text-transform: capitalize;">${node.role}</span></td>
          <td style="font-family: var(--font-mono); font-size: 0.75rem;">${node.ip_address}</td>
          <td><strong style="color: ${scoreColor}">${node.health_score} / 100</strong></td>
          <td><span class="kpi-badge ${statusBadge}">${node.status.toUpperCase()}</span></td>
        </tr>
      `;
    }).join('');
  } else {
    tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-secondary);">No fabric switches discovered</td></tr>';
  }

  // Populate logical tenant architecture
  const logicalBody = document.getElementById('apic-logical-table-body');
  if (apic.logical && apic.logical.length) {
    logicalBody.innerHTML = apic.logical.map(row => `
      <tr>
        <td style="font-weight: 500; color: var(--text-primary);"><i class="fa-solid fa-building" style="font-size:0.65rem; margin-right:0.35rem; color:var(--color-blue);"></i>${row.tenant}</td>
        <td>${row.vrf}</td>
        <td>${row.bd_name}</td>
        <td><span class="kpi-badge" style="background-color:rgba(139, 92, 246, 0.1); color: var(--color-purple); font-size: 0.7rem;">${row.epg}</span></td>
      </tr>
    `).join('');
  } else {
    logicalBody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">No logical tenants configured</td></tr>';
  }

  // Populate active ports table
  const interfacesBody = document.getElementById('apic-interfaces-table-body');
  if (apic.interfaces && apic.interfaces.length) {
    interfacesBody.innerHTML = apic.interfaces.map(face => {
      const portStatus = face.status.toLowerCase() === 'up' ? 'success' : 'danger';
      return `
        <tr>
          <td style="font-weight: 500;">${face.node_name}</td>
          <td style="font-family: var(--font-mono);">${face.name}</td>
          <td><span class="kpi-badge ${portStatus}">${face.status.toUpperCase()}</span></td>
          <td>${formatBps(face.usage_in_bps)}</td>
          <td>${formatBps(face.usage_out_bps)}</td>
        </tr>
      `;
    }).join('');
  } else {
    interfacesBody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-secondary);">No ports active</td></tr>';
  }

  // Traffic Rate chart
  renderTrafficChart(echartsInstances.apicTraffic, apic.traffic_history);
}

// 4. ==================== Render Tab 4: Alert Center ====================
function updateAlertsCenter(alerts) {
  if (activeTab !== 'alerts') return;
  
  const container = document.getElementById('alerts-center-table-body');
  
  if (!alerts || alerts.length === 0) {
    container.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-secondary); padding: 3rem;">No system alerts recorded</td></tr>`;
  } else {
    container.innerHTML = alerts.map(alert => {
      const badgeClass = alert.severity.toLowerCase() === 'critical' ? 'danger' : alert.severity.toLowerCase() === 'warning' ? 'warning' : 'success';
      const rowStyle = alert.resolved ? 'opacity: 0.55;' : '';
      const actionBtn = alert.resolved 
        ? `<span style="color: var(--color-emerald); font-size: 0.75rem;"><i class="fa-solid fa-check"></i> Resolved</span>`
        : `<button class="btn-small" onclick="resolveAlert(${alert.id})">Acknowledge</button>`;
      
      return `
        <tr style="${rowStyle}">
          <td style="font-family: var(--font-mono); font-size: 0.75rem;">${formatTimestamp(alert.timestamp)}</td>
          <td style="font-weight: 600; text-transform: uppercase;">${alert.source}</td>
          <td><span class="kpi-badge ${badgeClass}">${alert.severity.toUpperCase()}</span></td>
          <td style="font-weight: 500;">${alert.entity_name}</td>
          <td>${alert.message}</td>
          <td>${actionBtn}</td>
        </tr>
      `;
    }).join('');
  }
}

// Inspect blade server details
async function openBladeDetails(bladeId, bladeName) {
  const modal = document.getElementById('hardware-modal');
  const modalTitle = document.getElementById('modal-server-title');
  const detailsEl = document.getElementById('modal-server-details');
  
  modalTitle.textContent = `${bladeName} Hardware Properties`;
  detailsEl.innerHTML = '<p class="text-secondary" style="padding: 1rem 0;">Loading hardware settings...</p>';
  modal.style.display = 'flex';
  
  try {
    const res = await fetch(`/api/metrics/server/${bladeId}`);
    if (!res.ok) throw new Error("Server details unavailable");
    const blade = await res.json();
    
    const statusBadgeClass = blade.status.toLowerCase() === 'critical' ? 'danger' : blade.status.toLowerCase() === 'warning' ? 'warning' : 'success';
    
    detailsEl.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.5rem;">
        <div class="detail-row">
          <span class="detail-label">Model</span>
          <span class="detail-value">${blade.model}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Serial Number</span>
          <span class="detail-value" style="font-family: var(--font-mono);">${blade.serial_number}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Status</span>
          <span class="kpi-badge ${statusBadgeClass}">${blade.status.toUpperCase()}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Profile Assigned</span>
          <span class="detail-value" style="color: var(--color-blue); font-weight: 600;">${blade.profile_name || 'Unassigned'}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">CPU Core Allocation</span>
          <span class="detail-value">${blade.cpu_cores} Cores</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Installed Memory</span>
          <span class="detail-value">${Math.round(blade.memory_mb/1024)} GB RAM</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Telemetry CPU Load</span>
          <span class="detail-value">${blade.cpu_util_pct}%</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Power Consumption</span>
          <span class="detail-value">${blade.power_watts} Watts</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Chassis Thermal Temp</span>
          <span class="detail-value" style="font-weight:600; color: ${blade.temp_c > 65 ? colors.red : blade.temp_c > 45 ? colors.amber : colors.emerald}">${blade.temp_c} °C</span>
        </div>
      </div>
      <button class="btn-primary" style="width: 100%; margin-top: 1.5rem;" onclick="closeModal()">Close Panel</button>
    `;
    
  } catch (err) {
    detailsEl.innerHTML = '<p class="text-secondary" style="color: var(--color-red); padding: 1rem 0;">Failed to retrieve server inventory metrics.</p>';
  }
}

function closeModal() {
  document.getElementById('hardware-modal').style.display = 'none';
}

// 5. ==================== Fault Injection Trigger Handler ====================
async function toggleSimulation(simType) {
  try {
    const res = await fetch('/api/sim/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: simType })
    });
    
    if (res.ok) {
      const data = await res.json();
      activeSimulations[simType] = data.active;
      
      const btn = document.getElementById(`sim-${simType}-btn`);
      if (btn) {
        if (data.active) {
          btn.classList.add('active');
          btn.textContent = 'Clear Failure';
        } else {
          btn.classList.remove('active');
          btn.textContent = 'Inject Failure';
        }
      }
      
      // Force immediate poll to reflect alerts/metrics change
      fetchData();
    }
  } catch (err) {
    console.error("Failed to post simulation trigger", err);
  }
}

// 6. ==================== Knowledge Base Handlers ====================
async function searchKB() {
  const query = document.getElementById('kb-search-input').value;
  if (!query) return;
  
  const grid = document.getElementById('kb-docs-grid');
  grid.innerHTML = '<p class="text-secondary" style="padding: 1rem;">Searching knowledge base using pgvector...</p>';
  
  try {
    const res = await fetch(`/api/kb/search?query=${encodeURIComponent(query)}`);
    const docs = await res.json();
    
    renderKBDocs(docs);
  } catch (err) {
    console.error("Vector search failed", err);
    grid.innerHTML = '<p class="text-secondary" style="color: var(--color-red);">Failed to retrieve search results.</p>';
  }
}

async function submitRunbook() {
  const title = document.getElementById('kb-title-input').value;
  const category = document.getElementById('kb-category-select').value;
  const content = document.getElementById('kb-content-input').value;
  
  if (!title || !content) {
    alert("Please fill in both the Title and the content");
    return;
  }
  
  try {
    const res = await fetch('/api/kb/index', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, category, content })
    });
    
    if (res.ok) {
      alert("Document indexed successfully in pgvector!");
      document.getElementById('kb-title-input').value = '';
      document.getElementById('kb-content-input').value = '';
      
      // Reload KB documents
      loadKBDocs();
    }
  } catch (err) {
    console.error("Failed to index SOP", err);
  }
}

async function loadKBDocs() {
  const grid = document.getElementById('kb-docs-grid');
  try {
    const res = await fetch('/api/kb/list');
    const docs = await res.json();
    renderKBDocs(docs);
  } catch (err) {
    grid.innerHTML = '<p class="text-secondary">Failed to load Knowledge Base.</p>';
  }
}

function renderKBDocs(docs) {
  const grid = document.getElementById('kb-docs-grid');
  if (!docs || docs.length === 0) {
    grid.innerHTML = '<p class="text-secondary" style="padding: 1rem;">No reference documents found</p>';
    return;
  }
  
  grid.innerHTML = docs.map(doc => `
    <div class="kb-card">
      <span class="kb-category">${doc.category}</span>
      <h4 class="kb-title">${doc.title}</h4>
      <p class="kb-body">${doc.content}</p>
    </div>
  `).join('');
}

// Load documents initial state if on KB tab
document.getElementById('nav-kb').addEventListener('click', () => {
  loadKBDocs();
});

// Acknowledge single Alert
async function resolveAlert(alertId) {
  try {
    const res = await fetch(`/api/alerts/resolve/${alertId}`, { method: 'POST' });
    if (res.ok) fetchData();
  } catch (err) {
    console.error("Failed to acknowledge alert", err);
  }
}

// Acknowledge All Alerts
async function resolveAllAlerts() {
  try {
    const res = await fetch('/api/alerts/resolve-all', { method: 'POST' });
    if (res.ok) fetchData();
  } catch (err) {
    console.error("Failed to acknowledge alerts", err);
  }
}

// ==================== Chart Options Helper Functions ====================

function renderHealthGauge(chartInstance, title, score, color) {
  if (!chartInstance) return;
  
  const option = {
    title: {
      text: title,
      left: 'center',
      top: 'bottom',
      textStyle: { color: colors.textSecondary, fontSize: 11, fontFamily: 'Inter' }
    },
    series: [{
      type: 'gauge',
      startAngle: 180,
      endAngle: 0,
      min: 0,
      max: 100,
      radius: '85%',
      center: ['50%', '65%'],
      pointer: { show: false },
      progress: {
        show: true,
        overlap: false,
        roundCap: true,
        clip: false,
        itemStyle: { color: score < 70 ? colors.red : score < 90 ? colors.amber : color }
      },
      axisLine: {
        lineStyle: { width: 8, color: [[1, colors.slateBorder]] }
      },
      splitLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      data: [{ value: score }],
      detail: {
        valueAnimation: true,
        offsetCenter: [0, -10],
        fontSize: 22,
        fontWeight: 'bold',
        color: score < 70 ? colors.red : score < 90 ? colors.amber : colors.textPrimary,
        formatter: '{value}%',
        fontFamily: 'Inter'
      }
    }]
  };
  
  chartInstance.setOption(option);
}

function renderTelemetryChart(chartInstance, history) {
  if (!chartInstance) return;
  
  const timestamps = history ? history.map(h => formatTimeOnly(h.timestamp)) : [];
  const temps = history ? history.map(h => h.temp_c) : [];
  const power = history ? history.map(h => h.power_watts) : [];
  
  const option = {
    tooltip: { trigger: 'axis', backgroundColor: colors.slateDark, borderColor: colors.slateBorder, textStyle: { color: colors.textPrimary } },
    grid: { left: '8%', right: '8%', top: '15%', bottom: '15%' },
    legend: { data: ['Avg Temp (°C)', 'Total Power (W)'], textStyle: { color: colors.textSecondary }, bottom: 0 },
    xAxis: {
      type: 'category',
      data: timestamps,
      axisLine: { lineStyle: { color: colors.slateBorder } },
      axisLabel: { color: colors.textSecondary }
    },
    yAxis: [
      {
        type: 'value',
        name: 'Temp (°C)',
        splitLine: { lineStyle: { color: colors.slateBorder } },
        axisLabel: { color: colors.textSecondary }
      },
      {
        type: 'value',
        name: 'Power (W)',
        splitLine: { show: false },
        axisLabel: { color: colors.textSecondary }
      }
    ],
    series: [
      {
        name: 'Avg Temp (°C)',
        type: 'line',
        data: temps,
        smooth: true,
        itemStyle: { color: colors.amber },
        lineStyle: { width: 2 }
      },
      {
        name: 'Total Power (W)',
        type: 'line',
        yAxisIndex: 1,
        data: power,
        smooth: true,
        itemStyle: { color: colors.blue },
        lineStyle: { width: 2 }
      }
    ]
  };
  
  chartInstance.setOption(option);
}

function renderTrafficChart(chartInstance, history) {
  if (!chartInstance) return;
  
  const timestamps = history ? history.map(h => formatTimeOnly(h.timestamp)) : [];
  const inbound = history ? history.map(h => h.inbound_mbps) : [];
  const outbound = history ? history.map(h => h.outbound_mbps) : [];
  
  const option = {
    tooltip: { trigger: 'axis', backgroundColor: colors.slateDark, borderColor: colors.slateBorder, textStyle: { color: colors.textPrimary } },
    grid: { left: '8%', right: '8%', top: '15%', bottom: '15%' },
    legend: { data: ['Inbound Traffic (Mbps)', 'Outbound Traffic (Mbps)'], textStyle: { color: colors.textSecondary }, bottom: 0 },
    xAxis: {
      type: 'category',
      data: timestamps,
      axisLine: { lineStyle: { color: colors.slateBorder } },
      axisLabel: { color: colors.textSecondary }
    },
    yAxis: {
      type: 'value',
      name: 'Mbps',
      splitLine: { lineStyle: { color: colors.slateBorder } },
      axisLabel: { color: colors.textSecondary }
    },
    series: [
      {
        name: 'Inbound Traffic (Mbps)',
        type: 'line',
        data: inbound,
        smooth: true,
        itemStyle: { color: colors.purple },
        lineStyle: { width: 2 }
      },
      {
        name: 'Outbound Traffic (Mbps)',
        type: 'line',
        data: outbound,
        smooth: true,
        itemStyle: { color: colors.blue },
        lineStyle: { width: 2 }
      }
    ]
  };
  
  chartInstance.setOption(option);
}

// Formatting helpers
function formatTimestamp(tsString) {
  if (!tsString) return '';
  const d = new Date(tsString);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' ' + d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function formatTimeOnly(tsString) {
  if (!tsString) return '';
  const d = new Date(tsString);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatBps(bps) {
  if (bps === 0) return '0 bps';
  const k = 1000;
  const sizes = ['bps', 'Kbps', 'Mbps', 'Gbps'];
  const i = Math.floor(Math.log(bps) / Math.log(k));
  return parseFloat((bps / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
