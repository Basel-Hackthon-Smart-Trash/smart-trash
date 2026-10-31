// SIMULATED sample data for the crew prototype.
// Places are real Basel locations; fill levels, forecasts and reasons are invented.
// Backend (Dennis): replace this file with an API call that returns the same shape.
window.SMART_TRASH_DATA = {
  dataLabel: "SIMULATED",
  teams: ["Team KB-3", "Team KB-1", "Team GB-2"], // sign-in choices: teams only, no personal accounts
  tour: {
    id: "tour-2026-10-31-kb",
    name: "Kleinbasel & Centre",
    date: "2026-10-31",
    crew: "Team KB-3", // a team, never a person: no worker tracking
    depot: { name: "Depot", lat: 47.5700, lon: 7.5930, phone: "+41610000000" }, // placeholder number, not a real line
  },
  // Ordered stops for today. source: "sensor" | "fixed-schedule" (no valid sensor data)
  // Demo: four bins, one per case. demo: scripted outcome when the simulated feed reaches the stop.
  stops: [
    { binId: "BS-0412", name: "Messeplatz", area: "Kleinbasel", lat: 47.5636, lon: 7.6002,
      fill: 95, source: "sensor", why: ["full ~11:00", "Herbstmesse", "Saturday"] }, // sensor sees the drop
    { binId: "BS-0388", name: "Claraplatz", area: "Kleinbasel", lat: 47.5627, lon: 7.5939,
      fill: 88, source: "sensor", why: ["full ~13:00", "shopping Saturday"],
      demo: "sensor-fault" }, // no fill drop after the visit: sensor gets flagged
    { binId: "BS-0290", name: "Mittlere Brücke", area: "Kleinbasel", lat: 47.5603, lon: 7.5898,
      fill: null, source: "fixed-schedule", why: ["sensor fault", "fixed schedule"] }, // no sensor: one tap
    { binId: "BS-0105", name: "Barfüsserplatz", area: "Grossbasel", lat: 47.5547, lon: 7.5893,
      fill: 97, source: "sensor", why: ["full ~10:00", "Herbstmesse"],
      demo: "bin-damaged" }, // crew reports a problem and skips
  ],
  // Bins near the route that are not on today's tour (crew can add them).
  nearby: [
    { binId: "BS-0395", name: "Theodorskirchplatz", area: "Kleinbasel", lat: 47.5605, lon: 7.5960, fill: 40 },
    { binId: "BS-0420", name: "Rosentalanlage", area: "Kleinbasel", lat: 47.5650, lon: 7.6010, fill: 70 },
    { binId: "BS-0350", name: "Wettsteinplatz", area: "Kleinbasel", lat: 47.5590, lon: 7.5975, fill: 35 },
    { binId: "BS-0101", name: "Marktplatz", area: "Grossbasel", lat: 47.5582, lon: 7.5878, fill: 55 },
  ],
};
