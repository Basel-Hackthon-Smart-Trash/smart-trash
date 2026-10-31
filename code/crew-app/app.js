// Smart Trash crew prototype. Covers the crew user stories:
//   #1 see which bins need me today and why
//   #2 zero taps: the sensor detects emptying; the crew only reports problems
//   #3 stay in control: skip a stop or add a bin
//   #12 menu: report, problems, legend, language, sign in / out
(function () {
  "use strict";

  const DATA = window.SMART_TRASH_DATA;
  const I18N = window.SMART_TRASH_I18N;
  const FEEDBACK_KEY = "smarttrash.feedback";
  const SESSION_KEY = "smarttrash.session";

  // Exceptions only. A normal stop needs no tap: the fill drop tells the system it was emptied.
  const PROBLEMS = [
    { id: "not-reachable", key: "notReachable" },
    { id: "unsafe", key: "unsafe" },
    { id: "bin-damaged", key: "binDamaged" },
  ];

  // Demo pace of the simulated sensor feed: one fill-drop event every few seconds.
  const SENSOR_TICK_MS = 1500;

  let stops, nearby, map, routeLayer, undoTimer, lastAction, started, sensorTimer;
  let lastSync = new Date(), pending = 0;  // reports stay on the phone while offline
  const session = loadSession();        // { team, lang }: a team, never a person
  let loginTeam = session.team || DATA.teams[0];

  const $ = (id) => document.getElementById(id);

  function reset() {
    started = false;
    clearInterval(sensorTimer);
    stops = DATA.stops.map((s) => ({ ...s, status: "todo", result: null }));
    nearby = DATA.nearby.map((b) => ({ ...b }));
  }

  // ---------- language ----------

  function t(key, vars) {
    const text = (I18N[session.lang] || I18N.en)[key] ?? I18N.en[key] ?? key;
    return vars ? text.replace(/\{(\w+)\}/g, (_, k) => vars[k]) : text;
  }

  // "why" keywords come from the data in English; translate the ones we know.
  function whyText(w) {
    const full = /^full ~(.+)$/.exec(w);
    if (full) return t("full", { t: full[1] });
    return (I18N[session.lang] || I18N.en)[w] || w;
  }

  const problemLabel = (id) => t(PROBLEMS.find((p) => p.id === id).key);
  const locale = () => (I18N.languages.find((l) => l.id === session.lang) || I18N.languages.find((l) => l.id === "en")).locale;

  function langButtons() {
    return I18N.languages.map((l) =>
      `<button class="lang ${l.id === session.lang ? "lang--on" : ""}" type="button" data-lang="${l.id}">${l.label}</button>`).join("");
  }

  function setLang(id) {
    session.lang = id;
    saveSession();
    if (!$("sheet").hidden) openMenu();
    render();
  }

  // ---------- session (per-device convenience only) ----------

  function loadSession() {
    try {
      const s = JSON.parse(localStorage.getItem(SESSION_KEY) || "{}");
      return { team: s.team || null, lang: "en" }; // every launch starts in English
    } catch (e) { return { team: null, lang: "en" }; }
  }

  function saveSession() {
    try { localStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch (e) { /* ignore */ }
  }

  function login() {
    session.team = loginTeam;
    saveSession();
    reset();
    render();
  }

  function logout() {
    session.team = null;
    saveSession();
    closeSheet();
    reset();
    render();
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
    if (pct == null) return `<span class="badge badge--fixed">${t("fixedSchedule")}</span>`;
    return `<span class="fill"><span class="fill-bar"><i style="width:${pct}%;background:${fillColor(pct)}"></i></span>${pct}%</span>`;
  }

  function whyHtml(why) {
    return `<div class="why">${why.map((w) => `<span>${escapeHtml(whyText(w))}</span>`).join("")}</div>`;
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

  // Route progress by distance: depot → stops in order; skipped stops drop out of the route.
  function routeProgress() {
    let prev = DATA.tour.depot, total = 0, done = 0;
    stops.forEach((s) => {
      if (s.status === "skipped") return;
      const leg = distanceM(prev, s);
      total += leg;
      if (s.status !== "todo") done += leg;
      prev = s;
    });
    return { total, done };
  }

  const nextIndex = () => stops.findIndex((s) => s.status === "todo");

  // Where the crew is now: last finished stop, or the depot at the start.
  function currentPosition() {
    const finished = stops.filter((s) => s.status !== "todo");
    return finished.length ? finished[finished.length - 1] : DATA.tour.depot;
  }

  // Crew reports are stored per bin only: no worker id, no timing per person.
  function saveFeedback(entry) {
    if (navigator.onLine) lastSync = new Date();
    else pending++;
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

  // Created on first render of the tour screen: Leaflet needs a visible container.
  function initMap() {
    if (!window.L) { $("map").hidden = true; return; }
    map = L.map("map", { zoomControl: false, attributionControl: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors",
    }).addTo(map);
    routeLayer = L.layerGroup().addTo(map);
    const pts = [DATA.tour.depot, ...stops].map((s) => [s.lat, s.lon]);
    map.fitBounds(pts, { padding: [20, 20] });
  }

  function renderMap() {
    if (!map) initMap();
    if (!map) return;
    map.invalidateSize();
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

  // ---------- screens ----------

  function renderStatic() {
    document.documentElement.lang = session.lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-label]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nLabel)); });
  }

  function render() {
    renderStatic();
    const signedIn = !!session.team;
    $("topbar-right").hidden = !signedIn;
    $("screen-login").hidden = signedIn;
    if (!signedIn) {
      $("status").hidden = true;
      $("screen-tour").hidden = true;
      $("screen-done").hidden = true;
      return renderLogin();
    }
    renderTour();
  }

  function renderLogin() {
    $("team-list").innerHTML = DATA.teams.map((team) =>
      `<button class="team ${team === loginTeam ? "team--on" : ""}" type="button" data-team="${escapeHtml(team)}">${escapeHtml(team)}</button>`).join("");
    $("login-langs").innerHTML = langButtons();
  }

  // Tour screen (story #1)
  function renderTour() {
    const total = stops.length;
    const finished = stops.filter((s) => s.status !== "todo").length;
    const next = nextIndex();

    $("data-label").textContent = DATA.dataLabel;
    $("tour-date").textContent = new Date(DATA.tour.date).toLocaleDateString(locale(), { weekday: "long", day: "numeric", month: "long" });
    $("tour-name").textContent = DATA.tour.name;
    $("crew-name").textContent = session.team;
    const route = routeProgress();
    $("status").hidden = !started;
    $("status-stops").textContent = `${finished}/${total}`;
    $("status-left").textContent = t("left", { d: formatDistance(route.total - route.done) });
    // One segment per bin, coloured by its status
    $("segments").innerHTML = stops.map((s, i) =>
      `<i class="seg seg--${i === next ? "next" : s.status}"></i>`).join("");

    $("screen-tour").hidden = next === -1;
    $("screen-done").hidden = next !== -1;
    if (next === -1) return renderDone();

    if (!started) {
      const bySensor = stops.filter((s) => s.source === "sensor").length;
      $("next-card").innerHTML = `
        <p class="next-label">${t("today")}</p>
        <h2>${t("stopsN", { n: total })}</h2>
        <p class="hint">${t("startHint", { s: bySensor, f: total - bySensor })}</p>
        <div class="actions" style="display:grid;margin-top:14px">
          <button class="btn btn--primary btn--start" type="button" data-start>${t("start")}</button>
        </div>`;
    } else {
      const n = stops[next];
      const from = currentPosition();
      $("next-card").innerHTML = `
        <p class="next-label">${t("nextStop")} <span class="live">${t("live")}</span></p>
        <h2>${escapeHtml(n.name)}</h2>
        <div class="row">
          ${fillHtml(n.fill)}
          <span class="stop-meta">${formatDistance(distanceM(from, n))} · ${escapeHtml(n.area)}</span>
        </div>
        ${whyHtml(n.why)}
        <p class="hint">${n.source === "sensor" ? t("hintSensor") : t("hintFixed")}</p>
        <div class="actions" style="display:grid;gap:8px;margin-top:10px">
          ${n.source === "sensor" ? "" : `<button class="btn btn--primary" type="button" data-emptied="${next}">${t("emptied")}</button>`}
          <a class="btn" href="https://www.google.com/maps/dir/?api=1&destination=${n.lat},${n.lon}" target="_blank" rel="noopener">${t("navigate")}</a>
          <button class="btn btn--ghost" type="button" data-open="${next}">${t("problemQ")}</button>
        </div>`;
    }

    $("stops").innerHTML = stops.map((s, i) => {
      const state = s.status === "fault" ? t("stateFault")
        : s.status === "done" ? (s.result === "sensor" ? t("stateSensor") : t("stateEmptied"))
        : s.status === "skipped" ? problemLabel(s.result) : i === next ? t("stateNext") : "";
      const tag = s.source === "crew-added" ? `<span class="badge badge--added">${t("addedByCrew")}</span>` : "";
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

  // Report about the tour and the bins, never about the worker: no times, no speed.
  function reportRows() {
    const count = (fn) => stops.filter(fn).length;
    return [
      [count((s) => s.result === "sensor"), t("rSensor")],
      [count((s) => s.result === "crew"), t("rTap")],
      [count((s) => s.result === "sensor-fault"), t("rFault")],
      ...PROBLEMS.map((p) => [count((s) => s.result === p.id), t("rSkipped", { reason: t(p.key) })]),
      [count((s) => s.source === "crew-added"), t("rAdded")],
    ].filter(([n]) => n > 0);
  }

  const reportHtml = (rows) => rows.map(([n, label]) => `<li><b>${n}</b> ${label}</li>`).join("");

  function renderDone() {
    clearInterval(sensorTimer);
    $("done-title").textContent = t("wellDone", { crew: session.team });
    $("done-sub").textContent = t("allDone", { n: stops.length });
    $("done-summary").innerHTML = reportHtml(reportRows());
  }

  // ---------- bottom sheet ----------

  function openSheet(html) {
    $("sheet").innerHTML = `<div class="sheet-grip"></div>${html}`;
    $("sheet").hidden = false;
    $("sheet-backdrop").hidden = false;
  }

  function closeSheet() {
    $("sheet").hidden = true;
    $("sheet-backdrop").hidden = true;
  }

  // Stop sheet: problems only (stories #2 and #3)
  function openStop(i) {
    const s = stops[i];
    if (s.status !== "todo") return;
    openSheet(`
      <h2>${escapeHtml(s.name)}</h2>
      <p class="sub">${s.fill == null ? t("noValid") : t("predicted", { p: s.fill })} · ${escapeHtml(s.binId)}</p>
      ${whyHtml(s.why)}
      ${s.source === "sensor" ? "" : `<div class="actions"><button class="btn btn--primary" type="button" data-emptied="${i}">${t("emptied")}</button></div>`}
      <p class="question">${t("skipQ")}</p>
      <div class="choices">
        ${PROBLEMS.map((p) => `<button class="choice choice--wide" type="button" data-problem="${p.id}" data-stop="${i}">${t(p.key)}</button>`).join("")}
      </div>
      <p class="privacy">${t("privacy")}</p>
      <div class="actions"><button class="btn btn--ghost" type="button" data-close>${t("back")}</button></div>`);
  }

  // ---------- menu (#12) ----------

  function openMenu() {
    openSheet(`
      <h2>${t("menu")}</h2>
      <p class="sub">${escapeHtml(session.team)}</p>
      ${syncHtml()}
      <div class="menu-list">
        <button class="menu-item" type="button" data-menu="report">${t("mReport")}</button>
        <button class="menu-item" type="button" data-menu="problems">${t("mProblems")}</button>
        <button class="menu-item" type="button" data-menu="legend">${t("mLegend")}</button>
        <button class="menu-item" type="button" data-menu="privacy">${t("mPrivacy")}</button>
        <a class="menu-item menu-item--call" href="tel:${DATA.tour.depot.phone}">${t("mCall")}</a>
      </div>
      <p class="question">${t("language")}</p>
      <div class="lang-list">${langButtons()}</div>
      <div class="actions">
        <button class="btn" type="button" data-menu="logout">${t("mLogout")}</button>
        <button class="btn btn--ghost" type="button" data-close>${t("back")}</button>
      </div>`);
  }

  function syncHtml() {
    const time = lastSync.toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });
    return navigator.onLine
      ? `<p class="sync sync--on">● ${t("syncOnline", { t: time })}</p>`
      : `<p class="sync sync--off">● ${t("syncOffline", { n: pending })}</p>`;
  }

  const backToMenu = () => `<div class="actions"><button class="btn btn--ghost" type="button" data-menu="menu">${t("back")}</button></div>`;

  function openMenuPage(page) {
    if (page === "menu") return openMenu();
    if (page === "logout") return logout();
    if (page === "report") {
      const rows = reportRows();
      return openSheet(`
        <h2>${t("mReport")}</h2>
        <p class="sub">${escapeHtml(DATA.tour.name)} · ${stops.filter((s) => s.status !== "todo").length}/${stops.length}</p>
        ${rows.length ? `<ul class="done-report">${reportHtml(rows)}</ul>` : `<p class="stop-meta">${t("reportEmpty")}</p>`}
        ${backToMenu()}`);
    }
    if (page === "problems") {
      const list = stops.filter((s) => s.status === "fault" || s.status === "skipped");
      return openSheet(`
        <h2>${t("mProblems")}</h2>
        <ul class="nearby">
          ${list.map((s) => `<li class="problem-row"><span class="stop-name">${escapeHtml(s.name)}</span>
            <span class="stop-meta">${s.status === "fault" ? t("stateFault") : problemLabel(s.result)}</span></li>`).join("")
            || `<li class="stop-meta">${t("noProblems")}</li>`}
        </ul>
        ${backToMenu()}`);
    }
    // Matches what the app really does: reports per bin, no GPS, no per-person timing.
    if (page === "privacy") {
      const row = (ok, key) => `<li class="${ok ? "pv-yes" : "pv-no"}"><b>${ok ? "✓" : "✕"}</b>${t(key)}</li>`;
      return openSheet(`
        <h2>${t("pvTitle")}</h2>
        <ul class="legend">
          ${row(true, "pvYes1")}${row(true, "pvYes2")}${row(false, "pvNo1")}${row(false, "pvNo2")}${row(false, "pvNo3")}
        </ul>
        ${backToMenu()}`);
    }
    if (page === "legend") {
      const seg = (cls, key) => `<li><i class="seg seg--${cls} legend-seg"></i>${t(key)}</li>`;
      return openSheet(`
        <h2>${t("mLegend")}</h2>
        <ul class="legend">
          ${seg("done", "lgDone")}${seg("next", "lgNext")}${seg("fault", "lgFault")}${seg("skipped", "lgSkipped")}${seg("todo", "lgTodo")}
          <li><span class="badge badge--data">${DATA.dataLabel}</span>${t("lgSimulated")}</li>
          <li><span class="badge badge--fixed">${t("fixedSchedule")}</span>${t("lgFixed")}</li>
        </ul>
        ${backToMenu()}`);
    }
  }

  // ---------- simulated sensor feed ----------

  // Start collecting: from here the crew needs no taps; sensor events check off the stops.
  function startTour() {
    started = true;
    clearInterval(sensorTimer);
    sensorTimer = setInterval(sensorTick, SENSOR_TICK_MS);
    render();
  }

  // In the real system the backend pushes a fill-drop event; here a timer simulates the feed.
  // A fixed-schedule bin has no sensor: in the demo the crew's tap is simulated too, so the run never stalls.
  function sensorTick() {
    const i = nextIndex();
    if (i === -1 || !$("sheet").hidden) return;
    if (stops[i].source === "fixed-schedule") demoCrewTap(i);
    else if (stops[i].demo === "sensor-fault") sensorFault(i);
    else if (stops[i].demo === "bin-damaged") demoProblem(i, "bin-damaged");
    else sensorEmptied(i);
    if (navigator.onLine) lastSync = new Date();
  }

  function sensorEmptied(i) {
    const s = stops[i];
    s.status = "done";
    s.result = "sensor";
    showToast(t("tSensor", { name: s.name }));
    render();
  }

  // Crew visited, but the fill level did not drop: the sensor is flagged for maintenance.
  function sensorFault(i) {
    const s = stops[i];
    s.status = "fault";
    s.result = "sensor-fault";
    showToast(t("tFault", { name: s.name }));
    render();
  }

  function demoCrewTap(i) {
    const s = stops[i];
    s.status = "done";
    s.result = "crew";
    showToast(t("tTap", { name: s.name }));
    render();
  }

  function demoProblem(i, problem) {
    const s = stops[i];
    s.status = "skipped";
    s.result = problem;
    showToast(t("tSkipped", { name: s.name, reason: problemLabel(problem) }));
    render();
  }

  // ---------- crew actions ----------

  // Bins without valid sensor data (fixed schedule) need one tap.
  function crewEmptied(i) {
    const s = stops[i];
    s.status = "done";
    s.result = "crew";
    saveFeedback({ binId: s.binId, emptied: true, at: new Date().toISOString() });
    closeSheet();
    showToast(t("tEmptied", { name: s.name }), () => { s.status = "todo"; s.result = null; removeLastFeedback(); });
    render();
  }

  function reportProblem(i, problem) {
    const s = stops[i];
    s.status = "skipped";
    s.result = problem;
    saveFeedback({ binId: s.binId, problem, at: new Date().toISOString() });
    closeSheet();
    showToast(t("tSkipped", { name: s.name, reason: problemLabel(problem) }),
      () => { s.status = "todo"; s.result = null; removeLastFeedback(); });
    render();
  }

  // Adding a bin changes the route, so a supervisor confirms it with a code first.
  function openSupervisor() {
    openSheet(`
      <h2>${t("supTitle")}</h2>
      <p class="sub">${t("supSub")}</p>
      <input class="pin" id="sup-pin" type="password" inputmode="numeric" maxlength="4" autocomplete="off" aria-label="${t("supPin")}">
      <p class="pin-error" id="sup-error" hidden>${t("supWrong")}</p>
      <p class="privacy">${t("supHint", { pin: DATA.supervisorPin })}</p>
      <div class="actions">
        <button class="btn btn--primary" type="button" data-sup>${t("supOk")}</button>
        <button class="btn btn--ghost" type="button" data-close>${t("cancel")}</button>
      </div>`);
    setTimeout(() => $("sup-pin").focus(), 50);
  }

  function checkSupervisor() {
    if ($("sup-pin").value === DATA.supervisorPin) return openAddBin();
    $("sup-error").hidden = false;
    $("sup-pin").value = "";
    $("sup-pin").focus();
  }

  // Add a bin (story #3)
  function openAddBin() {
    const from = currentPosition();
    const list = nearby
      .map((b) => ({ ...b, d: distanceM(from, b) }))
      .sort((a, b) => a.d - b.d);
    openSheet(`
      <h2>${t("addBin").replace("＋ ", "")}</h2>
      <p class="sub">${t("addSub")}</p>
      <ul class="nearby">
        ${list.map((b) => `
          <li><button type="button" data-add="${b.binId}">
            <span><span class="stop-name">${escapeHtml(b.name)}</span><br><span class="stop-meta">${formatDistance(b.d)} · ${t("sensorPct", { p: b.fill })}</span></span>
            <span class="badge badge--added">${t("add")}</span>
          </button></li>`).join("") || `<li class="stop-meta">${t("noNearby")}</li>`}
      </ul>
      <div class="actions"><button class="btn btn--ghost" type="button" data-close>${t("cancel")}</button></div>`);
  }

  function addBin(binId) {
    const idx = nearby.findIndex((b) => b.binId === binId);
    const bin = nearby.splice(idx, 1)[0];
    const at = nextIndex() === -1 ? stops.length : nextIndex();
    stops.splice(at, 0, { ...bin, source: "crew-added", why: ["added by crew"], status: "todo", result: null });
    saveFeedback({ binId: bin.binId, addedByCrew: true, at: new Date().toISOString() });
    closeSheet();
    showToast(t("tAdded", { name: bin.name }), () => {
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
    const el = e.target.closest("button, [data-close]");
    if (!el) return;
    const d = el.dataset;
    if (d.start !== undefined) startTour();
    else if (d.open !== undefined) openStop(Number(d.open));
    else if (d.emptied !== undefined) crewEmptied(Number(d.emptied));
    else if (d.problem) reportProblem(Number(d.stop), d.problem);
    else if (d.add) addBin(d.add);
    else if (d.sup !== undefined) checkSupervisor();
    else if (d.menu) openMenuPage(d.menu);
    else if (d.lang) setLang(d.lang);
    else if (d.team) { loginTeam = d.team; renderLogin(); }
    else if (d.close !== undefined) closeSheet();
  });
  $("sheet-backdrop").addEventListener("click", closeSheet);
  // Back online: waiting reports are sent
  window.addEventListener("online", () => { pending = 0; lastSync = new Date(); if (!$("sheet").hidden && $("sheet").querySelector(".sync")) openMenu(); });
  window.addEventListener("offline", () => { if (!$("sheet").hidden && $("sheet").querySelector(".sync")) openMenu(); });
  $("add-bin-btn").addEventListener("click", openSupervisor);
  $("menu-btn").addEventListener("click", openMenu);
  $("login-btn").addEventListener("click", login);
  $("toast-undo").addEventListener("click", () => {
    if (lastAction) lastAction();
    lastAction = null;
    $("toast").hidden = true;
    render();
  });
  $("restart-btn").addEventListener("click", () => { reset(); render(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeSheet();
    if (e.key === "Enter" && e.target.id === "sup-pin") checkSupervisor();
  });

  reset();
  render();
})();
