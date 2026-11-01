// Live data: the same bins.json the city dashboard (code/web) reads, made by the
// prediction + routing pipeline (code/prediction, code/routing). One route = one truck team.
// Without the file, or with ?demo in the URL, the app keeps the demo tour from data.js.
window.SMART_TRASH_LIVE = (function () {
  "use strict";

  const URL = "../web/data/bins.json";
  const CACHE_KEY = "smarttrash.bins";  // last good bins.json: the app still opens offline
  const TIMEOUT_MS = 5000;              // slow network: fall back instead of a blank screen

  const valid = (raw) => !!raw && Array.isArray(raw.bins) && Array.isArray(raw.routes) && raw.routes.length > 0 && !!raw.depot;

  // Fresh file → last good copy on this phone → null (demo tour)
  async function load() {
    if (new URLSearchParams(location.search).has("demo")) return null;
    try {
      const signal = AbortSignal.timeout ? AbortSignal.timeout(TIMEOUT_MS) : undefined;
      const res = await fetch(URL, { cache: "no-store", signal });
      const raw = res.ok ? await res.json() : null;
      if (valid(raw)) {
        try { localStorage.setItem(CACHE_KEY, JSON.stringify(raw)); } catch (e) { /* storage full: keep going */ }
        return raw;
      }
    } catch (e) { /* offline, too slow or not served */ }
    try {
      const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      return valid(cached) ? cached : null;
    } catch (e) { return null; }
  }

  const teamName = (i) => `Truck ${i + 1}`;

  // "Full by Sun 12:00, before the next tour (weekend)" -> ["full ~12:00", "weekend"]
  function why(b) {
    if (b.fault) return ["sensor fault", "fixed schedule"];
    const tags = [b.hours_until_full <= 0 ? "full now" : `full ~${String(b.predicted_full_at).slice(11, 16)}`];
    const context = /\(([^)]+)\)/.exec(b.reason || "");
    if (context) tags.push(...context[1].split(",").map((s) => s.trim()).filter(Boolean));
    return tags.slice(0, 3);
  }

  // Shape of one bin in data.js. The pipeline has no street names yet: fall back to the bin id.
  function stop(b) {
    return {
      binId: b.id,
      name: b.name || b.street || b.id,
      area: `Zone ${b.zone}`,
      lat: b.lat,
      lon: b.lon,
      fill: b.fault ? null : Math.round(b.fill_percent),
      source: b.fault ? "fixed-schedule" : "sensor",
      why: why(b),
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
    const stops = (route.stops || []).map((id) => byId.get(id)).filter(Boolean).map(stop);
    if (!stops.length) return null;
    const mid = stops[Math.floor(stops.length / 2)];
    const dist = (b) => (b.lat - mid.lat) ** 2 + (b.lon - mid.lon) ** 2;
    // Bins the crew may add: not on any route, sensor working, closest to the middle of this route
    const nearby = raw.bins.filter((b) => !routed.has(b.id) && !b.fault)
      .sort((a, b) => dist(a) - dist(b)).slice(0, 6).map(stop);
    return {
      dataLabel: raw.simulated ? "SIMULATED" : "REAL",
      tour: {
        id: `${raw.generated_at}-${route.zone}`,
        name: `${teamName(Math.max(0, i))} · Zone ${route.zone}`,
        date: String(raw.generated_at).slice(0, 10),
        distanceKm: route.distance_km,  // same number as the city dashboard
        depot: { name: raw.depot.name, lat: raw.depot.lat, lon: raw.depot.lon, phone: "+41610000000" },  // placeholder number
      },
      stops,
      nearby,
    };
  }

  return { load, teams, tour };
})();
