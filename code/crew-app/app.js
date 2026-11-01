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
  const TOUR_KEY = "smarttrash.tour";  // sessionStorage: survives back, reload and a trip to the start page
  const LANG_KEY = "smarttrash.lang";  // sessionStorage: a new launch starts in English again

  // Exceptions only. A normal stop needs no tap: the fill drop tells the system it was emptied.
  const PROBLEMS = [
    { id: "not-reachable", key: "notReachable" },
    { id: "unsafe", key: "unsafe" },
    { id: "bin-damaged", key: "binDamaged" },
  ];

  // Demo pace of the simulated sensor feed: a pause at each stop, then the event animates.
  const SENSOR_TICK_MS = 1600;
  const EVENT_MS = 1300;
  const ALERT_MS = 6000;  // fault alert confirms itself after this, like a navigation alert
  const NEAR_M = 40;      // crew opens the app this close to a suspect bin: ask about it
  const LOW_BATTERY = 15; // %, same threshold as the fault detector (code/prediction config.LOW_BATTERY)

  // One place for every finished-bin status: colour token, icon and labels.
  // Used by the map badges, the stop list, the status bar, the report and both legends.
  // Colours stay clear of the fill-level scale (green → amber → orange → red).
  const STATUS = {
    done: { color: "var(--st-done)", icon: "✓", short: "stDone", long: "lgDone" },
    skipped: { color: "var(--st-skipped)", icon: "✕", short: "stSkipped", long: "lgSkipped" },
    fault: { color: "var(--fault)", icon: "!", short: "stFault", long: "lgFault" },
  };
  const statusBadge = (status, cls = "st-badge") =>
    STATUS[status] ? `<span class="${cls}" style="background:${STATUS[status].color}" aria-hidden="true">${STATUS[status].icon}</span>` : "";

  let stops, nearby, map, routeLayer, started, sensorTimer;
  let lastSync = new Date(), pending = 0, faultAlert = null, alertTimer, defectStop = null, paused = false, geoWatch = null;
  let lastTour = null;  // finished tour kept after Done, so today's report can still be opened and corrected
  const asked = new Set();  // suspect bins already asked about by location  // reports stay on the phone while offline
  const session = loadSession();        // { team, lang }: a team, never a person
  let loginTeam = session.team || DATA.teams[0];
  let live = null, mapFit = false;  // live: bins.json from the prediction pipeline (null = demo tour)

  const $ = (id) => document.getElementById(id);

  // Tablet mounted in the truck (or ?tablet to preview it on a laptop): map and stop list side by side
  const tablet = matchMedia("(min-width: 700px) and (pointer: coarse)").matches || new URLSearchParams(location.search).has("tablet");
  document.documentElement.classList.toggle("tablet", tablet);

  function reset() {
    started = false;
    stopGeo();
    asked.clear();
    clearTimeout(sensorTimer);
    clearTimeout(alertTimer);
    faultAlert = null;
    paused = false;
    $("live-event").hidden = true;
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
      return { team: s.team || null, lang: sessionStorage.getItem(LANG_KEY) || "en" }; // every launch starts in English
    } catch { return { team: null, lang: "en" }; }
  }

  function saveSession() {
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify({ team: session.team }));
      sessionStorage.setItem(LANG_KEY, session.lang);
    } catch { /* ignore */ }
  }

  // The tour itself: which stops are done, skipped or faulty, and today's report.
  // Saved on every render, so pressing back or reloading never loses it.
  const tourKey = () => `${DATA.tour.id}|${session.team}`;

  function saveTour() {
    try {
      sessionStorage.setItem(TOUR_KEY, JSON.stringify({ key: tourKey(), started, stops, nearby, lastTour }));
    } catch { /* storage unavailable: the tour still runs, it just is not kept */ }
  }

  // A running tour comes back paused: the crew taps Resume, nothing moves on its own.
  function restoreTour() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(TOUR_KEY) || "null");
      if (!saved || saved.key !== tourKey() || !Array.isArray(saved.stops)) return;
      ({ started, stops, nearby, lastTour } = saved);
      paused = started && nextIndex() !== -1;
    } catch { /* broken entry: start fresh */ }
  }

  // Live data: the signed-in truck team gets its own route from bins.json
  function applyTeamTour(team) {
    const route = live && window.SMART_TRASH_LIVE.tour(live, team);
    if (!route) return;  // no usable stops: keep the demo tour
    Object.assign(DATA, route);
    lastTour = null;
    mapFit = true;
  }

  function login() {
    session.team = loginTeam;
    applyTeamTour(loginTeam);
    saveSession();
    reset();
    render();
  }

  function logout() {
    session.team = null;
    lastTour = null;
    saveSession();
    closeSheet();
    reset();
    render();
  }

  // ---------- helpers ----------

  function fillColor(pct) {
    if (pct == null) return "var(--fault)";
    if (pct >= 80) return "var(--fill-over)";
    if (pct >= 55) return "var(--fill-mid)";
    return "var(--fill-low)";
  }

  function fillHtml(pct) {
    if (pct == null) return `<span class="badge badge--fixed">${t("fixedSchedule")}</span>`;
    return `<span class="fill"><span class="fill-bar"><i style="width:${pct}%;background:${fillColor(pct)}"></i></span><span class="fill-num">${pct}%</span></span>`;
  }

  // Sensor battery: "Battery 82%" in lists, "Sensor battery 82%" on the next stop; low is highlighted
  function batteryHtml(pct, long = false) {
    if (pct == null) return "";
    const low = pct < LOW_BATTERY;
    return `<span class="battery ${low ? "battery--low" : ""}">${t(long ? "batteryLong" : "battery", { p: pct })}${low ? ` · ${t("batteryLow")}` : ""}</span>`;
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

  function drivingDistanceM(from, to) {
    const roadFeatures = DATA.tour.roadRoute?.features || [];
    if (!roadFeatures.length) return distanceM(from, to);

    const sourceId = from.binId || null;
    const feature = roadFeatures.find((item) => {
      const props = item.properties || {};
      return props.target_id === to.binId
        && (sourceId ? props.source_id === sourceId : !stops.some((s) => s.binId === props.source_id));
    });
    const value = feature?.properties?.distance_meters;
    return Number.isFinite(value) ? value : null;
  }

  function displayDistanceM(from, to) {
    const distance = drivingDistanceM(from, to);
    return distance === null ? "—" : formatDistance(distance);
  }

  // Route progress by driving distance: skipped stops remain part of the travel sequence.
  function routeProgress() {
    let prev = DATA.tour.depot, total = 0, done = 0;
    stops.forEach((s) => {
      const leg = drivingDistanceM(prev, s);
      if (leg !== null) {
        total += leg;
        if (s.status !== "todo") done += leg;
      }
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
    } catch { /* storage unavailable: prototype keeps working */ }
  }

  function removeLastFeedback() {
    try {
      const all = JSON.parse(localStorage.getItem(FEEDBACK_KEY) || "[]");
      all.pop();
      localStorage.setItem(FEEDBACK_KEY, JSON.stringify(all));
    } catch { /* ignore */ }
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
    // Small legend for the status badges, in a corner of the map
    const legend = L.control({ position: "bottomleft" });
    legend.onAdd = () => {
      const el = L.DomUtil.create("div", "map-legend");
      el.id = "map-legend";
      return el;
    };
    legend.addTo(map);
    const pts = [DATA.tour.depot, ...stops].map((s) => [s.lat, s.lon]);
    map.fitBounds(pts, { padding: [20, 20] });
  }

  // While collecting, the map fills the screen between the top bar and the Stop bar.
  function sizeMap() {
    const el = $("map");
    const h = !$("action-bar").hidden
      ? Math.max(260, Math.floor(window.innerHeight - (el.getBoundingClientRect().top + window.scrollY) - $("action-bar").offsetHeight - 12))
      : 340;
    if (tablet) $("tour-side").style.maxHeight = `${h}px`;  // the list beside the map scrolls on its own
    if (el.offsetHeight === h) return false;
    el.style.height = `${h}px`;
    return true;
  }

  function renderMap() {
    if (!map) initMap();
    if (!map) return;
    const resized = sizeMap();
    map.invalidateSize();
    if (resized || mapFit) map.fitBounds([DATA.tour.depot, ...stops].map((s) => [s.lat, s.lon]), { padding: [36, 36] });
    mapFit = false;
    routeLayer.clearLayers();
    const next = nextIndex();
    if (DATA.tour.roadRoute?.features?.length && !stops.some((s) => s.status === "skipped")) {
      L.geoJSON(DATA.tour.roadRoute, {
        style: { color: "#14231b", weight: 4, opacity: 0.75 },
      }).addTo(routeLayer);
    } else {
      const line = [DATA.tour.depot, ...stops.filter((s) => s.status !== "skipped")]
        .map((s) => [s.lat, s.lon]);
      L.polyline(line, { color: "#14231b", weight: 3, opacity: 0.5, dashArray: "6 6" }).addTo(routeLayer);
    }

    L.marker([DATA.tour.depot.lat, DATA.tour.depot.lon], {
      icon: L.divIcon({ className: "", html: `<div class="marker marker--depot">D</div>`, iconSize: [26, 26] }),
    }).addTo(routeLayer);

    stops.forEach((s, i) => {
      const cls = i === next ? "marker--next" : s.status !== "todo" ? "marker--finished" : "";
      const m = L.marker([s.lat, s.lon], {
        icon: L.divIcon({ className: "", html: `<div class="marker ${cls}">${i + 1}${statusBadge(s.status)}</div>`, iconSize: [30, 30] }),
        zIndexOffset: i === next ? 1000 : 0,
      }).on("click", () => openStop(i)).addTo(routeLayer);
      // Next stop's name sits on the map, since the card is hidden while collecting
      if (i === next) m.bindTooltip(escapeHtml(s.name), { permanent: true, direction: "top", offset: [0, -16], className: "next-tip" });
    });
    $("map-legend").innerHTML = Object.keys(STATUS).map((k) => `<span>${statusBadge(k)}${t(STATUS[k].short)}</span>`).join("");
  }

  // ---------- screens ----------

  function renderStatic() {
    document.documentElement.lang = session.lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-label]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nLabel)); });
  }

  function render() {
    saveTour();
    renderStatic();
    const signedIn = !!session.team;
    $("topbar-right").hidden = !signedIn;
    $("screen-login").hidden = signedIn;
    syncUrl(!signedIn ? "login" : nextIndex() === -1 ? "done" : "tour");
    if (!signedIn) {
      $("status").hidden = true;
      $("action-bar").hidden = true;  // Start belongs to a route: never before sign-in
      $("screen-tour").hidden = true;
      $("screen-done").hidden = true;
      return renderLogin();
    }
    renderTour();
  }

  // The URL names the route and the screen (#route=Truck%202&view=tour): a reload or a shared link opens the same route.
  // ?demo stays in the query string.
  function syncUrl(view) {
    const hash = session.team ? `#${new URLSearchParams({ route: session.team, view })}` : "";
    if (location.hash !== hash) history.replaceState(history.state, "", location.pathname + location.search + hash);
  }

  const routeFromUrl = () => new URLSearchParams(location.hash.slice(1)).get("route");

  // Back button: closes an open sheet first, pauses a running tour second, and only then leaves the app.
  // One extra history entry catches the press; the tour is saved in any case.
  function guardBack() {
    if (!history.state || !history.state.guard) history.pushState({ guard: true }, "");
  }

  function onBack(e) {
    if (e.state && e.state.guard) return;  // forward onto our own entry: nothing to do
    if (!$("sheet").hidden) { closeSheet(); guardBack(); }
    else if (started && !paused && nextIndex() !== -1) { stopTour(); guardBack(); }
    else history.back();  // nothing to close: go where the user wanted
  }

  function renderLogin() {
    $("team-list").innerHTML = DATA.teams.map((team) =>
      `<button class="team ${team === loginTeam ? "team--on" : ""}" type="button" data-team="${escapeHtml(team)}">${escapeHtml(team)}${
        DATA.teamMeta ? `<small>${escapeHtml(DATA.teamMeta[team])}</small>` : ""}</button>`).join("");
    $("login-langs").innerHTML = langButtons();
  }

  // Tour screen (story #1)
  function renderTour() {
    const total = stops.length;
    const finished = stops.filter((s) => s.status !== "todo").length;
    const next = nextIndex();

    $("data-label").textContent = DATA.dataLabel;
    $("tour-date").textContent = new Date(`${DATA.tour.date}T12:00`).toLocaleDateString(locale(), { weekday: "long", day: "numeric", month: "long" });
    $("tour-name").textContent = DATA.tour.name;
    $("crew-name").textContent = session.team;
    const route = routeProgress();
    $("status").hidden = !started;
    // One bottom button for the whole tour: Start, then Stop, then Resume when paused
    $("action-bar").hidden = next === -1;
    $("stop-btn").textContent = !started ? t("start") : paused ? t("resume") : t("stop");
    $("stop-btn").classList.toggle("stop-btn--go", !started || paused);
    // The info line always stays, so the bar keeps one height from Start to Stop to Resume
    if (next !== -1) {
      $("bar-info").textContent = !started ? t("barInfo", { n: total, d: DATA.tour.distanceKm ? `${DATA.tour.distanceKm} km` : formatDistance(route.total), name: stops[next].name })
        : paused ? t("pTitle")
        : t("barNext", { name: stops[next].name, d: displayDistanceM(currentPosition(), stops[next]) });
    }
    $("screen-tour").classList.toggle("collecting", started);
    $("status-stops").textContent = `${finished}/${total}`;
    $("status-left").textContent = t("left", { d: formatDistance(route.total - route.done) });
    // One segment per bin, coloured by its status
    $("segments").innerHTML = stops.map((s, i) => segHtml(i === next ? "next" : s.status)).join("");

    $("screen-tour").hidden = next === -1;
    $("screen-done").hidden = next !== -1;
    if (next === -1) return renderDone();

    if (!started) {
      $("next-card").innerHTML = "";  // the summary and Start live in the bottom bar
    } else {
      const n = stops[next];
      const from = currentPosition();
      $("next-card").innerHTML = `
        <p class="next-label">${t("nextStop")} <span class="live">${t("live")}</span></p>
        <h2>${escapeHtml(n.name)}</h2>
        <div class="row">
          ${fillHtml(n.fill)}
          <span class="stop-meta">${displayDistanceM(from, n)} · ${escapeHtml(n.area)}</span>
        </div>
        ${batteryHtml(n.battery, true)}
        ${whyHtml(n.why)}
        <p class="hint">${n.source === "sensor" ? t("hintSensor") : t("hintFixed")}</p>
        <div class="actions" style="display:grid;gap:8px;margin-top:10px">
          ${n.source === "sensor" ? "" : `<button class="btn btn--primary" type="button" data-emptied="${next}">${t("emptied")}</button>`}
          <a class="btn" href="https://www.google.com/maps/dir/?api=1&destination=${n.lat},${n.lon}" target="_blank" rel="noopener">${t("navigate")}</a>
          <button class="btn btn--ghost" type="button" data-open="${next}">${t("problemQ")}</button>
        </div>`;
    }

    $("stops").innerHTML = stops.map((s, i) => {
      const state = i === next ? t("stateNext") : s.status === "todo" ? "" : binStateLabel(s);
      const tag = s.source === "crew-added" ? `<span class="badge badge--added">${t("addedByCrew")}</span>` : "";
      return `<li><button class="stop stop--${i === next ? "next" : s.status}" type="button" data-open="${i}">
          ${statusBadge(s.status, "stop-num") || `<span class="stop-num">${i + 1}</span>`}
          <span>
            <span class="stop-name">${escapeHtml(s.name)}</span> ${tag}
            ${whyHtml(s.why)}
          </span>
          <span class="stop-state">${fillHtml(s.fill)}${batteryHtml(s.battery)}${state ? `<br>${state}` : ""}</span>
        </button></li>`;
    }).join("");

    renderMap();
  }

  // Report about the tour and the bins, never about the worker: no times, no speed.
  // While a tour runs the report shows it; after Done it shows the finished tour.
  const reportStops = () => (started || !lastTour ? stops : lastTour);

  function reportRows(list = stops) {
    const count = (fn) => list.filter(fn).length;
    return [
      [count((s) => s.result === "sensor"), t("rSensor")],
      [count((s) => s.result === "crew"), t("rTap")],
      [count((s) => s.result === "corrected"), t("rCorrected")],
      [count((s) => s.result === "sensor-fault"), t("rFault")],
      [count((s) => s.result === "sensor-checked"), t("rChecked")],
      [count((s) => s.result === "defect-other"), t("rOther")],
      [count((s) => s.result === "not-done"), t("rNotDone")],
      ...PROBLEMS.map((p) => [count((s) => s.result === p.id), t("rSkipped", { reason: t(p.key) })]),
      [count((s) => s.source === "crew-added"), t("rAdded")],
    ].filter(([n]) => n > 0);
  }

  // Pencil = this row can be edited (inline SVG, not an emoji, so it takes the text colour)
  const PENCIL = `<svg class="pencil" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M13.5 6.5l4 4" stroke="currentColor" stroke-width="2"/></svg>`;

  // The status badge already shows ✓ ✕ !, so the label drops its own leading symbol
  function binStateLabel(s) {
    const label = s.status === "todo" ? t("lgTodo")
      : s.status === "fault" ? (s.result === "defect-other" ? t("fdOther") : t("stateFault"))
      : s.status === "done" ? (s.result === "sensor" ? t("stateSensor") : t("stateEmptied"))
      : s.result === "not-done" ? t("notDone") : problemLabel(s.result);
    return label.replace(/^[✓⚠✕]\ufe0e?\s*/u, "");
  }

  // Correct a bin in today's report, also after Done. The correction is saved as feedback.
  const CORRECTIONS = () => [["emptied", t("stateEmptied")], ["sensor", t("fdSensor")],
    ...PROBLEMS.map((p) => [p.id, t(p.key)]), ["not-done", t("notDone")]];

  function currentKey(s) {
    if (s.status === "done") return "emptied";
    if (s.result === "sensor-fault") return "sensor";
    return s.result;
  }

  function openEdit(i) {
    const s = reportStops()[i];
    openSheet(`
      <h2>${t("edTitle")}</h2>
      <p class="sub">${escapeHtml(s.name)} · ${escapeHtml(s.area)}</p>
      <div class="choices">
        ${CORRECTIONS().map(([key, label]) => `<button class="choice choice--wide ${key === currentKey(s) ? "choice--on" : ""}" type="button" data-set="${key}" data-edit-stop="${i}">${label}</button>`).join("")}
      </div>
      <div class="actions"><button class="btn btn--ghost" type="button" data-menu="report">${t("back")}</button></div>`);
  }

  function applyCorrection(i, key) {
    const s = reportStops()[i];
    if (key === "emptied") { s.status = "done"; s.result = "corrected"; }
    else if (key === "sensor") { s.status = "fault"; s.result = "sensor-fault"; }
    else { s.status = "skipped"; s.result = key; }
    saveFeedback({ binId: s.binId, corrected: key, at: new Date().toISOString() });
    liveEvent(t("tCorrected", { name: s.name }), "ok");
    render();
    openMenuPage("report");
  }

  // Status bar segment: finished bins take their STATUS colour
  const segHtml = (status, extra = "") =>
    `<i class="seg seg--${status} ${extra}"${STATUS[status] ? ` style="background:${STATUS[status].color}"` : ""}></i>`;

  const reportHtml = (rows) => rows.map(([n, label]) => `<li><b>${n}</b> ${label}</li>`).join("");

  function renderDone() {
    clearTimeout(sensorTimer);
    stopGeo();
    $("done-title").textContent = t("wellDone", { crew: session.team });
    const notDone = stops.filter((s) => s.result === "not-done").length;
    $("done-sub").textContent = notDone ? t("endedEarly", { n: notDone }) : t("allDone", { n: stops.length });
    $("done-summary").innerHTML = reportHtml(reportRows());
  }

  // ---------- bottom sheet ----------

  function openSheet(html) {
    guardBack();
    $("sheet").innerHTML = `<div class="sheet-grip"></div>${html}`;
    $("sheet").hidden = false;
    $("sheet-backdrop").hidden = false;
  }

  function closeSheet() {
    // Dismissing the fault alert without an answer keeps the sensor flagged
    if (faultAlert !== null) return answerFault("sensor");
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
      ${batteryHtml(s.battery, true)}
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
      const list = reportStops();
      const rows = reportRows(list);
      return openSheet(`
        <h2>${t("mReport")}</h2>
        <p class="sub">${escapeHtml(DATA.tour.name)} · ${list.filter((s) => s.status !== "todo").length}/${list.length}</p>
        ${rows.length ? `<ul class="done-report">${reportHtml(rows)}</ul>` : `<p class="stop-meta">${t("reportEmpty")}</p>`}
        <p class="question">${t("rBins")}</p>
        <ul class="bin-report">
          ${list.map((s, i) => `<li><button class="bin-row" type="button" data-edit="${i}" ${s.status === "todo" ? "disabled" : ""}>
            <span><span class="stop-name">${escapeHtml(s.name)}</span><br><span class="stop-meta">${escapeHtml(s.area)}</span></span>
            <span class="bin-state bin-state--${s.status}">${statusBadge(s.status)}${binStateLabel(s)}</span>${s.status === "todo" ? "" : PENCIL}</button></li>`).join("")}
        </ul>
        ${backToMenu()}`);
    }
    if (page === "problems") {
      const list = stops.filter((s) => s.status === "fault" || (s.status === "skipped" && s.result !== "not-done"));
      return openSheet(`
        <h2>${t("mProblems")}</h2>
        <ul class="nearby">
          ${list.map((s) => `<li class="problem-row"><span class="stop-name">${escapeHtml(s.name)}</span>
            <span class="stop-meta">${binStateLabel(s)}${s.note ? ` · ${escapeHtml(s.note)}` : ""}</span></li>`).join("")
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
      const pin = (status) => `<span class="marker ${status === "next" ? "marker--next" : status === "todo" ? "" : "marker--finished"}">3${statusBadge(status)}</span>`;
      const row = (status, key) => `<li>${pin(status)}${segHtml(status, "legend-seg")}${t(key)}</li>`;
      return openSheet(`
        <h2>${t("mLegend")}</h2>
        <ul class="legend">
          ${Object.keys(STATUS).map((k) => row(k, STATUS[k].long)).join("")}${row("next", "lgNext")}${row("todo", "lgTodo")}
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
    clearTimeout(sensorTimer);
    window.scrollTo(0, 0);  // Start sits mid-page; the full-screen map is sized from the top
    guardBack();
    render();
    startGeo();
    sensorTimer = setTimeout(sensorTick, SENSOR_TICK_MS);
  }

  // ---------- location: only while the app is open, only on the phone ----------
  // No new hardware: when the crew opens the app next to a suspect bin, the app asks about it.
  // The position is compared here and then dropped: never stored, never sent.
  // Browsers allow location only over HTTPS; on plain http this quietly does nothing.

  function startGeo() {
    if (geoWatch !== null || !started || !window.isSecureContext || !navigator.geolocation) return;
    geoWatch = navigator.geolocation.watchPosition(onPosition, () => {}, { enableHighAccuracy: true, maximumAge: 10000 });
  }

  function stopGeo() {
    if (geoWatch !== null) navigator.geolocation.clearWatch(geoWatch);
    geoWatch = null;
  }

  function onPosition(p) {
    if (paused || faultAlert !== null || !$("sheet").hidden) return;
    const here = { lat: p.coords.latitude, lon: p.coords.longitude };
    const i = stops.findIndex((s) => s.status === "todo" && s.suspect && !asked.has(s.binId) && distanceM(here, s) < NEAR_M);
    if (i === -1) return;
    asked.add(stops[i].binId);
    openFaultAlert(i);
  }

  // In the real system the backend pushes a fill-drop event; here a timer simulates the feed.
  // A fixed-schedule bin has no sensor: in the demo the crew's tap is simulated too, so the run never stalls.
  // Each event first animates (so the jury sees the process), then updates the tour.
  function sensorTick() {
    const i = nextIndex();
    if (i === -1 || paused) return;
    if (!$("sheet").hidden) { sensorTimer = setTimeout(sensorTick, 500); return; }
    const s = stops[i];
    const kind = s.source === "fixed-schedule" ? "tap" : s.demo === "sensor-fault" ? "fault" : s.demo === "bin-damaged" ? "skip" : "ok";
    animateEvent(kind);
    sensorTimer = setTimeout(() => {
      if (s.status === "todo") {
        if (kind === "tap") setStop(i, "done", "crew");
        else if (kind === "fault") openFaultAlert(i);
        else if (kind === "skip") setStop(i, "skipped", "bin-damaged");
        else setStop(i, "done", "sensor");
        if (navigator.onLine) lastSync = new Date();
      }
      sensorTimer = setTimeout(sensorTick, SENSOR_TICK_MS);
    }, EVENT_MS);
  }

  // Marker pings like a sensor signal; on a normal stop the fill bar drains to 0 %.
  function animateEvent(kind) {
    const card = $("next-card");
    card.classList.add(`next--${kind}`);
    const marker = document.querySelector(".marker--next");
    if (marker) marker.classList.add(kind === "fault" ? "marker--ping-fault" : "marker--ping");
    if (kind === "tap") card.querySelector("[data-emptied]")?.classList.add("btn--pressed");
    const bar = card.querySelector(".fill-bar i"), num = card.querySelector(".fill-num");
    if (kind !== "ok" || !bar || !num) return;
    const from = parseInt(num.textContent, 10), t0 = performance.now();
    bar.style.transition = `width ${EVENT_MS * 0.8}ms ease-in`;
    bar.style.width = "0%";
    (function count(now) {
      const p = Math.min(1, Math.max(0, (now - t0) / (EVENT_MS * 0.8)));  // rAF time can be slightly before t0
      num.textContent = `${Math.round(from * (1 - p))}%`;
      if (p < 1) requestAnimationFrame(count);
    })(t0);
  }

  // Sensor events go to the live line in the top bar, so they never cover the next-stop card.
  function liveEvent(text, kind) {
    const el = $("live-event");
    el.textContent = text;
    el.className = `live-event live-event--${kind}`;
    el.hidden = false;
    void el.offsetWidth;  // restart the fade-in for every event
    el.classList.add("live-event--in");
  }

  // Every status change of a stop goes through here: set it, show it on the live line, redraw.
  // status: "done" | "skipped" | "fault"; result: how it got there (sensor, crew, a problem id, ...)
  const EVENT = {
    sensor: ["tSensor", "ok"], crew: ["tTap", "ok"], "sensor-fault": ["tFault", "fault"],
    "defect-other": ["tOther", "fault"], "sensor-checked": ["tChecked", "ok"],
  };

  function setStop(i, status, result, eventKey) {
    const s = stops[i];
    s.status = status;
    s.result = result;
    const [key, kind] = eventKey ? [eventKey, "ok"] : EVENT[result] || ["tSkipped", "skip"];
    liveEvent(t(key, { name: s.name, reason: status === "skipped" ? problemLabel(result) : "" }), kind);
    render();
  }

  // No fill drop after the visit: the phone buzzes and asks the crew, like a navigation alert.
  // The answer is ground truth for the fault detector.
  function openFaultAlert(i) {
    faultAlert = i;
    if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
    openSheet(`
      <div class="alert">
        <p class="alert-icon" aria-hidden="true">${"⚠\ufe0e"}</p>
        <h2>${t("faTitle")}</h2>
        <p class="sub">${t("faSub", { name: escapeHtml(stops[i].name) })}</p>
        <div class="alert-choices">
          <button class="btn btn--fault" type="button" data-fault="yes">${t("faYes")}</button>
          <button class="btn" type="button" data-fault="no">${t("faNo")}</button>
          <a class="btn btn--help" href="tel:${DATA.tour.depot.phone}" data-help>${t("faHelp")}</a>
        </div>
        <div class="countdown" id="countdown"><i style="animation-duration:${ALERT_MS}ms"></i></div>
        <p class="privacy" id="countdown-text">${t("faAuto", { s: ALERT_MS / 1000 })}</p>
      </div>`);
    clearTimeout(alertTimer);
    alertTimer = setTimeout(() => answerFault("sensor"), ALERT_MS);
  }

  // The crew is engaged: no more auto-confirm.
  function stopCountdown() {
    clearTimeout(alertTimer);
    $("countdown")?.remove();
    $("countdown-text")?.remove();
  }

  // Common defects with one tap; the note is optional (typing with gloves is hard).
  function openDefectList(i) {
    defectStop = i;
    stopCountdown();
    openSheet(`
      <h2>${t("fdTitle")}</h2>
      <p class="sub">${escapeHtml(stops[i].name)}</p>
      <div class="choices">
        ${["sensor", "bin", "other"].map((k) =>
          `<button class="choice choice--wide" type="button" data-defect="${k}">${t({ sensor: "fdSensor", bin: "fdBin", other: "fdOther" }[k])}</button>`).join("")}
      </div>
      <input class="note" id="defect-note" type="text" maxlength="120" placeholder="${t("fdNote")}">
      <div class="actions">
        <button class="btn btn--primary" type="button" data-defect-send disabled>${t("fdSend")}</button>
      </div>`);
  }

  function pickDefect(kind) {
    $("sheet").querySelectorAll("[data-defect]").forEach((b) => b.classList.toggle("choice--on", b.dataset.defect === kind));
    $("sheet").querySelector("[data-defect-send]").disabled = false;
  }

  function sendDefect() {
    const picked = $("sheet").querySelector(".choice--on");
    if (!picked) return;
    const note = $("defect-note").value.trim();
    if (faultAlert !== null) return answerFault(picked.dataset.defect, note);
    closeSheet();
    applyDefect(defectStop, picked.dataset.defect, note);
    if (paused) openPause(defectStop);
  }

  // kind: "sensor" | "bin" | "other" (defect) or "ok" (bin was emptied, sensor fine)
  function answerFault(kind, note = "") {
    const i = faultAlert;
    if (i === null) return;
    faultAlert = null;
    clearTimeout(alertTimer);
    closeSheet();
    applyDefect(i, kind, note);
  }

  function applyDefect(i, kind, note) {
    const s = stops[i];
    if (!s || s.status !== "todo") return;
    saveFeedback({ binId: s.binId, defect: kind === "ok" ? null : kind, note: note || undefined, at: new Date().toISOString() });
    s.note = note;
    if (kind === "sensor") setStop(i, "fault", "sensor-fault");  // visited, no fill drop: sensor to maintenance
    else if (kind === "bin") setStop(i, "skipped", "bin-damaged");
    else if (kind === "other") setStop(i, "fault", "defect-other");
    else setStop(i, "done", "sensor-checked");
    // Wrong answer? It is corrected in today's report (pencil); the pause sheet also offers Undo.
  }

  function undoStop(i) {
    const s = stops[i];
    s.status = "todo";
    s.result = null;
    s.note = "";
    removeLastFeedback();
  }

  // ---------- stop: pause the tour (sensor feed stops) ----------

  // Three choices and a small link: Resume is the big, safe default; End is hard to hit by mistake.
  // reportedStop: index of the stop just reported from this sheet, offers an Undo
  function openPause(reportedStop) {
    const reported = Number.isInteger(reportedStop);
    openSheet(`
      <h2>${t("pTitle")}</h2>
      ${reported ? `<p class="sync sync--on reported">${t("pReported")}
        <button class="undo-link" type="button" data-undo-stop="${reportedStop}">${t("undo")}</button></p>` : ""}
      <div class="actions">
        <button class="btn btn--primary btn--start" type="button" data-resume>${t("resume")}</button>
        <button class="btn" type="button" data-pause-report>${t("pReport")}</button>
        <a class="btn btn--help" href="tel:${DATA.tour.depot.phone}">${t("mCall")}</a>
        <button class="btn btn--ghost" type="button" data-end>${t("pEnd")}</button>
      </div>`);
  }

  function stopTour() {
    if (faultAlert !== null) return;
    paused = true;
    clearTimeout(sensorTimer);
    openPause(false);
    render();
  }

  function resumeTour() {
    paused = false;
    closeSheet();
    render();
    sensorTimer = setTimeout(sensorTick, SENSOR_TICK_MS);
  }

  // Remaining stops are kept in the report as "not done", never hidden.
  function endTour() {
    paused = false;
    closeSheet();
    stops.forEach((s) => { if (s.status === "todo") { s.status = "skipped"; s.result = "not-done"; } });
    render();
  }

  // ---------- crew actions ----------

  // Bins without valid sensor data (fixed schedule) need one tap.
  function crewEmptied(i) {
    saveFeedback({ binId: stops[i].binId, emptied: true, at: new Date().toISOString() });
    closeSheet();
    setStop(i, "done", "crew", "tEmptied");
  }

  function reportProblem(i, problem) {
    saveFeedback({ binId: stops[i].binId, problem, at: new Date().toISOString() });
    closeSheet();
    setStop(i, "skipped", problem);
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
    liveEvent(t("tAdded", { name: bin.name }), "ok");
    render();
  }

  // ---------- events ----------

  document.addEventListener("click", (e) => {
    const el = e.target.closest("button, [data-close], [data-help]");
    if (!el) return;
    const d = el.dataset;
    if (d.start !== undefined) startTour();
    else if (d.open !== undefined) openStop(Number(d.open));
    else if (d.emptied !== undefined) crewEmptied(Number(d.emptied));
    else if (d.problem) reportProblem(Number(d.stop), d.problem);
    else if (d.add) addBin(d.add);
    else if (d.sup !== undefined) checkSupervisor();
    else if (d.fault === "yes") openDefectList(faultAlert);
    else if (d.resume !== undefined) resumeTour();
    else if (d.pauseReport !== undefined) openDefectList(nextIndex());
    else if (d.end !== undefined) endTour();
    else if (d.undoStop !== undefined) { undoStop(Number(d.undoStop)); openPause(); render(); }
    else if (d.fault === "no") answerFault("ok");
    else if (d.help !== undefined) stopCountdown();  // the tel: link still opens the call
    else if (d.defect) pickDefect(d.defect);
    else if (d.defectSend !== undefined) sendDefect();
    else if (d.menu) openMenuPage(d.menu);
    else if (d.edit !== undefined) openEdit(Number(d.edit));
    else if (d.set) applyCorrection(Number(d.editStop), d.set);
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
  // Logo = back to the start page (demo / today's routes / dashboard). The tour is saved and comes back paused.
  window.addEventListener("popstate", onBack);
  window.addEventListener("resize", () => { if (map && sizeMap()) map.invalidateSize(); });
  // Phone back in the pocket: stop reading the location
  document.addEventListener("visibilitychange", () => (document.hidden ? stopGeo() : startGeo()));
  $("stop-btn").addEventListener("click", () => (!started ? startTour() : paused ? openPause(false) : stopTour()));
  $("login-btn").addEventListener("click", login);
  $("edit-report-btn").addEventListener("click", () => openMenuPage("report"));
  $("restart-btn").addEventListener("click", () => { lastTour = stops.map((s) => ({ ...s })); reset(); render(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeSheet();
    if (e.key === "Enter" && e.target.id === "sup-pin") checkSupervisor();
  });

  // Start: today's routes from bins.json (real routes, simulated sensors) unless ?demo; without the file, the demo tour
  (async function init() {
    live = await window.SMART_TRASH_LIVE.load();
    if (live) {
      const teams = window.SMART_TRASH_LIVE.teams(live);
      DATA.teams = teams.map((x) => x.name);
      DATA.teamMeta = Object.fromEntries(teams.map((x) => [x.name, x.meta]));
    }
    // A route in the URL wins over the last sign-in on this phone; unknown routes go back to sign-in
    if (DATA.teams.includes(routeFromUrl())) session.team = routeFromUrl();
    if (!DATA.teams.includes(session.team)) session.team = null;
    if (!DATA.teams.includes(loginTeam)) loginTeam = session.team || DATA.teams[0];
    if (session.team) { applyTeamTour(session.team); saveSession(); }
    reset();
    restoreTour();
    render();
  })();
})();
