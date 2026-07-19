# Supermarket Deals Ranker — Project Plan & Roadmap

A web app that takes a Dutch location + food preferences (e.g. "vegetarian, Middle Eastern inspired") and ranks nearby supermarkets by how good their current deals are *for you*, weighing deal relevance, discount depth, and distance.

Primary goal of the project: practice software engineering best practices — clean architecture, unit testing, CI, typed code, documentation — on a system with real-world messiness.

---

## 1. Concept refinement

Your instinct to score **supermarkets, not deals**, is correct. People shop at one store per trip, so the unit of recommendation is the store. The pipeline becomes:

1. Ingest deals per chain (weekly refresh — Dutch "bonus"/"aanbiedingen" cycles are weekly).
2. Tag/classify each deal product (vegetarian? cuisine affinity? category: legumes, dairy, spices...).
3. Given user preferences, compute a **relevance-weighted deal utility** per store.
4. Penalize by distance, produce a ranked list with the top matching deals shown per store as justification.

Think of the final score as a utility function you can tune:

```
score(store) = f(Σ relevance(deal) × discount_value(deal)) − λ · g(distance)
```

with normalization so stores with huge catalogs don't win by volume alone (e.g. top-k deals only, or diminishing returns via log/sqrt). This is a nice, testable, pure function — perfect for unit tests.

---

## 2. High-level architecture

Keep it a modular monolith with a separate ingestion job. Microservices would be overkill and would slow down your learning.

```
┌────────────────────┐         ┌──────────────────────────┐
│  Frontend (SPA)    │  HTTP   │  Backend API (FastAPI)   │
│  React + TS        │ ──────► │  /rank, /stores, /deals  │
└────────────────────┘         └───────────┬──────────────┘
                                           │
                              ┌────────────▼─────────────┐
                              │  Core domain logic        │
                              │  scoring, matching, geo   │
                              └────────────┬─────────────┘
                                           │
        ┌──────────────────┐   ┌───────────▼─────────────┐
        │ Ingestion worker  │──►│  PostgreSQL              │
        │ (scheduled, CLI)  │   │  stores, products, deals,│
        └──────────────────┘   │  tags                    │
                               └──────────────────────────┘
```

Key design principles to practice deliberately:

- **Separate the domain core from I/O.** Scoring, preference matching, and distance logic should be pure Python with no HTTP/DB imports. This is what makes unit testing trivial. (Hexagonal / "ports and adapters" architecture — worth reading about.)
- **Ingestion is a separate process**, not part of the web request cycle. Run it as a CLI command on a schedule (cron or GitHub Actions scheduled workflow). The web app only ever reads from the DB — fast and reliable even when a supermarket's site breaks.
- **One scraper interface, N implementations.** Define an abstract `DealSource` (e.g. `fetch_deals() -> list[RawDeal]`), implement `AlbertHeijnSource`, `JumboSource`, etc. This gives you practice with interfaces, dependency injection, and mocking.

---

## 3. Recommended tech stack

Chosen to leverage your Python strength while pushing you into new territory where it's most valuable:

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python + FastAPI** | You know Python well; FastAPI teaches modern typed APIs, Pydantic validation, async, and auto-generates OpenAPI docs |
| DB | **PostgreSQL** (SQLite for the very first iteration) | Industry standard; supports geo queries; SQLite lets you start with zero setup |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic** | Core industry skills; migrations are a best practice people skip and regret |
| Frontend | **React + TypeScript + Vite** | The biggest gap in your stack; TS will feel familiar coming from typed C++ |
| HTTP client (scrapers) | **httpx** | Modern, supports async, easy to mock in tests |
| Testing | **pytest** (+ `pytest-cov`, `respx` for HTTP mocking, `factory_boy` or fixtures for test data) | The heart of this project |
| Lint/format/types | **ruff + mypy (strict on the core package) + pre-commit** | Cheap to set up, huge habit-forming value |
| CI | **GitHub Actions** | Run lint + type check + tests on every push/PR |
| Packaging | **uv** (or poetry) with `pyproject.toml`, src-layout | Modern Python project structure |
| Deployment | **Docker + docker-compose** (app + Postgres), deploy later to a small VPS or Fly.io/Railway | Docker is near-mandatory professionally, and directly transfers to robotics (ROS 2 in Docker is common) |

---

## 4. Data layer

### 4.1 Deal data (the hard part)

No official public APIs exist. Options, roughly in order of preference for an MVP:

1. **Unofficial mobile APIs** — Albert Heijn and Jumbo have mobile app APIs that open-source projects use (see `bartmachielsen/SupermarktConnector` on GitHub). Cleanest data, but unofficial and can change without notice.
2. **Scraping the "aanbiedingen" pages** of each chain's website — more brittle (HTML changes, anti-bot measures), but a valuable skill.
3. **Aggregator scrapers as reference** — Apify hosts paid scrapers covering all major Dutch chains; GitHub has several open projects (search topics `albert-heijn`, `dutch-supermarkets`). Study their approaches even if you build your own.

Important practices to bake in from day one:

- **Rate limiting and politeness** (delays between requests, identifying User-Agent, respect robots.txt).
- **Cache raw responses to disk** during development so you're not hammering their servers while debugging — and so your tests can replay real payloads as fixtures.
- **Anti-corruption layer:** parse the messy external format into your own clean, validated `Deal` Pydantic model immediately at the boundary. Never let scraped JSON shapes leak into your domain code.
- **Legal/ethical awareness:** this is a personal learning project; keep request volume tiny (weekly deal refresh = a handful of requests), and be aware that ToS of these sites generally prohibit scraping — a reason to keep this non-commercial and low-volume.

Design the system so it degrades gracefully: if the Jumbo scraper breaks, AH results still work, and the failure is logged and visible.

### 4.2 Store locations

- **OpenStreetMap Overpass API**: query all `shop=supermarket` nodes in NL, with brand tags. Free, legitimate, one-time-ish import.
- Store per-branch: chain, name, lat/lon, address, city.

### 4.3 Geocoding user location

- **PDOK Locatieserver** — free official Dutch government geocoding API. Turns "Leiden" or a postcode into coordinates. No API key needed. This is the easy win of building for NL specifically.

### 4.4 Schema sketch

```
chains(id, name, slug)
stores(id, chain_id, name, lat, lon, address, city)
deals(id, chain_id, product_name, description, normal_price, deal_price,
      deal_mechanic,  -- "2e halve prijs", "25% korting", "2 voor €5"
      valid_from, valid_to, scraped_at, source_url)
deal_tags(deal_id, tag)        -- "vegetarian", "middle_eastern", "legumes", ...
```

Note: deals are per **chain**, not per store (national promotions), which keeps ingestion simple. A store's deal set = its chain's active deals.

Gotcha worth a unit test or five: **normalizing deal mechanics.** "2e halve prijs" = 25% off if you buy two; "2 voor €5" needs the normal unit price to compute a discount. Write a `parse_deal_mechanic()` function with a big table-driven test suite of real Dutch examples.

---

## 5. Preference → deal matching

This is the most interesting design problem. Three tiers, in increasing sophistication:

1. **Tier 1 (MVP): keyword taxonomy.** Hand-build a mapping: `middle_eastern → {aubergine, kikkererwten, couscous, tahin, feta, granaatappel, munt, komijn, ...}`, `vegetarian → exclude {vlees, kip, rund, ...} categories`. Dutch product names, so build the vocabularies in Dutch. Simple, transparent, very testable.
2. **Tier 2: embedding similarity.** Embed product names and preference descriptions (e.g. `sentence-transformers` with a multilingual model), score by cosine similarity. Handles "labneh" matching "middle eastern" without you enumerating it.
3. **Tier 3: LLM tagging at ingestion time.** Once a week, batch-classify new deal products into your tag schema via an LLM API. Cheap at this volume, high quality, and keeps the request path fast because tagging is precomputed.

Recommended path: build Tier 1 first (it forces you to design the tag schema), then swap in Tier 3 behind the same interface — a nice exercise in designing for substitutability (strategy pattern).

Vegetarian/vegan should be a **hard filter**, not a soft score — a great deal on chicken is worth zero, not "less."

---

## 6. Scoring engine

Per store *s* with active relevant deals *D(s)*:

```
deal_value(d)   = discount_fraction(d) × relevance(d, prefs)      ∈ [0, 1]
basket_score(s) = Σ over top-k deals of deal_value                (k ≈ 8–12)
distance_pen(s) = distance_km(user, s) / d_max                    (cap & normalize)
score(s)        = w_b · norm(basket_score) − w_d · distance_pen
```

Design decisions to make explicit (and document in an ADR — see §8):

- Top-k vs sum-with-diminishing-returns (log) to avoid rewarding catalog size.
- Haversine distance for MVP; optionally cycling time via OSRM/OpenRouteService later (this is NL, after all).
- Expose `w_b`, `w_d` as a user-facing slider ("I'll travel further for better deals") — makes the tradeoff tangible and gives the frontend something interesting.
- Return **explanations** with each ranking: the top deals that drove the score. Non-explainable rankings feel broken to users and are harder to debug.

This module should be 100% pure functions → property-based testing candidate (`hypothesis`): e.g. "adding a relevant deal never lowers a store's score," "score is monotonically non-increasing in distance."

---

## 7. API design (first pass)

```
GET  /api/health
GET  /api/stores?lat=..&lon=..&radius_km=..
GET  /api/deals?chain=ah&tags=vegetarian
POST /api/rank        body: { location: "2311 XY" | {lat, lon},
                              preferences: ["vegetarian", "middle_eastern"],
                              radius_km: 5, distance_weight: 0.4 }
      → ranked stores, each with score breakdown + top matching deals
```

Practices to apply: Pydantic request/response models, proper HTTP status codes, input validation errors that are actually helpful, and the auto-generated `/docs` (Swagger UI) as your manual test surface.

---

## 8. Engineering practices checklist (the real point)

- **Repo hygiene:** src-layout, `pyproject.toml`, README with setup instructions, `.env` config via `pydantic-settings` (never hardcode config), MIT license.
- **Git discipline:** small commits, meaningful messages, feature branches + PRs to your own main (yes, even solo — review your own diffs; it works), protected main requiring CI green.
- **Testing pyramid:**
  - Unit tests: scoring, deal-mechanic parsing, tag matching, distance math (fast, hundreds of them).
  - Integration tests: API endpoints via FastAPI's `TestClient` against a temp SQLite/dockerized Postgres; scraper parsers against **saved fixture payloads** (never live sites in CI).
  - A handful of end-to-end smoke tests.
  - Aim for high coverage of the domain core (>90%) rather than a blanket number.
- **CI (GitHub Actions):** ruff check + format check, mypy, pytest with coverage on every push; scheduled workflow for the weekly ingestion job later.
- **Type hints everywhere**, mypy strict on the core package.
- **Logging** (structured, e.g. `structlog`) instead of prints — especially in the ingestion worker where failures are silent otherwise.
- **ADRs (Architecture Decision Records):** short markdown files recording big choices and why (scoring formula, chain-level deals, tier-1 matching). Excellent habit, and great thesis-adjacent writing practice.
- **Robotics crossover:** the `DealSource` plugin interface ≈ hardware abstraction layers; ingestion pipeline ≈ your MuJoCo trial orchestration (config-driven, idempotent, logged); scoring ≈ metric design. Docker skills transfer directly to ROS 2 deployment.

---

## 9. Roadmap (phased)

### Phase 0 — Foundations (1 evening)
Repo setup, `pyproject.toml`, ruff/mypy/pre-commit, pytest skeleton, GitHub Actions CI running a trivial test. Get the green checkmark before writing features.

### Phase 1 — Domain core, no I/O (1–2 weeks)
- `Deal`, `Store`, `Preferences` models (Pydantic).
- `parse_deal_mechanic()` with table-driven tests.
- Tier-1 tag matching + tests.
- Scoring function + tests (add `hypothesis` here).
- Haversine distance + tests.
- ✅ Milestone: `rank_stores(stores, deals, prefs, location)` works entirely in-memory with hand-written sample data.

### Phase 2 — First real data source (1–2 weeks)
- `DealSource` interface; implement AH (mobile API or aanbiedingen page).
- Save raw payloads as test fixtures; parser tests against them.
- SQLite + SQLAlchemy models + Alembic; ingestion CLI (`python -m app.ingest --source ah`).
- OSM store import for one city (Leiden) + PDOK geocoding wrapper.
- ✅ Milestone: run ingestion, then rank real Leiden stores from a script.

### Phase 3 — API (1 week)
- FastAPI app with the endpoints above; integration tests with TestClient.
- ✅ Milestone: `POST /api/rank` returns real ranked results in Swagger UI.

### Phase 4 — Frontend (2–3 weeks, most new learning here)
- React + TS + Vite: preference input (tag chips), location field, distance-weight slider, ranked store cards with score breakdown and top deals; map view (Leaflet + OSM tiles) as stretch.
- ✅ Milestone: usable in the browser end-to-end.

### Phase 5 — Second source + robustness (1–2 weeks)
- Add Jumbo. Refactor pain here tells you how good your Phase 2 abstraction was — that feedback is the lesson.
- Graceful per-source failure handling, ingestion run logging, deal expiry cleanup.

### Phase 6 — Ship it (1 week)
- Dockerfile + docker-compose (app + Postgres), switch SQLite → Postgres.
- Deploy (Fly.io / Railway / small VPS). Scheduled weekly ingestion via GitHub Actions or cron.
- ✅ Milestone: a URL you can put on your CV and show recruiters.

### Phase 7 — Stretch goals
- Tier 3 LLM tagging; embedding search; cycling-time distances (OSRM); price history tracking ("is this actually a good deal?"); recipe-based mode ("what can I cook cheaply this week near me?" — this one demos extremely well).

---

## 10. Areas to study before implementing (tailored to you)

Ordered by (gap size × importance):

1. **Frontend fundamentals — your biggest gap.** Modern JS/TS, then React: components, props/state, hooks (`useState`, `useEffect`), fetching data. TS will feel natural from C++. Do the official React tutorial + a small toy app *before* Phase 4 so you're not learning React and building simultaneously. Budget real time here.
2. **Relational databases & ORMs.** You've lived in CSVs; this is different. Learn: schema design/normalization basics, indexes, SQLAlchemy 2.0 style (it changed significantly from older tutorials), and why migrations (Alembic) exist. A common trap: writing code that queries in loops (N+1 problem).
3. **HTTP/REST and web app anatomy.** Request/response cycle, methods, status codes, JSON APIs, CORS (you *will* hit a CORS error when the React dev server calls FastAPI — read about it before it happens so it costs you 5 minutes, not an evening).
4. **Async Python.** FastAPI and httpx push you toward `async`/`await`. Conceptually different from ROS callbacks/executors, though your intuition about event-driven systems helps. Understand when async matters (concurrent I/O) and when it doesn't (your CPU-bound scoring) — it's fine to start fully sync and add async deliberately.
5. **Testing web systems.** You've tested numerical/sim code; web testing adds: mocking HTTP (respx), test databases and fixtures, dependency injection/overrides in FastAPI, and the fixture-payload pattern for scrapers. Also look at `hypothesis` for property-based testing — you'll like it given your stats background.
6. **Web scraping in practice.** DevTools network tab (finding the JSON endpoints behind a page — often you don't need HTML parsing at all), BeautifulSoup for when you do, anti-bot basics, and etiquette/legal considerations.
7. **Docker.** Images vs containers, Dockerfile, docker-compose for app+DB. Directly reusable in robotics.
8. **CI/CD with GitHub Actions.** Straightforward given your shell-scripting experience; mostly YAML plumbing. Learn caching of dependencies to keep runs fast.

Things you can safely learn *as you go* (don't pre-study): FastAPI itself (excellent docs, very discoverable), Pydantic (you'll absorb it), Leaflet maps, deployment platforms.

---

## 11. First three concrete actions

1. Create the repo with Phase 0 tooling and a passing CI pipeline.
2. Open the AH aanbiedingen page with DevTools → Network open, and figure out where the deal data actually comes from. Save one raw payload as your first test fixture.
3. Write `parse_deal_mechanic("2e halve prijs", normal_price=3.98)` test-first. Your first red-green-refactor cycle sets the tone for the whole project.
