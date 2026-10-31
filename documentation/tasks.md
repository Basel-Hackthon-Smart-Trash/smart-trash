# Smart Trash: Empty When Full
**Predict · Detect · Optimize**

> Living document. Every assumption is marked **(A)** and must be checked or replaced with real data.

---

## 0. Team and Responsibilities

| Member | Role | Main responsibility |
|---|---|---|
| Abbas | Development + **Project Lead (A)** | Architecture, backend, routing, hardware, final technical decisions, sprint planning |
| Rai | UI/UX | Dashboard, mobile crew app, user research, pitch design |
| Andy | Data Science | Forecast, fault detection, simulation, evaluation, impact numbers |
| Achim | Marketing, Value & Finance | Business model, pricing, finance, market, legal/compliance, sales, pitch content |
| Dennis | Backend | API and data flow that connects sensors, models and the dashboard |
| Maria | Brand identity | Smart Trash visual identity (logo, colours, typography) |

### Decision rules
- Each owner decides within their own area.
- Cross-area decisions (business model, scope, pilot) are made together in the weekly sync. If there is no agreement, the project lead decides.
- Every important decision goes into the **decision log** (date, decision, reason, who).

---

## 1. Goal and Scope

### Vision
Swiss cities empty public bins **when they are full, not when the plan says so**, which saves staff time, bags, fuel and CO₂, and leaves fewer overflowing bins.

### Goal for this project phase (A: 6 weeks)
A **working pilot-ready system** plus a **signed or agreed pilot** with the City of Lucerne (or one other Swiss city).

### In scope (MVP)
- Fill-level forecast per bin
- Fault detection without labels
- Daily selection of which bins to empty + route
- Dashboard for city and maintenance + mobile crew view
- 1 physical sensor prototype tested on real bins
- Business model, pricing, financial plan, pilot proposal

### Out of scope (later)
- Own sensor mass production
- Multi-city rollout
- Dog-waste bins, events, school grounds
- Native iOS/Android apps (MVP = mobile web app)

### Definition of success (end of phase)
- [ ] All bugs from section 3 closed or consciously accepted
- [ ] Results reported honestly against a fair baseline
- [ ] At least 3 interviews with cities/Werkhof done
- [ ] Pilot proposal sent to at least 1 city
- [ ] Pitch delivered with live demo and backup demo

---

## 2. The Idea

Swiss cities empty public waste bins on a fixed schedule. Half-empty bins get emptied, while bins at lakesides, parks and events overflow on hot weekends. Lucerne alone has about **960 public bins** and spends around **16,100 working hours per year** emptying them.

**Solution:** fill-level sensors + software that does three things:
1. **Predict** when each bin will be full (time, weekday, weather, events, holidays).
2. **Detect** faulty sensors. False readings made Bern stop two pilots (2012, 2018).
3. **Optimize** which bins to empty today and the route from the depot.

**Users:** Werkhof crew (mobile), city administration (overview, reports), maintenance (sensor health).

### Current state
- Prototype with 28 real Lucerne bin locations, **simulated** sensor data
- Linear regression forecast, Random Forest fault detector, nearest-neighbour + 2-opt routing
- Dashboard (online + offline copy), 3D sensor model, pitch deck, BaselHack challenge

### Honest results (simulated week)
- 54% fewer unnecessary emptyings
- Overflow hours almost halved
- Both built-in sensor faults detected
- **Route length unchanged.** The gain comes from timing, not shorter routes.

### Differentiation (vs. BrighterBins, Sensoneo, Bigbelly)
- Catches false readings (Bern's failure reason)
- Explains every decision ("full at ~2 pm because of 28 °C and an event")
- Sensor-agnostic software layer, Swiss-hosted, local team

---

## 3. Known Bugs and Open Problems

| # | Problem | Owner | Prio |
|---|---|---|---|
| 1 | Fault detector needs labels, but real pilots start without labels | Andy | High |
| 2 | Earlier bug: false fault alarm on every full bin. Fixed but no tests | Andy + Abbas | High |
| 3 | All sensor data simulated, results not proven with real data | Andy + Abbas | High |
| 4 | Forecast: simple linear model, no confidence range, no new-bin handling | Andy | Medium |
| 5 | Routing: one truck, no capacity/time windows, no distance gain in dense areas | Abbas | Medium |
| 6 | Online/offline dashboards are two copies with hardcoded data | Abbas | High |
| 7 | No data pipeline (sensor → server → model → dashboard) | Abbas | High |
| 8 | Dashboard too much text, "nicht übersichtlich" | Rai | High |
| 9 | Simulated vs. real data not always labelled | Rai + Andy | High |
| 10 | Crew trust in daily changing routes | Rai | Medium |
| 11 | Competition slide had wrong facts | Achim + Rai | High |
| 12 | Business model open (HaaS vs. software license) | Achim | High |
| 13 | CHF 20/month per bin is only an assumption | Achim | High |
| 14 | No proof the system pays off for a city | Achim + Andy | High |
| 15 | Sensor choice open (dead zones, steel bins, battery) | Abbas | Medium |
| 16 | Demo video not recorded | Rai | Medium |
| 17 | **No physical sensor tested on a real bin** | Abbas | High |
| 18 | **No ground truth**: nobody records the real fill level when a bin is emptied | Rai + Andy | High |
| 19 | **Data protection and hosting not defined** (nDSG, Swiss hosting) | Achim + Abbas | Medium |
| 20 | **Public procurement rules unknown** (how a city may buy from us) | Achim | Medium |
| 21 | **No team agreement** on ownership of code, idea and revenue | Achim | High |
| 22 | **Environmental impact not measured** (CO₂, bags, km), which is weak for an SDG 11 project | Andy + Achim | Medium |
| 23 | **No installation and maintenance concept** (mounting, battery change, vandalism, support) | Abbas + Achim | Medium |
| 24 | **Only one language**; Swiss cities need DE/FR/IT | Rai | Low |
| 25 | **No security concept** (API auth, device security, data integrity) | Abbas | Medium |
| 26 | **No backup if the live demo fails** | Abbas + Rai | High |

---

## 4. Tasks per Role

### Rai: UI/UX
**Design**
- [ ] Dashboard redesign: **one view per user** (crew, city, maintenance), keywords + numbers instead of sentences
- [ ] **Mobile crew view**: today's tour, next bin, "why is this bin on the route" per stop
- [ ] **Crew feedback button**: when emptying, the crew taps the real fill level (25/50/75/100%) or "sensor broken". This gives Andy ground truth labels (solves #1 and #18)
- [ ] Sensor fault alarm design + what the crew should do next
- [ ] Outdoor-ready UI: big buttons (gloves), high contrast (sunlight), works offline
- [ ] "Simulated" / "real" labels on every chart and number
- [ ] Small design system (colors, fonts, components) for app, pitch and flyer
- [ ] Prepare DE/FR/IT/EN texts (start: DE + EN)

**Research & testing**
- [ ] Interview 1–2 Werkhof/street-cleaning workers: How do they plan today? What builds trust?
- [ ] Usability test with 3–5 people (task: "find out which bins to empty today"), document results
- [ ] Map the crew's current day (user journey before vs. after)

**Pitch**
- [ ] Record demo video + sensor-building video (self-made)
- [ ] Pitch deck design (content from Achim)
- [ ] Prepare **backup demo** (screen recording + offline version) with Abbas

### Andy: Data Science
**Models**
- [ ] **Fault detection without labels** (rule-based plausibility checks + Isolation Forest), measure false-alarm rate and cost
- [ ] Later: use crew feedback as labels to retrain
- [ ] **Forecast**: weather, holidays, events, confidence range, new bins without history (use similar bins)
- [ ] Model **explanations** for the "why" line (feature contributions)
- [ ] Model monitoring: detect when forecast error grows, plan retraining

**Data**
- [ ] Test cases for faults: stuck value, jump-and-freeze, "full but 0 kg", full bins that are *not* faults (#2)
- [ ] More realistic simulation; document every assumption
- [ ] Data quality checks (missing values, gaps, duplicates)
- [ ] Collect open data from Lucerne and other cities to check the simulation
- [ ] Analyse real data from Abbas' sensor prototype

**Evaluation & impact**
- [ ] Honest metrics vs. fair baseline: unnecessary emptyings, overflow hours, detected faults, distance, staff hours
- [ ] **Impact numbers**: saved km, fuel, CO₂, plastic bags per year (input for Achim)
- [ ] Sensitivity analysis: how good are results if sensors fail 5%/10%/20% of the time?

### Abbas: Development + Project Lead
**Architecture & code**
- [ ] One dashboard codebase with online/offline switch (#6)
- [ ] Data pipeline: sensor API, database, daily job (model → decision → route) (#7)
- [ ] Routing with OR-Tools: several vehicles, capacity, time windows (#5)
- [ ] Sensor-agnostic adapter layer (e.g. BrighterBins open API)
- [ ] Export/integration for city systems (CSV, GIS, maybe fleet software)

**Hardware**
- [ ] Sensor research: ultrasonic vs. ToF vs. radar, LoRaWAN coverage, battery life, price per bin (input for Achim)
- [ ] **Build 1 sensor prototype and test it on 1–3 real bins** (with permission) for at least 1 week (#17)
- [ ] Mounting concept for different bin types

**Quality & security**
- [ ] Automated tests + CI pipeline in Azure DevOps (incl. Andy's fault tests)
- [ ] Security: API authentication, encrypted transfer, device IDs, access roles (crew/city/admin)
- [ ] Swiss/EU hosting decision (with Achim)
- [ ] Technical documentation (setup, architecture diagram, API)
- [ ] Backup demo that works without internet (#26)

**Project lead**
- [ ] Set up Azure DevOps board, sprints and Definition of Done (see section 8)
- [ ] Lead the weekly sync, keep the decision log and risk list up to date

### Achim: Marketing, Value & Finance
**Value & positioning**
- [ ] Value proposition per customer: city administration, Werkhof crew, waste contractors
- [ ] Fix competition slide with correct facts (BrighterBins, Sensoneo, Bigbelly, others)
- [ ] Choose and sharpen **one main differentiator**

**Finance & business model**
- [ ] Business model recommendation: HaaS vs. software license (pros, cons)
- [ ] Realistic price research to replace CHF 20/month (#13)
- [ ] Unit economics per bin: sensor, connectivity, battery, installation, support, hosting vs. revenue
- [ ] Break-even for us + payback time for a city (#14)
- [ ] 3-year financial plan (costs, revenue, funding need)
- [ ] **Project budget** for this phase (sensor prototype, hosting, travel)

**Market & sales**
- [ ] Market size: public bins in Swiss cities (Lucerne, Zurich, Bern, Winterthur, Basel …)
- [ ] **Customer interviews with 3–5 cities** before building more features
- [ ] Buying Center map: who decides, pays, uses, can block
- [ ] Customer journey from first contact to contract
- [ ] Partnerships: sensor vendors, LoRaWAN network providers, waste contractors
- [ ] Funding: innovation funds, city programs, Innosuisse, hackathon prizes

**Legal & compliance**
- [ ] **Team agreement**: who owns the code and idea, how revenue/shares are split, what happens if someone leaves (#21)
- [ ] Data protection check (nDSG): what data we store, where, how long (#19)
- [ ] Public procurement: thresholds and procedures for cities (#20)
- [ ] Permission needed to mount sensors on city bins
- [ ] Later: company form (e.g. GmbH) and name/trademark check

**Marketing & pitch**
- [ ] Pitch storyline (Kawasaki method) and all numbers on slides
- [ ] **SDG 11 impact story** with Andy's CO₂/bags/km numbers (#22)
- [ ] Prepare **jury Q&A**: 15 hardest questions with answers (price, competitors, Bern failure, data protection, why us)
- [ ] One-page flyer, landing page text, LinkedIn
- [ ] Lead the pilot proposal for Lucerne

### Shared (all four)
- [ ] Decide business model (Achim recommends)
- [ ] Sign the team agreement
- [ ] Pilot proposal: 20–30 bins, 3 months, success metrics, go/no-go criteria
- [ ] Rehearse the pitch at least 3 times with timer and Q&A

---

## 5. Operations Concept (for the pilot)

| Topic | Question to answer | Owner |
|---|---|---|
| Installation | Who mounts sensors, how long per bin, which tools? | Abbas |
| Battery | How long does it last, who changes it, alarm before empty? | Abbas |
| Vandalism/theft | Mounting, insurance, replacement cost | Abbas + Achim |
| Support | Who answers when the city has a problem, response time? | Achim |
| Data loss | What happens if the network or a sensor is down? (fallback = fixed schedule) | Abbas + Andy |
| Training | How is the crew trained (15-min session, short guide)? | Rai |

---

## 6. KPIs

### Product (measured in pilot)
| KPI | Target (A) |
|---|---|
| Unnecessary emptyings | −30% vs. fixed schedule |
| Overflow hours | −40% |
| Fault detection: found faults | ≥ 80% |
| False alarms | ≤ 1 per 50 bins per week |
| Forecast error (fill level, 24 h) | ≤ 15 percentage points |
| Crew uses the app daily | ≥ 80% of tours |
| CO₂ / km / bags saved | measured and reported |

### Project
| KPI | Target |
|---|---|
| City interviews | ≥ 3 |
| Usability test participants | ≥ 3 |
| Pilot proposal sent | ≥ 1 city |
| Real sensor test days | ≥ 7 |

---

## 7. Risks

| Risk | Impact | Likelihood | Countermeasure | Owner |
|---|---|---|---|---|
| Sensors give false readings (like Bern) | High | Medium | Plausibility checks + crew feedback + field test | Andy + Abbas |
| No city wants a pilot | High | Medium | Interviews early, offer free pilot, ask contractors too | Achim |
| Competitors are cheaper/better | High | Medium | Focus on differentiator, sensor-agnostic software | Achim |
| Crew doesn't trust the app | Medium | Medium | Explanations, involve crew early, fallback to fixed plan | Rai |
| Real savings smaller than simulated | Medium | High | Report honestly, focus on overflow reduction | Andy |
| Team members leave/no time | High | Medium | Team agreement, documentation, clear owners | Abbas |
| Live demo fails at pitch | High | Low | Offline backup + screen recording | Abbas + Rai |
| Procurement makes sales slow | Medium | High | Start under thresholds with a pilot | Achim |

---

## 8. Ways of Working

- **Tool:** Azure DevOps (Boards for tasks, Repos for code, Pipelines for CI)
- **Sprints:** 2 weeks, planning on Monday, review on Friday
- **Weekly sync:** 30 min, fixed day/time (A: Monday evening)
- **Chat:** one team channel (A: WhatsApp or Teams)
- **Git:** `main` (stable) + feature branches + pull request reviewed by one other person
- **Definition of Done:** code reviewed, tests pass, documented, data labelled (sim/real), shown in sync
- **Files:** one shared folder with pitch, data, decision log, risk list

---

## 9. Dependencies

| Who needs | What | From |
|---|---|---|
| Achim | Savings + impact numbers | Andy |
| Achim | Hardware, connectivity, hosting cost | Abbas |
| Rai | Pitch content and numbers | Achim |
| Rai | Model explanations for the "why" line | Andy |
| Andy | Real sensor data + crew feedback data | Abbas + Rai |
| Abbas | Final model and test cases | Andy |
| Abbas | Screen designs | Rai |
| Dennis | Data each screen needs (data contract) | Rai |
| Rai | API endpoints for the screens | Dennis |
| Rai | Brand identity (colours, logo, fonts) | Maria |

---

## 10. Timeline and Milestones

| Phase | Weeks | Focus | Milestone |
|---|---|---|---|
| 1 | 1–2 | Fix #2, #6, #8, #11, #26; label all data; team agreement; city interviews start; sensor ordered | **M1:** Clean prototype + signed team agreement |
| 2 | 3–4 | Label-free fault detection, pipeline, crew view + feedback button, sensor field test, unit economics, Buying Center | **M2:** Real sensor data flowing into the dashboard |
| 3 | 5–6 | Forecast + routing, usability tests, impact numbers, break-even, pilot proposal, pitch rehearsal | **M3:** Pitch + pilot proposal sent |

### Go/No-Go after the pilot
- **Go:** KPIs in section 6 mostly reached, city willing to pay
- **Pivot:** sensors work but city won't pay → sell to waste contractors or software-only
- **Stop:** false readings can't be solved or no customer interest

---

## 11. Assumptions to Check

| # | Assumption | Check by | Owner |
|---|---|---|---|
| A1 | Abbas is project lead | Team decision | All |
| A2 | Project phase = 6 weeks | Team decision | All |
| A3 | CHF 20/month per bin | Price research + interviews | Achim |
| A4 | KPI targets in section 6 | Literature + pilot data | Andy |
| A5 | LoRaWAN coverage in Lucerne | Coverage maps | Abbas |
| A6 | City allows sensor test on its bins | Ask Lucerne | Achim |
| A7 | Weekly sync on Monday evening | Team decision | Abbas |