# Smart Bins: Empty When Full

BaselHack project. Fill-level sensors + software that **predicts** when public bins are full, **detects** faulty sensors, and **optimizes** which bins to empty and the route. Pilot city: Lucerne (~960 bins). Tasks and roles: [documentation/tasks.md](documentation/tasks.md).

Team: Rai (UI/UX), Andy (Data Science), Abbas (Development, lead), Achim (Business). Talk to each person in the language they write in; code, docs and commits are in English.

## Hackathon rules (judged: "Compliance with the rules")

- Coding started at the hack (Fri 2026-10-30, ~20:30). **No code prepared upfront.** Never copy or adapt code from the earlier Zentral Hack prototype; reuse only ideas, public data and documentation.
- Libraries, frameworks and AI tooling are allowed.
- Keep the BaselHack template structure: all code in `code/`, docs about the code in `documentation/`, videos/slides/designs in `assets/`. The repo is **public**: never commit secrets, API keys, personal data, finances or the team agreement.
- **Hands-off: Sunday 2026-11-01, 12:00.** Nothing is pushed after that.
- Jury criteria: innovation, content + quality of presentation, significance, technical sophistication, rule compliance, quality of the demonstrated prototype. Keep the scope small enough to demo working.

## Git workflow

- **Never commit or push directly to `main` or to a teammate's branch.**
- Branch from `main`: `feat/...`, `fix/...`, `docs/...`, `design/...`.
- Small commits, pushed often, merged through a pull request that one other person reviews.

## Product rules

- **Honest data:** every chart and number is labelled `SIMULATED` or `REAL`. Compare only against the city's real fixed schedule (fair baseline); never claim the dropped "64% less distance".
- **Glanceable UI:** keywords and numbers, not sentences.
- **Explain decisions:** every bin on a route shows a short "why" line (e.g. "full ~14:00 · 28 °C · event").
- **Outdoor-ready crew view:** big touch targets (gloves), high contrast (sunlight), works offline.
- **Fallback visible:** a bin with no valid data shows it is back on the fixed schedule.
- Three views: crew (mobile), city administration (desktop), maintenance (desktop). DE + EN.
- Real open data for Basel lives in `assets/geojson/` (`100070`: litter reports, `100288`: street cleanliness index). It is not bin fill-level data; fill levels stay `SIMULATED`.

## Design system

- Use the [Swiss Federal Design System](https://github.com/swiss/designsystem) (MIT, [Storybook](https://swiss.github.io/designsystem/)) with the green `body--freebrand` skin and Noto Sans. Keep its MIT copyright notice.
- **Never use Swiss Government brand elements** (federal logo, coat of arms, "Schweizerische Eidgenossenschaft" header, favicon). They are excluded from the license, and the app must not look like an official government app. The brand is "Smart Bins".
- It has no map or chart components: use Leaflet and a chart library styled with its color tokens.
- Crew view needs larger touch targets than the defaults.
