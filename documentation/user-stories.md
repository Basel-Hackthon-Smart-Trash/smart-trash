# User Stories

Draft by Rai (UI/UX). Format: *As a [persona], I can [action], so that [benefit]*. Priority uses MoSCoW: **Must** = needed for the demo on Sunday, **Should** = if time allows, **Could** = after the hackathon.
Each story is also a GitHub issue with the label `user story` on the project board.

## Personas

- **Crew member:** Werkhof worker who empties public bins. Works outdoors, on foot or in a small truck, often with gloves, phone in one hand. Wants a clear tour and no wasted trips.
- **City administrator:** Works in the city's street-cleaning / waste department at a desk. Pays for staff hours, bags and fuel, answers complaints and reports to politics.
- **Maintenance technician:** Installs and repairs sensors. Needs to know which sensors are broken, where, and what to do before bad data reaches the route.

## Overview

| ID | Persona | Priority | Story |
|---|---|---|---|
| US01 | Crew member | Must have | Today's tour as an ordered list |
| US02 | Crew member | Must have | Next bin with map |
| US03 | Crew member | Must have | Why is this bin on my route |
| US04 | Crew member | Must have | One-tap fill-level feedback |
| US05 | Crew member | Should have | Outdoor-ready crew view |
| US06 | Crew member | Could have | Works offline |
| US07 | City administrator | Must have | Fill-level map of all bins |
| US08 | City administrator | Must have | Weekly savings vs. fixed schedule |
| US09 | City administrator | Should have | Litter hotspots from Basel open data |
| US10 | City administrator | Could have | Weekly report export |
| US11 | Maintenance technician | Must have | Sensor health list |
| US12 | Maintenance technician | Must have | Fault alarm with next action |
| US13 | Maintenance technician | Should have | Fallback bins visible |
| US14 | Any user | Must have | Simulated vs. real always visible |
| US15 | Any user | Could have | German and English |

## US01 · Today's tour as an ordered list

**As a crew member, I can see today's tour as an ordered list of bins, so that I know exactly where to go and in which order.**

Persona: Crew member · Priority: Must have · `US01`

### Acceptance criteria
- Shows number of stops and estimated duration at the top
- Each stop shows street/place and predicted fill level
- Finished stops are visibly checked off
- Readable at a glance: keywords and numbers, no sentences

## US02 · Next bin with map

**As a crew member, I can see the next bin on a map with its distance, so that I can get there without searching.**

Persona: Crew member · Priority: Must have · `US02`

### Acceptance criteria
- The next bin is highlighted on a map with the route from my position or the depot
- Distance and walking/driving time are shown
- One tap opens the location in the phone's map app

## US03 · Why is this bin on my route

**As a crew member, I can see a short reason for each bin on the route, so that I trust a route that changes every day.**

Persona: Crew member · Priority: Must have · `US03`

### Acceptance criteria
- Each stop shows one 'why' line, e.g. 'full ~14:00 · 28 °C · event'
- At most 3 reasons, shown as keywords
- Bins on the fixed-schedule fallback say so

## US04 · One-tap fill-level feedback

**As a crew member, I can report the real fill level with one tap after emptying a bin, so that the system learns and wrong sensors are caught.**

Persona: Crew member · Priority: Must have · `US04`

### Acceptance criteria
- Options: empty / half / full / overflowing / sensor broken
- One tap saves and moves to the next stop
- Takes about 2 seconds per bin
- Feedback can be undone right after tapping

## US05 · Outdoor-ready crew view

**As a crew member, I can use the app with gloves and in bright sunlight, so that I don't have to take my gloves off or search for shade.**

Persona: Crew member · Priority: Should have · `US05`

### Acceptance criteria
- Touch targets at least 56 px
- High contrast text and status colours (WCAG AA or better)
- Main actions reachable with one thumb

## US06 · Works offline

**As a crew member, I can keep working when the mobile connection drops, so that the tour is not interrupted.**

Persona: Crew member · Priority: Could have · `US06`

### Acceptance criteria
- Today's tour is available without connection
- Feedback is stored and sent when the connection returns
- An offline indicator is visible

## US07 · Fill-level map of all bins

**As a city administrator, I can see a map of all bins coloured by fill level, so that I understand the situation in the city at a glance.**

Persona: City administrator · Priority: Must have · `US07`

### Acceptance criteria
- Bins are coloured by fill level (empty → full → overflowing)
- Faulty sensors and fallback bins have their own marker
- The map is labelled SIMULATED or REAL
- Clicking a bin shows fill level, forecast and last emptying

## US08 · Weekly savings vs. fixed schedule

**As a city administrator, I can see weekly KPIs compared with today's fixed schedule, so that I can prove the system pays off.**

Persona: City administrator · Priority: Must have · `US08`

### Acceptance criteria
- KPIs: emptyings avoided, overflow hours, km driven, CO2
- Each KPI shows the fixed-schedule baseline next to it
- Every number is labelled SIMULATED or REAL

## US09 · Litter hotspots from Basel open data

**As a city administrator, I can see where litter complaints and dirty streets cluster, so that I know where smart bins help most.**

Persona: City administrator · Priority: Should have · `US09`

### Acceptance criteria
- Heat map of litter reports (open data 100070)
- Street cleanliness index layer (open data 100288)
- Filter by district and waste category
- Labelled REAL with source and data date

## US10 · Weekly report export

**As a city administrator, I can export a weekly report, so that I can share results with my team and politicians.**

Persona: City administrator · Priority: Could have · `US10`

### Acceptance criteria
- Export as PDF or CSV
- Contains the KPIs from US08 and the data labels

## US11 · Sensor health list

**As a maintenance technician, I can see all sensors with their status, battery and last reading, so that I find broken sensors quickly.**

Persona: Maintenance technician · Priority: Must have · `US11`

### Acceptance criteria
- Table with bin, location, status (OK / suspicious / faulty / offline), battery %, last reading time
- Sortable and filterable by status
- Faulty and offline sensors appear first

## US12 · Fault alarm with next action

**As a maintenance technician, I get a fault alarm that says what is wrong and what to do, so that I can fix sensors before bad data reaches the route.**

Persona: Maintenance technician · Priority: Must have · `US12`

### Acceptance criteria
- Alarm shows fault type: stuck value, jump-and-freeze, implausible reading
- Shows a suggested action, e.g. 'clean lens' or 'check mounting'
- A simply full bin never raises a fault alarm
- Alarm can be marked as resolved or as false alarm

## US13 · Fallback bins visible

**As a maintenance technician, I can see which bins are back on the fixed schedule because their data is missing or faulty, so that nothing is forgotten.**

Persona: Maintenance technician · Priority: Should have · `US13`

### Acceptance criteria
- Fallback bins are listed with the reason and since when
- The same bins are marked in the crew and city views

## US14 · Simulated vs. real always visible

**As any user, I can always see whether a number or chart is simulated or real, so that I can trust what I see.**

Persona: Any user · Priority: Must have · `US14`

### Acceptance criteria
- Every chart, KPI and map has a SIMULATED or REAL badge
- Real data shows its source

## US15 · German and English

**As any user, I can switch between German and English, so that I can use the app in my language.**

Persona: Any user · Priority: Could have · `US15`

### Acceptance criteria
- Language switch in the header
- All UI texts available in DE and EN
