# User Stories

We keep the project lean: all user stories are for the crew member. Each one is a GitHub issue on the [project board](https://github.com/orgs/Basel-Hackthon-Smart-Trash/projects/1).

## Persona

**Crew member:** public street-cleaning worker who empties the city's bins. Works outdoors, often with gloves, phone in one hand. Knows the area well, wants a clear tour, no wasted trips, and no feeling of being monitored.

## Stories

| # | Story | Issue |
|---|---|---|
| 1 | See which bins need me today and why | [#1](https://github.com/Basel-Hackthon-Smart-Trash/smart-trash/issues/1) |
| 2 | Zero taps: the sensor detects emptying, I only report problems | [#2](https://github.com/Basel-Hackthon-Smart-Trash/smart-trash/issues/2) |
| 3 | Stay in control: skip a stop or add a bin | [#3](https://github.com/Basel-Hackthon-Smart-Trash/smart-trash/issues/3) |
| 4 | Start collecting, sensors check off bins, tour report | [#10](https://github.com/Basel-Hackthon-Smart-Trash/smart-trash/issues/10) |
| 5 | Always see how far along the route I am | [#11](https://github.com/Basel-Hackthon-Smart-Trash/smart-trash/issues/11) |
| 6 | Menu: report, problems, help, language, sign in / out | [#12](https://github.com/Basel-Hackthon-Smart-Trash/smart-trash/issues/12) |

### 1 · See which bins need me today and why

**As a crew member, I can see which bins really need emptying today and why, so that I don't waste trips and can trust a route that changes every day.**

- Today's stops shown as an ordered list with total stops and estimated time
- Each stop shows place, predicted fill level and one "why" line with at most 3 keywords, e.g. "full ~14:00 · 28 °C · event"
- Bins without valid sensor data are marked "fixed schedule"
- All fill levels carry a SIMULATED or REAL badge
- Readable at a glance outdoors: large text, high contrast

### 2 · Zero taps: the sensor detects emptying, I only report problems

**As a crew member, I just empty the bin and move on, so that the app adds no work to my day. The sensor sees the fill level drop and checks the stop off.**

- A normal stop needs no tap: the fill drop marks it as emptied
- Bins without valid sensor data (fixed schedule) need one tap: "Emptied"
- Problems only, one tap: not reachable / unsafe / bin damaged
- Large buttons usable with gloves; any answer can be corrected later in today's report
- A sensor that shows no drop after a visit triggers an alert: the phone buzzes and asks "Defect?" with Yes / No / Help (call the depot). "Yes" opens a short list of common defects (sensor broken, bin damaged, other) with an optional note; without an answer it confirms itself after a few seconds, like a navigation alert. The answer is ground truth for fault detection
- Reports are stored per bin, not per worker: no time tracking, no ranking of workers

### 3 · Stay in control: skip a stop or add a bin

**As a crew member, I can skip a stop or add a bin that is not on my route, so that my own experience on the street still counts and the system learns from it.**

- Skip a stop with one tap and a reason: not reachable / unsafe / bin damaged
- Add an overflowing bin I see nearby from the map or list; a supervisor confirms it with a code, because it changes the route
- Skipped and added bins are sent back as feedback for the forecast
- No extra justification beyond the one-tap reason

### 4 · Start collecting, sensors check off bins, tour report

**As a crew member, I tap "Start collecting" once and then just work. The sensors check off each bin, and at the end I see a short tour report.**

- One "Start collecting" button before the tour
- After start: no taps needed; fill-drop events check off the stops
- "Stop" pauses the tour at any time: Resume (big), Report a problem (same defect list), Call depot, or End tour now (small link); remaining stops show as "not done" in the report
- Opening the app within about 40 m of a suspect bin brings up the same Defect alert; the location is used only while the app is open, stays on the phone, and is never sent or stored
- Every answer can be corrected in today's report: each bin is listed with its place and a pencil, also after Done
- End of tour: "Well done" and a report: emptied by sensor, emptied by tap, sensor faults, skipped with reason, added
- The report is about bins and the tour, never about the worker: no times, no speed, no ranking

### 5 · Always see how far along the route I am

**As a crew member, I always see how far along my route I am, so that I know at a glance how much is left while I walk.**

- Status bar fixed under the top bar, visible while scrolling, shown after "Start collecting"
- One segment per bin, coloured by status: emptied, next, sensor fault, skipped, to do
- Stops done / total and km left

### 6 · Menu: report, problems, help, language, sign in / out

**As a crew member, I can open a simple menu to find what I need without leaving the tour.**

- Sign in as a team, never as a person; sign out from the menu
- Today's report at any time, problems reported today, legend of colours and badges
- Sync status: online with last sync, or offline with reports waiting
- One tap to call the depot
- Privacy page: what we store and what we do not
- Languages: DE, FR, IT, EN (starts in English)
