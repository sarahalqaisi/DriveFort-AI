/* ============================================================
   DRIVEFORT AI — Improved Frontend (v3)
   Chart.js Radar + Risk History, icon tabs, clean event log
   ============================================================ */

// ── Utilities ────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const clamp = (n, min, max) => Math.max(min, Math.min(max, Number(n) || 0));
const pretty = (v) => String(v ?? '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
const safeToken = (v, fallback = 'info') => {
  const t = String(v ?? '').trim().replace(/[^a-zA-Z0-9_-]/g, '-');
  return t || fallback;
};
const addClassSafe = (el, token) => { const t = safeToken(token, ''); if (el && t) el.classList.add(t); };

async function api(url, method = 'GET', body = null) {
  const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : null });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.status?.message || data?.message || `Request failed: ${res.status}`);
  return data;
}

function toast(message, type = 'success') {
  const host = $('toastHost'); if (!host) return;
  const el = document.createElement('div');
  el.className = 'toast';
  addClassSafe(el, safeToken(type, 'info'));
  el.textContent = message || 'Action completed';
  host.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(20px)'; setTimeout(() => el.remove(), 240); }, 2600);
}

async function withButton(btn, label, fn) {
  if (!btn) return;
  const old = btn.innerHTML; btn.classList.add('is-busy'); btn.textContent = label;
  try { const out = await fn(); toast('Action completed', 'success'); return out; }
  catch (e) { console.error(e); toast(e.message || 'Action failed', 'error'); }
  finally { btn.classList.remove('is-busy'); btn.innerHTML = old; }
}

function setText(id, val) { const el = $(id); if (el) el.textContent = val; }
function setWidth(id, pct) { const el = $(id); if (el) el.style.width = `${clamp(pct, 0, 100)}%`; }
function riskColor(v) { v = Number(v) || 0; if (v > .72) return '#ef4444'; if (v > .42) return '#f59e0b'; return '#22c55e'; }
function mini(label, value) { return `<div><span>${label}</span><strong>${value}</strong></div>`; }
function hasLiveVehicle(carla) { return !!(carla && carla.connected && carla.actor_found); }
function metricValue(live, value, suffix = '', digits = 0) {
  if (!live) return '—';
  const n = Number(value); if (!Number.isFinite(n)) return '—';
  return `${digits === 0 ? Math.round(n) : n.toFixed(digits)}${suffix}`;
}
function meterValue(live, value, scale = 100) { if (!live) return 0; return (Number(value) || 0) / scale * 100; }

// ── Chart.js Radar ────────────────────────────────────────────
let _radarChart = null;
function initRadarChart() {
  const canvas = $('radarChart'); if (!canvas || _radarChart || typeof window.Chart === 'undefined') return;
  Chart.defaults.color = '#8ea3c5';
  Chart.defaults.font.family = "'Space Grotesk', system-ui, sans-serif";
  _radarChart = new Chart(canvas, {
    type: 'radar',
    data: {
      labels: ['Safety', 'Privacy', 'Availability', 'Physical', 'AI'],
      datasets: [{
        label: 'Risk',
        data: [0.05, 0.02, 0.02, 0.03, 0.04],
        backgroundColor: 'rgba(34,211,238,.18)',
        borderColor: '#22d3ee',
        borderWidth: 2,
        pointBackgroundColor: '#22d3ee',
        pointRadius: 3,
        pointHoverRadius: 5,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      animation: { duration: 300 },
      scales: {
        r: {
          min: 0, max: 1,
          ticks: { stepSize: .25, color: 'rgba(148,163,184,.5)', font: { size: 9 }, backdropColor: 'transparent' },
          grid: { color: 'rgba(148,163,184,.12)' },
          angleLines: { color: 'rgba(148,163,184,.1)' },
          pointLabels: { color: '#8ea3c5', font: { size: 11, weight: '600' } },
        }
      },
      plugins: { legend: { display: false }, tooltip: { enabled: true } }
    }
  });
}

function updateRadarChart(labels, values) {
  initRadarChart();
  if (!_radarChart) return;
  if (labels && labels.length) _radarChart.data.labels = labels;
  if (values && values.length) {
    _radarChart.data.datasets[0].data = values;
    const maxVal = Math.max(...values);
    const col = maxVal > .72 ? '#ef4444' : maxVal > .42 ? '#f59e0b' : '#22d3ee';
    _radarChart.data.datasets[0].borderColor = col;
    _radarChart.data.datasets[0].backgroundColor = col.replace('#', 'rgba(').replace('ef4444', '239,68,68').replace('f59e0b', '245,158,11').replace('22d3ee', '34,211,238') + ',.18)';
  }
  _radarChart.update('none');
}

// ── Risk History Sparkline ────────────────────────────────────
let _histChart = null;
const _riskHistory = Array(30).fill(0.05);

function initHistChart() {
  const canvas = $('riskHistoryChart'); if (!canvas || _histChart || typeof window.Chart === 'undefined') return;
  _histChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: _riskHistory.map((_, i) => i),
      datasets: [{
        data: [..._riskHistory],
        borderColor: '#22d3ee',
        borderWidth: 1.5,
        fill: true,
        backgroundColor: 'rgba(34,211,238,.08)',
        pointRadius: 0,
        tension: 0.3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 200 },
      scales: {
        x: { display: false },
        y: { display: false, min: 0, max: 1 }
      },
      plugins: { legend: { display: false }, tooltip: { enabled: false } }
    }
  });
}

function pushRiskHistory(val) {
  initHistChart();
  _riskHistory.push(Number(val) || 0);
  if (_riskHistory.length > 30) _riskHistory.shift();
  if (!_histChart) return;
  const maxVal = Math.max(..._riskHistory);
  const col = maxVal > .72 ? '#ef4444' : maxVal > .42 ? '#f59e0b' : '#22d3ee';
  _histChart.data.datasets[0].data = [..._riskHistory];
  _histChart.data.datasets[0].borderColor = col;
  _histChart.data.datasets[0].backgroundColor = col.replace('#', 'rgba(').replace('ef4444', '239,68,68').replace('f59e0b', '245,158,11').replace('22d3ee', '34,211,238') + ',.08)';
  _histChart.update('none');
}

// ── Event log with visual timeline ───────────────────────────
function classifyEvent(text) {
  const t = String(text).toLowerCase();
  if (t.includes('attack') || t.includes('critical') || t.includes('error') || t.includes('blocked')) return 'event-danger';
  if (t.includes('warn') || t.includes('alert') || t.includes('suspicious')) return 'event-warn';
  if (t.includes('recover') || t.includes('connect') || t.includes('boot') || t.includes('safe')) return 'event-ok';
  return '';
}

function renderEventLog(events) {
  const el = $('eventLog'); if (!el) return;
  const items = (events || []).slice(-9).reverse();
  el.innerHTML = items.map(x => `<li class="${classifyEvent(x)}">${x}</li>`).join('') || '<li>No events yet.</li>';
}

// ── Intensity display ─────────────────────────────────────────
$('liveAttackIntensity')?.addEventListener('input', function () {
  const disp = $('intensityDisplay');
  if (disp) disp.textContent = Number(this.value).toFixed(2);
});

// ── Damage renderer ───────────────────────────────────────────
function normalizeComponent(c) {
  const text = `${c?.id || ''} ${c?.label || ''}`.toLowerCase();
  if (text.includes('camera') || text.includes('lidar')) return 'part-camera';
  if (text.includes('steer')) return 'part-steering';
  if (text.includes('brake')) return 'part-brake';
  if (text.includes('battery') || text.includes('bms')) return 'part-battery';
  if (text.includes('gateway')) return 'part-gateway';
  if (text.includes('can')) return 'part-can';
  if (text.includes('gps') || text.includes('navigation')) return 'part-gps';
  if (text.includes('hmi') || text.includes('driver')) return 'part-hmi';
  return '';
}

function renderDamage(snapshot) {
  const od = snapshot.owner_diagnostics || {};
  const proto = od.prototype || {};
  const comps = proto.components || [];
  document.querySelectorAll('.part').forEach(p => { p.classList.remove('affected', 'warn', 'recovered'); p.title = p.dataset.part || ''; });
  comps.forEach(c => {
    const cls = normalizeComponent(c); if (!cls) return;
    const el = document.querySelector(`.${cls}`);
    if (el) { const sc = c.status === 'affected' ? 'affected' : (c.severity === 'medium' ? 'warn' : ''); addClassSafe(el, sc); el.title = `${c.label || c.id}: ${c.description || c.status || 'healthy'}`; }
  });
  const affected = comps.filter(c => c.status === 'affected' || ['critical', 'high', 'medium'].includes(c.severity));
  const rows = (affected.length ? affected : comps.slice(0, 4)).map(c =>
    `<div class="damage-row ${c.severity || 'normal'}"><strong>${c.label || c.id}</strong><span>${pretty(c.status || 'healthy')} · ${c.description || 'No abnormal impact detected'}</span></div>`
  ).join('');
  setText('ownerNotice', od.owner_message || (snapshot.attack?.active ? 'Attack detected. Safety diagnostics are active.' : 'Vehicle is operating normally.'));
  setText('severityChip', od.severity || snapshot.risks?.threat_level || 'NORMAL');
  setText('prototypeState', snapshot.attack?.active ? 'Compromised' : 'Healthy');
  setText('ownerDisplayStatus', proto.driver_status || (snapshot.attack?.active ? 'Security Warning' : 'Vehicle Secure'));
  setText('ownerDisplaySub', od.recommended_action || 'Continue monitoring');
  $('damageList').innerHTML = rows || '<div class="damage-row"><strong>No damaged parts</strong><span>All monitored components are nominal.</span></div>';
  $('cabinGrid').innerHTML = [
    mini('Steering', comps.find(c => /steer/i.test(c.id || c.label || ''))?.status || 'healthy'),
    mini('Brakes', comps.find(c => /brake/i.test(c.id || c.label || ''))?.status || 'healthy'),
    mini('Vision', comps.find(c => /camera|lidar/i.test(c.id || c.label || ''))?.status || 'healthy'),
    mini('Battery', comps.find(c => /battery|bms/i.test(c.id || c.label || ''))?.status || 'healthy'),
  ].join('');
  $('cabinScreen').classList.toggle('attack', !!snapshot.attack?.active);
}

// ── Full demo + evidence renderers ────────────────────────────
function renderFullDemo(snapshot) {
  const demo = snapshot.full_demo || {};
  setText('fullDemoStatus', pretty(demo.status || 'not_run'));
  const summary = $('fullDemoSummary');
  if (summary) summary.textContent = demo.owner_message || 'Run the full demo to capture baseline and post-attack evidence.';
  const before = demo.before || {}, after = demo.after || {}, delta = demo.delta || {};
  const rows = [
    ['Speed', before.speed_kmh, after.speed_kmh, delta.speed_kmh, 'km/h'],
    ['Battery', before.battery_soc, after.battery_soc, delta.battery_soc, '%'],
    ['Battery Heat', before.battery_temp_c, after.battery_temp_c, delta.battery_temp_c, '°C'],
    ['Motor Heat', before.motor_temp_c, after.motor_temp_c, delta.motor_temp_c, '°C'],
    ['Lane', before.lane_status, after.lane_status, delta.lane_change, '']
  ];
  const ba = $('beforeAfterMetrics');
  if (ba) ba.innerHTML = rows.map(r => `<div class="ba-row"><span>${r[0]}</span><b>${r[1] ?? '--'}</b><i>→</i><b>${r[2] ?? '--'}</b><em>${r[3] ?? '--'} ${r[4]}</em></div>`).join('');
  const tl = $('fullDemoTimeline');
  if (tl) tl.innerHTML = (demo.timeline || []).map(x => `<li><strong>${x.title || 'Step'}</strong><span>${x.detail || ''}</span></li>`).join('') || '<li><strong>Waiting</strong><span>Press Run Full Demo to build the evidence chain.</span></li>';
}

function renderEvidence(snapshot) {
  const ev = snapshot.evidence_recorder || {};
  const sev = ev.severity_meter || {};
  const score = Number(sev.score || 0);
  setText('evidenceSeverityChip', `${score}% ${sev.level || 'NORMAL'}`);
  setText('severityScore', `${score}%`);
  setText('severityLabel', sev.level || 'NORMAL');
  const ring = $('severityRing'); if (ring) ring.style.setProperty('--sev', `${score}%`);
  const rec = ev.recovery || {};
  setText('recoveryStatus', pretty(rec.status || 'standby'));
  setText('recoveryMessage', rec.message || 'No recovery action recorded yet.');
  const caps = (ev.captures || []).slice(-6).reverse();
  const box = $('evidenceCaptures');
  if (box) {
    box.innerHTML = caps.map(c => {
      const m = c.metrics || {}; const ctrl = c.control || {};
      return `<div class="capture-row"><b>${pretty(c.stage || 'capture')}</b><span>${c.note || 'Evidence captured'}<br>Speed ${m.speed_kmh ?? '--'} km/h · Battery ${m.battery_soc ?? '--'}% · Temp ${m.battery_temp_c ?? '--'}°C</span><em>steer ${Number(ctrl.steer || 0).toFixed(2)} · brake ${Number(ctrl.brake || 0).toFixed(2)}</em></div>`;
    }).join('') || '<div class="capture-row"><b>Waiting</b><span>Run Full Demo or apply an attack.</span><em>--</em></div>';
  }
}

// ── Main render ───────────────────────────────────────────────
function render(snapshot) {
  const v = snapshot.vehicle || {}, r = snapshot.risks || {}, d = snapshot.defense_dashboard || {}, carla = snapshot.carla || {};
  const runtime = snapshot.runtime || {};
  const attack = !!snapshot.attack?.active;
  const liveVehicle = hasLiveVehicle(carla);
  const syntheticMode = !liveVehicle && runtime.mock_actions_enabled === true;
  const displayVehicle = liveVehicle || syntheticMode;
  const carlaState = liveVehicle ? 'connected' : (syntheticMode ? 'partial' : (carla.connected ? 'partial' : 'disconnected'));
  const carlaLabel = liveVehicle ? 'Connected ✓' : (syntheticMode ? 'Optional / Disconnected' : (carla.connected ? 'Connected - No Vehicle' : 'Disconnected'));
  const carlaDetail = liveVehicle
    ? `Vehicle linked: ${carla.vehicle_type || 'vehicle'} #${carla.vehicle_id ?? '--'} · ${carla.live_loop_running ? 'Live loop running' : 'Live loop stopped'}`
    : (syntheticMode
      ? 'DriveFort Synthetic Engine is active. Connect CARLA only for high-fidelity vehicle validation.'
      : (carla.connected
        ? `CARLA server reachable on ${carla.host || 'localhost'}:${carla.port || 2000}, but no ego vehicle is linked. Press Connect + Spawn.`
        : (carla.message || 'Simulator not connected yet. Start CARLA, then press Connect + Spawn.')));

  setText('carlaStatus', carlaLabel);
  setText('carlaConnectionLabel', carlaLabel);
  setText('carlaConnectionDetail', carlaDetail);
  const carlaPill = $('carlaConnectionPill');
  if (carlaPill) { carlaPill.classList.remove('connected', 'partial', 'disconnected'); carlaPill.classList.add(carlaState); }

  const riskOverall = Number(r.overall || 0);
  setText('threatLevelHero', r.threat_level || 'NORMAL');
  if ($('threatLevelHero')) $('threatLevelHero').style.color = riskColor(riskOverall);
  setText('scenarioName', attack ? pretty(snapshot.attack.attack_name) : (liveVehicle ? 'Normal Drive' : (syntheticMode ? 'Synthetic Simulation Ready' : 'Waiting for CARLA')));
  setText('defenseMode', r.defense_mode || 'Defense Normal');
  const lifecycle = snapshot.lifecycle || {};
  setText('systemPhase', lifecycle.phase || 'READY');
  setText('railSystemPhase', lifecycle.phase || 'READY');
  setText('actorBadge', liveVehicle ? 'Vehicle Actor Ready' : (syntheticMode ? 'Synthetic Vehicle Active' : 'Waiting For Vehicle'));
  setText('mapName', liveVehicle ? (carla.map_name || d.map?.label || 'CARLA Map') : (syntheticMode ? (d.map?.label || 'DriveFort Synthetic Map') : 'CARLA not connected'));
  setText('zoneChip', displayVehicle ? pretty(v.zone_type || d.map?.zone || 'Urban') : 'Waiting');

  setText('speedValue', metricValue(displayVehicle, v.speed_kmh));
  setText('batteryValue', metricValue(displayVehicle, v.battery_soc));
  setText('batteryTempValue', metricValue(displayVehicle, v.battery_temp_c));
  setText('motorTempValue', metricValue(displayVehicle, v.motor_temp_c));
  setText('riskValue', displayVehicle ? riskOverall.toFixed(3) : '—');

  setWidth('speedMeter', meterValue(displayVehicle, v.speed_kmh, 180));
  setWidth('batteryMeter', displayVehicle ? (v.battery_soc || 0) : 0);
  setWidth('batteryTempMeter', meterValue(displayVehicle, v.battery_temp_c, 120));
  setWidth('motorTempMeter', meterValue(displayVehicle, v.motor_temp_c, 140));
  setWidth('riskMeter', displayVehicle ? riskOverall * 100 : 0);

  setText('locationName', displayVehicle ? (v.location_label || d.map?.label || (syntheticMode ? 'Synthetic Route' : 'CARLA Route')) : 'Waiting for live CARLA vehicle');
  setText('coordX', displayVehicle ? Number(v.location_x || d.map?.lon || 0).toFixed(4) : '—');
  setText('coordY', displayVehicle ? Number(v.location_y || d.map?.lat || 0).toFixed(4) : '—');
  setText('headingValue', displayVehicle ? `${Math.round(v.heading_deg || 0)}°` : '—');

  $('attackBeam').classList.toggle('active', attack);
  $('mapCar').classList.toggle('attack', attack);
  $('riskRadius').classList.toggle('active', attack);
  const mapX = displayVehicle ? clamp(48 + ((Number(v.location_x) || 0) % 1) * 35, 8, 92) : 50;
  const mapY = displayVehicle ? clamp(50 - ((Number(v.location_y) || 0) % 1) * 35, 8, 92) : 50;
  $('mapCar').style.left = `${mapX}%`; $('mapCar').style.top = `${mapY}%`;
  $('mapCar').style.transform = `translate(-50%,-50%) rotate(${displayVehicle ? Number(v.heading_deg || 25) : 0}deg)`;

  $('controlGrid').innerHTML = displayVehicle ? [
    mini('Autopilot', v.autopilot_enabled ? 'Enabled' : 'Manual'),
    mini('Throttle', `${Math.round((v.throttle || 0) * 100)}%`),
    mini('Brake', `${Math.round((v.brake || 0) * 100)}%`),
    mini('Steering', Number(v.steer || 0).toFixed(2)),
    mini('Obstacle', `${v.obstacle_distance_m || 0} m`),
    mini('Lane', pretty(v.lane_status || 'centered'))
  ].join('') : [mini('Autopilot', '—'), mini('Throttle', '—'), mini('Brake', '—'), mini('Steering', '—'), mini('Obstacle', '—'), mini('Lane', 'Waiting')].join('');

  // Chart.js radar update
  updateRadarChart(d.radar?.labels, d.radar?.values || [r.safety || .05, r.privacy || .02, r.availability || .02, r.cyber_physical || .03, r.ai || .04]);
  pushRiskHistory(riskOverall);

  // Event log with styled timeline
  renderEventLog(snapshot.event_log);

  // Telemetry grid
  const vt = snapshot.vehicle_telemetry || {}, bt = snapshot.battery_twin || {};
  setText('telemetrySourceChip', liveVehicle ? (vt.source || 'CARLA live actor') : (syntheticMode ? 'DriveFort Synthetic Engine' : 'Waiting for CARLA'));
  setText('batteryTwinNote', displayVehicle ? (vt.note || bt.source || 'Battery digital twin monitoring.') : 'No live vehicle telemetry yet. Start CARLA first.');
  const tg = $('vehicleTelemetryGrid');
  if (tg) tg.innerHTML = [
    mini('Speed', metricValue(displayVehicle, v.speed_kmh, ' km/h')),
    mini('Coordinates', displayVehicle ? `${Number(v.location_x || 0).toFixed(4)}, ${Number(v.location_y || 0).toFixed(4)}` : '—'),
    mini('Heading', metricValue(displayVehicle, v.heading_deg, '°')),
    mini('Battery Charge', metricValue(displayVehicle, v.battery_soc, '%')),
    mini('Battery Temp', metricValue(displayVehicle, v.battery_temp_c, '°C')),
    mini('Motor Temp', metricValue(displayVehicle, v.motor_temp_c, '°C')),
    mini('BMS Source', displayVehicle ? (bt.source || 'Digital Twin') : 'Waiting'),
    mini('BMS Mode', displayVehicle ? (bt.tamper_mode || 'none') : '—'),
    mini('Consumption Δ', displayVehicle ? `${bt.last_consumption_delta ?? '--'}%/tick` : '—'),
    mini('Simulation Source', liveVehicle ? 'CARLA Live' : (syntheticMode ? 'Synthetic' : 'Unavailable'))
  ].join('');

  // Attacker console evidence
  const lastApply = carla.last_apply || {};
  setText('attackerConsoleStatus', lastApply.attack_applied ? 'Applied to CARLA' : (syntheticMode ? 'Synthetic Engine Armed' : 'Armed'));
  const ev = $('attackEvidence');
  if (ev) {
    const ctrl = lastApply.applied_control || {};
    const impact = lastApply.impact || carla.impact || {};
    const impactLabel = impact.active ? `${impact.verified ? 'verified collision' : 'impact target spawned'} · ${impact.target || 'target'} · ${impact.severity || 'critical'}` : 'no impact yet';
    const evidenceSource = liveVehicle ? 'CARLA' : (syntheticMode ? 'Synthetic model' : 'Unavailable');
    const evidenceAction = liveVehicle
      ? (lastApply.attack_applied ? 'physical control applied' : 'waiting')
      : (syntheticMode ? 'analytical scenario available' : 'waiting');
    ev.innerHTML = `<strong>${attack ? pretty(snapshot.attack?.attack_name) : 'No active attack'}</strong><span>${evidenceSource}: ${evidenceAction} · ${impactLabel} · steer ${Number(ctrl.steer || 0).toFixed(2)} · throttle ${Number(ctrl.throttle || 0).toFixed(2)} · brake ${Number(ctrl.brake || 0).toFixed(2)}</span><small>${impact.message || lastApply.diagnostic_notice || (syntheticMode ? 'Run a synthetic attack scenario or connect CARLA for physical validation.' : 'Select an attack and press Apply to CARLA.')}</small>`;
  }

  renderDamage(snapshot);
  renderFullDemo(snapshot);
  renderEvidence(snapshot);

  if (attack && window.__lastAttackName !== snapshot.attack?.attack_name) {
    toast(`Attack detected: ${pretty(snapshot.attack?.attack_name)}`, 'error');
    window.__lastAttackName = snapshot.attack?.attack_name;
  }
  if (!attack) window.__lastAttackName = null;
}

async function refresh() { try { render(await api('/api/state')); } catch (e) { toast(e.message, 'error'); } }
function bind(id, label, fn) { const b = $(id); if (b) b.addEventListener('click', () => withButton(b, label, fn)); }

// ── Button bindings ───────────────────────────────────────────
// Manual-CARLA workflow: CARLA is started by the operator before DriveFort AI.
// These controls must never launch a second CarlaUE4 process.
bind('connectCarlaBtn', 'Connecting...', async () => {
  const d = await api('/api/carla/connect', 'POST', { host: 'localhost', port: 2000, spawn_if_missing: false, synchronous: true, fps: 20 });
  render(d.snapshot || d);
  const ok = d?.status?.connected;
  toast(ok ? 'CARLA server connected. Now press Spawn Vehicle.' : (d?.status?.message || 'Could not connect to CARLA on port 2000.'), ok ? 'success' : 'error');
});
bind('spawnCarlaBtn', 'Spawning...', async () => {
  const d = await api('/api/carla/start_full', 'POST');
  render(d.snapshot || d);
  const ok = d?.status?.connected && (d?.status?.actor_found || d?.snapshot?.carla?.actor_found);
  toast(ok ? 'Ego vehicle spawned and normal drive started.' : (d?.status?.message || 'Vehicle spawn failed.'), ok ? 'success' : 'error');
});
bind('normalDriveBtn', 'Starting...', async () => {
  const d = await api('/api/carla/start_full', 'POST');
  render(d.snapshot || d);
  toast(d?.status?.message || 'Normal drive started.', 'success');
});
bind('resetScenarioTopBtn', 'Resetting...', async () => render(await api('/api/reset', 'POST')));
bind('applySelectedAttackTopBtn', 'Applying...', async () => {
  const attack = $('liveAttackSelect')?.value || 'steering_manipulation';
  const intensity = Number($('liveAttackIntensity')?.value || 0.9);
  const d = await api('/api/carla/force_attack', 'POST', { attack, intensity });
  render(d.snapshot || d); toast(d?.blocked ? 'DriveFort AI blocked the attacker command — Safe Mode restored.' : `Attack applied: ${pretty(attack)}`, d?.blocked ? 'success' : 'error');
});
bind('trainBaselineTopBtn', 'Training...', async () => { const d = await api('/api/ai/train_baseline', 'POST', { samples: 24 }); render(d.snapshot || d); toast('AI baseline trained.', 'success'); });
bind('adaptiveRecoveryTopBtn', 'Recovering...', async () => { const d = await api('/api/ai/adaptive_recovery', 'POST'); render(d.snapshot || d); toast('Adaptive recovery executed.', 'success'); });
bind('emergencySafeStopTopBtn', 'Stopping...', async () => { const d = await api('/api/defense/emergency_stop', 'POST'); render(d.snapshot || d); toast('Emergency stop activated.', 'success'); });
bind('applyLiveAttackBtn', 'Applying...', async () => {
  const attack = $('liveAttackSelect')?.value || 'mixed_attack';
  const intensity = Number($('liveAttackIntensity')?.value || 0.9);
  const d = await api('/api/carla/force_attack', 'POST', { attack, intensity });
  render(d.snapshot || d); toast(d?.blocked ? 'DriveFort AI blocked the attacker command — Safe Mode restored.' : `Live attack: ${pretty(attack)}`, d?.blocked ? 'success' : 'error');
});
bind('recoverVehicleBtn', 'Recovering...', async () => { const d = await api('/api/attack/recover', 'POST'); render(d.snapshot || d); toast('Vehicle recovered.', 'success'); });
bind('recoverVehicleBtn2', 'Recovering...', async () => { const d = await api('/api/attack/recover', 'POST'); render(d.snapshot || d); toast('Vehicle recovered.', 'success'); });
bind('carlaTickBtn', 'Ticking...', async () => { const d = await api('/api/carla/tick', 'POST'); render(d.snapshot || d); });
bind('disconnectCarlaBtn', 'Switching...', async () => { const d = await api('/api/carla/disconnect', 'POST'); render(d.snapshot || d); });

$('downloadReport')?.addEventListener('click', async () => {
  const data = await api('/api/report');
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob); const a = document.createElement('a');
  a.href = url; a.download = 'drivefort_ai_incident_report.json'; a.click(); URL.revokeObjectURL(url);
});
$('downloadPdfReport')?.addEventListener('click', () => { window.location.href = '/api/report/pdf'; });
document.addEventListener('click', e => { const b = e.target?.closest?.('button'); if (b) { addClassSafe(b, 'clicked'); setTimeout(() => b.classList.remove('clicked'), 220); } });

// ── Protection Lab ────────────────────────────────────────────
function zgMetric(name, value) { return `<div><span>${name}</span><strong>${value ?? '--'}</strong></div>`; }
function zgPackMetrics(pack) {
  if (!pack || !Object.keys(pack).length) return '<div><span>Status</span><strong>Waiting</strong></div>';
  const ctrl = pack.carla_control || {};
  return [zgMetric('Speed', `${pack.speed_kmh ?? '--'} km/h`), zgMetric('Lane', pretty(pack.lane_status || 'unknown')), zgMetric('Risk', `${pack.risk_score ?? '--'} · ${pack.threat_level || ''}`), zgMetric('Action', pretty(pack.action || 'none')), zgMetric('Control', `S ${Number(ctrl.steer || 0).toFixed(2)} / T ${Number(ctrl.throttle || 0).toFixed(2)} / B ${Number(ctrl.brake || 0).toFixed(2)}`), zgMetric('Damage', (pack.damaged_parts || []).slice(0, 2).join(', ') || 'None')].join('');
}
function renderProtectionLab(snapshot) {
  const p = snapshot.protection_demo || {};
  setText('protectionStatusChip', p.protection_enabled ? 'Protection Active' : 'Protection Standby');
  setText('ownerDefenseChip', p.protection_enabled ? 'Safe Mode Armed' : 'Owner Control');
  setText('protectionVerdict', p.verdict || 'Run both scenarios to show the difference.');
  const un = p.unprotected || {}, pr = p.protected || {};
  const uo = $('unprotectedOutcome'); if (uo) uo.textContent = un.outcome || 'Not run yet.';
  const po = $('protectedOutcome'); if (po) po.textContent = pr.outcome || 'Not run yet.';
  const um = $('unprotectedMetrics'); if (um) um.innerHTML = zgPackMetrics(un.after || {});
  const pm = $('protectedMetrics'); if (pm) pm.innerHTML = zgPackMetrics(pr.after || {});
}
const _origRender0 = render;
render = function (snapshot) { _origRender0(snapshot); renderProtectionLab(snapshot); };
async function zgSelectedAttack() { return $('liveAttackSelect')?.value || 'mixed_attack'; }
bind('activateProtectionBtn', 'Arming...', async () => { const d = await api('/api/protection/activate', 'POST'); render(d.snapshot || d); toast('DriveFort AI protection armed.', 'success'); });
bind('activateProtectionBtn2', 'Arming...', async () => { const d = await api('/api/protection/activate', 'POST'); render(d.snapshot || d); toast('Owner protection + safe mode armed.', 'success'); });
bind('runUnprotectedScenarioBtn', 'Attacking...', async () => { const d = await api('/api/protection/unprotected_scenario', 'POST', { attack: await zgSelectedAttack() }); render(d.snapshot || d); toast('Unprotected scenario complete.', 'error'); });
bind('runProtectedScenarioBtn', 'Testing...', async () => { const d = await api('/api/protection/protected_scenario', 'POST', { attack: await zgSelectedAttack() }); render(d.snapshot || d); toast('Protected scenario complete.', 'success'); });
bind('runProtectedScenarioBtn2', 'Testing...', async () => { const d = await api('/api/protection/protected_scenario', 'POST', { attack: await zgSelectedAttack() }); render(d.snapshot || d); toast('Protected scenario complete.', 'success'); });
bind('runCompareDemoBtn', 'Running comparison...', async () => {
  const attack = await zgSelectedAttack();
  let d = await api('/api/protection/unprotected_scenario', 'POST', { attack }); render(d.snapshot || d);
  d = await api('/api/protection/activate', 'POST'); render(d.snapshot || d);
  d = await api('/api/protection/protected_scenario', 'POST', { attack }); render(d.snapshot || d);
  toast('Full comparison complete.', 'success');
});

// ── AI Security ───────────────────────────────────────────────
function renderAISecurity(snapshot) {
  const ai = snapshot.ai_security || {}, cls = ai.classification || {};
  const score = Number(ai.risk_score || ai.anomaly_score || 0);
  setText('aiThreatChip', ai.threat_class || 'NORMAL');
  setText('aiRiskScore', `${Math.round(score)}%`);
  setWidth('aiRiskMeter', score);
  setText('aiConfidence', `Confidence ${Number(ai.confidence || 0).toFixed(2)}`);
  setText('aiThreatLabel', cls.label || ai.threat_class || 'Normal');
  setText('aiTargetComponent', `Target component: ${cls.target_component || 'none'}`);
  setText('aiExplanation', ai.explanation || 'AI layer is monitoring vehicle behavior.');
  setText('adaptiveRecoveryStatus', ai.adaptive_recovery?.status || 'standby');
  setText('adaptiveRecoveryMessage', ai.adaptive_recovery?.message || `Action: ${ai.adaptive_recovery?.action || 'None'}`);
  const sampleText = ai.sample_count !== undefined ? ` · samples ${ai.sample_count}` : '';
  const validation = ai.validation || {};
  const valText = validation.cases_total ? ` · self-test ${validation.cases_passed}/${validation.cases_total}` : '';
  setText('aiModelStatus', `${ai.model || 'Behavior model'} · ${ai.mode || 'monitoring'}${sampleText}${valText}`);
  const sig = [...(ai.signals || [])];
  if ((ai.contributions || []).length) sig.push(...ai.contributions.slice(0, 3).map(c => `Contribution: ${c.label || c.feature} impact ${c.impact}%`));
  const list = $('aiSignals'); if (list) list.innerHTML = sig.length ? sig.map(x => `<li>${x}</li>`).join('') : '<li>No abnormal signal detected.</li>';
}
const _origRender1 = render;
render = function (snapshot) { _origRender1(snapshot); renderAISecurity(snapshot); };

// Manual sliders
function updateManualLabels() {
  setText('manualSteerVal', Number($('manualSteer')?.value || 0).toFixed(2));
  setText('manualThrottleVal', Number($('manualThrottle')?.value || 0).toFixed(2));
  setText('manualBrakeVal', Number($('manualBrake')?.value || 0).toFixed(2));
}
['manualSteer', 'manualThrottle', 'manualBrake'].forEach(id => $(id)?.addEventListener('input', updateManualLabels));
updateManualLabels();
async function sendManualControl() {
  const payload = { steer: Number($('manualSteer')?.value || 0), throttle: Number($('manualThrottle')?.value || 0), brake: Number($('manualBrake')?.value || 0) };
  const d = await api('/api/attacker/manual_control', 'POST', payload);
  render(d.snapshot || d); toast(d?.blocked ? 'Manual takeover blocked by DriveFort AI — Safe Mode restored.' : 'Attacker manual control sent.', d?.blocked ? 'success' : 'error');
}
bind('sendManualControlBtn', 'Sending...', sendManualControl);
function setManual(steer, throttle, brake) { if ($('manualSteer')) $('manualSteer').value = steer; if ($('manualThrottle')) $('manualThrottle').value = throttle; if ($('manualBrake')) $('manualBrake').value = brake; updateManualLabels(); }
bind('presetSwerveBtn', 'Sending...', async () => { setManual(0.85, 0.25, 0.0); await sendManualControl(); });
bind('presetHardBrakeBtn', 'Sending...', async () => { setManual(0.0, 0.0, 1.0); await sendManualControl(); });
bind('presetThrottleBtn', 'Sending...', async () => { setManual(0.1, 1.0, 0.0); await sendManualControl(); });
bind('presetReleaseBtn', 'Releasing...', async () => { setManual(0.0, 0.0, 0.0); await sendManualControl(); });
bind('adaptiveRecoveryBtn', 'Recovering...', async () => { const d = await api('/api/ai/adaptive_recovery', 'POST'); render(d.snapshot || d); toast('AI adaptive recovery executed.', 'success'); });
bind('trainAiBaselineBtn', 'Training AI...', async () => { const d = await api('/api/ai/train_baseline', 'POST', { samples: 24 }); render(d.snapshot || d); toast('AI baseline trained.', 'success'); });
bind('runAiSelfTestBtn', 'Testing AI...', async () => { const d = await api('/api/ai/self_test', 'POST'); render(d.snapshot || d); toast(d.validation?.message || 'AI self-test completed.', d.ok ? 'success' : 'error'); });

// Battery tamper sliders
function updateBatteryTamperLabels() {
  const td = Number($('batteryTempDelta')?.value || 0);
  const sd = Number($('batterySocDelta')?.value || 0);
  setText('batteryTempDeltaVal', `${td >= 0 ? '+' : ''}${td}°C`);
  setText('batterySocDeltaVal', `${sd >= 0 ? '+' : ''}${sd}%`);
}
['batteryTempDelta', 'batterySocDelta'].forEach(id => $(id)?.addEventListener('input', updateBatteryTamperLabels));
updateBatteryTamperLabels();
bind('sendBatteryTamperBtn', 'Tampering BMS...', async () => {
  const payload = { temp_delta: Number($('batteryTempDelta')?.value || 0), soc_delta: Number($('batterySocDelta')?.value || 0), mode: $('batteryTamperMode')?.value || 'thermal_spike' };
  const d = await api('/api/attacker/battery_control', 'POST', payload);
  render(d.snapshot || d);
  const ev = $('batteryTamperEvidence'); if (ev) ev.innerHTML = `<strong>BMS tamper sent</strong><span>Temp ${payload.temp_delta >= 0 ? '+' : ''}${payload.temp_delta}°C · Charge ${payload.soc_delta >= 0 ? '+' : ''}${payload.soc_delta}% · ${pretty(payload.mode)}</span>`;
  toast('Battery BMS telemetry tampering applied.', 'error');
});

// ── Final Defense Stack ───────────────────────────────────────
function renderFinalDefense(snapshot) {
  const fd = snapshot.final_defense || {}, cv = fd.command_validation || {}, pp = fd.predictive_protection || {}, aw = fd.driver_awareness || {}, bus = fd.secure_bus || {};
  setText('finalStackStatus', fd.sandbox_mode ? 'Sandbox Active' : (fd.secure_comm_enabled ? 'Secure' : 'Open Bus'));
  setText('validationStatus', pretty(cv.status || 'monitoring'));
  setText('validationDecision', cv.last_decision || 'No command checked yet.');
  setText('allowedCount', cv.allowed_count || 0);
  setText('blockedCount', cv.blocked_count || 0);
  setText('predictiveScore', `${pp.score || 0}% ${pp.label || 'LOW'}`);
  setWidth('predictiveMeter', pp.score || 0);
  setText('predictiveRecommendation', pp.recommendation || 'Continue monitoring.');
  setText('secureBusTrust', `${bus.trust ?? 100}% Trust`);
  setText('secureBusStats', `Signed ${bus.signed_commands || 0} · Rejected ${bus.rejected_commands || 0}`);
  setText('driverAwarenessPriority', pretty(aw.priority || 'normal'));
  setText('driverAwarenessMessage', aw.message || 'Vehicle secure. DriveFort AI is monitoring.');
  const list = $('driverAwarenessList'); if (list) list.innerHTML = (aw.instructions || []).map(x => `<li>${x}</li>`).join('') || '<li>Continue monitoring.</li>';
  const cov = $('coverageGrid'); if (cov) cov.innerHTML = (fd.coverage || []).map(c => `<div><strong>${c.layer}</strong><span>${c.status}</span><p>${c.detail}</p></div>`).join('');
  const replay = $('replayStrip'); if (replay) {
    const frames = (fd.attack_replay || []).slice(-8).reverse();
    replay.innerHTML = frames.length ? frames.map(f => `<div class="replay-frame"><b>${pretty(f.stage)}</b><span>${f.note || ''}</span><small>${pretty(f.attack || 'normal')} · ${f.vehicle?.speed_kmh ?? '--'} km/h · risk ${f.risk ?? 0}%</small></div>`).join('') : 'Replay frames will appear here after running attacks or the final showcase.';
  }
}
const _origRender2 = render;
render = function (snapshot) { _origRender2(snapshot); renderFinalDefense(snapshot); };
bind('enableSandboxBtn', 'Enabling...', async () => { const d = await api('/api/defense/sandbox', 'POST', { enabled: true }); render(d.snapshot || d); toast('Attack sandbox enabled.', 'success'); });
bind('disableSandboxBtn', 'Disabling...', async () => { const d = await api('/api/defense/sandbox', 'POST', { enabled: false }); render(d.snapshot || d); toast('Sandbox disabled.', 'warn'); });
bind('toggleSecureCommBtn', 'Toggling...', async () => { const cur = window.__zgSecureEnabled; const d = await api('/api/defense/secure_comm', 'POST', { enabled: !cur }); window.__zgSecureEnabled = !cur; render(d.snapshot || d); toast(`Secure communication ${!cur ? 'enabled' : 'disabled'}.`, !cur ? 'success' : 'warn'); });
bind('emergencySafeStopBtn', 'Stopping...', async () => { const d = await api('/api/defense/emergency_stop', 'POST'); render(d.snapshot || d); toast('Emergency Safe Stop activated.', 'success'); });
bind('runFinalShowcaseBtn', 'Running...', async () => { const attack = await zgSelectedAttack(); const d = await api('/api/defense/final_showcase', 'POST', { attack }); render(d.snapshot || d); toast('Final showcase complete.', 'success'); });
bind('loadReplayBtn', 'Loading...', async () => {
  const d = await api('/api/replay'); render(d.snapshot || {});
  const strip = $('replayStrip'); if (strip) strip.innerHTML = (d.frames || []).slice().reverse().map(f => `<div class="replay-frame"><b>${pretty(f.stage)}</b><span>${f.note || ''}</span><small>${pretty(f.attack || 'normal')} · ${f.vehicle?.speed_kmh ?? '--'} km/h</small></div>`).join('') || 'No replay frames yet.';
  toast('Replay loaded.', 'success');
});

// ── Role-based Tabs ───────────────────────────────────────────
(function initDriveFortAITabs() {
  const tabMeta = {
    driver: { title: 'Driver / Owner View', desc: 'Live CARLA view, EV telemetry, coordinates, driver alerts, prototype impact, and owner safety context.' },
    attacker: { title: 'Attacker Console', desc: 'Simulation-only attacker interface for selecting attacks, steering/brake/throttle takeover, and BMS telemetry tampering.' },
    defense: { title: 'DriveFort AI Defense', desc: 'AI anomaly detection, threat classification, command validation, sandboxing, safe mode, recovery, and protected-vs-unprotected comparison.' },
    evidence: { title: 'Evidence & Replay', desc: 'Executive demo, before/after metrics, incident evidence, risk timeline, attack replay, and PDF/Markdown reporting.' },
    innovation: { title: 'DriveFort AI V3 Innovation Lab', desc: 'Ghost digital twin, time-machine replay, intelligent attack chains, automated recovery, fleet intelligence, V2V sharing, and secure OTA validation.' }
  };
  function assignTabs() {
    const mapping = [
      ['.live-card', 'driver'], ['.map-card', 'driver'], ['.prototype-card', 'driver'], ['.diagnostic-card', 'driver'], ['.vehicle-telemetry-panel', 'driver'],
      ['.attacker-console-panel', 'attacker'],
      ['.protection-lab-panel', 'defense'], ['.owner-console-panel', 'defense'], ['.ai-security-panel', 'defense'], ['.final-defense-panel', 'defense'],
      ['.full-demo-panel', 'evidence'], ['.evidence-panel', 'evidence'],
      ['.innovation-lab-panel', 'innovation']
    ];
    mapping.forEach(([sel, tab]) => document.querySelectorAll(sel).forEach(el => el.dataset.zoneTab = tab));
    const genericCards = [...document.querySelectorAll('.content-grid > article.panel-card.span-4')];
    if (genericCards[0]) genericCards[0].dataset.zoneTab = 'driver';
    if (genericCards[1]) genericCards[1].dataset.zoneTab = 'driver';
    if (genericCards[2]) genericCards[2].dataset.zoneTab = 'driver';
  }
  function ensureIntro() {
    const grid = document.querySelector('.content-grid'); if (!grid || $('tabIntroCard')) return;
    const intro = document.createElement('article'); intro.id = 'tabIntroCard'; intro.className = 'tab-intro-card glass-panel';
    intro.innerHTML = '<h2></h2><p></p>'; grid.prepend(intro);
  }
  function showTab(tab) {
    assignTabs(); ensureIntro();
    document.querySelectorAll('.tab-button').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tab));
    document.querySelectorAll('.content-grid > article').forEach(card => {
      if (card.id === 'tabIntroCard') return;
      card.classList.toggle('zone-tab-hidden', (card.dataset.zoneTab || 'driver') !== tab);
    });
    const meta = tabMeta[tab] || tabMeta.driver;
    const intro = $('tabIntroCard');
    if (intro) { intro.dataset.zoneTab = tab; intro.querySelector('h2').textContent = meta.title; intro.querySelector('p').textContent = meta.desc; }
    localStorage.setItem('drivefort_active_tab', tab);
  }
  window.showDriveFortAITab = showTab;
  document.querySelectorAll('.tab-button').forEach(btn => btn.addEventListener('click', () => showTab(btn.dataset.tab)));
  const hashTab = location.hash === '#innovationLab' ? 'innovation' : null;
  showTab(hashTab || localStorage.getItem('drivefort_active_tab') || 'driver');
})();

// ── Leaflet Map + Vehicle Parts + Driver Mode ─────────────────
(function initPracticalUpgrades() {
  let zgMap = null, zgCarMarker = null, zgRouteLine = null, zgRiskCircle = null;
  let keyboardMode = false;
  const pressed = new Set();
  let lastKeyboardSend = 0;
  const attackToParts = {
    acceleration_injection: ['motor', 'inverter', 'battery', 'can'],
    throttle_injection: ['motor', 'inverter', 'battery', 'can'],
    brake_override: ['brakes', 'can'],
    steering_manipulation: ['steering', 'can'],
    lane_drift_attack: ['steering'],
    sensor_spoofing: ['sensors', 'camera', 'hmi'],
    gps_spoofing: ['gps', 'can'],
    can_bus_injection: ['can', 'inverter', 'motor', 'steering', 'brakes'],
    dos: ['can', 'hmi', 'sensors'],
    pedestrian_detection_attack: ['sensors', 'camera', 'brakes']
  };
  function carlaToLatLng(x, y) { return [31.9539 + (Number(y) || 0) * 0.000018, 35.9106 + (Number(x) || 0) * 0.000018]; }
  function initMap() {
    const el = $('leafletMap'); if (!el) return;
    const surface = el.closest('.map-surface');
    if (surface && !surface.querySelector('.map-placeholder')) {
      const ph = document.createElement('div');
      ph.className = 'map-placeholder';
      ph.innerHTML = '<div><strong>Waiting for live CARLA vehicle</strong><span>The map will appear only after CARLA is connected and an ego vehicle actor is linked. No static fake route is shown.</span></div>';
      surface.appendChild(ph);
    }
    if (typeof L === 'undefined' || zgMap) return;
    zgMap = L.map(el, { zoomControl: false, attributionControl: true, dragging: true, scrollWheelZoom: false }).setView([31.9539, 35.9106], 16);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(zgMap);
    const icon = L.divIcon({ className: 'zg-leaflet-car', iconSize: [26, 26], iconAnchor: [13, 13] });
    zgCarMarker = L.marker([31.9539, 35.9106], { icon }).addTo(zgMap);
    zgRouteLine = L.polyline([[31.9528, 35.9088], [31.9539, 35.9106], [31.9551, 35.9123]], { color: '#22d3ee', weight: 3, opacity: .8 }).addTo(zgMap);
    zgRiskCircle = L.circle([31.9539, 35.9106], { radius: 35, className: 'zg-leaflet-risk', color: '#ef4444', fillColor: '#ef4444', fillOpacity: .1, weight: 2 }).addTo(zgMap);
    setTimeout(() => zgMap.invalidateSize(), 250);
  }
  function updateMap(snapshot) {
    initMap();
    const v = snapshot.vehicle || {}, carla = snapshot.carla || {};
    const live = !!(carla.connected && carla.actor_found);
    const surface = document.querySelector('.real-map-surface');
    if (surface) surface.classList.toggle('waiting', !live);
    if (zgMap) setTimeout(() => zgMap.invalidateSize(false), 80);
    if (!live) return;
    const latlng = carlaToLatLng(v.location_x, v.location_y);
    if (zgCarMarker) zgCarMarker.setLatLng(latlng);
    if (zgRiskCircle) { zgRiskCircle.setLatLng(latlng); zgRiskCircle.setRadius(snapshot.attack?.active ? 70 : 25); }
    if (zgRouteLine) {
      const hx = Number(v.heading_deg || 0) * Math.PI / 180;
      const ahead = carlaToLatLng((Number(v.location_x)||0) + Math.cos(hx) * 45, (Number(v.location_y)||0) + Math.sin(hx) * 45);
      const back = carlaToLatLng((Number(v.location_x)||0) - Math.cos(hx) * 25, (Number(v.location_y)||0) - Math.sin(hx) * 25);
      zgRouteLine.setLatLngs([back, latlng, ahead]);
    }
    zgMap.panTo(latlng, { animate: true, duration: .4 });
  }
  function clearPartHighlights() { document.querySelectorAll('.track-hotspot,.part').forEach(el => el.classList.remove('danger', 'warn', 'recovered', 'affected')); }
  function updateVehicleParts(snapshot) {
    clearPartHighlights();
    const risk = Number(snapshot.ai_security?.risk_score || (snapshot.risks?.overall || 0) * 100 || 0);
    const attackName = String(snapshot.attack?.attack_name || '').toLowerCase().replace(/\s+/g, '_');
    if (!snapshot.attack?.active && risk < 35) return;
    let parts = [];
    Object.entries(attackToParts).forEach(([key, val]) => { if (attackName.includes(key)) parts = val; });
    if (!parts.length && snapshot.ai_security?.classification?.target_component) {
      const tgt = String(snapshot.ai_security.classification.target_component).toLowerCase();
      if (tgt.includes('powertrain')) parts = ['motor', 'inverter', 'battery'];
      else if (tgt.includes('brake')) parts = ['brakes'];
      else if (tgt.includes('steer')) parts = ['steering'];
      else if (tgt.includes('gps')) parts = ['gps'];
      else if (tgt.includes('sensor') || tgt.includes('vision')) parts = ['sensors', 'camera'];
      else if (tgt.includes('can') || tgt.includes('gateway')) parts = ['can'];
    }
    const cls = snapshot.ai_security?.adaptive_recovery?.status === 'active' ? 'recovered' : (risk >= 75 ? 'danger' : 'warn');
    const idMap = { motor: ['track-motor', '.part-motor'], inverter: ['track-inverter', '.part-gateway'], gateway: ['track-gateway', '.part-gateway'], battery: ['track-battery', '.part-battery'], brakes: ['track-brakes', '.part-brake'], steering: ['track-steering', '.part-steering'], sensors: ['track-sensors', '.part-camera'], camera: ['track-camera', '.part-camera'], gps: ['track-gps', '.part-gps'], hmi: ['track-hmi', '.part-hmi'], can: ['track-can', '.part-can'] };
    parts.forEach(p => { (idMap[p] || []).forEach(sel => { if (!sel) return; const el = sel.startsWith('.') ? document.querySelector(sel) : $(sel); if (el) { el.classList.add(cls); if (cls === 'danger') el.classList.add('affected'); } }); });
  }
  function renderDriverMode(snapshot) {
    const mode = snapshot.driver_control?.mode || (snapshot.vehicle?.manual_override ? 'keyboard' : 'autonomous');
    keyboardMode = mode === 'keyboard';
    setText('driverControlChip', keyboardMode ? 'Human Keyboard' : 'Autonomous');
    const help = $('keyboardHelp');
    if (help) { help.classList.toggle('active', keyboardMode); help.textContent = keyboardMode ? 'Keyboard control ACTIVE: W accelerate · S brake · A/D steer · Space brake · R recovery. DriveFort AI safety filter blocks unsafe inputs.' : 'Autonomous mode ACTIVE: CARLA autopilot drives normally. DriveFort AI can override if risk becomes critical.'; }
  }
  async function setDriverMode(mode) { const d = await api('/api/driver/control_mode', 'POST', { mode }); render(d.snapshot || d); toast(mode === 'keyboard' ? 'Human keyboard control enabled.' : 'Autonomous driving enabled.', 'success'); }
  function keyboardControlFromKeys() { return { steer: (pressed.has('a') ? -0.55 : 0) + (pressed.has('d') ? 0.55 : 0), throttle: pressed.has('w') ? 0.55 : 0, brake: (pressed.has('s') || pressed.has(' ')) ? 0.85 : 0 }; }
  async function sendKeyboardControl(force = false) {
    if (!keyboardMode && !force) return;
    const now = Date.now(); if (!force && now - lastKeyboardSend < 120) return; lastKeyboardSend = now;
    try { const d = await api('/api/driver/keyboard_control', 'POST', keyboardControlFromKeys()); render(d.snapshot || d); } catch (e) { }
  }
  const _prev = render;
  render = function (snapshot) { _prev(snapshot); updateMap(snapshot || {}); updateVehicleParts(snapshot || {}); renderDriverMode(snapshot || {}); };
  bind('autonomousModeBtn', 'Switching...', async () => setDriverMode('autonomous'));
  bind('keyboardModeBtn', 'Switching...', async () => setDriverMode('keyboard'));
  bind('keyboardStopBtn', 'Stopping...', async () => { pressed.clear(); await api('/api/driver/keyboard_control', 'POST', { steer: 0, throttle: 0, brake: 1 }); const d = await api('/api/defense/emergency_stop', 'POST'); render(d.snapshot || d); toast('Keyboard safe stop applied.', 'success'); });
  bind('autonomousModeTopBtn', 'Switching...', async () => setDriverMode('autonomous'));
  bind('keyboardModeTopBtn', 'Switching...', async () => setDriverMode('keyboard'));
  document.addEventListener('keydown', async (e) => {
    const k = e.key.toLowerCase();
    if (['w', 'a', 's', 'd', ' '].includes(k)) { e.preventDefault(); pressed.add(k); sendKeyboardControl(); }
    if (k === 'r' && keyboardMode) { e.preventDefault(); const d = await api('/api/ai/adaptive_recovery', 'POST'); render(d.snapshot || d); toast('Keyboard recovery requested.', 'success'); }
  });
  document.addEventListener('keyup', (e) => { const k = e.key.toLowerCase(); if (['w', 'a', 's', 'd', ' '].includes(k)) { pressed.delete(k); sendKeyboardControl(true); } });
  document.addEventListener('DOMContentLoaded', initMap);
})();

// ── Mission Sidebar ───────────────────────────────────────────
(function initMissionSidebar() {
  function setMissionStep(id, state) {
    const el = $(id); if (!el) return;
    el.classList.remove('done', 'current', 'pending', 'danger', 'active'); el.classList.add(state || 'pending');
    const icon = el.querySelector('.step-state');
    if (icon) { icon.classList.remove('done', 'current', 'pending', 'danger'); icon.classList.add(state || 'pending'); icon.textContent = state === 'done' ? '✓' : state === 'current' ? '●' : state === 'danger' ? '!' : '○'; }
  }
  function normalizeRiskLevel(risk, label) {
    const raw = Number(risk || 0);
    // The backend sometimes sends risk as a 0..1 ratio and some UI fields use 0..100 percent.
    // Convert percent-style values before comparing, otherwise 62.3% becomes incorrectly CRITICAL.
    const n = raw > 1 ? raw / 100 : raw;
    const t = String(label || '').toLowerCase();
    if (t.includes('critical')) return 'Critical';
    if (n >= .75) return 'Critical';
    if (t.includes('high')) return 'High';
    if (n >= .50) return 'High';
    if (t.includes('medium') || t.includes('suspicious')) return 'Medium';
    if (n >= .25) return 'Medium';
    return 'Low';
  }
  function detectBaseline(ai) {
    const mode = String(ai?.mode || ai?.model || ai?.status || '').toLowerCase();
    return ((Number(ai?.sample_count || 0) > 0) || mode.includes('baseline') || mode.includes('monitor')) ? 'Trained' : 'Not trained';
  }
  function updateMissionSidebar(snapshot) {
    snapshot = snapshot || {};
    const carla = snapshot.carla || {}, ai = snapshot.ai_security || {}, risks = snapshot.risks || {}, attack = snapshot.attack || {};
    const connected = !!(carla.connected && carla.actor_found), serverOnly = !!(carla.connected && !carla.actor_found);
    const activeAttack = !!attack.active, recovery = ai.adaptive_recovery || {};
    const recoveryActive = ['active', 'completed', 'recovered'].includes(String(recovery.status || '').toLowerCase());
    const rawRisk = Number(ai.risk_score || 0) || (Number(risks.overall || 0) * 100);
    const normalizedRisk = rawRisk > 1 ? rawRisk / 100 : rawRisk;
    const normalLabel = String(ai.classification?.label || risks.threat_level || ai.threat_class || '').toLowerCase();
    const normalScene = !activeAttack && (!normalLabel || normalLabel.includes('normal') || normalLabel === 'none');
    let riskLevel = normalizeRiskLevel(rawRisk, risks.threat_level || ai.threat_class);
    if (normalScene) riskLevel = 'Low';
    const danger = activeAttack || (!normalScene && (riskLevel === 'Critical' || riskLevel === 'High'));
    const baseline = detectBaseline(ai);
    const mode = snapshot.driver_control?.mode || (snapshot.vehicle?.manual_override ? 'keyboard' : 'autonomous');
    const threat = activeAttack ? pretty(attack.attack_name || ai.classification?.label || 'Active Attack') : 'None';
    setText('railBaselineStatus', baseline); setText('railDriveMode', mode === 'keyboard' ? 'Human' : 'Autonomous');
    setText('railRiskLevel', riskLevel); setText('railThreatName', threat);
    const riskEl = $('railRiskLevel'); if (riskEl) { riskEl.className = riskLevel.toLowerCase(); }
    const threatEl = $('railThreatName'); if (threatEl) { threatEl.className = danger ? 'critical' : ''; }
    setMissionStep('flow-setup', connected ? 'done' : 'current');
    setMissionStep('flow-monitor', connected ? 'done' : 'pending');
    setMissionStep('flow-driver', connected ? 'current' : 'pending');
    setMissionStep('flow-attack', activeAttack ? 'danger' : 'pending');
    setMissionStep('flow-ai', danger ? 'danger' : (connected && baseline === 'Trained' ? 'done' : 'pending'));
    setMissionStep('flow-recovery', recoveryActive ? 'done' : (danger ? 'current' : 'pending'));
    setMissionStep('flow-logs', (snapshot.event_log || []).length ? 'done' : (danger ? 'current' : 'pending'));
  }
  const _prev = render;
  render = function (snapshot) { _prev(snapshot); updateMissionSidebar(snapshot || {}); };
})();

// ── Component Details ─────────────────────────────────────────
(function initComponentDetails() {
  const details = {
    motor: { title: 'Electric Motor / Powertrain', structure: ['Battery Pack', 'Inverter', 'Motor Controller', 'Electric Motor', 'Drivetrain'], summary: 'The powertrain converts high-voltage battery energy into mechanical torque. Affected by acceleration and torque-related attacks.', functionText: 'Converts electrical energy into wheel torque.', attacks: 'Acceleration Injection, CAN Bus Injection, DoS.', cyberImpact: 'Unauthorized throttle command can force sudden acceleration.', defense: 'Throttle blocking, torque limitation, emergency braking.' },
    inverter: { title: 'Inverter / PCU', structure: ['Battery DC', 'Inverter', 'Control Logic', 'Motor Torque Request'], summary: 'The inverter translates digital torque requests into electrical drive behavior.', functionText: 'Controls power conversion and motor torque response.', attacks: 'Acceleration Injection, CAN Bus Injection, DoS.', cyberImpact: 'Malicious command injection may create unsafe torque demand.', defense: 'Command firewall, torque validation, throttle cut.' },
    battery: { title: 'High-Voltage Battery Pack', structure: ['Battery Cells', 'BMS', 'HV Bus', 'Inverter', 'Motor'], summary: 'The battery pack stores high-voltage energy for the EV.', functionText: 'Stores energy and supplies high-voltage power to propulsion.', attacks: 'Acceleration Injection, CAN Bus Injection, collision scenarios.', cyberImpact: 'Unsafe propulsion demand can increase high-voltage safety risk.', defense: 'Powertrain isolation, risk reporting, emergency stop.' },
    brakes: { title: 'Brake System', structure: ['Brake Command', 'Brake Controller', 'Brake Actuator', 'Brake Disc', 'Deceleration'], summary: 'The brake system provides emergency stopping. Failure directly increases collision probability.', functionText: 'Reduces vehicle speed and provides emergency stopping.', attacks: 'Brake Override, Pedestrian Detection Attack, CAN Bus Injection.', cyberImpact: 'Suppressed brakes increase stopping distance and collision risk.', defense: 'Forced emergency braking, throttle cut, safe stop mode.' },
    steering: { title: 'Steering System', structure: ['Steering Command', 'Steering ECU', 'Steering Rack', 'Front Wheels', 'Lane Position'], summary: 'The steering subsystem controls lateral movement and lane position.', functionText: 'Controls vehicle direction, lateral stability, and lane keeping.', attacks: 'Steering Manipulation, Lane Drift Attack, CAN Bus Injection.', cyberImpact: 'Abnormal steering command can cause lane departure.', defense: 'Steering stabilization, lane recovery, speed reduction.' },
    sensors: { title: 'Perception Sensors / Camera', structure: ['Camera', 'Perception Model', 'Object Detection', 'Decision Logic', 'Response'], summary: 'Sensors allow the vehicle to understand its environment.', functionText: 'Detects lanes, vehicles, obstacles, and pedestrians.', attacks: 'Sensor Spoofing, Pedestrian Detection Attack.', cyberImpact: 'False perception can make the vehicle ignore a pedestrian.', defense: 'Sensor validation, AI anomaly detection, emergency braking.' },
    gps: { title: 'GPS Antenna / Localization', structure: ['GPS Signal', 'Localization', 'Map Position', 'Path Decision', 'Motion'], summary: 'Localization estimates where the vehicle is. Spoofed GPS can mislead route behavior.', functionText: 'Provides positioning for navigation and route context.', attacks: 'GPS Spoofing, Sensor Spoofing.', cyberImpact: 'False position can cause wrong-route decisions.', defense: 'Cross-check GPS with IMU, heading; reduce GPS trust.' },
    can: { title: 'ECU Gateway / CAN Network', structure: ['Vehicle ECU', 'CAN Message', 'Gateway', 'Actuator Command', 'Response'], summary: 'The CAN/Gateway layer represents internal communication between controllers.', functionText: 'Transfers control messages between vehicle modules.', attacks: 'CAN Bus Injection, DoS, Acceleration Injection, Brake Override.', cyberImpact: 'Injected messages can create throttle/brake conflict.', defense: 'Command firewall, conflict rejection, safe stop mode.' },
    hmi: { title: 'HMI / Driver Display', structure: ['Vehicle State', 'Driver Display', 'Warning', 'Driver Decision', 'Recovery Request'], summary: 'The HMI communicates warnings and system state to the driver.', functionText: 'Displays alerts, vehicle state, and recovery messages.', attacks: 'Sensor Spoofing, GPS Spoofing, DoS.', cyberImpact: 'Misleading info can delay driver response.', defense: 'Clear threat classification, owner alerts, emergency stop.' }
  };
  details.camera = details.sensors; details.gateway = details.can;
  let selectedComponent = null, lastSnapshot = null;
  function normalizeKey(key) {
    key = String(key || '').toLowerCase().trim();
    if (key.includes('brake')) return 'brakes'; if (key.includes('steer')) return 'steering'; if (key.includes('motor') || key.includes('drive')) return 'motor'; if (key.includes('invert')) return 'inverter'; if (key.includes('battery') || key.includes('bms')) return 'battery'; if (key.includes('gps')) return 'gps'; if (key.includes('can')) return 'can'; if (key.includes('gateway') || key.includes('ecu')) return 'gateway'; if (key.includes('hmi') || key.includes('display')) return 'hmi'; if (key.includes('camera') || key.includes('sensor') || key.includes('vision') || key.includes('perception')) return 'sensors'; return key;
  }
  function inferComponentFromEl(el) { if (!el) return ''; if (el.dataset?.component) return el.dataset.component; return normalizeKey(`${el.id || ''} ${el.className || ''} ${el.dataset?.part || ''} ${el.textContent || ''}`); }
  function selectedElementStatus(component) {
    const selectors = { motor: ['#track-motor', '.part-motor'], inverter: ['#track-inverter', '.part-gateway'], gateway: ['#track-gateway', '.part-gateway'], can: ['#track-can', '.part-can'], battery: ['#track-battery', '.part-battery'], brakes: ['#track-brakes', '.part-brake'], steering: ['#track-steering', '.part-steering'], sensors: ['#track-sensors', '.part-camera'], camera: ['#track-sensors', '.part-camera'], gps: ['#track-gps', '.part-gps'], hmi: ['#track-hmi', '.part-hmi'] };
    for (const sel of (selectors[component] || [])) { const el = sel.startsWith('.') ? document.querySelector(sel) : $(sel); if (!el) continue; if (el.classList.contains('recovered')) return 'recovered'; if (el.classList.contains('danger') || el.classList.contains('affected')) return 'critical'; if (el.classList.contains('warn')) return 'warning'; }
    const risk = Number(lastSnapshot?.ai_security?.risk_score || (lastSnapshot?.risks?.overall || 0) * 100 || 0);
    return risk >= 75 ? 'critical' : risk >= 35 ? 'warning' : 'idle';
  }
  function renderComponentDetail(component) {
    component = normalizeKey(component || selectedComponent || ''); const d = details[component]; if (!d) return;
    selectedComponent = component;
    const viewer = $('teslaRender');
    if (viewer) {
      viewer.dataset.focus = component;
      viewer.classList.add('is-focused');
      document.querySelectorAll('.track-hotspot').forEach(h => h.classList.toggle('selected', normalizeKey(h.dataset.component || h.textContent) === component || (component === 'camera' && h.id === 'track-camera') || (component === 'gateway' && h.id === 'track-gateway')));
    }
    const status = selectedElementStatus(component);
    const statusText = { critical: 'Critical', warning: 'Warning', recovered: 'Recovered', idle: 'Normal' }[status] || 'Normal';
    setText('componentDetailTitle', d.title); setText('componentDetailSummary', d.summary); setText('componentFunction', d.functionText); setText('componentAttacks', d.attacks); setText('componentCyberImpact', d.cyberImpact); setText('componentDefense', d.defense);
    const chip = $('componentDetailStatus');
    if (chip) { chip.className = `component-status-chip ${status === 'idle' ? '' : status}`; chip.textContent = statusText; }
    const chain = $('componentStructureChain');
    if (chain) chain.innerHTML = d.structure.map((item, idx) => `${idx ? '<i>→</i>' : ''}<span>${item}</span>`).join('');
  }
  function bindComponentClicks() {
    document.querySelectorAll('.component-clickable, .track-hotspot, .part').forEach(el => {
      if (el.dataset.componentBound === '1') return; el.dataset.componentBound = '1';
      el.addEventListener('click', (e) => { e.preventDefault(); renderComponentDetail(inferComponentFromEl(el)); const panel = $('componentDetailPanel'); if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); });
    });
  }
  const _prev = render;
  render = function (snapshot) { lastSnapshot = snapshot || {}; _prev(snapshot); bindComponentClicks(); if (selectedComponent) renderComponentDetail(selectedComponent); };
  document.addEventListener('DOMContentLoaded', () => { bindComponentClicks(); renderComponentDetail('motor'); });
})();

// ── 2D Cyber-Physical EV Digital Twin ─────────────────────────
(function () {
  const attackComponents = {
    acceleration_injection: ['motor', 'inverter', 'battery', 'can'],
    throttle_injection: ['motor', 'inverter', 'battery', 'can'],
    brake_override: ['brakes', 'can'],
    steering_manipulation: ['steering', 'can'],
    sensor_spoofing: ['sensors', 'camera', 'hmi'],
    gps_spoofing: ['gps', 'gateway', 'can', 'hmi'],
    can_bus_injection: ['can', 'gateway', 'motor', 'brakes', 'steering'],
    denial_of_service: ['gateway', 'can', 'hmi', 'sensors'],
    dos: ['gateway', 'can', 'hmi', 'sensors'],
    lane_drift_attack: ['steering'],
    lane_drift: ['steering'],
    pedestrian_detection_attack: ['sensors', 'camera', 'brakes'],
    pedestrian_detection: ['sensors', 'camera', 'brakes']
  };

  let currentLayer = 'all';

  function normAttackName(v) {
    return String(v || '').toLowerCase().trim().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
  }
  function classifyRecovery(snapshot) {
    const rec = snapshot?.evidence_recorder?.recovery?.status || snapshot?.ai_security?.adaptive_recovery?.status || '';
    const r = String(rec).toLowerCase();
    return r.includes('recover') || r.includes('mitigat') || r.includes('safe');
  }
  function isCyberKey(key) {
    return ['gps','camera','can','gateway','hmi'].includes(String(key || '').toLowerCase());
  }
  function setLayer(layer) {
    currentLayer = layer || 'all';
    const viewer = $('teslaRender');
    if (viewer) viewer.dataset.layer = currentLayer;
    document.querySelectorAll('.ev-view-btn[data-layer]').forEach(btn => btn.classList.toggle('active', btn.dataset.layer === currentLayer));
    const label = $('ev360ViewLabel');
    if (label) {
      const labels = { all: 'Unified X-Ray View', mechanical: 'Mechanical Systems Layer', cyber: 'Cyber Control Layer', attack: 'Attack Path Layer' };
      label.textContent = labels[currentLayer] || 'Unified X-Ray View';
    }
    const mode = $('ev360ModePill');
    if (mode && currentLayer !== 'attack') mode.textContent = currentLayer === 'cyber' ? 'Cyber Overlay' : currentLayer === 'mechanical' ? 'Mechanical Overlay' : 'Unified 2D X-Ray';
  }
  function clearFocus() {
    const viewer = $('teslaRender');
    if (viewer) {
      delete viewer.dataset.focus;
      viewer.classList.remove('is-focused');
    }
    document.querySelectorAll('.track-hotspot.selected').forEach(el => el.classList.remove('selected'));
  }
  function bind2DControls() {
    document.querySelectorAll('.ev-view-btn[data-layer]').forEach(btn => {
      if (btn.dataset.bound2D === '1') return;
      btn.dataset.bound2D = '1';
      btn.addEventListener('click', () => { clearFocus(); setLayer(btn.dataset.layer || 'all'); });
    });
    const resetBtn = $('ev360AutoRotateBtn');
    if (resetBtn && resetBtn.dataset.boundReset2D !== '1') {
      resetBtn.dataset.boundReset2D = '1';
      resetBtn.addEventListener('click', () => { clearFocus(); setLayer('all'); resetBtn.classList.remove('is-active'); });
    }
    const viewer = $('teslaRender');
    if (viewer && viewer.dataset.boundPan2D !== '1') {
      viewer.dataset.boundPan2D = '1';
      viewer.addEventListener('dblclick', () => { clearFocus(); setLayer('all'); });
    }
  }
  function update2DImpact(snapshot) {
    const stage = $('cameraStage'), mode = $('ev360ModePill'), affectedPill = $('ev360AffectedPill'), defensePill = $('ev360DefensePill');
    if (!stage) return;
    const active = !!snapshot?.attack?.active;
    const attackName = normAttackName(snapshot?.attack?.attack_name || '');
    const risk = Number(snapshot?.ai_security?.risk_score || (snapshot?.risks?.overall || 0) * 100 || 0);
    const recovered = classifyRecovery(snapshot);
    let components = attackComponents[attackName] || [];
    if (!components.length) {
      Object.entries(attackComponents).forEach(([key, val]) => { if (attackName.includes(key)) components = val; });
    }
    const viewer = $('teslaRender');
    const frame = $('ev360Frame');
    if (frame) frame.classList.toggle('attack-mode', active && !recovered);
    if (viewer) {
      viewer.classList.toggle('attack-layer-active', active);
      viewer.dataset.attackComponents = components.join(',');
    }
    if (mode) {
      if (active) mode.textContent = currentLayer === 'attack' ? 'Live Attack Path' : 'Attack Impact View';
      else mode.textContent = recovered ? 'Defense View' : (currentLayer === 'cyber' ? 'Cyber Overlay' : currentLayer === 'mechanical' ? 'Mechanical Overlay' : 'Unified 2D X-Ray');
    }
    if (affectedPill) {
      affectedPill.textContent = components.length ? `Affected: ${components.map(c => c[0].toUpperCase() + c.slice(1)).join(', ')}` : 'Affected: none';
      affectedPill.className = active ? (risk >= 75 ? 'critical' : 'warning') : (recovered ? 'recovered' : '');
    }
    if (defensePill) {
      defensePill.textContent = recovered ? 'Defense: recovery active' : (active ? 'Defense: ready to override' : 'Defense: standby');
      defensePill.className = recovered ? 'recovered' : (active && risk >= 75 ? 'critical' : (active ? 'warning' : ''));
    }
  }

  const _prev = render;
  render = function (snapshot) { _prev(snapshot); bind2DControls(); update2DImpact(snapshot || {}); };
  document.addEventListener('DOMContentLoaded', () => { bind2DControls(); setLayer('all'); });
})();

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => { initRadarChart(); initHistChart(); });
refresh();
setInterval(refresh, 1400);

// ── Roadmap Enhancement Dashboard (XAI + Digital Twin + Forensics + Metrics) ──
(function () {
  function ensureRoadmapPanel() {
    let panel = document.getElementById('roadmapEnhancementPanel');
    if (panel) return panel;
    panel = document.createElement('section');
    panel.id = 'roadmapEnhancementPanel';
    panel.className = 'roadmap-enhancement-panel';
    panel.innerHTML = `
      <div class="roadmap-head">
        <div><small>DriveFort AI EV Roadmap</small><h3>XAI · Digital Twin · Forensics · Metrics</h3></div>
        <span id="roadmapIntegrityChip" class="roadmap-chip">Integrity Pending</span>
      </div>
      <div class="roadmap-grid">
        <div class="roadmap-card"><span>XAI Top Factor</span><strong id="roadmapXaiTop">—</strong><p id="roadmapXaiReason">Waiting for telemetry.</p></div>
        <div class="roadmap-card"><span>Digital Twin</span><strong id="roadmapTwinStatus">—</strong><p id="roadmapTwinMsg">Shadow model not evaluated yet.</p></div>
        <div class="roadmap-card"><span>Context Response</span><strong id="roadmapContextMode">—</strong><p id="roadmapContextActions">No action.</p></div>
        <div class="roadmap-card"><span>ECU Consensus</span><strong id="roadmapConsensusDecision">—</strong><p id="roadmapConsensusVotes">Waiting for votes.</p></div>
      </div>
      <div class="roadmap-kpis" id="roadmapKpis"></div>
      <ul class="roadmap-reasons" id="roadmapReasons"></ul>`;
    const anchor = document.querySelector('.ai-security-panel') || document.querySelector('main') || document.body;
    if (anchor.parentNode) anchor.parentNode.insertBefore(panel, anchor.nextSibling); else document.body.appendChild(panel);
    return panel;
  }

  function pct(v) { return `${Math.round(Number(v || 0))}%`; }
  function ms(v) { return `${Number(v || 0).toFixed(1)} ms`; }
  function setRoadText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }

  window.renderRoadmapEnhancements = function (snapshot) {
    ensureRoadmapPanel();
    const xai = snapshot.xai || snapshot.ai_security?.xai || {};
    const twin = snapshot.security_digital_twin || snapshot.defense_dashboard?.digital_twin || {};
    const ctx = snapshot.context_aware_response || {};
    const forensic = snapshot.forensic_audit || {};
    const consensus = snapshot.ecu_consensus || {};
    const perf = snapshot.performance_dashboard || {};
    const k = perf.kpis || {};

    setRoadText('roadmapXaiTop', xai.top_factor || 'Normal operation');
    setRoadText('roadmapXaiReason', xai.explanation || xai.recommendation || 'No explanation available yet.');
    setRoadText('roadmapTwinStatus', twin.status || (twin.mismatch ? 'DIGITAL_TWIN_MISMATCH' : 'SYNCHRONIZED'));
    setRoadText('roadmapTwinMsg', twin.message || `Deviation score: ${twin.deviation_score ?? 0}`);
    setRoadText('roadmapContextMode', String(ctx.mode || 'normal_monitoring').replaceAll('_', ' '));
    setRoadText('roadmapContextActions', (ctx.actions || ['continue_monitoring']).join(' · '));
    setRoadText('roadmapConsensusDecision', consensus.decision || 'ALLOW_COMMAND');
    setRoadText('roadmapConsensusVotes', `${consensus.approved_votes ?? 0}/${consensus.quorum ?? 0} approved · ${consensus.rejected_votes ?? 0} rejected`);

    const chip = document.getElementById('roadmapIntegrityChip');
    if (chip) {
      chip.textContent = forensic.status || 'Integrity Pending';
      chip.classList.toggle('ok', !!forensic.integrity_verified);
      chip.classList.toggle('warn', !forensic.integrity_verified);
    }

    const kpis = document.getElementById('roadmapKpis');
    if (kpis) kpis.innerHTML = [
      ['Detection Rate', pct(k.detection_rate_percent)],
      ['Mitigation Rate', pct(k.mitigation_rate_percent)],
      ['Detection Time', ms(k.avg_detection_time_ms)],
      ['Response Time', ms(k.avg_response_time_ms)],
      ['Incidents', k.incidents_analyzed ?? 0],
      ['Risk', pct(k.current_risk_percent)]
    ].map(([a,b]) => `<div><span>${a}</span><strong>${b}</strong></div>`).join('');

    const reasons = document.getElementById('roadmapReasons');
    if (reasons) {
      const items = (xai.evidence || []).slice(0, 5);
      reasons.innerHTML = items.length ? items.map(e => `<li><b>${e.factor}</b>: ${e.detail} <small>${e.impact}% impact</small></li>`).join('') : '<li>No abnormal XAI evidence detected.</li>';
    }
  };

  const oldRenderRoadmap = window.render;
  if (typeof oldRenderRoadmap === 'function') {
    window.render = function (snapshot) {
      oldRenderRoadmap(snapshot);
      try { window.renderRoadmapEnhancements(snapshot); } catch (e) { console.warn('Roadmap panel render failed', e); }
    };
  }
})();

// ---------------------------------------------------------------------------
// DRIVEFORT DUAL-RUNTIME UI CONTRACT
// ---------------------------------------------------------------------------
// CARLA-only physical controls remain locked without a live actor. Cyberattack,
// digital-twin, defense, recovery, and benchmark workflows remain available
// when DRIVEFORT_ALLOW_MOCK=1 enables the local synthetic engine.
(function(){
  const mockCapableButtonIds = [
    'applySelectedAttackTopBtn','applyLiveAttackBtn','trainBaselineTopBtn',
    'adaptiveRecoveryTopBtn','emergencySafeStopTopBtn','recoverVehicleBtn','recoverVehicleBtn2',
    'runUnprotectedScenarioBtn','runProtectedScenarioBtn','runProtectedScenarioBtn2',
    'runCompareDemoBtn','runFinalShowcaseBtn'
  ];
  const carlaOnlyButtonIds = [
    'normalDriveBtn','carlaTickBtn','sendManualControlBtn','sendBatteryTamperBtn',
    'manualApplyBtn','manualControlBtn'
  ];
  const mockCapableInputs = ['liveAttackSelect','liveAttackIntensity'];
  const carlaOnlyInputs = ['manualSteer','manualThrottle','manualBrake'];

  function liveBound(snapshot){
    const b = snapshot?.carla_binding || {};
    const c = snapshot?.carla || {};
    return !!(b.live || (c.connected && c.actor_found && c.dashboard_bound !== false));
  }

  function syntheticEnabled(snapshot){
    return snapshot?.runtime?.mock_actions_enabled === true;
  }

  function setElementsDisabled(ids, disabled, reason){
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.disabled = !!disabled;
      el.title = disabled ? reason : '';
      el.classList.toggle('disabled-carla-bound', !!disabled);
    });
  }

  const previousRenderStrictCarlaBound = render;
  render = function(snapshot){
    previousRenderStrictCarlaBound(snapshot);
    const bound = liveBound(snapshot);
    const synthetic = !bound && syntheticEnabled(snapshot);
    const carlaReason = snapshot?.carla_binding?.message || snapshot?.carla?.ui_lock_reason || 'Connect CARLA and spawn/link the ego vehicle.';
    const syntheticReason = 'Start DriveFort with DRIVEFORT_ALLOW_MOCK=1, or connect CARLA for live vehicle control.';

    setElementsDisabled(carlaOnlyButtonIds, !bound, carlaReason);
    setElementsDisabled(carlaOnlyInputs, !bound, carlaReason);
    setElementsDisabled(mockCapableButtonIds, !(bound || synthetic), syntheticReason);
    setElementsDisabled(mockCapableInputs, !(bound || synthetic), syntheticReason);

    setText('carlaStatus', bound ? 'CARLA Live Bound ✓' : (synthetic ? 'CARLA Optional' : 'CARLA Required'));
    setText('telemetrySourceChip', bound ? 'CARLA live actor' : (synthetic ? 'DriveFort Synthetic Engine' : 'Locked: no simulation source'));

    // Setup-not-ready is a connection state, not an attack state.
    if (!bound && !snapshot?.attack?.active) {
      setText('railRiskLevel', 'Low');
      setText('railThreatName', 'None');
      const riskEl = document.getElementById('railRiskLevel'); if (riskEl) riskEl.className = 'low';
      const threatEl = document.getElementById('railThreatName'); if (threatEl) threatEl.className = '';
    }

    const evidence = document.getElementById('attackEvidence');
    if (evidence && synthetic && !snapshot?.attack?.active) {
      evidence.innerHTML = '<strong>DriveFort Synthetic Engine Active</strong><span>Attack, Digital Twin, risk, defense, recovery, evidence, and benchmark workflows are available without CARLA.</span><small>Displayed motion and impact values are analytical simulation results; connect CARLA for simulator-specific physical validation.</small>';
    } else if (evidence && !bound && !synthetic) {
      evidence.innerHTML = '<strong>Waiting for a simulation source</strong><span>Start with DRIVEFORT_ALLOW_MOCK=1 for local synthetic scenarios, or connect a real CARLA ego actor.</span><small>No live physical-control claims are produced while both sources are unavailable.</small>';
    }

    const sourceBadge = document.getElementById('carlaConnectionDetail');
    if (sourceBadge && synthetic) {
      sourceBadge.textContent = 'DriveFort Synthetic Engine active · CARLA is optional for high-fidelity validation.';
    } else if (sourceBadge && !bound) {
      sourceBadge.textContent = carlaReason;
    }
  };
})();


// FINAL BASELINE DISPLAY CONTRACT (v2)
// No attack = LOW / None, regardless of any stale demo/percent score supplied
// by legacy panels. Connectivity and training state are separate concerns.
(function(){
  const previousRenderBaselineContract = window.render;
  window.render = function(snapshot){
    previousRenderBaselineContract(snapshot);
    const attack = snapshot && snapshot.attack ? snapshot.attack : {};
    if (!attack.active) {
      const risk = document.getElementById('railRiskLevel');
      const threat = document.getElementById('railThreatName');
      if (risk) { risk.textContent = 'Low'; risk.className = 'low'; }
      if (threat) { threat.textContent = 'None'; threat.className = ''; }
    }
  };
})();


// ---------------------------------------------------------------------------
// DRIVEFORT CONSOLE ACTION STATUS (live-CARLA action transparency)
// ---------------------------------------------------------------------------
(function(){
  function renderDriveFortAIConsole(snapshot){
    const c = snapshot?.drivefort_console || snapshot?.zoneguard_console || {};
    const el = document.getElementById('consoleActionStatus');
    if (!el) return;
    const label = c.last_action || 'Console status';
    const msg = c.message || 'Ready.';
    const synthetic = snapshot?.runtime?.mock_actions_enabled === true;
    const live = c.live_carla ? 'CARLA Live ✓' : (synthetic ? 'Synthetic Mode ✓' : 'CARLA Required');
    el.innerHTML = `<strong>${label} · ${live}</strong><br><span>${msg}</span>`;
    el.classList.toggle('console-error', ['error','blocked'].includes(String(c.status||'').toLowerCase()));
    el.classList.toggle('console-ok', ['active','armed','complete'].includes(String(c.status||'').toLowerCase()));
  }
  const prior = window.render;
  window.render = function(snapshot){ prior(snapshot); try { renderDriveFortAIConsole(snapshot || {}); } catch(e){} };
})();

// ===========================================================================
// DriveFort AI V3 Innovation Lab — modular feature renderer and controls
// ===========================================================================
(function initDriveFortV3InnovationLab(){
  const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  const pct1 = value => `${Number(value || 0).toFixed(1)}%`;

  function setHtml(id, html){ const el = $(id); if (el) el.innerHTML = html; }

  function normalizePath(path){
    if (!Array.isArray(path) || !path.length) return '';
    const xs = path.map(p => Number(p.x) || 0), ys = path.map(p => Number(p.y) || 0);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const dx = Math.max(.000001, maxX - minX), dy = Math.max(.000001, maxY - minY);
    return path.map((p, i) => {
      const x = 35 + ((Number(p.x) - minX) / dx) * 650;
      const y = 215 - ((Number(p.y) - minY) / dy) * 175 + Math.sin(i * .42) * 3;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }

  function renderTwin(twin, envelope){
    const expected = $('v3ExpectedPath'), actual = $('v3ActualPath');
    if (expected) expected.setAttribute('points', normalizePath(twin?.expected?.path || []));
    if (actual) actual.setAttribute('points', normalizePath(twin?.actual?.path || []));
    const grid = $('v3TwinGrid');
    if (grid && !grid.childNodes.length) {
      grid.innerHTML = Array.from({length:9},(_,i)=>`<line x1="${40+i*80}" y1="20" x2="${40+i*80}" y2="230" stroke="rgba(100,160,210,.09)"/><line x1="25" y1="${25+i*25}" x2="695" y2="${25+i*25}" stroke="rgba(100,160,210,.07)"/>`).join('');
    }
    setText('v3TwinDrift', pct1(twin?.deviation_score));
    setText('v3TwinStatus', twin?.status || 'SYNCHRONIZED');
    setText('v3CollisionRisk', `${pct1(twin?.collision_probability)} collision risk`);
    const limits = envelope?.limits || {};
    setText('v3Envelope', `${envelope?.status || 'ENFORCED'} · steer ${Number(limits.steering_min || 0).toFixed(2)} to ${Number(limits.steering_max || 0).toFixed(2)} · max throttle ${Number(limits.max_throttle || 0).toFixed(2)} · minimum brake ${Number(limits.minimum_brake || 0).toFixed(2)}${(envelope?.violations || []).length ? ` · violations: ${envelope.violations.join(', ')}` : ''}`);
  }

  function renderDecision(explainer){
    setText('v3Decision', explainer?.decision || 'Normal Operation');
    setText('v3DecisionConfidence', pct1(explainer?.confidence));
    setText('v3DecisionSummary', explainer?.summary || 'Waiting for telemetry.');
    setHtml('v3DecisionEvidence', (explainer?.evidence || []).slice(0,5).map(e => `<li><b>${esc(e.factor)}</b> · ${esc(e.value)}% — ${esc(e.detail)}</li>`).join('') || '<li>No abnormal evidence.</li>');
  }

  function renderEcuMap(map){
    const nodes = map?.nodes || [];
    setText('v3MinTrust', `${Number(map?.summary?.minimum_trust ?? 100).toFixed(1)}%`);
    setHtml('v3EcuGrid', nodes.map(n => `<div class="v3-ecu ${esc(String(n.status||'healthy').toLowerCase())}"><strong>${esc(n.label)}</strong><span>${Number(n.trust||0).toFixed(1)}% · ${esc(pretty(n.status||'HEALTHY'))}${n.targeted?' · TARGETED':''}</span></div>`).join(''));
  }

  function renderBenchmark(benchmark){
    setText('v3BenchmarkStatus', pretty(benchmark?.status || 'not run'));
    if (benchmark?.status !== 'complete') { setHtml('v3BenchmarkGrid','<p>Run the model to compare both outcomes.</p>'); return; }
    const u = benchmark.unprotected || {}, p = benchmark.protected || {}, imp = benchmark.improvement || {};
    setHtml('v3BenchmarkGrid', `
      <div class="v3-benchmark-case bad"><h4>Without Protection</h4><p>Outcome: ${esc(u.outcome)}</p><p>Deviation: ${esc(u.maximum_lateral_deviation_m)} m</p><p>Collision risk: ${esc(u.collision_probability_percent)}%</p><p>ECU trust loss: ${esc(u.ecu_trust_loss_percent)}%</p></div>
      <div class="v3-benchmark-case good"><h4>DriveFort AI Protected</h4><p>Outcome: ${esc(p.outcome)}</p><p>Detection: ${esc(p.detection_time_ms)} ms</p><p>Deviation: ${esc(p.maximum_lateral_deviation_m)} m</p><p>Risk reduced: ${esc(imp.collision_risk_reduction_percent)} pts</p></div>`);
  }

  function renderPerformance(score){
    setText('v3OverallScore', pct1(score?.overall));
    setText('v3ScoreGrade', `Grade ${score?.grade || '—'}`);
    setText('v3PerformanceGrade', `${pct1(score?.overall)} · ${score?.grade || '—'}`);
    const rows = [['Safety',score?.safety],['Cyber Defense',score?.cyber_defense],['Vehicle Stability',score?.vehicle_stability],['Recovery',score?.recovery_readiness],['ECU Integrity',score?.ecu_integrity]];
    setHtml('v3PerformanceBars', rows.map(([label,value]) => `<div class="v3-bar-row"><span>${esc(label)}</span><div class="v3-bar-track"><i style="width:${clamp(value,0,100)}%"></i></div><b>${Math.round(Number(value||0))}</b></div>`).join(''));
  }

  function renderChain(chain){
    setText('v3ChainStatus', pretty(chain?.status || 'idle'));
    setHtml('v3AttackChain', (chain?.stages || []).map(s => `<li><b>${esc(pretty(s.attack))}</b> · ${Math.round(Number(s.intensity||0)*100)}% · ${esc(pretty(s.status||'pending'))}</li>`).join('') || '<li>No chain configured.</li>');
  }

  function renderPlaybook(playbook){
    setText('v3PlaybookStatus', pretty(playbook?.status || 'standby'));
    setHtml('v3PlaybookSteps', (playbook?.steps || []).map(s => `<li><b>${esc(s.label)}</b> · ${esc(pretty(s.status||'pending'))}</li>`).join('') || '<li>Prepare a recovery playbook.</li>');
  }

  function renderStoryboard(storyboard){
    setHtml('v3Storyboard', (storyboard?.chapters || []).map(ch => `<div class="v3-story"><b>${esc(ch.title)}</b><small>${esc(ch.detail)}</small></div>`).join('') || '<div class="v3-story"><b>Waiting</b><small>No incident story yet.</small></div>');
  }

  function renderScenario(director){
    setText('v3ScenarioStatus', pretty(director?.status || 'ready'));
    setHtml('v3ScenarioSteps', (director?.steps || []).map(s => `<li><b>${esc(pretty(s.name))}</b> · ${esc(pretty(s.status||'pending'))}</li>`).join('') || '<li>Select and start a guided scenario.</li>');
  }

  function renderTimeline(timeMachine){
    setText('v3TimelineCount', timeMachine?.frame_count || 0);
    setHtml('v3Timeline', (timeMachine?.preview || []).slice().reverse().map(f => `<div class="v3-frame ${esc(f.event_type)}"><b>${esc(f.phase)} · ${esc(pretty(f.attack))}</b><span>Threat ${esc(f.threat_score)}% · Twin ${esc(f.twin_deviation)}%</span><small>${esc(f.timestamp)}</small></div>`).join('') || '<div class="v3-frame"><b>Recording</b><span>Timeline frames will appear here.</span></div>');
  }

  function renderGraph(graph){
    setText('v3GraphStatus', pretty(graph?.status || 'standby'));
    const nodes = graph?.nodes || [], edges = graph?.edges || [];
    if (!nodes.length) { setHtml('v3AttackGraph',''); return; }
    const parts = [];
    nodes.forEach((node,i)=>{
      parts.push(`<span class="v3-graph-node ${esc(node.status||'')}">${esc(node.label)}</span>`);
      if (i < nodes.length-1) parts.push('<span class="v3-graph-arrow">→</span>');
    });
    if (edges.some(e=>e.status==='contained')) parts.push('<span class="v3-graph-node">Containment confirmed</span>');
    setHtml('v3AttackGraph', parts.join(''));
  }

  function renderFleet(fleet){
    const sum = fleet?.summary || {};
    setText('v3FleetSummary', `${sum.online || 0} online · ${sum.at_risk || 0} at risk`);
    setHtml('v3FleetGrid', (fleet?.vehicles || []).map(v => `<div class="v3-vehicle ${esc(String(v.status||'').toLowerCase())}"><strong>${esc(v.vehicle_id)} · ${esc(v.model)}</strong><span>${esc(pretty(v.status))} · Risk ${esc(v.risk)}%</span><small>${esc(v.location)} · Policy ${esc(v.policy)}</small></div>`).join(''));
  }

  function renderFeatures(matrix){
    const implemented = (matrix || []).filter(x => x.status === 'implemented').length;
    setText('v3FeatureCount', `${implemented}/${(matrix||[]).length}`);
    setText('v3FeatureStatus', `${implemented}/${(matrix||[]).length} Implemented`);
    setHtml('v3FeatureMatrix', (matrix || []).map(f => `<div class="v3-feature"><i></i><span>${esc(f.name)}</span></div>`).join(''));
  }

  function renderV3(snapshot){
    const lab = snapshot?.innovation_lab; if (!lab) return;
    const fusion = lab.threat_fusion || {};
    setText('v3ThreatFusion', pct1(fusion.overall_score));
    setText('v3ThreatLevel', fusion.level || 'LOW');
    const evidence = lab.evidence_integrity || {};
    setText('v3EvidenceVerified', `${evidence.verified || 0}/${evidence.checked || 0}`);
    setText('v3EvidenceStatus', evidence.status || 'VALID');
    renderTwin(lab.ghost_twin || {}, lab.safety_envelope || {});
    renderDecision(lab.decision_explainer || {});
    renderEcuMap(lab.ecu_integrity || {});
    renderBenchmark(lab.defense_benchmark || {});
    renderPerformance(lab.performance_score || {});
    renderChain(lab.attack_chain || {});
    renderPlaybook(lab.recovery_playbook || {});
    renderStoryboard(lab.incident_storyboard || {});
    renderScenario(lab.scenario_director || {});
    renderTimeline(lab.time_machine || {});
    renderGraph(lab.attack_graph || {});
    renderFleet(lab.fleet || {});
    renderFeatures(lab.feature_matrix || []);
  }

  async function runAction(buttonId, busyLabel, url, body, message){
    const button = $(buttonId);
    return withButton(button, busyLabel, async()=>{
      const data = await api(url,'POST',body || {});
      await refresh();
      if (message) toast(message,'success');
      return data;
    });
  }

  function wireControls(){
    const add = (id, fn) => { const el=$(id); if (el && !el.dataset.v3Bound){ el.dataset.v3Bound='1'; el.addEventListener('click',fn); } };
    add('v3MissionModeBtn',()=>{
      const panel=$('innovationLab'), btn=$('v3MissionModeBtn');
      if (!panel || !btn) return;
      const enabled=panel.classList.toggle('v3-mission-mode');
      btn.textContent=enabled?'Exit Mission View':'Mission Control View';
      localStorage.setItem('drivefort_v3_mission_mode',enabled?'1':'0');
    });
    add('v3RunBenchmarkBtn',()=>runAction('v3RunBenchmarkBtn','Running…','/api/v3/benchmark/run',{attack:$('v3BenchmarkAttack')?.value || 'steering_manipulation',intensity:.92},'Counterfactual benchmark complete.'));
    add('v3BuildChainBtn',()=>runAction('v3BuildChainBtn','Building…','/api/v3/attack-chain/configure',{name:'Coordinated low-and-slow campaign',stages:[{attack:'gps_spoofing',intensity:.28,duration_sec:4},{attack:'sensor_spoofing',intensity:.48,duration_sec:4},{attack:'can_bus_injection',intensity:.76,duration_sec:5}]}));
    add('v3AdvanceChainBtn',()=>runAction('v3AdvanceChainBtn','Advancing…','/api/v3/attack-chain/advance',{}));
    add('v3AdaptiveAttackBtn',()=>runAction('v3AdaptiveAttackBtn','Planning…','/api/v3/adaptive-attacker/run',{apply_to_engine:false},'Adaptive attack plan generated safely.'));
    add('v3StealthAttackBtn',()=>runAction('v3StealthAttackBtn','Starting…','/api/v3/stealth/start',{attack:'gps_spoofing',intensity:.2,apply_to_engine:false},'Stealth attack model started in analytical mode.'));
    add('v3ActivateVirtualEcuBtn',()=>runAction('v3ActivateVirtualEcuBtn','Activating…','/api/v3/virtual-ecu/activate',{ecu_id:$('v3VirtualEcuSelect')?.value || 'steering_ecu'},'Virtual backup ECU activated.'));
    add('v3PreparePlaybookBtn',()=>runAction('v3PreparePlaybookBtn','Preparing…','/api/v3/recovery/playbook/prepare',{attack:$('v3BenchmarkAttack')?.value || 'steering_manipulation'}));
    add('v3AdvancePlaybookBtn',()=>runAction('v3AdvancePlaybookBtn','Advancing…','/api/v3/recovery/playbook/advance',{execute_engine_recovery:false}));
    add('v3StartScenarioBtn',()=>runAction('v3StartScenarioBtn','Starting…','/api/v3/scenario/start',{scenario_id:$('v3ScenarioSelect')?.value || 'gps_spoofing_demo'}));
    add('v3AdvanceScenarioBtn',()=>runAction('v3AdvanceScenarioBtn','Advancing…','/api/v3/scenario/advance',{}));
    add('v3ShareThreatBtn',async()=>{
      const d=await runAction('v3ShareThreatBtn','Sharing…','/api/v3/v2v/share',{},'Threat intelligence shared with the connected fleet.');
      setText('v3FleetActionResult',d?.event?`Shared ${d.event.attack} with ${d.recipients} vehicles.`:'V2V sharing complete.');
    });
    add('v3VerifyOtaBtn',async()=>{
      const packageName='drivefort-policy-update.bin', version='3.0.1', payload='drivefort-demo-update';
      // The API intentionally rejects unsigned packages. It returns the derived hash
      // and optionally a demo signature so the validation workflow can be shown.
      const first=await api('/api/v3/ota/verify','POST',{package_name:packageName,version,payload,include_demo_signature:true});
      if(!first.ota.expected_demo_signature){
        setText('v3FleetActionResult','OTA signing demo is disabled. Configure DRIVEFORT_OTA_SECRET and enable controlled demo signing.');
        return;
      }
      const d=await api('/api/v3/ota/verify','POST',{package_name:packageName,version,payload,sha256:first.ota.actual_sha256,signature:first.ota.expected_demo_signature});
      setText('v3FleetActionResult',d.ota.accepted?`OTA ${d.ota.version} verified and approved for canary deployment.`:'OTA package rejected.');
      await refresh();
    });
    add('v3CopilotAskBtn',async()=>{
      const btn=$('v3CopilotAskBtn');
      await withButton(btn,'Asking…',async()=>{
        const d=await api('/api/v3/copilot/query','POST',{question:$('v3CopilotQuestion')?.value || ''});
        setText('v3CopilotAnswer',d.answer || 'No answer returned.');
      });
    });
  }

  wireControls();
  if (localStorage.getItem('drivefort_v3_mission_mode') === '1') { const panel=$('innovationLab'), btn=$('v3MissionModeBtn'); if(panel) panel.classList.add('v3-mission-mode'); if(btn) btn.textContent='Exit Mission View'; }
  const previousRenderV3 = window.render;
  window.render = function(snapshot){ previousRenderV3(snapshot); try{ renderV3(snapshot); }catch(error){ console.warn('V3 Innovation Lab render failed',error); } };
})();
