# User Stories

We keep the project lean: **three user stories**, all for the crew member. Each one is a GitHub issue on the [project board](https://github.com/orgs/Basel-Hackthon-Smart-Trash/projects/1).

## Persona

**Crew member:** public street-cleaning worker who empties the city's bins. Works outdoors, often with gloves, phone in one hand. Knows the area well, wants a clear tour, no wasted trips, and no feeling of being monitored.

## Stories

| # | Story | Issue |
|---|---|---|
| 1 | See which bins need me today and why | [#1](https://github.com/Basel-Hackthon-Smart-Trash/smart-trash/issues/1) |
| 2 | One-tap feedback after emptying | [#2](https://github.com/Basel-Hackthon-Smart-Trash/smart-trash/issues/2) |
| 3 | Stay in control: skip a stop or add a bin | [#3](https://github.com/Basel-Hackthon-Smart-Trash/smart-trash/issues/3) |

### 1 · See which bins need me today and why

**As a crew member, I can see which bins really need emptying today and why, so that I don't waste trips and can trust a route that changes every day.**

- Today's stops shown as an ordered list with total stops and estimated time
- Each stop shows place, predicted fill level and one "why" line with at most 3 keywords, e.g. "full ~14:00 · 28 °C · event"
- Bins without valid sensor data are marked "fixed schedule"
- All fill levels carry a SIMULATED or REAL badge
- Readable at a glance outdoors: large text, high contrast

### 2 · One-tap feedback after emptying

**As a crew member, I can report the real fill level with one tap after emptying a bin, so that the system learns and broken sensors are caught, without extra work for me.**

- Options: empty / half / full / overflowing / sensor broken
- One tap saves and jumps to the next stop; about 2 seconds per bin
- Large buttons usable with gloves
- Undo is possible right after tapping
- Feedback is stored per bin, not per worker: no time tracking, no ranking of workers

### 3 · Stay in control: skip a stop or add a bin

**As a crew member, I can skip a stop or add a bin that is not on my route, so that my own experience on the street still counts and the system learns from it.**

- Skip a stop with one tap and a reason: already empty / not reachable / unsafe
- Add an overflowing bin I see nearby from the map or list
- Skipped and added bins are sent back as feedback for the forecast
- No extra justification beyond the one-tap reason
