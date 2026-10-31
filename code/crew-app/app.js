// Smart Trash crew prototype. Covers the three user stories:
//   #1 see which bins need me today and why
//   #2 zero taps: the sensor detects emptying; the crew only reports problems
//   #3 stay in control: skip a stop or add a bin
(function () {
  "use strict";

  const DATA = window.SMART_TRASH_DATA;
  const FEEDBACK_KEY = "smarttrash.feedback";

  // Exceptions only. A normal stop needs no tap: the fill drop tells the system it was emptied.
  const PROBLEMS = [
    { id: "not-reachable", label: "Not reachable" },
    { id: "unsafe", label: "Unsafe" },
    { id: "bin-damaged", label: "Bin damaged" },
  ];

  let stops, nearby, map, routeLayer, undoTimer, lastAction;

  const $ = (id) => document.getElementById(id);

  function reset() {
    stops = DATA.stops.map((s) => ({ ...s, status: "todo", result: null }));
    nearby = DATA.nearby.map((b) => ({ ...b }));
  }

  // ---------- helpers ----------

  function fillColor(pct) {
    if (pct == null) return "var(--fault)";
    if (pct >= 100) return "var(--fill-over)";
    if (pct >= 85) return "var(--fill-high)";
    if (pct >= 60) return "var(--fill-mid)";
    return "var(--fill-low)";
  }

  function fillHtml(pct) {
    if (pct == null) return `<span class="badge badge--fixed">fixed schedule</span>`;
    return `<span class="fill"><span class="fill-bar"><i style="width:${pct}%;background:${fillColor(pct)}"></i></span>${pct}%</span>`;
  }

  function whyHtml(why) {
    return `<div class="why">${why.map((w) => `<span>${escapeHtml(w)}</span>`).join("")}</div>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function distanceM(a, b) {
    const R = 6371000, rad = Math.PI / 180;
    const dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function formatDistance(m) {
    return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(1)} km`;
  }

  const nextIndex = () => stops.findIndex((s) => s.status === "todo");

  // Where the crew is now: last finished stop, or the depot at the start.
  function currentPosition() {
    const finished = stops.filter((s) => s.status !== "todo");
    return finished.length ? finished[finished.length - 1] : DATA.tour.depot;
  }

  // Crew reports are stored per bin only: no worker id, no timing per person.
  function saveFeedback(entry) {
    try {
      const all = JSON.parse(localStorage.getItem(FEEDBACK_KEY) || "[]");
      all.push(entry);
      localStorage.setItem(FEEDBACK_KEY, JSON.stringify(all));
    } catch (e) { /* storage unavailable: prototype keeps working */ }
  }

  function removeLastFeedback() {
    try {
      const all = JSON.parse(localStorage.getItem(FEEDBACK_KEY) || "[]");
      all.pop();
      localStorage.setItem(FEEDBACK_KEY, JSON.stringify(all));
    } catch (e) { /* ignore */ }
  }

  // ---------- map ----------

  function initMap() {
    if (!window.L) { $("map").hidden = true; return; }
    map = L.map("map", { zoomControl: false, attributionControl: true });
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap, © CARTO",
    }).addTo(map);
    routeLayer = L.layerGroup().addTo(map);
    const pts = [DATA.tour.depot, ...stops].map((s) => [s.lat, s.lon]);
    map.fitBounds(pts, { padding: [20, 20] });
  }

  function renderMap() {
    if (!map) return;
    routeLayer.clearLayers();
    const next = nextIndex();
    const line = [DATA.tour.depot, ...stops.filter((s) => s.status !== "skipped")].map((s) => [s.lat, s.lon]);
    L.polyline(line, { color: "#14231b", weight: 3, opacity: 0.5, dashArray: "6 6" }).addTo(routeLayer);

    L.marker([DATA.tour.depot.lat, DATA.tour.depot.lon], {
      icon: L.divIcon({ className: "", html: `<div class="marker marker--depot">D</div>`, iconSize: [26, 26] }),
    }).addTo(routeLayer);

    stops.forEach((s, i) => {
      const cls = i === next ? "marker--next" : s.status !== "todo" ? `marker--${s.status}` : "";
      L.marker([s.lat, s.lon], {
        icon: L.divIcon({ className: "", html: `<div class="marker ${cls}">${s.status === "done" ? "✓" : i + 1}</div>`, iconSize: [30, 30] }),
        zIndexOffset: i === next ? 1000 : 0,
      }).on("click", () => openStop(i)).addTo(routeLayer);
    });
  }

  // ---------- tour screen (story #1) ----------

  function render() {
    const total = stops.length;
    const finished = stops.filter((s) => s.status !== "todo").length;
    const next = nextIndex();

    $("data-label").textContent = DATA.dataLabel;
    $("tour-date").textContent = new Date(DATA.tour.date).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
    $("tour-name").textContent = DATA.tour.name;
    $("progress-num").textContent = `${finished}/${total}`;
    $("progress-fill").style.width = `${(finished / total) * 100}%`;

    $("screen-tour").hidden = next === -1;
    $("screen-done").hidden = next !== -1;
    if (next === -1) return renderDone();

    const n = stops[next];
    const from = currentPosition();
    $("next-card").innerHTML = `
      <p class="next-label">Next stop</p>
      <h2>${escapeHtml(n.name)}</h2>
      <div class="row">
        ${fillHtml(n.fill)}
        <span class="stop-meta">${formatDistance(distanceM(from, n))} · ${escapeHtml(n.area)}</span>
      </div>
      ${whyHtml(n.why)}
      <p class="hint">${n.source === "sensor" ? "Just empty it. The sensor checks it off." : "No sensor here: tap when emptied."}</p>
      <div class="actions" style="display:grid;gap:8px;margin-top:10px">
        ${n.source === "sensor"
          ? `<button class="btn btn--demo" type="button" data-sensor="${next}">▶ Demo: sensor sees emptying</button>`
          : `<button class="btn btn--primary" type="button" data-emptied="${next}">✓ Emptied</button>`}
        <a class="btn" href="https://www.google.com/maps/dir/?api=1&destination=${n.lat},${n.lon}" target="_blank" rel="noopener">Navigate</a>
        <button class="btn btn--ghost" type="button" data-open="${next}">Problem?</button>
      </div>`;

    $("stops").innerHTML = stops.map((s, i) => {
      const state = s.status === "done" ? (s.result === "sensor" ? "✓ Sensor" : "✓ Emptied")
        : s.status === "skipped" ? PROBLEMS.find((p) => p.id === s.result).label : i === next ? "Next" : "";
      const tag = s.source === "crew-added" ? `<span class="badge badge--added">added by crew</span>` : "";
      return `<li><button class="stop stop--${i === next ? "next" : s.status}" type="button" data-open="${i}">
          <span class="stop-num">${s.status === "done" ? "✓" : i + 1}</span>
          <span>
            <span class="stop-name">${escapeHtml(s.name)}</span> ${tag}
            ${whyHtml(s.why)}
          </span>
          <span class="stop-state">${fillHtml(s.fill)}<br>${state}</span>
        </button></li>`;
    }).join("");

    renderMap();
  }

  function renderDone() {
    const done = stops.filter((s) => s.status === "done").length;
    const skipped = stops.filter((s) => s.status === "skipped").length;
    const bySensor = stops.filter((s) => s.result === "sensor").length;
    const added = stops.filter((s) => s.source === "crew-added").length;
    $("done-summary").textContent = `${done} emptied · ${bySensor} checked off by sensor, no tap · ${skipped} skipped · ${added} added`;
  }

  // ---------- stop sheet: problems only (stories #2 and #3) ----------

  function openSheet(html) {
    $("sheet").innerHTML = `<div class="sheet-grip"></div>${html}`;
    $("sheet").hidden = false;
    $("sheet-backdrop").hidden = false;
  }

  function closeSheet() {
    $("sheet").hidden = true;
    $("sheet-backdrop").hidden = true;
  }

  function openStop(i) {
    const s = stops[i];
    if (s.status !== "todo") return;
    openSheet(`
      <h2>${escapeHtml(s.name)}</h2>
      <p class="sub">${s.fill == null ? "No valid sensor data · fixed schedule" : `Predicted ${s.fill}%`} · ${escapeHtml(s.binId)}</p>
      ${whyHtml(s.why)}
      ${s.source === "sensor" ? "" : `<div class="actions"><button class="btn btn--primary" type="button" data-emptied="${i}">✓ Emptied</button></div>`}
      <p class="question">Problem? Skip with one tap:</p>
      <div class="choices">
        ${PROBLEMS.map((p) => `<button class="choice choice--wide" type="button" data-problem="${p.id}" data-stop="${i}">${p.label}</button>`).join("")}
      </div>
      <p class="privacy">Reports are about the bin, not about you.</p>
      <div class="actions"><button class="btn btn--ghost" type="button" data-close>Back</button></div>`);
  }

  // In the real system this comes from the backend when the fill level drops; here a demo button triggers it.
  function sensorEmptied(i) {
    const s = stops[i];
    s.status = "done";
    s.result = "sensor";
    showToast(`${s.name} ✓ detected by sensor`);
    render();
  }

  // Bins without valid sensor data (fixed schedule) need one tap.
  function crewEmptied(i) {
    const s = stops[i];
    s.status = "done";
    s.result = "crew";
    saveFeedback({ binId: s.binId, emptied: true, at: new Date().toISOString() });
    closeSheet();
    showToast(`${s.name} ✓ emptied`, () => { s.status = "todo"; s.result = null; removeLastFeedback(); });
    render();
  }

  function reportProblem(i, problem) {
    const s = stops[i];
    s.status = "skipped";
    s.result = problem;
    saveFeedback({ binId: s.binId, problem, at: new Date().toISOString() });
    closeSheet();
    showToast(`${s.name} skipped`, () => { s.status = "todo"; s.result = null; removeLastFeedback(); });
    render();
  }

  // ---------- add a bin (story #3) ----------

  function openAddBin() {
    const from = currentPosition();
    const list = nearby
      .map((b) => ({ ...b, d: distanceM(from, b) }))
      .sort((a, b) => a.d - b.d);
    openSheet(`
      <h2>Add a bin</h2>
      <p class="sub">Saw one that needs emptying? It becomes your next stop.</p>
      <ul class="nearby">
        ${list.map((b) => `
          <li><button type="button" data-add="${b.binId}">
            <span><span class="stop-name">${escapeHtml(b.name)}</span><br><span class="stop-meta">${formatDistance(b.d)} · sensor ${b.fill}%</span></span>
            <span class="badge badge--added">＋ Add</span>
          </button></li>`).join("") || `<li class="stop-meta">No bins nearby.</li>`}
      </ul>
      <div class="actions"><button class="btn btn--ghost" type="button" data-close>Cancel</button></div>`);
  }

  function addBin(binId) {
    const idx = nearby.findIndex((b) => b.binId === binId);
    const bin = nearby.splice(idx, 1)[0];
    const at = nextIndex() === -1 ? stops.length : nextIndex();
    stops.splice(at, 0, { ...bin, source: "crew-added", why: ["added by crew"], status: "todo", result: null });
    saveFeedback({ binId: bin.binId, addedByCrew: true, at: new Date().toISOString() });
    closeSheet();
    showToast(`${bin.name} added as next stop`, () => {
      stops.splice(stops.findIndex((s) => s.binId === binId), 1);
      nearby.push(bin);
      removeLastFeedback();
    });
    render();
  }

  // ---------- toast with undo ----------

  function showToast(text, undo) {
    clearTimeout(undoTimer);
    lastAction = undo || null;
    $("toast-text").textContent = text;
    $("toast-undo").hidden = !undo;
    $("toast").hidden = false;
    undoTimer = setTimeout(() => { $("toast").hidden = true; lastAction = null; }, 5000);
  }

  // ---------- events ----------

  document.addEventListener("click", (e) => {
    const t = e.target.closest("button, [data-close]");
    if (!t) return;
    const d = t.dataset;
    if (d.open !== undefined) openStop(Number(d.open));
    else if (d.sensor !== undefined) sensorEmptied(Number(d.sensor));
    else if (d.emptied !== undefined) crewEmptied(Number(d.emptied));
    else if (d.problem) reportProblem(Number(d.stop), d.problem);
    else if (d.add) addBin(d.add);
    else if (d.close !== undefined) closeSheet();
  });
  $("sheet-backdrop").addEventListener("click", closeSheet);
  $("add-bin-btn").addEventListener("click", openAddBin);
  $("toast-undo").addEventListener("click", () => {
    if (lastAction) lastAction();
    lastAction = null;
    $("toast").hidden = true;
    render();
  });
  $("restart-btn").addEventListener("click", () => { reset(); render(); if (map) map.invalidateSize(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });

  reset();
  initMap();
  render();
})();
