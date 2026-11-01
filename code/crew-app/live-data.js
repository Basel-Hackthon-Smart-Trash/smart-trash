// Live data: the same snapshot the city dashboard (code/web) reads, made by the
// prediction + routing pipeline (code/prediction, code/routing). One route = one truck team.
// Without the file, or with ?demo in the URL, the app keeps the demo tour from data.js.
window.SMART_TRASH_LIVE = (function () {
  "use strict";

  // The API serves the same snapshot that the city dashboard uses.
  // Set window.SMART_TRASH_API_URL before this script for another host.
  const API_URL = window.SMART_TRASH_API_URL || "http://127.0.0.1:8000/api/bins";
  const STATIC_URL = "../web/data/bins.json";
  const CACHE_KEY = "smarttrash.bins";  // last good bins.json: the app still opens offline
  const API_TIMEOUT_MS = 2000;          // no local API (e.g. GitHub Pages, a phone): move on fast
  const TIMEOUT_MS = 5000;              // slow network: fall back instead of a blank screen
  const STALE_H = 6;                    // a reading this much older than the plan counts as missing

  const valid = (raw) => !!raw && Array.isArray(raw.bins) && Array.isArray(raw.routes) && raw.routes.length > 0 && !!raw.depot;

  // API → committed snapshot → last good copy on this phone → null (demo tour)
  async function load() {
    if (new URLSearchParams(location.search).has("demo")) return null;
    const sources = [[API_URL, API_TIMEOUT_MS], [STATIC_URL, TIMEOUT_MS]];
    for (const [url, ms] of sources) {
      try {
        const signal = AbortSignal.timeout ? AbortSignal.timeout(ms) : undefined;
        const res = await fetch(url, { cache: "no-store", signal });
        const raw = res.ok ? await res.json() : null;
        if (valid(raw)) {
          try { localStorage.setItem(CACHE_KEY, JSON.stringify(raw)); } catch { /* storage full: keep going */ }
          return raw;
        }
      } catch { /* offline, too slow or not served: try the next source */ }
    }
    try {
      const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      return valid(cached) ? cached : null;
    } catch { return null; }
  }

  const teamName = (i) => `Truck ${i + 1}`;

  // Real sensors drop out or report late. No valid reading = the bin goes back on the fixed schedule.
  // "ok" | "fault" (flagged, or no fill level) | "stale" (last reading too old when the plan was made)
  function reading(b, plannedAt) {
    if (b.fault || !Number.isFinite(b.fill_percent)) return "fault";
    const age = (Date.parse(plannedAt) - Date.parse(b.observed_at)) / 3600000;
    return age > STALE_H ? "stale" : "ok";  // no timestamp: age is NaN, the reading is used
  }

  // "Full by Sun 12:00, before the next tour (weekend)" -> ["full ~12:00", "weekend"]
  function why(b, state) {
    if (state !== "ok") return [state === "stale" ? "no recent data" : "sensor fault", "fixed schedule"];
    const at = /T(\d\d:\d\d)/.exec(b.predicted_full_at || "");
    const tags = b.hours_until_full <= 0 ? ["full now"] : at ? [`full ~${at[1]}`] : [];
    const context = /\(([^)]+)\)/.exec(b.reason || "");
    if (context) tags.push(...context[1].split(",").map((s) => s.trim()).filter(Boolean));
    return tags.slice(0, 3);
  }

  // Sensor battery in %: from the pipeline (battery_percent). Until bins.json is regenerated with it,
  // simulated data gets a stable stand-in from the bin id, like the simulator (40–100 %, about 1 in 12 low);
  // real data without it shows nothing.
  function battery(b, simulated) {
    if (Number.isFinite(b.battery_percent)) return Math.round(b.battery_percent);
    if (!simulated) return null;
    let h = 2166136261;  // FNV-1a: neighbouring ids get unrelated values
    for (const c of String(b.id)) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0;
    return h % 12 === 0 ? 5 + (h % 10) : 40 + (h % 61);
  }

  // Shape of one bin in data.js. The pipeline has no street names yet: fall back to the bin id.
  function stop(b, raw) {
    const state = reading(b, raw.generated_at);
    return {
      binId: b.id,
      name: b.name || b.street || b.id,
      area: `Zone ${b.zone}`,
      lat: b.lat,
      lon: b.lon,
      fill: state === "ok" ? Math.round(b.fill_percent) : null,
      fillBand: state === "ok" ? b.fill_band || null : null,
      source: state === "ok" ? "sensor" : "fixed-schedule",
      why: why(b, state),
      battery: battery(b, raw.simulated),
    };
  }

  // Returns the fields of window.SMART_TRASH_DATA for every truck, plus the route of one truck.
  function teams(raw) {
    return raw.routes.map((r, i) => ({ name: teamName(i), meta: `${r.stops.length} stops · ${r.distance_km} km` }));
  }

  // null when the route has no usable stops: the app then keeps the demo tour
  function tour(raw, team) {
    const i = raw.routes.findIndex((r, n) => teamName(n) === team);
    const route = raw.routes[Math.max(0, i)];
    const byId = new Map(raw.bins.map((b) => [b.id, b]));
    const routed = new Set(raw.routes.flatMap((r) => r.stops));
    const located = (b) => !!b && Number.isFinite(b.lat) && Number.isFinite(b.lon);  // no position: cannot be routed
    const toStop = (b) => stop(b, raw);
    const stops = (route.stops || []).map((id) => byId.get(id)).filter(located).map(toStop);
    if (!stops.length) return null;
    const mid = stops[Math.floor(stops.length / 2)];
    const dist = (b) => (b.lat - mid.lat) ** 2 + (b.lon - mid.lon) ** 2;
    // Bins the crew may add: not on any route, sensor working, closest to the middle of this route
    const nearby = raw.bins.filter((b) => located(b) && !routed.has(b.id) && reading(b, raw.generated_at) === "ok")
      .sort((a, b) => dist(a) - dist(b)).slice(0, 6).map(toStop);
    return {
      dataLabel: raw.simulated ? "SIMULATED" : "REAL",
      tour: {
        id: `${raw.generated_at}-${route.zone}`,
        name: `${teamName(Math.max(0, i))} · Zone ${route.zone}`,
        date: String(raw.generated_at).slice(0, 10),
        distanceKm: route.distance_km,  // same number as the city dashboard
        roadRoute: route.road_route?.geometry || null,
        depot: { name: raw.depot.name, lat: raw.depot.lat, lon: raw.depot.lon, phone: "+41610000000" },  // placeholder number
      },
      stops,
      nearby,
    };
  }

  return { load, teams, tour };
})();
