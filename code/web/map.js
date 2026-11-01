// ===== Settings =====
// Today: fake data. Tomorrow: change this to the backend URL, e.g. "http://localhost:8000/api/bins"
const DATA_URL = "data/bins.json";
const REFRESH_SECONDS = 60;               // reload data every minute (0 = off)
const START_VIEW = [47.5596, 7.5886];     // Basel
const START_ZOOM = 14;

// Colours are read from style.css, so the designers only change them in one place
const css = getComputedStyle(document.documentElement);
const COLORS = {
  red: css.getPropertyValue("--red").trim(),
  orange: css.getPropertyValue("--orange").trim(),
  green: css.getPropertyValue("--green").trim(),
  fault: css.getPropertyValue("--fault").trim(),
  depot: css.getPropertyValue("--depot").trim(),
};
const ZONE_COLORS = ["#2b6cb0", "#c05621", "#2f855a", "#805ad5", "#b83280", "#2c7a7b"];

// ===== Map =====
const map = L.map("map").setView(START_VIEW, START_ZOOM);

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);

// One layer group per zone, so zones can be switched on and off
const zoneLayers = {};
let firstLoad = true;

// ===== Load data =====
async function loadData() {
  const badge = document.getElementById("data-badge");
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    draw(data);
    const time = new Date().toLocaleTimeString("de-CH", { hour: "2-digit", minute: "2-digit" });
    badge.textContent = (data.simulated ? "Simulated data" : "Live data") + " · updated " + time;
    badge.classList.remove("error");
  } catch (err) {
    badge.textContent = "Data could not be loaded (" + err.message + "). Check DATA_URL in map.js.";
    badge.classList.add("error");
    console.error(err);
  }
}

// ===== Draw everything =====
function draw(data) {
  // Remove old layers before redrawing
  Object.values(zoneLayers).forEach(layer => map.removeLayer(layer));
  Object.keys(zoneLayers).forEach(k => delete zoneLayers[k]);

  const binsById = Object.fromEntries(data.bins.map(b => [b.id, b]));
  const depot = data.depot;

  // 1. Bins as coloured circles
  data.bins.forEach(bin => {
    const layer = getZoneLayer(bin.zone);
    const color = bin.fault ? COLORS.fault : COLORS[bin.fill_band] || COLORS.green;
    L.circleMarker([bin.lat, bin.lon], {
      radius: bin.fill_band === "red" ? 9 : 7,
      color: "#ffffff",
      weight: 2,
      fillColor: color,
      fillOpacity: 0.95,
    })
      .bindPopup(popupHtml(bin))
      .addTo(layer);
  });

  // 2. Routes as lines: Werkhof -> stops -> Werkhof
  data.routes.forEach(route => {
    const points = route.stops.map(id => binsById[id]).filter(Boolean).map(b => [b.lat, b.lon]);
    if (points.length === 0) return;
    const path = depot ? [[depot.lat, depot.lon], ...points, [depot.lat, depot.lon]] : points;
    const layer = getZoneLayer(route.zone);
    const tooltip = `Truck ${route.zone}: ${route.stops.length} stops, ${route.distance_km} km`
      + (route.duration_h ? `, ${route.duration_h} h, ${route.load_l} L` : "");
    const geometry = route.road_route?.geometry;
    if (geometry?.features?.length) {
      L.geoJSON(geometry, {
        style: { color: zoneColor(route.zone), weight: 5, opacity: 0.85 },
      }).bindTooltip(`${tooltip} · road network`).addTo(layer);
    } else {
      L.polyline(path, {
        color: zoneColor(route.zone),
        weight: 4,
        opacity: 0.8,
        dashArray: "8 6",
      }).bindTooltip(`${tooltip} · straight-line fallback`).addTo(layer);
    }
  });

  // 3. Werkhof (depot)
  if (depot) {
    L.marker([depot.lat, depot.lon], {
      icon: L.divIcon({ className: "", html: '<span class="dot depot" style="width:18px;height:18px"></span>' }),
    })
      .bindPopup(`<strong>${depot.name}</strong>`)
      .addTo(map);
  }

  // Show all zone layers that are ticked
  Object.entries(zoneLayers).forEach(([zone, layer]) => {
    const box = document.querySelector(`#zone-filter input[value="${zone}"]`);
    if (!box || box.checked) layer.addTo(map);
  });

  buildZoneFilter(data);
  buildSummary(data);

  // Zoom to all bins on first load only (not on every refresh)
  if (firstLoad && data.bins.length) {
    map.fitBounds(data.bins.map(b => [b.lat, b.lon]), { padding: [30, 30] });
    firstLoad = false;
  }
}

function getZoneLayer(zone) {
  if (!zoneLayers[zone]) zoneLayers[zone] = L.layerGroup();
  return zoneLayers[zone];
}

function zoneColor(zone) {
  return ZONE_COLORS[(zone - 1) % ZONE_COLORS.length];
}

function popupHtml(bin) {
  const full = bin.predicted_full_at
    ? new Date(bin.predicted_full_at).toLocaleString("de-CH", { weekday: "short", hour: "2-digit", minute: "2-digit" })
    : "–";
  const fill = bin.fill_percent == null ? "–" : `${Math.round(bin.fill_percent)} %`;
  const statusText = {
    red: "Urgent collection", orange: "Collect today", green: "Skip this round", fault: "Sensor fault",
  }[bin.status] || bin.status;
  const fillBand = bin.fill_band ? `Observed band: ${bin.fill_band}` : "Observed band: –";
  return `
    <div class="popup">
      <h3>${bin.id}</h3>
      <p><strong>${fill}</strong> full</p>
      <p>${fillBand}</p>
      <p>${statusText}</p>
      <p>Predicted full: ${full}</p>
      <p class="reason">${bin.reason}</p>
    </div>`;
}

// ===== Sidebar =====
function buildZoneFilter(data) {
  const box = document.getElementById("zone-filter");
  if (box.childElementCount) return; // build only once
  const zones = [...new Set(data.bins.map(b => b.zone))].sort((a, b) => a - b);
  zones.forEach(zone => {
    const route = data.routes.find(r => r.zone === zone);
    if (zone === 0) {
      const label = document.createElement("label");
      label.innerHTML = `<input type="checkbox" value="0" checked> Not emptied today`;
      label.querySelector("input").addEventListener("change", e => {
        const layer = zoneLayers[0];
        if (layer) e.target.checked ? layer.addTo(map) : map.removeLayer(layer);
      });
      box.appendChild(label);
      return;
    }
    const label = document.createElement("label");
    label.innerHTML = `
      <input type="checkbox" value="${zone}" checked>
      <span class="zone-swatch" style="background:${zoneColor(zone)}"></span>
      Truck ${zone} · ${route && route.stops.length ? `${route.stops.length} stops · ${route.distance_km} km${route.duration_h ? ` · ${route.duration_h} h` : ""}` : "no tour today"}`;
    label.querySelector("input").addEventListener("change", e => {
      const layer = zoneLayers[zone];
      if (!layer) return;
      e.target.checked ? layer.addTo(map) : map.removeLayer(layer);
    });
    box.appendChild(label);
  });
}

function buildSummary(data) {
  const routed = new Set(data.routes.flatMap(route => route.stops));
  const count = s => data.bins.filter(b => routed.has(b.id) && b.status === s).length;
  const km = data.routes.reduce((sum, r) => sum + r.distance_km, 0).toFixed(1);
  document.getElementById("summary").innerHTML = `
    <li>Bins total <strong>${data.bins.length}</strong></li>
    <li>Empty today <strong>${count("red")}</strong></li>
    <li>Also empty today <strong>${count("orange")}</strong></li>
    <li>Skip <strong>${count("green")}</strong></li>
    <li>Sensor faults <strong>${count("fault")}</strong></li>
    <li>Route length <strong>${km} km</strong></li>`;
}

// ===== Waste hotspots (Basel open data 100070, illegal dumping reports) =====
const HOTSPOT_URL = "data/hotspots.json";
const hotspotLayer = L.layerGroup();

async function loadHotspots() {
  try {
    const res = await fetch(HOTSPOT_URL);
    if (!res.ok) return;
    const data = await res.json();
    const max = Math.max(...data.cells.map(c => c.count));
    data.cells.forEach(c => {
      L.circle([c.lat, c.lon], {
        radius: 40 + 110 * Math.sqrt(c.count / max),   // bigger circle = more reports
        stroke: false,
        fillColor: COLORS.red,
        fillOpacity: 0.08 + 0.25 * (c.count / max),
      })
        .bindTooltip(`${c.count} waste reports (2019–2026)`)
        .addTo(hotspotLayer);
    });
    hotspotLayer.addTo(map);
    hotspotLayer.eachLayer(l => l.bringToBack());
  } catch (err) {
    console.warn("Hotspots not loaded:", err);
  }
}

document.getElementById("toggle-hotspots").addEventListener("change", e => {
  e.target.checked ? hotspotLayer.addTo(map) : map.removeLayer(hotspotLayer);
});

// ===== Start =====
loadHotspots();
loadData();
if (REFRESH_SECONDS > 0) setInterval(loadData, REFRESH_SECONDS * 1000);
