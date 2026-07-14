import { useState, useEffect, useRef, useCallback } from 'react';
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, PieChart, Pie, Cell, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ScatterChart, Scatter } from 'recharts';
import './index.css';

export default function App() {
  const [tab, setTab] = useState('oneview');
  const [theme, setTheme] = useState('dark-steel');
  const [metrics, setMetrics] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [sims, setSims] = useState({});
  const [modalBlade, setModalBlade] = useState(null);
  const [endpointSearch, setEndpointSearch] = useState('');
  const [endpointEpgFilter, setEndpointEpgFilter] = useState('all');

  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState([
    { role: 'assistant', content: 'Hello! I am your Qwen-powered AIOps Assistant. Ask me to plot telemetry metrics (like CPU, temperature, bandwidth) or describe incident mitigation guides, and I will generate them dynamically.' }
  ]);
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatHistory]);

  const sendChatMessage = async (txt = chatInput) => {
    const promptText = txt.trim();
    if (!promptText || chatLoading) return;

    const userMsg = { role: 'user', content: promptText };
    setChatHistory(prev => [...prev, userMsg]);
    setChatInput('');
    setChatLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: promptText, history: chatHistory })
      });
      if (res.ok) {
        const data = await res.json();
        setChatHistory(prev => [...prev, { role: 'assistant', content: data.reply }]);
      } else {
        setChatHistory(prev => [...prev, { role: 'assistant', content: "Failed to connect to the backend server." }]);
      }
    } catch (e) {
      setChatHistory(prev => [...prev, { role: 'assistant', content: "Error communicating with chatbot: " + e.message }]);
    } finally {
      setChatLoading(false);
    }
  };
  const [scmbEvents, setScmbEvents] = useState([]);
  const [msmbMetrics, setMsmbMetrics] = useState([]);
  const [msmbLatest, setMsmbLatest] = useState([]);
  const [busFilter, setBusFilter] = useState('all');

  useEffect(() => {
    document.body.className = '';
    if (theme !== 'dark-steel') {
      document.body.classList.add(`theme-${theme}`);
    }
  }, [theme]);

  const thermalRef = useRef(null);
  const bwRef = useRef(null);
  const thermalChart = useRef(null);
  const bwChart = useRef(null);
  const isThermalFirst = useRef(true);
  const isBwFirst = useRef(true);

  /* ── Fetch ── */
  const poll = useCallback(async () => {
    try {
      const [m, a, s] = await Promise.all([
        fetch('/api/metrics'),
        fetch('/api/alerts'),
        fetch('/api/sim/status')
      ]);
      if (m.ok) setMetrics(await m.json());
      if (a.ok) setAlerts(await a.json());
      if (s.ok) setSims(await s.json());
    } catch (_) {}
  }, []);

  const pollBus = useCallback(async () => {
    try {
      const [s, ml] = await Promise.all([
        fetch('/api/bus/scmb?limit=100'),
        fetch('/api/bus/msmb/latest'),
      ]);
      if (s.ok) setScmbEvents(await s.json());
      if (ml.ok) setMsmbLatest(await ml.json());
    } catch (_) {}
  }, []);

  useEffect(() => { poll(); const id = setInterval(poll, 4000); return () => clearInterval(id); }, [poll]);
  useEffect(() => { pollBus(); const id = setInterval(pollBus, 3000); return () => clearInterval(id); }, [pollBus]);

  useEffect(() => {
    isThermalFirst.current = true;
    isBwFirst.current = true;
  }, [tab]);

  /* ── Sim toggle ── */
  const toggleSim = async (k) => {
    const v = !sims[k];
    setSims(s => ({ ...s, [k]: v }));
    try {
      await fetch('/api/sim/trigger', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario: k, active: v }) });
      setTimeout(poll, 600);
    } catch (_) {}
  };

  const ackAlert = async (id) => {
    try { await fetch(`/api/alerts/${id}/resolve`, { method: 'POST' }); poll(); } catch (_) {}
  };

  /* ── ECharts ── */
  useEffect(() => {
    if (!window.echarts) {
      const s = document.createElement('script');
      // NOTE FOR OFFLINE DEPLOYMENT:
      // Since the target PC has no internet, download echarts.min.js locally, 
      // place it in the "frontend/public/" directory, and change the line below to:
      // s.src = '/echarts.min.js';
      s.src = 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js';
      s.async = true;
      s.onload = () => mountCharts();
      document.head.appendChild(s);
    } else mountCharts();
    return () => { thermalChart.current?.dispose(); bwChart.current?.dispose(); };
  }, []);

  function mountCharts() {
    if (!window.echarts) return;
    if (thermalRef.current) {
      if (thermalChart.current) {
        thermalChart.current.dispose();
      }
      thermalChart.current = window.echarts.init(thermalRef.current);
    }
    if (bwRef.current) {
      if (bwChart.current) {
        bwChart.current.dispose();
      }
      bwChart.current = window.echarts.init(bwRef.current);
    }
  }

  useEffect(() => {
    if (!metrics || !window.echarts) return;
    mountCharts();
    renderThermal();
    renderBandwidth();
  }, [metrics, tab]);

  const chartBase = {
    backgroundColor: 'transparent',
    grid: { left: 44, right: 16, top: 28, bottom: 24 },
    tooltip: { trigger: 'axis', backgroundColor: '#1e2028', borderColor: '#2a2d38', textStyle: { color: '#dcdfe6', fontSize: 11 } },
    xAxis: { type: 'category', axisLine: { lineStyle: { color: '#2a2d38' } }, axisLabel: { color: '#5c6070', fontSize: 10 }, axisTick: { show: false } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#2a2d38' } }, axisLabel: { color: '#5c6070', fontSize: 10 } },
  };

  function makeSeries(name, data, color) {
    return { name, type: 'line', data, smooth: true, showSymbol: false, lineStyle: { width: 1.5, color }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: color.replace(')', ',0.15)').replace('rgb', 'rgba') }, { offset: 1, color: 'transparent' }] } } };
  }

  function renderThermal() {
    if (!thermalChart.current) return;
    const h = metrics?.oneview?.telemetry_history || [];
    thermalChart.current.setOption({
      ...chartBase,
      animation: isThermalFirst.current,
      legend: { show: true, top: 2, right: 0, textStyle: { color: '#8b8fa3', fontSize: 10 } },
      xAxis: { ...chartBase.xAxis, data: h.map(x => x.ts?.substring(11, 16) || '') },
      series: [
        makeSeries('Temp °C', h.map(x => x.avg_temp), 'rgb(239, 68, 68)'),
        makeSeries('Power W', h.map(x => x.avg_power), 'rgb(59, 130, 246)'),
      ]
    });
    isThermalFirst.current = false;
  }

  function renderBandwidth() {
    if (!bwChart.current) return;
    const h = metrics?.apic?.telemetry_history || [];
    bwChart.current.setOption({
      ...chartBase,
      animation: isBwFirst.current,
      legend: { show: true, top: 2, right: 0, textStyle: { color: '#8b8fa3', fontSize: 10 } },
      xAxis: { ...chartBase.xAxis, data: h.map(x => x.ts?.substring(11, 16) || '') },
      series: [
        makeSeries('Ingress Mbps', h.map(x => x.ingress_mbps), 'rgb(6, 182, 212)'),
        makeSeries('Egress Mbps', h.map(x => x.egress_mbps), 'rgb(139, 92, 246)'),
      ]
    });
    isBwFirst.current = false;
  }

  /* ── Derived values ── */
  const ov = metrics?.oneview || {};
  const ap = metrics?.apic || {};
  const blades = ov.blades || [];
  const encs = ov.enclosures || [];
  const pools = ov.storage_pools || [];
  const profiles = ov.profiles || [];
  const profilesCompliant = ov.profiles_compliant || 0;
  const profilesTotal = ov.profiles_total || 0;
  const networks = ov.networks || [];
  const firmwareList = ov.firmware || [];

  const sws = ap.switches || [];
  const ifaces = ap.interfaces || [];
  const tenants = ap.tenants || [];
  const endpoints = ap.endpoints || [];
  const endpointsCount = ap.endpoints_count || 0;
  const contracts = ap.contracts || [];
  const equipment = ap.equipment || [];
  const equipmentOk = ap.equipment_ok || 0;
  const equipmentTotal = ap.equipment_total || 0;

  const bladesOk = blades.filter(b => b.status === 'OK').length;
  const avgTemp = blades.length ? Math.round(blades.reduce((s, b) => s + (b.temperature || 0), 0) / blades.length) : 0;
  const avgPow = blades.length ? Math.round(blades.reduce((s, b) => s + (b.power_draw || 0), 0) / blades.length) : 0;
  const swOnline = sws.filter(s => (s.health_score || s.health || 0) >= 80).length;
  const portsUp = ifaces.filter(i => i.oper_state === 'up').length;
  const active = alerts.filter(a => a.status === 'active');
  const crits = active.filter(a => a.severity === 'critical').length;
  const warns = active.filter(a => a.severity === 'warning').length;

  /* ── Nav config ── */
  const nav = [
    { id: 'oneview', icon: 'fa-server', label: 'HPE OneView' },
    { id: 'apic', icon: 'fa-network-wired', label: 'Cisco APIC' },
    { id: 'sim', icon: 'fa-flask-vial', label: 'Fault Simulator' },
    { id: 'chat', icon: 'fa-comments', label: 'AIOps Assistant' },
  ];

  const pageTitle = nav.find(n => n.id === tab)?.label || 'Overview';

  return (
    <div className="app-shell">
      {/* ═══ LEFT NAV ═══ */}
      <aside className="left-nav">
        <div className="nav-brand">
          <div className="nav-brand-icon"><i className="fa-solid fa-bolt"></i></div>
          <span className="nav-brand-text">AIOps Monitor</span>
        </div>

        <div className="nav-section-label">Navigation</div>
        <div className="nav-items">
          {nav.map(n => (
            <button key={n.id} className={`nav-item ${tab === n.id ? 'active' : ''}`} onClick={() => setTab(n.id)}>
              <i className={`fa-solid ${n.icon}`}></i>
              {n.label}
              {n.id === 'alerts' && crits > 0 && <span className="nav-badge red">{crits}</span>}
              {n.id === 'alerts' && crits === 0 && warns > 0 && <span className="nav-badge yellow">{warns}</span>}
            </button>
          ))}
        </div>

        <div className="nav-spacer"></div>

        <div className="nav-footer">
          <div className="system-status-row">
            <span>Flask API</span>
            <div className="status-indicator"><div className="status-led"></div> Online</div>
          </div>
          <div className="system-status-row">
            <span>Scheduler</span>
            <div className="status-indicator"><div className="status-led"></div> Running</div>
          </div>
          <div className="system-status-row">
            <span>Database</span>
            <div className="status-indicator"><div className="status-led"></div> SQLite</div>
          </div>
        </div>
      </aside>

      {/* ═══ MAIN ═══ */}
      <div className="main-area">
        <header className="top-bar">
          <div className="top-bar-left">
            <span className="page-title">{pageTitle}</span>
            <span className="page-subtitle">• Live data</span>
            <div className="live-dot"></div>
          </div>
          <div className="top-bar-right">
            <select className="theme-select" value={theme} onChange={(e) => setTheme(e.target.value)} style={{
              background: 'var(--bg-panel)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-base)',
              borderRadius: '4px',
              padding: '2px 8px',
              fontSize: '11px',
              marginRight: '8px',
              cursor: 'pointer',
              outline: 'none'
            }}>
              <option value="dark-steel">Dark Steel Theme</option>
              <option value="nordic-navy">Nordic Navy Theme</option>
              <option value="cyberpunk">Cyberpunk Emerald</option>
              <option value="light-mode">Enterprise Light</option>
              <option value="nordic-light">Nordic Ice Light</option>
              <option value="warm-sand">Minimalist Warm Sand</option>
              <option value="clinical-white">Stark Clinical White</option>
            </select>
            {crits > 0 && <span className="chip red"><i className="fa-solid fa-circle-exclamation"></i> {crits} Critical</span>}
            {warns > 0 && <span className="chip yellow"><i className="fa-solid fa-triangle-exclamation"></i> {warns} Warning</span>}
            <span className="chip blue"><i className="fa-solid fa-clock"></i> 4s poll</span>
          </div>
        </header>

        <div className="content-area">


          {/* ═══ HPE ONEVIEW ═══ */}
          {tab === 'oneview' && (<>
            <div className="stat-grid">
              <StatCard label="Compute Blades" value={blades.length} unit={`${bladesOk}/${blades.length} OK`} tag={bladesOk === blades.length ? 'Healthy' : 'Degraded'} tagColor={bladesOk === blades.length ? 'green' : 'yellow'} />
              <StatCard label="Server Profiles" value={`${profilesCompliant}/${profilesTotal}`} unit="Compliant Templates" tag={profilesCompliant === profilesTotal ? 'Compliant' : 'Mismatch'} tagColor={profilesCompliant === profilesTotal ? 'green' : 'yellow'} />
              <StatCard label="Active VLANs" value={networks.length} unit="Networks Configured" tag="Active" tagColor="blue" />
              <StatCard label="Firmware SPPs" value={firmwareList.length} unit="SPP ISO Bundles" tag="Up to Date" tagColor="green" />
            </div>

            <div className="row-2-wide">
              {/* Left Column: Physical Chassis Enclosure Bays */}
              <div>
                <div className="section-divider" style={{ padding: '0 0 6px 0' }}>Physical Enclosure Bays</div>
                {encs.map((enc, ei) => {
                  const eb = blades.filter(b => b.enclosure_id === enc.id || b.enclosure === enc.name);
                  return (
                    <div className="enclosure-block" key={ei}>
                      <div className="enclosure-header">
                        <span className="enc-name"><i className="fa-solid fa-hard-drive"></i> {enc.name}</span>
                        <div className="enc-meta">
                          <span>Serial: <strong>{enc.serial || `SY480-${ei + 1}`}</strong></span>
                          <span>Bays: <strong>{eb.length} / 8</strong></span>
                          <span>Status: <strong style={{ color: enc.status === 'OK' ? 'var(--green)' : 'var(--red)' }}>{enc.status || 'OK'}</strong></span>
                        </div>
                      </div>
                      <div className="bay-row">
                        {Array.from({ length: 8 }, (_, bi) => {
                          const blade = eb.find(b => b.bay === bi + 1);
                          if (!blade) return (
                            <div className="bay-slot empty" key={bi}>
                              <div className="bay-top"><span className="bay-id">Bay {bi + 1}</span></div>
                              <span className="bay-label" style={{ color: 'var(--text-muted)', fontSize: '10px' }}>Empty</span>
                            </div>
                          );
                          const led = blade.status === 'Critical' ? 'crit' : blade.status === 'Warning' ? 'warn' : 'ok';
                          return (
                            <div className="bay-slot" key={bi} onClick={() => setModalBlade(blade)}>
                              <div className="bay-top">
                                <span className="bay-id">Bay {bi + 1}</span>
                                <div className={`bay-led ${led}`}></div>
                              </div>
                              <span className="bay-label">{blade.short_name || blade.name?.split(' ').pop() || `BL-${bi + 1}`}</span>
                              <div className="bay-stats">
                                <span>{blade.temperature || '--'}°C</span>
                                <span>{blade.power_draw || '--'}W</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Right Column: SCMB Message Bus Live Logs */}
              <div>
                <div className="section-divider" style={{ padding: '0 0 6px 0' }}>SCMB Live Event Stream</div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-bolt"></i> State-Change Message Bus (AMQP)</span>
                    <div style={{ display: 'flex', gap: 3 }}>
                      {['all', 'server-hardware', 'alert', 'task'].map(f => (
                        <button key={f} className={`btn-ack ${busFilter === f ? 'active' : ''}`}
                          style={busFilter === f ? { background: 'var(--blue)', color: 'white', borderColor: 'var(--blue)', padding: '2px 6px', fontSize: '9px' } : { padding: '2px 6px', fontSize: '9px' }}
                          onClick={() => setBusFilter(f)}>{f === 'all' ? 'All' : f.split('-')[0]}</button>
                      ))}
                    </div>
                  </div>
                  <div className="panel-body flush">
                    <div className="alert-list" style={{ maxHeight: '380px', overflowY: 'auto' }}>
                      {scmbEvents.length === 0 ? (
                        <div className="empty-state" style={{ padding: '20px' }}><i className="fa-solid fa-satellite-dish"></i>Waiting for SCMB events...</div>
                      ) : (
                        [...scmbEvents].filter(e => busFilter === 'all' || e.resourceType === busFilter).reverse().slice(0, 30).map((evt, i) => (
                          <div className="alert-item" key={i} style={{ gridTemplateColumns: '70px 70px 1fr auto', padding: '6px 10px' }}>
                            <span className={`tag ${evt.resourceType === 'alert' ? 'red' : evt.resourceType === 'server-hardware' ? 'blue' : evt.resourceType === 'enclosure' ? 'purple' : evt.resourceType === 'storage' ? 'yellow' : 'green'}`} style={{ fontSize: '9px', padding: '0px 4px' }}>
                              {evt.resourceType?.split('-')[0]}
                            </span>
                            <span className="td-mono" style={{ fontSize: '9px', color: 'var(--text-muted)' }}>{evt.changeType?.split('-')[0]}</span>
                            <span className="alert-msg" style={{ fontSize: '11px' }}>
                              <strong>{evt.resourceName}</strong> — {evt.details?.reason || 'State change'}
                            </span>
                            <span className="alert-ts" style={{ fontSize: '9px' }}>{evt.timestamp?.substring(11, 19)}</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="row-2-wide">
              {/* Left Column: MSMB live detailed telemetry stream */}
              <div>
                <div className="section-divider" style={{ padding: '8px 0 6px 0' }}>MSMB Real-time Metric Streaming</div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-wave-square"></i> Metric Streaming Bus</span>
                    <span className="panel-badge">Live telemetry</span>
                  </div>
                  <div className="panel-body flush">
                    {msmbLatest.length === 0 ? (
                      <div className="empty-state" style={{ padding: '30px' }}><i className="fa-solid fa-chart-line"></i>Waiting for MSMB streams...</div>
                    ) : (
                      <table className="dtable" style={{ fontSize: '11.5px' }}>
                        <thead>
                          <tr>
                            <th>Blade</th>
                            <th>CPU %</th>
                            <th>Temp</th>
                            <th>Power</th>
                            <th>Memory</th>
                            <th>Fan RPM</th>
                            <th>NIC Mbps</th>
                            <th>Updated</th>
                          </tr>
                        </thead>
                        <tbody>
                          {msmbLatest.map((m, i) => {
                            const mt = m.metrics || {};
                            const tempColor = mt.cpuTemperature > 80 ? 'var(--red)' : mt.cpuTemperature > 60 ? 'var(--yellow)' : 'var(--green)';
                            const cpuColor = mt.cpuUtilization > 90 ? 'var(--red)' : mt.cpuUtilization > 70 ? 'var(--yellow)' : 'var(--text-primary)';
                            const fanColor = mt.fanSpeedRpm < 1000 ? 'var(--red)' : 'var(--text-secondary)';
                            return (
                              <tr key={i}>
                                <td className="td-bold" style={{ padding: '5px 12px' }}>{m.resourceName}<br/><span style={{ fontSize: '8.5px', color: 'var(--text-muted)' }}>{m.enclosure}</span></td>
                                <td className="td-mono" style={{ color: cpuColor, padding: '5px 12px' }}>{mt.cpuUtilization}%</td>
                                <td className="td-mono" style={{ color: tempColor, padding: '5px 12px' }}>{mt.cpuTemperature}°C</td>
                                <td className="td-mono" style={{ padding: '5px 12px' }}>{mt.powerConsumed}W</td>
                                <td className="td-mono" style={{ padding: '5px 12px' }}>{mt.memoryUtilization}%</td>
                                <td className="td-mono" style={{ color: fanColor, padding: '5px 12px' }}>{mt.fanSpeedRpm}</td>
                                <td className="td-mono" style={{ padding: '5px 12px' }}>{mt.networkAdapterThroughputMbps}</td>
                                <td className="alert-ts" style={{ padding: '5px 12px', fontSize: '9px' }}>{m.timestamp?.substring(11, 19)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
              </div>

              {/* Right Column: Storage Pools and ECharts Thermal Trend */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div className="section-divider" style={{ padding: '8px 0 6px 0' }}>Storage & Telemetry History</div>
                
                {/* Storage Pools */}
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-database"></i> SAN Storage Pools</span>
                  </div>
                  <div className="panel-body" style={{ padding: '8px 12px' }}>
                    <div className="pool-row">
                      {pools.map((p, i) => {
                        const pct = p.total_tb > 0 ? Math.round((p.used_tb / p.total_tb) * 100) : 0;
                        const c = pct > 85 ? 'var(--red)' : pct > 70 ? 'var(--yellow)' : 'var(--green)';
                        return (
                          <div className="pool-item" key={i} style={{ padding: '4px 0', fontSize: '11px' }}>
                            <span className="pool-name">{p.name}</span>
                            <div className="pool-bar"><div className="pool-fill" style={{ width: `${pct}%`, background: c }}></div></div>
                            <span className="pool-pct" style={{ color: c }}>{pct}%</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Thermal Chart */}
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-chart-area"></i> Power & Thermal Trend</span>
                  </div>
                  <div className="panel-body" style={{ padding: '8px' }}>
                    <div className="chart-container" style={{ height: '140px' }} ref={tab === 'oneview' ? thermalRef : undefined}></div>
                  </div>
                </div>
              </div>
            </div>

            <div className="row-2-wide" style={{ marginTop: '12px' }}>
              {/* Server Profiles Compliance */}
              <div>
                <div className="section-divider" style={{ padding: '0 0 6px 0' }}>Server Profile Compliance</div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-id-card"></i> Profiles ({profilesCompliant}/{profilesTotal} Compliant)</span>
                  </div>
                  <div className="panel-body flush">
                    <table className="dtable" style={{ fontSize: '11px' }}>
                      <thead>
                        <tr>
                          <th>Profile Name</th>
                          <th>Assigned Server</th>
                          <th>Template</th>
                          <th>Compliance</th>
                          <th>Firmware Baseline</th>
                        </tr>
                      </thead>
                      <tbody>
                        {profiles.length === 0 ? (
                          <tr><td colSpan="5" className="empty-state">No profiles found</td></tr>
                        ) : (
                          profiles.map((p, i) => (
                            <tr key={i}>
                              <td className="td-bold">{p.name}</td>
                              <td className="td-mono">{p.server_hardware_id || 'Unassigned'}</td>
                              <td>{p.template_name || '--'}</td>
                              <td>
                                <span className={`tag ${p.compliance_state === 'Compliant' ? 'green' : 'yellow'}`}>
                                  {p.compliance_state}
                                </span>
                              </td>
                              <td className="td-mono">{p.firmware_baseline || '--'}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* Ethernet Networks */}
              <div>
                <div className="section-divider" style={{ padding: '0 0 6px 0' }}>Ethernet & SAN Networks</div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-network-wired"></i> Network Configurations</span>
                  </div>
                  <div className="panel-body flush">
                    <table className="dtable" style={{ fontSize: '11px' }}>
                      <thead>
                        <tr>
                          <th>Network Name</th>
                          <th>Type</th>
                          <th>VLAN ID</th>
                          <th>Typical BW</th>
                          <th>Subnet</th>
                          <th>Purpose</th>
                        </tr>
                      </thead>
                      <tbody>
                        {networks.length === 0 ? (
                          <tr><td colSpan="6" className="empty-state">No networks configured</td></tr>
                        ) : (
                          networks.map((n, i) => (
                            <tr key={i}>
                              <td className="td-bold">{n.name}</td>
                              <td><span className="tag blue">{n.type}</span></td>
                              <td className="td-mono">{n.vlan_id || 'Untagged'}</td>
                              <td className="td-mono">{n.bandwidth_typical ? `${n.bandwidth_typical/1000} Gbps` : '--'}</td>
                              <td className="td-mono">{n.subnet || '--'}</td>
                              <td><span className="tag green">{n.purpose || 'General'}</span></td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>

            <div className="row-2-wide" style={{ marginTop: '12px' }}>
              {/* Interconnect Port Health */}
              <div>
                <div className="section-divider" style={{ padding: '0 0 6px 0' }}>Virtual Connect Interconnect Port Status</div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-ethernet"></i> Interconnect Switch Modules</span>
                  </div>
                  <div className="panel-body flush" style={{ padding: '12px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      {encs.map((enc, ei) => (
                        <div key={ei} style={{ background: 'var(--bg-card-header)', borderRadius: '4px', padding: '8px' }}>
                          <div style={{ fontSize: '11px', fontWeight: 'bold', marginBottom: '6px' }}>{enc.name} Modules</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', borderBottom: '1px solid var(--border-color)', paddingBottom: '2px' }}>
                              <span>Module (Bay 3)</span>
                              <span style={{ color: sims['interconnect_uplink_down'] ? 'var(--yellow)' : 'var(--green)' }}>
                                {sims['interconnect_uplink_down'] ? 'Warning (Port 1 Down)' : 'Healthy'}
                              </span>
                            </div>
                            <div style={{ display: 'flex', gap: '3px', marginTop: '4px' }}>
                              {Array.from({ length: 8 }, (_, pi) => {
                                const isDown = pi === 0 && ei === 0 && sims['interconnect_uplink_down'];
                                return (
                                  <div key={pi} className={`bay-led ${isDown ? 'crit' : 'ok'}`} style={{ width: '18px', height: '18px', borderRadius: '2px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px', color: 'white', fontWeight: 'bold', cursor: 'help' }} title={`Port-${pi+1}: ${isDown ? 'Unlinked (No signal)' : 'Linked (40Gbps)'}`}>
                                    {pi+1}
                                  </div>
                                );
                              })}
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', borderBottom: '1px solid var(--border-color)', paddingBottom: '2px', marginTop: '6px' }}>
                              <span>Module (Bay 6)</span>
                              <span style={{ color: 'var(--green)' }}>Healthy</span>
                            </div>
                            <div style={{ display: 'flex', gap: '3px', marginTop: '4px' }}>
                              {Array.from({ length: 8 }, (_, pi) => (
                                <div key={pi} className="bay-led ok" style={{ width: '18px', height: '18px', borderRadius: '2px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px', color: 'white', fontWeight: 'bold' }}>
                                  {pi+1}
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Firmware Repository */}
              <div>
                <div className="section-divider" style={{ padding: '0 0 6px 0' }}>Appliance Firmware Bundle Repository (SPPs)</div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-box-archive"></i> Firmware ISO Bundles</span>
                  </div>
                  <div className="panel-body flush">
                    <table className="dtable" style={{ fontSize: '11px' }}>
                      <thead>
                        <tr>
                          <th>SPP Version</th>
                          <th>Release Date</th>
                          <th>ISO Filename</th>
                          <th>Size</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {firmwareList.length === 0 ? (
                          <tr><td colSpan="5" className="empty-state">No firmware bundles registered</td></tr>
                        ) : (
                          firmwareList.map((f, i) => (
                            <tr key={i}>
                              <td className="td-bold">{f.name} {f.version}</td>
                              <td className="td-mono">{f.release_date || '--'}</td>
                              <td className="td-mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{f.iso_file_name}</td>
                              <td className="td-mono">{f.size_mb ? `${(f.size_mb/1024).toFixed(1)} GB` : '--'}</td>
                              <td><span className={`tag ${f.status === 'Active' ? 'green' : 'gray'}`}>{f.status}</span></td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </>)}

          {/* ═══ CISCO APIC ═══ */}
          {tab === 'apic' && (<>
            <div className="stat-grid">
              <StatCard label="Fabric Switches" value={sws.length} unit={`${swOnline} healthy`} tag={swOnline === sws.length ? 'All Up' : 'Degraded'} tagColor={swOnline === sws.length ? 'green' : 'yellow'} />
              <StatCard label="Learned Endpoints" value={endpointsCount} unit="IP/MAC Mappings" tag="Active" tagColor="blue" />
              <StatCard label="Hardware Equipment" value={`${equipmentOk}/${equipmentTotal}`} unit="PSUs & Fans OK" tag={equipmentOk === equipmentTotal ? 'Healthy' : 'Failure'} tagColor={equipmentOk === equipmentTotal ? 'green' : 'red'} />
              <StatCard label="Traffic Contracts" value={contracts.length} unit="Security Profiles" tag="Active" tagColor="green" />
            </div>

            {/* Switch table */}
            <div className="panel">
              <div className="panel-head">
                <span className="panel-title"><i className="fa-solid fa-microchip"></i> ACI Fabric Nodes</span>
                <span className="panel-badge">{sws.length} nodes</span>
              </div>
              <div className="panel-body flush">
                <table className="dtable">
                  <thead><tr><th>Node</th><th>Role</th><th>Model</th><th>Serial</th><th>Health</th><th>State</th></tr></thead>
                  <tbody>
                    {sws.map((sw, i) => {
                      const hp = sw.health_score || sw.health || 0;
                      const hc = hp >= 80 ? 'var(--green)' : hp >= 50 ? 'var(--yellow)' : 'var(--red)';
                      return (
                        <tr key={i}>
                          <td className="td-bold">{sw.name}</td>
                          <td><span className={`tag ${sw.role === 'spine' ? 'purple' : 'blue'}`}>{sw.role}</span></td>
                          <td className="td-mono">{sw.model}</td>
                          <td className="td-mono">{sw.serial}</td>
                          <td>
                            <span className="health-mini">
                              <span style={{ color: hc }}>{hp}%</span>
                              <div className="track"><div className="fill" style={{ width: `${hp}%`, background: hc }}></div></div>
                            </span>
                          </td>
                          <td><span className={`tag ${hp >= 80 ? 'green' : hp >= 50 ? 'yellow' : 'red'}`}>{hp >= 80 ? 'Online' : 'Degraded'}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="row-2">
              {/* Left: Switch Interfaces Ports */}
              <div className="panel">
                <div className="panel-head">
                  <span className="panel-title"><i className="fa-solid fa-ethernet"></i> Interface Ports</span>
                </div>
                <div className="panel-body flush">
                  <table className="dtable">
                    <thead><tr><th>Interface</th><th>Speed</th><th>State</th><th>Errors</th></tr></thead>
                    <tbody>
                      {ifaces.map((f, i) => (
                        <tr key={i}>
                          <td className="td-bold">{f.name}</td>
                          <td className="td-mono">{f.speed || '10G'}</td>
                          <td><span className={`tag ${f.oper_state === 'up' ? 'green' : 'red'}`}>{f.oper_state}</span></td>
                          <td className="td-mono" style={{ color: (f.errors || 0) > 0 ? 'var(--yellow)' : undefined }}>{f.errors || 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Right: Tenants & Faults Stack */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {/* Tenants */}
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-diagram-project"></i> Logical Tenants</span>
                  </div>
                  <div className="panel-body" style={{ padding: '8px 12px' }}>
                    {tenants.map((t, i) => (
                      <div className="tenant-row" key={i} style={{ padding: '4px 0', fontSize: '11.5px' }}>
                        <span className="tenant-name" style={{ minWidth: '80px' }}>{t.tenant}</span>
                        <div className="tenant-path">
                          <span className="tag blue">VRF: {t.vrf}</span>
                          <span className="arrow">→</span>
                          <span className="tag purple">BD: {t.bd}</span>
                          <span className="arrow">→</span>
                          <span className="tag green">EPG: {t.epg}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Active Fabric Faults */}
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-triangle-exclamation"></i> Active Fabric Faults</span>
                    {alerts.filter(a => a.source === 'apic' && a.status === 'active').length > 0 && (
                      <span className="tag red">{alerts.filter(a => a.source === 'apic' && a.status === 'active').length} active</span>
                    )}
                  </div>
                  <div className="panel-body flush">
                    {alerts.filter(a => a.source === 'apic' && a.status === 'active').length === 0 ? (
                      <div className="empty-state" style={{ padding: '15px' }}><i className="fa-solid fa-check-circle" style={{ color: 'var(--green)' }}></i>No active fabric faults</div>
                    ) : (
                      <div className="alert-list" style={{ maxHeight: '140px', overflowY: 'auto' }}>
                        {alerts.filter(a => a.source === 'apic' && a.status === 'active').map((a, i) => (
                          <div className="alert-item" key={i} style={{ gridTemplateColumns: '8px 1fr auto', padding: '6px 12px' }}>
                            <div className={`alert-dot ${a.severity}`}></div>
                            <span className="alert-msg" style={{ fontSize: '11px' }}><strong>{a.entity_name}</strong>: {a.message}</span>
                            <span className="alert-ts" style={{ fontSize: '9px' }}>{a.timestamp?.substring(11, 19)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Bandwidth chart */}
            <div className="panel">
              <div className="panel-head">
                <span className="panel-title"><i className="fa-solid fa-signal"></i> Interface Bandwidth — 12h</span>
              </div>
              <div className="panel-body">
                <div className="chart-container" ref={tab === 'apic' ? bwRef : undefined}></div>
              </div>
            </div>

            <div className="row-2-wide" style={{ marginTop: '12px' }}>
              {/* Learned Endpoints */}
              <div>
                <div className="section-divider" style={{ padding: '0 0 6px 0' }}>Learned Endpoints (IP & MAC Mapping)</div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-fingerprint"></i> Active Endpoints ({endpointsCount} total)</span>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      <input 
                        type="text" 
                        placeholder="Search MAC/IP..." 
                        value={endpointSearch} 
                        onChange={(e) => setEndpointSearch(e.target.value)} 
                        style={{ background: 'var(--bg-input)', border: '1px solid var(--border-color)', borderRadius: '3px', color: 'white', padding: '2px 6px', fontSize: '10px', width: '100px' }}
                      />
                      <select 
                        value={endpointEpgFilter} 
                        onChange={(e) => setEndpointEpgFilter(e.target.value)}
                        style={{ background: 'var(--bg-input)', border: '1px solid var(--border-color)', borderRadius: '3px', color: 'white', padding: '2px 4px', fontSize: '10px' }}
                      >
                        <option value="all">All EPGs</option>
                        <option value="Prod-App-EPG">Prod-App</option>
                        <option value="Prod-DB-EPG">Prod-DB</option>
                        <option value="Dev-App-EPG">Dev-App</option>
                        <option value="SharedSvc-DNS-EPG">SharedSvc-DNS</option>
                      </select>
                    </div>
                  </div>
                  <div className="panel-body flush">
                    <div style={{ maxHeight: '250px', overflowY: 'auto' }}>
                      <table className="dtable" style={{ fontSize: '11px' }}>
                        <thead>
                          <tr>
                            <th>MAC Address</th>
                            <th>IP Address</th>
                            <th>EPG</th>
                            <th>Encap</th>
                            <th>Switch Port</th>
                          </tr>
                        </thead>
                        <tbody>
                          {endpoints.length === 0 ? (
                            <tr><td colSpan="5" className="empty-state">No endpoints learned</td></tr>
                          ) : (
                            endpoints
                              .filter(ep => {
                                const matchesSearch = (ep.mac?.toLowerCase().includes(endpointSearch.toLowerCase()) || 
                                                       ep.ip?.includes(endpointSearch));
                                const matchesEpg = (endpointEpgFilter === 'all' || ep.epg === endpointEpgFilter);
                                return matchesSearch && matchesEpg;
                              })
                              .map((ep, i) => (
                                <tr key={i}>
                                  <td className="td-mono td-bold">{ep.mac}</td>
                                  <td className="td-mono">{ep.ip || '0.0.0.0'}</td>
                                  <td><span className="tag blue">{ep.epg}</span></td>
                                  <td className="td-mono" style={{ color: 'var(--text-muted)' }}>{ep.encap || 'vlan-100'}</td>
                                  <td className="td-mono">{ep.node_id || 'leaf-101'}:{ep.interface || 'eth1/1'}</td>
                                </tr>
                              ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>

              {/* Equipment Health */}
              <div>
                <div className="section-divider" style={{ padding: '0 0 6px 0' }}>Fabric Node Hardware Equipment Health</div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-server"></i> PSUs & Fans ({equipmentOk}/{equipmentTotal} Healthy)</span>
                  </div>
                  <div className="panel-body flush" style={{ padding: '12px', maxHeight: '250px', overflowY: 'auto' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {sws.map((sw, i) => {
                        const swEq = equipment.filter(e => e.node_id === sw.id);
                        return (
                          <div key={i} style={{ background: 'var(--bg-card-header)', borderRadius: '4px', padding: '6px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontSize: '11px', fontWeight: 'bold' }}>{sw.name}</span>
                            <div style={{ display: 'flex', gap: '15px' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>PSUs:</span>
                                {swEq.filter(e => e.type === 'psu').map((p, pi) => {
                                  const isPsuOk = p.status === 'ok' || p.status === 'online';
                                  return (
                                    <i key={pi} className={`fa-solid fa-plug-circle-bolt`} style={{ color: isPsuOk ? 'var(--green)' : 'var(--red)', fontSize: '11px', cursor: 'help' }} title={`${p.name}: ${p.status} (${p.model})`}></i>
                                  );
                                })}
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Fans:</span>
                                {swEq.filter(e => e.type === 'fan').map((f, fi) => {
                                  const isFanOk = f.status === 'ok' || f.status === 'online';
                                  return (
                                    <i key={fi} className={`fa-solid fa-fan`} style={{ color: isFanOk ? 'var(--green)' : 'var(--red)', fontSize: '10px', cursor: 'help' }} title={`${f.name}: ${f.status}`}></i>
                                  );
                                })}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="row-2-wide" style={{ marginTop: '12px' }}>
              {/* Traffic Contracts */}
              <div>
                <div className="section-divider" style={{ padding: '0 0 6px 0' }}>Security Traffic Contracts & Access Policies</div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-shield-halved"></i> Tenant Contracts</span>
                  </div>
                  <div className="panel-body flush">
                    <table className="dtable" style={{ fontSize: '11px' }}>
                      <thead>
                        <tr>
                          <th>Contract</th>
                          <th>Tenant</th>
                          <th>Scope</th>
                          <th>Filter Name</th>
                          <th>Protocol</th>
                          <th>Port</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {contracts.length === 0 ? (
                          <tr><td colSpan="7" className="empty-state">No contracts loaded</td></tr>
                        ) : (
                          contracts.map((c, i) => (
                            <tr key={i}>
                              <td className="td-bold">{c.name}</td>
                              <td><span className="tag blue">{c.tenant}</span></td>
                              <td className="td-mono">{c.scope}</td>
                              <td className="td-mono">{c.filter_name || 'Allow-Filter'}</td>
                              <td className="td-mono">{c.protocol || 'tcp'}</td>
                              <td className="td-mono">{c.dst_port || 'Any'}</td>
                              <td><span className="tag green">{c.action || 'permit'}</span></td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* Fabric Health Heatmap */}
              <div>
                <div className="section-divider" style={{ padding: '0 0 6px 0' }}>Fabric Node Health Distribution</div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-fire-burner"></i> Node Heatmap</span>
                  </div>
                  <div className="panel-body flush" style={{ padding: '12px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '8px' }}>
                      {sws.map((sw, i) => {
                        const score = sw.health_score || sw.health || 0;
                        const scoreBg = score >= 90 ? 'rgba(46, 204, 113, 0.2)' : score >= 75 ? 'rgba(241, 196, 15, 0.2)' : 'rgba(231, 76, 60, 0.2)';
                        const scoreBorder = score >= 90 ? 'var(--green)' : score >= 75 ? 'var(--yellow)' : 'var(--red)';
                        return (
                          <div key={i} style={{ border: `1px solid ${scoreBorder}`, background: scoreBg, borderRadius: '4px', padding: '10px 4px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '3px' }}>
                            <span style={{ fontSize: '10px', fontWeight: 'bold' }}>{sw.name}</span>
                            <span style={{ fontSize: '14px', fontWeight: 'bold', color: scoreBorder }}>{score}%</span>
                            <span style={{ fontSize: '8px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>{sw.role}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            </>)}
 
          {/* ═══ FAULT SIMULATOR ═══ */}
          {tab === 'sim' && (<>
            <div className="panel" style={{ marginBottom: 12 }}>
              <div className="panel-head">
                <span className="panel-title"><i className="fa-solid fa-flask-vial"></i> Fault Injection Console</span>
              </div>
              <div className="panel-body">
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 16 }}>
                  Trigger hardware faults or network anomalies. The background scheduler (15s interval) fetches data from mock API simulators and propagates state changes to the dashboard in near-real-time.
                </p>
 
                <div className="section-divider">HPE OneView — Physical Failures</div>
                <div className="sim-grid" style={{ marginBottom: 16 }}>
                  {[
                    { k: 'fan_failure', t: 'Enclosure Fan Outage', d: 'Complete fan assembly failure on Enclosure-01. Causes severe blade heating cascade.' },
                    { k: 'psu_failure', t: 'Server PSU Failure', d: 'Redundant power supply failure on Blade 3, Enclosure-01. Raises critical alert.' },
                    { k: 'storage_failure', t: 'Storage Pool Degraded', d: 'RAID failure on SAN-Prod-Pool-01. Shrinks free capacity.' },
                    { k: 'thermal_throttling', t: 'Thermal Throttle Warning', d: 'CPU temps exceed 85°C on Blade 2, Enclosure-02.' },
                    { k: 'firmware_mismatch', t: 'Firmware Compliance Mismatch', d: 'Marks server profiles as non-compliant with template baselines.' },
                    { k: 'interconnect_uplink_down', t: 'Interconnect Uplink Down', d: 'Severs Port-1 link on Virtual Connect Switch Module 3.' }
                  ].map(s => (
                    <div className="sim-card" key={s.k}>
                      <span className="sim-title">{s.t}</span>
                      <span className="sim-desc">{s.d}</span>
                      <button className={`btn-fault ${sims[s.k] ? 'active' : ''}`} onClick={() => toggleSim(s.k)}>
                        {sims[s.k] ? '✕ Clear' : '⚡ Inject'}
                      </button>
                    </div>
                  ))}
                </div>
 
                <div className="section-divider">Cisco APIC — Network Failures</div>
                <div className="sim-grid">
                  {[
                    { k: 'leaf_down', t: 'Leaf Switch Power Down', d: 'Complete power loss to Leaf-102. Health drops to 0%.' },
                    { k: 'interface_flap', t: 'Interface Link Flapping', d: 'Packet drops and connection flapping on Spine-202 eth1/1.' },
                    { k: 'epg_fault', t: 'Fault F1024 (EPG Drops)', d: 'Logical fault on Tenant Production EPG Prod-DB-EPG.' },
                    { k: 'apic_psu_failure', t: 'Leaf Switch PSU Failure', d: 'Fails redundant PSU-2 module on Leaf-102 switch hardware.' },
                    { k: 'contract_deny_log', t: 'Contract Policy Deny Logs', d: 'Spikes traffic deny log events inside the ACI security filters.' }
                  ].map(s => (
                    <div className="sim-card" key={s.k}>
                      <span className="sim-title">{s.t}</span>
                      <span className="sim-desc">{s.d}</span>
                      <button className={`btn-fault ${sims[s.k] ? 'active' : ''}`} onClick={() => toggleSim(s.k)}>
                        {sims[s.k] ? '✕ Clear' : '⚡ Inject'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>)}

          {/* ═══ AIOPS ASSISTANT (CHAT) ═══ */}
          {tab === 'chat' && (
            <div className="chat-container-layout" style={{
              display: 'grid',
              gridTemplateColumns: '3fr 1.2fr',
              gap: '16px',
              height: 'calc(100vh - 100px)',
              minHeight: 0
            }}>
              {/* Main chat log panel */}
              <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
                <div className="panel-head">
                  <span className="panel-title"><i className="fa-solid fa-comments"></i> AIOps Conversational Terminal</span>
                  <span className="panel-badge" style={{ color: 'var(--green)' }}><i className="fa-solid fa-circle-check"></i> Qwen 8B Online</span>
                </div>
                
                {/* Scrollable messages container */}
                <div className="chat-history-scroll" style={{
                  flexGrow: 1,
                  overflowY: 'auto',
                  padding: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  background: 'var(--bg-surface)'
                }}>
                  {chatHistory.map((msg, idx) => {
                    const { text, chart } = parseChatContent(msg.content);
                    const isUser = msg.role === 'user';
                    return (
                      <div key={idx} style={{
                        alignSelf: isUser ? 'flex-end' : 'flex-start',
                        maxWidth: '80%',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: isUser ? 'flex-end' : 'flex-start'
                      }}>
                        {/* Speaker Label */}
                        <span style={{
                          fontSize: '9px',
                          color: 'var(--text-muted)',
                          marginBottom: '3px',
                          textTransform: 'uppercase',
                          fontWeight: '600'
                        }}>
                          {isUser ? 'Operator' : 'Qwen Assistant'}
                        </span>
                        {/* Bubble */}
                        <div style={{
                          background: isUser ? 'var(--blue)' : 'var(--bg-panel)',
                          border: isUser ? 'none' : '1px solid var(--border-base)',
                          color: isUser ? '#ffffff' : 'var(--text-primary)',
                          borderRadius: '8px',
                          padding: '10px 14px',
                          fontSize: '12.5px',
                          lineHeight: '1.5',
                          wordBreak: 'break-word',
                          boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
                          whiteSpace: 'pre-line'
                        }}>
                          {text}
                          {chart && <ChatChart chart={chart} />}
                        </div>
                      </div>
                    );
                  })}
                  {chatLoading && (
                    <div style={{ alignSelf: 'flex-start', display: 'flex', gap: '6px', alignItems: 'center', color: 'var(--text-secondary)', fontSize: '11px', padding: '4px 8px' }}>
                      <i className="fa-solid fa-spinner fa-spin"></i> Qwen is thinking...
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                {/* Input action bar */}
                <div className="chat-input-bar" style={{
                  padding: '12px',
                  borderTop: '1px solid var(--border-base)',
                  display: 'flex',
                  gap: '10px',
                  background: 'var(--bg-panel)'
                }}>
                  <input 
                    type="text" 
                    placeholder="Ask Qwen to compare telemetry metrics, plot blade CPU utilization, or explain faults..." 
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') sendChatMessage(); }}
                    style={{
                      flexGrow: 1,
                      background: 'var(--bg-input)',
                      border: '1px solid var(--border-base)',
                      borderRadius: '4px',
                      color: 'var(--text-primary)',
                      padding: '8px 12px',
                      fontSize: '12px',
                      outline: 'none'
                    }}
                  />
                  <button 
                    onClick={() => sendChatMessage()} 
                    disabled={chatLoading || !chatInput.trim()}
                    style={{
                      background: 'var(--blue)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      padding: '0 16px',
                      fontSize: '12px',
                      cursor: chatLoading || !chatInput.trim() ? 'not-allowed' : 'pointer',
                      opacity: chatLoading || !chatInput.trim() ? 0.6 : 1,
                      fontWeight: '500'
                    }}
                  >
                    Send
                  </button>
                </div>
              </div>

              {/* Sidebar Quick Prompts Panel */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div className="panel">
                  <div className="panel-head">
                    <span className="panel-title"><i className="fa-solid fa-wand-magic-sparkles"></i> Prompt Deck</span>
                  </div>
                  <div className="panel-body" style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: '600', textTransform: 'uppercase' }}>Visualizations</span>
                    {[
                      { label: "📊 Plot CPU utilization of all blades", prompt: "Create a bar chart comparing the CPU utilization of Blade-01, Blade-02, Blade-03, Blade-04, Blade-05, and Blade-06." },
                      { label: "📈 Show temperature vs power trends", prompt: "Generate a line graph showing server temperature and power draw metrics across Blade-01 to Blade-06." },
                      { label: "📉 Plot storage capacity comparison", prompt: "Plot a bar chart comparing used vs total capacity in TB for SAN-Prod-Pool-01, SAN-Backup-Pool, and SAN-Archive-Pool." },
                      { label: "📊 Switch interface speed statistics", prompt: "Create an area chart comparing the port traffic in Mbps for spine switches Spine-201 and Spine-202." }
                    ].map((p, idx) => (
                      <button 
                        key={idx} 
                        className="btn-ack" 
                        onClick={() => sendChatMessage(p.prompt)}
                        style={{
                          textAlign: 'left',
                          fontSize: '11px',
                          padding: '8px',
                          borderRadius: '4px',
                          display: 'block',
                          width: '100%',
                          border: '1px solid var(--border-base)'
                        }}
                      >
                        {p.label}
                      </button>
                    ))}

                    <div style={{ height: '4px' }}></div>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: '600', textTransform: 'uppercase' }}>Conversational SOPs</span>
                    {[
                      { label: "🔧 Resolve Leaf Switch Offline", prompt: "How do I troubleshoot a Leaf Switch Power Down event in Cisco ACI fabric?" },
                      { label: "🔋 Resolve Server PSU Failure", prompt: "What is the standard procedure to resolve a redundant PSU warning alert on an HPE Blade server?" }
                    ].map((p, idx) => (
                      <button 
                        key={idx} 
                        className="btn-ack" 
                        onClick={() => sendChatMessage(p.prompt)}
                        style={{
                          textAlign: 'left',
                          fontSize: '11px',
                          padding: '8px',
                          borderRadius: '4px',
                          display: 'block',
                          width: '100%',
                          border: '1px solid var(--border-base)'
                        }}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

        </div>
      </div>

      {/* ═══ MODAL ═══ */}
      {modalBlade && (
        <div className="modal-backdrop" onClick={(e) => { if (e.target.className === 'modal-backdrop') setModalBlade(null); }}>
          <div className="modal-box">
            <div className="modal-header">
              <h3>{modalBlade.name}</h3>
              <button className="modal-close-btn" onClick={() => setModalBlade(null)}>✕</button>
            </div>
            <div className="modal-body">
              {[
                ['Model', modalBlade.model],
                ['Serial', modalBlade.serial],
                ['Bay', `Bay ${modalBlade.bay}`],
                ['Status', modalBlade.status],
                ['Temperature', `${modalBlade.temperature || '--'}°C`],
                ['Power Draw', `${modalBlade.power_draw || '--'} W`],
                ['Firmware', modalBlade.firmware || 'iLO 5 v2.78'],
                ['UUID', modalBlade.uuid || 'A1B2C3D4-E5F6-7890'],
              ].map(([k, v], i) => (
                <div className="prop-row" key={i}>
                  <span className="prop-key">{k}</span>
                  <span className="prop-val" style={{
                    color: k === 'Status' ? (v === 'OK' ? 'var(--green)' : v === 'Critical' ? 'var(--red)' : 'var(--yellow)') : undefined
                  }}>{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Stat Card Component ── */
function StatCard({ label, value, unit, tag, tagColor }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-row">
        <span className="stat-value">{value}</span>
        {unit && <span className="stat-unit">{unit}</span>}
      </div>
      {tag && <div className="stat-sub"><span className={`tag ${tagColor || 'green'}`}>{tag}</span></div>}
    </div>
  );
}

/* ── Chatbot Rendering & Charting Helpers ── */
function parseChatContent(content) {
  if (!content) return { text: '', chart: null };

  // 1. Try to find a JSON block enclosed in markdown code blocks (backticks, tildes, double-quotes)
  const delimiters = [
    /```json\s*([\s\S]*?)\s*```/,
    /""`json\s*([\s\S]*?)\s*""/,
    /""json\s*([\s\S]*?)\s*""/,
    /~~~json\s*([\s\S]*?)\s*~~~/,
    /`json\s*([\s\S]*?)\s*`/
  ];

  for (const regex of delimiters) {
    const match = content.match(regex);
    if (match) {
      const rawJson = match[1].trim();
      const parsed = tryParseJson(rawJson);
      if (parsed) {
        const textBefore = content.substring(0, match.index).trim();
        const textAfter = content.substring(match.index + match[0].length).trim();
        const cleanedText = [textBefore, textAfter].filter(Boolean).join('\n\n');
        return { text: cleanedText, chart: parsed };
      }
    }
  }

  // 2. Fallback: Search for the outermost JSON brace pair
  const firstBrace = content.indexOf('{');
  const lastBrace = content.lastIndexOf('}');
  if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
    const candidate = content.substring(firstBrace, lastBrace + 1);
    const parsed = tryParseJson(candidate);
    if (parsed) {
      const textBefore = content.substring(0, firstBrace).trim();
      const textAfter = content.substring(lastBrace + 1).trim();
      // Clean up leftover markers
      const cleanedBefore = textBefore.replace(/```json|""`json|""json|~~~json|`/gi, '').trim();
      const cleanedAfter = textAfter.replace(/```|""|~~~|`/gi, '').trim();
      const cleanedText = [cleanedBefore, cleanedAfter].filter(Boolean).join('\n\n');
      return { text: cleanedText, chart: parsed };
    }
  }

  return { text: content, chart: null };
}

function tryParseJson(str) {
  try {
    let cleanStr = str.trim();
    // Clean up common LLM syntax errors
    cleanStr = cleanStr
      .replace(/""/g, '"') // Remove duplicate double-quotes
      .replace(/,\s*([\]}])/g, '$1'); // Remove trailing commas

    const chartData = JSON.parse(cleanStr);
    if (chartData.chartType && chartData.data && chartData.series) {
      return chartData;
    }
  } catch (e) {
    // Ignore parse errors, let fallbacks run
  }
  return null;
}

function sanitizeAndNormalizeChart(chart) {
  if (!chart || !chart.data || !Array.isArray(chart.data)) {
    return null;
  }

  // 1. Copy data and series to prevent mutations
  let data = chart.data.map(item => ({ ...item }));
  let series = Array.isArray(chart.series) ? chart.series.map(s => ({ ...s })) : [];
  let xAxisKey = chart.xAxisKey || 'name';

  // 2. Convert all string values containing numbers to actual JS numbers
  data.forEach(item => {
    Object.keys(item).forEach(key => {
      if (key === xAxisKey) return;
      let val = item[key];
      if (typeof val === 'string') {
        const cleanStr = val.replace(/,/g, '').trim();
        const match = cleanStr.match(/^[-+]?[0-9]*\.?[0-9]+/);
        if (match) {
          item[key] = Number(match[0]);
        } else {
          item[key] = 0;
        }
      } else if (typeof val === 'number') {
        if (isNaN(val)) {
          item[key] = 0;
        }
      }
    });
  });

  // 3. Detect and fix sparse comparative series (where each entity has its own key with only 1 point)
  if (series.length > 1 && data.length > 1) {
    const counts = series.map(s => {
      return data.filter(d => d[s.key] !== undefined && d[s.key] !== null).length;
    });
    const isSparse = counts.every(count => count === 1);
    if (isSparse) {
      const unifiedKey = 'value';
      let unifiedName = series[0].name || series[0].key;
      unifiedName = unifiedName.replace(/^(Thor-Server|Loki-Server|Blade-\d+|Enclosure-\d+|Switch-\d+)\s*/i, '').trim();
      if (!unifiedName) unifiedName = 'Value';

      data.forEach(item => {
        const found = series.find(s => item[s.key] !== undefined && item[s.key] !== null);
        if (found) {
          item[unifiedKey] = item[found.key];
        }
      });

      series = [{
        key: unifiedKey,
        name: unifiedName,
        color: series[0].color || 'var(--blue)'
      }];
    }
  }

  // 4. Ensure xAxisKey matches a key in data
  if (data.length > 0) {
    const firstItem = data[0];
    if (!(xAxisKey in firstItem)) {
      if ('name' in firstItem) {
        xAxisKey = 'name';
      } else {
        const seriesKeys = new Set(series.map(s => s.key));
        const possibleKeys = Object.keys(firstItem).filter(k => !seriesKeys.has(k));
        if (possibleKeys.length > 0) {
          xAxisKey = possibleKeys[0];
        }
      }
    }
  }

  return {
    ...chart,
    data,
    series,
    xAxisKey
  };
}

const PIE_COLORS = ['#54a3ff', '#ff453a', '#34c759', '#ff9f0a', '#af52de', '#5ac8fa', '#ff2d55', '#4cd964'];

function ChatChart({ chart: rawChart }) {
  const chart = sanitizeAndNormalizeChart(rawChart);
  if (!chart || !chart.data || !chart.series || chart.series.length === 0) return null;

  const type = chart.chartType;
  const isPie = type === 'pie';
  const isRadar = type === 'radar';
  const isScatter = type === 'scatter';

  const ChartComp = type === 'bar' ? BarChart 
                  : type === 'area' ? AreaChart 
                  : LineChart;

  return (
    <div className="chat-chart-card" style={{
      background: 'var(--bg-base)',
      border: '1px solid var(--border-base)',
      borderRadius: '6px',
      padding: '12px 16px 12px 10px',
      marginTop: '12px',
      boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.1)'
    }}>
      <div style={{
        fontSize: '12px',
        fontWeight: '600',
        color: 'var(--text-primary)',
        marginBottom: '10px',
        textAlign: 'center'
      }}>
        {chart.title || 'Telemetry Visualization'}
      </div>
      <div style={{ width: '100%', height: 200, fontSize: '10px' }}>
        <ResponsiveContainer width="100%" height="100%">
          {isPie ? (
            <PieChart margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
              <RechartsTooltip 
                contentStyle={{ 
                  background: 'var(--bg-panel)', 
                  borderColor: 'var(--border-base)', 
                  color: 'var(--text-primary)', 
                  fontSize: '11px',
                  borderRadius: '4px'
                }} 
              />
              <Legend wrapperStyle={{ fontSize: '10px', paddingTop: '5px' }} />
              <Pie
                data={chart.data}
                cx="50%"
                cy="45%"
                labelLine={false}
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                outerRadius={65}
                dataKey={chart.series[0].key}
                nameKey={chart.xAxisKey || 'name'}
              >
                {chart.data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          ) : isRadar ? (
            <RadarChart cx="50%" cy="50%" outerRadius="75%" data={chart.data}>
              <PolarGrid stroke="var(--border-light)" />
              <PolarAngleAxis dataKey={chart.xAxisKey || 'name'} stroke="var(--text-secondary)" style={{ fontSize: '9px' }} />
              <PolarRadiusAxis stroke="var(--text-secondary)" style={{ fontSize: '8px' }} />
              <RechartsTooltip 
                contentStyle={{ 
                  background: 'var(--bg-panel)', 
                  borderColor: 'var(--border-base)', 
                  color: 'var(--text-primary)', 
                  fontSize: '11px',
                  borderRadius: '4px'
                }} 
              />
              <Legend wrapperStyle={{ fontSize: '10px', paddingTop: '5px' }} />
              {chart.series.map((s, idx) => (
                <Radar 
                  key={idx}
                  name={s.name || s.key}
                  dataKey={s.key}
                  stroke={s.color || 'var(--blue)'}
                  fill={s.color || 'var(--blue)'}
                  fillOpacity={0.3}
                />
              ))}
            </RadarChart>
          ) : isScatter ? (
            <ScatterChart margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
              <XAxis type="category" dataKey={chart.xAxisKey || 'name'} stroke="var(--text-secondary)" tickLine={false} />
              <YAxis type="number" stroke="var(--text-secondary)" tickLine={false} />
              <RechartsTooltip 
                cursor={{ strokeDasharray: '3 3' }}
                contentStyle={{ 
                  background: 'var(--bg-panel)', 
                  borderColor: 'var(--border-base)', 
                  color: 'var(--text-primary)', 
                  fontSize: '11px',
                  borderRadius: '4px'
                }} 
              />
              <Legend wrapperStyle={{ fontSize: '10px', paddingTop: '5px' }} />
              {chart.series.map((s, idx) => (
                <Scatter 
                  key={idx}
                  name={s.name || s.key}
                  data={chart.data}
                  fill={s.color || PIE_COLORS[idx % PIE_COLORS.length]}
                />
              ))}
            </ScatterChart>
          ) : (
            <ChartComp data={chart.data} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
              <XAxis dataKey={chart.xAxisKey || 'name'} stroke="var(--text-secondary)" tickLine={false} />
              <YAxis stroke="var(--text-secondary)" tickLine={false} />
              <RechartsTooltip 
                contentStyle={{ 
                  background: 'var(--bg-panel)', 
                  borderColor: 'var(--border-base)', 
                  color: 'var(--text-primary)', 
                  fontSize: '11px',
                  borderRadius: '4px'
                }} 
              />
              <Legend wrapperStyle={{ fontSize: '10px', paddingTop: '5px' }} />
              {chart.series.map((s, idx) => {
                if (type === 'bar') {
                  return <Bar key={idx} dataKey={s.key} name={s.name || s.key} fill={s.color || 'var(--blue)'} radius={[2, 2, 0, 0]} />;
                } else if (type === 'area') {
                  return (
                    <Area 
                      key={idx} 
                      type="monotone" 
                      dataKey={s.key} 
                      name={s.name || s.key} 
                      stroke={s.color || 'var(--blue)'} 
                      fill={s.color || 'var(--blue)'} 
                      fillOpacity={0.15} 
                    />
                  );
                } else {
                  return (
                    <Line 
                      key={idx} 
                      type="monotone" 
                      dataKey={s.key} 
                      name={s.name || s.key} 
                      stroke={s.color || 'var(--blue)'} 
                      strokeWidth={1.5} 
                      dot={{ r: 2 }} 
                      activeDot={{ r: 4 }} 
                    />
                  );
                }
              })}
            </ChartComp>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
