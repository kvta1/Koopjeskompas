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
| Packaging | **uv** (or poetry) with `pyproject.toml`, flat layout (the package at the repo root) | Modern Python project structure |
| Deployment | **AWS serverless demo** (S3 + CloudFront + Lambda, defined in AWS CDK; see §9.3); **Docker + docker-compose** for local app + Postgres later | Fits the AWS Free plan for an interview demo, and IaC + CI deploys are core industry skills. Docker is near-mandatory professionally, and directly transfers to robotics (ROS 2 in Docker is common) |

---

## 4. Data layer

### 4.1 Deal data (the hard part)

No official public APIs exist. Options, roughly in order of preference for an MVP:

1. **Unofficial mobile APIs** — Albert Heijn and Jumbo have mobile app APIs that open-source projects use (see `bartmachielsen/SupermarktConnector` on GitHub). Cleanest data, but unofficial and can change without notice.
2. **Scraping the "aanbiedingen" pages** of each chain's website — more brittle (HTML changes, anti-bot measures), but a valuable skill.
3. **Aggregator scrapers as reference** — Apify hosts paid scrapers covering all major Dutch chains; GitHub has several open projects (search topics `albert-heijn`, `dutch-supermarkets`). Study their approaches even if you build your own.

Important practices to bake in from day one:

- **Rate limiting and politeness** (delays between requests, one at a time, deal pages only). Identify honestly where that works; where a chain blocks honest requests, a browser identity is allowed within the limits of the scraping policy in §9.4, step 3.
- **Cache raw responses to disk** during development so you're not hammering their servers while debugging — and so your tests can replay real payloads as fixtures.
- **Anti-corruption layer:** parse the messy external format into your own clean, validated `Deal` Pydantic model immediately at the boundary. Never let scraped JSON shapes leak into your domain code.
- **Legal/ethical awareness:** this is a personal learning project; keep request volume tiny (weekly deal refresh = a handful of requests), and be aware that ToS of these sites generally prohibit scraping — a reason to keep this non-commercial and low-volume.

Design the system so it degrades gracefully: if the Jumbo scraper breaks, AH results still work, and the failure is logged and visible.

### 4.2 Store locations

- **OpenStreetMap Overpass API**: query all `shop=supermarket` nodes in NL, with brand tags. Free, legitimate, one-time-ish import.
- Store per-branch: chain, name, lat/lon, address, city.

### 4.3 Geocoding user location

- **PDOK Locatieserver** — free official Dutch government geocoding API. Turns "Leiden" or a postcode into coordinates. No API key needed. This is the easy win of building for NL specifically. It allows calls straight from the browser (`Access-Control-Allow-Origin: *`); its `suggest` endpoint autocompletes places and its `centroide_ll` field is `POINT(lon lat)`, longitude first. Planned in §9.4, step 2.

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

## 9. Roadmap

### 9.1 MVP roadmap (fastest path to something demoable)

Goal: prove the core idea end-to-end — real deals, real stores, a real ranked list — for **one
chain, one city**, with everything else deliberately cut. This collapses Phases 1–4 below into a
much smaller scope so you get a working vertical slice before investing in the parts that don't
change the core learning (a second chain, a database, deployment).

Cut from the full roadmap, on purpose, until the MVP works end-to-end:

- **No database.** Cache scraped deals as a JSON file on disk; load it into memory at startup.
  SQLAlchemy/Alembic/Postgres come later, once there's something worth persisting.
- **One chain only** (Albert Heijn). No `DealSource` abstraction yet beyond a single function —
  premature to design a plugin interface around a sample size of one.
  Jumbo is Phase 5 in the full roadmap.
- **One city only** (Leiden). Store list is a short hardcoded/OSM-exported list, not a live query.
- **Tier 1 matching only** (keyword taxonomy). No embeddings, no LLM tagging.
- **No Docker, no deployment.** Runs locally via `uv run`.
- **Minimal frontend**: one page, one form (location + preference checkboxes), one ranked list.
  No slider, no map, no tag chips UI.

MVP steps:

1. **Domain core** — same as full-roadmap Phase 1: `Deal`, `Store`, `Preferences` models;
   `parse_deal_mechanic()`; Tier-1 tag matching; scoring function; haversine distance — all with
   tests. Nothing here is MVP-specific; this layer is needed regardless of scope.
   ✅ Milestone: `rank_stores(stores, deals, prefs, location)` works in-memory with hand-written
   sample data (identical milestone to full-roadmap Phase 1).
2. **One real source, no DB** — scrape/pull AH deals for Leiden, parse into `Deal` models, cache
   to a JSON fixture. A short script loads that JSON + a hardcoded Leiden store list and calls
   `rank_stores()`.
   ✅ Milestone: running the script against real AH data produces a real ranked list of Leiden
   stores, printed to the terminal.
   - **2b. Range and per-weight deals.** Added after step 2: in real data about 40% of AH's deals
     scored zero. A range deal ("Alle AH Verse pizza's: 2 voor €12") comes without products or
     prices, and a per-weight price ("100 gram voor €1.39") can't be compared with a pack price.
     Fixes:
     - per-weight deals use the per-kilo price AH already sends;
     - each price-dependent range is looked up once through AH's GraphQL API (about 44 extra
       requests a week);
     - a range counts once, valued at the **median** over its products that pass the diet filters.

     Product-level names also made the diet filters stricter: a marker like "plantaardig" now only
     vouches for its own listed item.
     ✅ Milestone: every deal of the week of 2026-11-02 gets a discount (44 ranges, 451 products).
3. **Minimal API** — a single `POST /api/rank` FastAPI endpoint reading from the cached JSON
   (no DB session, no other endpoints yet).
   ✅ Milestone: `POST /api/rank` returns real ranked results in Swagger UI.
4. **Minimal frontend** — one Vite/React page: location input, a handful of preference checkboxes,
   submit, render the ranked list with each store's top matching deals.
   ✅ **MVP milestone: a working page in the browser, one chain, one city, real deals, real
   ranking.** This is the point to demo it to someone before continuing.
   - Done as: a Vite dev server that proxies `/api` to the API (one origin, so no CORS),
     TypeScript types generated from the API's OpenAPI schema, and a few preset Leiden places
     plus the browser's location instead of postcode search (which needs a geocoder, e.g. PDOK).

From here, the full roadmap resumes at Phase 2 (add the DB and a proper `DealSource` interface —
informed by now actually having one working scraper to abstract from) through Phase 6.

### 9.3 Deployment: an AWS demo for job interviews

Goal: after MVP step 4, put the app at a public URL you can open in an interview, show the code
behind it, and explain how it's deployed, at no cost. Optimise for "always works when I open it"
and "costs nothing", not for production scale.

**Architecture (serverless, so nothing runs or costs money while nobody uses it):**

```
Browser ──► CloudFront ──┬─► S3 bucket: React build (static files)
                         └─► /api/* ─► Lambda Function URL: FastAPI (via Mangum)
                                           │ reads at cold start
                                           ▼
                                   S3 bucket: deals snapshot (ah.json)
```

- **Frontend:** the Vite build in a private S3 bucket, served through CloudFront.
- **API:** the FastAPI app in one Lambda function, wrapped with
  [Mangum](https://mangum.fastapiexpert.com/). It's exposed through a Lambda Function URL instead of
  API Gateway, because Function URLs cost nothing beyond the Lambda calls themselves.
- **One domain:** CloudFront routes `/api/*` to the Lambda and everything else to S3. The browser
  only ever talks to one origin, so CORS never comes up in production.
- **Data:** the parsed deals (`data/deals/ah.json`) as an object in a second, private S3 bucket.
  `api/lambda_handler.py` downloads it into `/tmp` once per Lambda cold start, where `create_app`
  reads it exactly as it reads `data/` locally, so the app needs no storage adapter. The Leiden
  store list is packaged with the code. No database.

**Demo-specific decision: a deals snapshot, no scraping from AWS.**
`fetch-deals` keeps running on your own machine, about once a week (or just before an interview),
and the result is uploaded to S3. AWS never contacts AH. This:
- keeps the setup within PLAN.md's personal, low-volume use of AH's unofficial API (§4.1), because a
  scheduled job on AWS republishing AH data would go further than that;
- avoids AH blocking requests from cloud IP addresses, which would break the demo at the worst
  moment;
- removes the scheduler, a second Lambda and their failure modes from the setup.

Because the snapshot can be stale, the API ranks on the **nearest day with deals** when none is
active today (`domain.scoring.ranking_day`), instead of returning nothing, and the page shows that
day: *"Albert Heijn bonus deals on Sun 8 Nov"*. A stale but honest demo beats an empty one.

**Cost: the AWS Free plan.** Since July 2025 a new AWS account can choose a *Free account plan*.
In AWS's own words, you "will not incur any charges" on it; it ends after six months or when the
USD 100–200 of sign-up credits is used, whichever comes first, and then you upgrade to a paid plan
or the account closes. ([AWS docs](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html))
- **First six months:** no charges are possible on the Free plan.
- **After that (paid plan):** the parts above stay within AWS's *always free* monthly allowances at
  demo traffic, e.g. Lambda's 1M requests/month and CloudFront's free data transfer. S3 storage for
  a few MB costs a few cents at most. Check the [Free Tier page](https://aws.amazon.com/free/)
  before upgrading, since the allowances change.
- **What would cost money, so avoid it:** RDS/Aurora, EC2, NAT gateways, App Runner, API Gateway
  beyond its trial, Secrets Manager, and a custom domain (the domain name itself plus a Route 53
  hosted zone). The CloudFront `*.cloudfront.net` URL is fine for a demo.
- **Guardrails:** an AWS Budget with an alert at USD 1, and 7-day retention on Lambda's CloudWatch
  logs.

**Learn in the console first, then codify.** Each piece is first created by hand in the AWS
console, to see every setting and why it exists, and then defined with **AWS CDK in Python** (one
stack: both buckets, the Lambda, the CloudFront distribution and its two origins). The hand-made
resources are deleted before the first CDK deploy. With CDK the whole setup can be destroyed and
recreated with one command, and it's readable in an interview. Python keeps it in one language
with the rest of the backend.

**Deployment from the laptop, not CI.** A GitHub Actions deploy would authenticate through
**OIDC** (a role that trusts GitHub), but this AWS project's managed policies don't allow creating
an OIDC identity provider. So deploys run from the laptop after `aws login`, whose credentials
expire, and no AWS keys are stored anywhere.

**Locked down behind CloudFront.** The page's bucket only answers CloudFront (origin access
control), and the Function URL will too (auth type `AWS_IAM`, OAC for Lambda), so nobody can call
the Lambda directly and spend credits. Reserved concurrency caps how many copies run at once. One
consequence: through OAC, Lambda only accepts a POST whose body hash the browser sends in
`x-amz-content-sha256`, so the page computes it (`frontend/src/api/client.ts`).

Steps:

1. ✅ **Guardrails.** A zero-spend budget (credits excluded, so it shows real usage) and the
   Region confirmed (eu-north-1).
2. ✅ **The page on S3 + CloudFront, by hand.** A private bucket, read by CloudFront through OAC.
3. **Lambda-ready API.** ✅ Code: the Mangum entry point (`api/lambda_handler.py`) with the
   snapshot downloaded from S3, the nearest-day fallback, `scripts/build-lambda.sh` for the
   arm64 zip, and the body hash in the page. Tests use a fake S3; never real AWS in CI.
   ✅ By hand: the data bucket, the function (arm64, 512 MB, reserved concurrency 5), its
   Function URL and the `/api/*` behaviour.
   ✅ Milestone: the app works at its `*.cloudfront.net` URL (live since 2026-11-06).
4. ✅ **CDK stack and one-command deploy** (code): see §9.4, step 1.
5. **Interview polish.** A README section with the architecture diagram and the reasons for each
   choice above, and a footer link from the page to the repository.

### 9.4 Next steps after the demo went live

Four steps, in this order. Each ends in something that can be shown, and each is its own branch
and PR.

| # | Step | Why at this point |
|---|---|---|
| 1 | Infrastructure as code + one-command deploy | Everything after it has to be deployed; and the hand-made setup is still fresh in mind |
| 2 | Your own location, anywhere in the Netherlands | Low risk, free official data, high demo value; its nationwide store import is reused by Jumbo |
| 3 | Deals from three chains: AH, Jumbo and Lidl | Without them the ranking comes down to distance, so the app's core idea isn't visible yet |
| 4 | Continuous deployment, run inside AWS | Needs step 1; worth least to the demo, and its services still have to be checked on this plan |

Step 4 depends only on step 1, so it can move forward if the pipeline matters more than features.

#### Step 1 — Infrastructure as code and one-command deploy

Replace the console clicks with an **AWS CDK stack in Python** that recreates the demo exactly.

- **`infra/`:** a CDK app with one stack: the page bucket and the data bucket (versioned and
  `RETAIN`, so tearing down the stack never deletes snapshot history), the Lambda function (code
  from `build/lambda.zip`, python3.14, arm64, 512 MB, 10 s, reserved concurrency 5,
  `DEALS_BUCKET`), its log group (7 days), the Function URL (`AWS_IAM`) and the CloudFront
  distribution with both origins behind OAC, the `/api/*` behaviour (all methods, CachingDisabled,
  AllViewerExceptHostHeader) and `index.html` as the default root object.
- **Both Lambda permissions:** since October 2025 a Function URL needs `lambda:InvokeFunctionUrl`
  *and* `lambda:InvokeFunction`. Check that CDK's OAC helper for Function URL origins grants both;
  if not, add the second explicitly. A missing one is a 403, as seen by hand.
- **Tests without AWS:** `aws_cdk.assertions.Template` tests on the synthesised template (bucket
  public access blocked, the URL's auth type, the behaviour's methods and policies, the source-ARN
  condition on each permission), run in CI with `cdk synth`. They need no credentials.
- **`scripts/deploy.sh`:** build the Lambda zip, build the page, `cdk deploy` (which uploads both
  and invalidates `/index.html`). Run from the laptop after `aws login`.
- **`koopjeskompas publish-deals`:** uploads `data/deals/<chain>.json` to the data bucket (the
  bucket name read from the stack's outputs), so the weekly refresh is `fetch-deals` +
  `publish-deals`. New environments pick it up; warm ones within hours.
- **Cutover:** the CDK distribution gets a new `*.cloudfront.net` address. Once it works, delete
  the hand-made distribution, OACs, function, role and buckets, from a written checklist so
  nothing is left behind. The budget stays as it is.
- **Pitfalls to expect:** `cdk bootstrap` creates its own roles and bucket in eu-north-1 (allowed
  by this project's policies; only `managed/*` roles are protected). CloudFront is global, but the
  stack itself lives in eu-north-1. Lambda@Edge and cross-Region references are off limits.

✅ Milestone: `scripts/deploy.sh` on a fresh checkout recreates the whole demo, and the hand-made
resources are gone.

Built: `infra/` (stack, app, pinned CDK CLI, README with the cutover checklist), template tests in
`tests/infra/`, `koopjeskompas/publish.py` and `scripts/deploy.sh`. CDK's helper for Function URL
origins does grant both Lambda permissions (checked in the synthesised template, and pinned by a
test). Next: the user bootstraps, deploys and cuts over.

#### Step 2 — Your own location, anywhere in the Netherlands

Today the page offers four places in Leiden plus the browser's location, and the store list holds
Leiden's 6 AHs. The API already takes any coordinates, so the work is in two places: **stores
nationwide** and **a place search in the page**. Deals need no change: they are national per
chain (§4.4), so every AH in the country already has them.

- **Stores nationwide.** One Overpass query for every AH in the Netherlands (about 1,100), written
  by a `koopjeskompas fetch-stores` command instead of by hand: query, keep `shop=supermarket`,
  map OSM tags to `Store` (name from `addr:street`, address from `addr:*`, the centre of a way or
  relation as its location), validate, write `koopjeskompas/stores/nl_ah.json`. The file stays
  committed and packaged (about 200 kB) and is refreshed now and then, like the Leiden list now.
  Tests run the conversion on a captured Overpass response; tests never call Overpass.
- **Scoring at that size.** `rank_stores` computes a haversine distance per store per request:
  about 1,100 is well under a millisecond, so no spatial index. (One would matter with all chains
  and a database, e.g. PostGIS.)
- **Place search in the page,** with PDOK Locatieserver (§4.3), the Dutch government's free
  geocoder: no key, and it allows browser calls from any origin (`Access-Control-Allow-Origin: *`,
  checked 2026-11-06).
  - A search box that suggests places as you type (`suggest`), e.g. "utrecht oudegr" →
    "Oudegracht, Utrecht". Choosing one fetches its coordinates (`lookup`). A postcode alone
    (`2311EZ`) works too.
  - **The browser calls PDOK directly,** not through our API. That's no Lambda work, no AWS cost
    and nothing of ours to keep running; the trade-off is a second origin the page talks to, and
    that PDOK sees what's typed (a government service; mention it in the page footer). The
    alternative, an `/api/geocode` endpoint, keeps one origin but makes every search a Lambda call
    to an outside service.
  - **Pitfall:** PDOK returns `centroide_ll` as `POINT(lon lat)`, longitude first. Parse it in one
    tested function.
  - Be polite to PDOK: wait about 250 ms after the last keystroke, and only search from 2
    characters.
  - Accessibility: the box is a combobox (keyboard navigation, the chosen place announced), tested
    the way the page's tests already work: by label and role.
  - "Use my location" stays. The Leiden presets go; Leiden Centraal stays the default example.
- **When no store is near:** the API already returns an empty list; the page suggests a larger
  radius (up to 50 km).

✅ Milestone: an interviewer types their own postcode and sees their nearest AHs, ranked.

Built: `koopjeskompas fetch-stores` (`stores/osm.py`, `stores/nl_ah.overpassql`) wrote 1,000 stores
to `stores/nl_ah.json`, replacing the Leiden list. Lessons from the real fetch: two of three public
Overpass servers were too busy or lacked area data (so an empty answer is an error, never written);
38 "Albert Heijn XL" stores carry their own brand value, so the query also matches on name; that
brings in two pickup points, which are skipped. In the page, `PlaceSearch` asks PDOK directly
(checked in Chrome: one `suggest` request per pause in typing, no CORS issues), and a 20 km radius
was added for the countryside.

#### Step 3 — Deals from three chains: AH, Jumbo and Lidl

With one chain every store has the same deals, so the ranking comes down to distance and the
app's core idea isn't visible. This step adds Jumbo and Lidl next to AH.

**Scraping policy (decided 2026-11-11).** Koopjeskompas is a non-commercial hobby project that
fetches each chain's deals at most once a week. Within that, a scraper **may present itself as a
browser** (a browser User-Agent and the headers a browser sends) when an honest identity is
blocked. The limits that keep it a light, ordinary visitor:

- Only the deal pages a visitor would open, never the whole assortment.
- A fixed pause between requests (1 s), one request at a time, a timeout, no retries in a loop.
- No solving CAPTCHAs, no rotating IP addresses or proxies, no forging of bot-detection data
  (such as Akamai's sensor data or TLS fingerprints). If a chain still blocks after that, its
  source fails, is reported, and the other chains carry on.
- Raw answers are saved before parsing, so fixing a parser never needs a refetch.
- Fetching runs on the laptop; AWS never contacts a supermarket (§9.3).

The chains' terms of use generally forbid scraping; this is a conscious choice for a personal
project, not something to scale up or monetise.

**Weekly, not monthly.** Deals change every week (AH Monday to Sunday, Jumbo Wednesday to
Tuesday). Fetched monthly, the demo would show the previous snapshot's last day three weeks out of
four. Weekly costs about 200 requests across the three chains (AH ~65, Jumbo ~110, Lidl a few).

**Architecture: no fundamental change.** The ports-and-adapters design already fits: the domain
knows no chain, and `rank_stores` matches deals to stores by `chain`. What changes is everything
that still assumes one chain, plus two helpers that Jumbo and Lidl share. Not adopted from
projects like KortingKlok: a database and job queue, and crawling every product (thousands of
requests a run); deals alone are enough.

##### 3a — Many chains, before adding any (one PR)

- **A chain registry** (`koopjeskompas/chains.py`): per chain its key (`ah`, `jumbo`, `lidl`),
  display name, and OpenStreetMap brand (Wikidata ID and names). The CLI's `SOURCES`, the store
  fetch and the Lambda read from it, so adding a chain means one entry plus its source.
- **Read every snapshot:** `load_all_deals(data_dir)` in `ingestion/cache.py`; the API, `rank`
  and the Lambda use it. A missing chain is skipped with a warning; no snapshot at all is a 503.
  The Lambda downloads `deals/<chain>.json` for every registered chain (the IAM policy already
  covers `deals/*`).
- **Only rank chains that have deals:** a Jumbo store without a Jumbo snapshot would show up with
  nothing; such stores are left out, and the response says which chains were included.
- **The snapshot fallback per chain:** `ranking_day` per chain instead of over all deals, so a
  stale AH snapshot can't zero AH while Jumbo is current. The API response then reports the day
  per chain (a small change in `schemas.py`, so `openapi.json` and the page's types regenerate).
- **Shared ingestion helpers:**
  - `ingestion/http.py`: a polite client (fixed pause, timeout, a header profile per chain,
    saving each raw answer, and recognising a block as a `BlockedError`, which stops that
    source's remaining requests).
  - `ingestion/nuxt.py`: the Nuxt page-data unpacker (devalue format), moved out of
    `ingestion/jumbo/`, since both Jumbo and Lidl are Nuxt sites.
- **Stores for every chain:** `fetch-stores` asks for every registered brand in one Overpass
  query and writes `stores/nl_stores.json`, each store with its chain ("Jumbo Breestraat",
  "Lidl Breestraat"). AH's 1,000 stay as they are.

✅ Milestone: with only AH's snapshot, everything works as now; adding a second snapshot by hand
makes its stores rank.

Built (2026-11-11): `chains.py`; `load_snapshots` and per-chain `chain_ranking_days`, used by the
API, `rank` and the Lambda (which no longer takes `DEALS_KEY`); the response's `chains` (each
chain's `deals_on`), shown on the page; `ingestion/http.py` and `ingestion/nuxt.py`; and
`fetch-stores` for every chain, writing `stores/nl_stores.json`. Overpass was busy, so that list
was re-converted from the saved AH answer (the same 1,000 stores); Jumbo and Lidl stores come with
the next successful fetch, before 3b. "Only rank chains with deals" lives in the API and CLI, not
in `rank_stores`: which chains have data is the application's concern, and keeping it out of the
domain keeps the scoring properties (a deal never lowers a score) intact.

##### 3b — Jumbo (one PR)

What the first live check found still holds (details below); the policy above now allows the
browser identity it needs.

- **Live check again, briefly:** the deals page and one deal page with browser headers.
- **`ingestion/jumbo/`:** `payloads.py` (Pydantic models of the page data: runtimes, sections,
  categories, promotions with tags and ISO dates; a promotion page's products with prices in
  cents), `parser.py` (pure: deduplicate by ID, skip online-only (an inverse tag like "Alleen
  online"), non-food categories and hidden promotions; `price` is the normal price, `promoPrice`
  the deal price), `client.py` (the overview, then one deal page per deal whose discount needs a
  price, about 110), `source.py`.
- **Fixtures, already captured on 2026-11-10:** a trimmed overview with one deal per case, and
  the full data of one deal page (Campina Vla, 17 products).
- **Later, not in this PR:** per-weight deals in Jumbo's format ("2,49 per kilo", via the
  product's `pricePerUnit`).

Built (2026-11-11): `ingestion/jumbo/` and `JumboSource`, and `PoliteClient.get_text(keep=...)`
so only page data is saved. The first live run went through Akamai with the browser identity: 165
deals (4 to 17 November), 96 priced per product (1,117 products), 29 non-food and 20 online-only
left out, about 100 requests and 3.8 MB of raw data. 8 stay unscored: 5 per-weight ("2,49 per
kilo"), a gift, and two spirits promotions whose pages list no products. Lessons: `DELISTED` means
"uit het online assortiment" (all spirits), not "no longer sold", so availability is ignored;
discounts came out between 10% and 58% (median 25%). With one AH and one Jumbo in Leiden, Jumbo
wins for "no preference" and "vegetarian, Middle Eastern", AH for "vegan, Italian". Still to do:
Jumbo stores, from the next `fetch-stores` once Overpass answers (it timed out all day).

##### 3c — Lidl (one PR)

- **Live check first:** the deals page (`lidl.nl/c/aanbiedingen/…`), whether it needs a browser
  identity, how deals are embedded (JSON in `data-grid-data` attributes and/or `__NUXT_DATA__`,
  per [KortingKlok](https://github.com/RashadAnsari/KortingKlok/tree/master/backend/apps/products/scrapers),
  MIT), paging, and whether normal and deal prices are both on the page (then no per-deal pages).
  Lidl also runs non-food specials and in-store-only actions on set days: decide how to filter.
- **`ingestion/lidl/`:** the same four modules as Jumbo, using `ingestion/nuxt.py` if it applies.

##### 3d — The page and the routine (one PR)

- The page names the chain on each store card, and the hint "every AH has the same deals"
  goes. Possibly a filter for which chains to include.
- `scripts/refresh-deals.sh`: `fetch-deals` for every chain, then `publish-deals`; the weekly
  routine in one command, reporting which chains failed.

✅ Milestone: an AH, a Jumbo and a Lidl near each other rank differently for "vegetarian, Middle
Eastern" than for "no preference".

**Practical note:** Claude Code's auto mode may refuse requests that present a script as a
browser, even under this policy. Allow them with a permission rule, or run the live checks by hand.

<details>
<summary>The first Jumbo live check (2026-11-10), for reference</summary>

- **The old mobile API is gone.** `mobileapi.jumbo.com/v17/...` answers 404, as others report
  ([KianMeijers/Pickled#2](https://github.com/KianMeijers/Pickled/issues/2)). The website's GraphQL
  API (`www.jumbo.com/api/graphql`) has personal promotions behind a login
  ([jumbo-cli](https://pkg.go.dev/github.com/DanielOostdam-Create/jumbo-cli)) but also anonymous
  operations such as `SearchProducts`, as KortingKlok uses.
- **The deals page has everything.** `jumbo.com/aanbiedingen/nu` embeds all deals of this week and
  next (Wednesday to Tuesday) as Nuxt page data (`__NUXT_DATA__`, devalue format): 215 deals with
  title, category, ISO dates and deal text. 65 food deals need no price ("1+1 gratis", "25%
  korting"); 107 do ("2 voor 3,49", "voor 1,49"), and each deal's own page lists its products with
  prices in cents, the same shape as AH's range deals. `parse_deal_mechanic` already reads every
  Jumbo deal text except per-weight ("2,49 per kilo") and gift deals.
- **Akamai Bot Manager guards the site.** A request with a browser User-Agent gets through; the
  same request identifying itself honestly gets no answer (connection reset, then a timeout).
- **Jumbo's terms of use forbid scraping**, with no exception for personal use (per the issue
  above).

</details>

#### Step 4 — Continuous deployment, run inside AWS

GitHub Actions can't deploy here: it would log in through OIDC, which this project's managed
policies block, and storing long-lived AWS keys in GitHub is the practice OIDC exists to avoid.
So the pipeline runs inside AWS instead:

- **AWS CodePipeline + CodeBuild,** connected to the GitHub repository through **CodeConnections**
  (a GitHub app; no keys). A merge to `main` starts CodeBuild, which runs `scripts/deploy.sh`. The
  pipeline is a second CDK stack.
- **Check first:** that CodePipeline, CodeBuild and CodeConnections are available on this
  project's plan (`aws freetier get-account-plan-state` and AWS's supported-services list), and
  their free monthly allowances.
- **Security:** CodeBuild's role can deploy the stack, so it's scoped to CDK's bootstrap roles,
  not admin.
- **If it's not available:** the laptop deploy script stays. That's fine for a demo, and the
  reason is worth telling in an interview.

✅ Milestone: merging a PR to `main` updates the live demo with no manual step.

#### Along the way

- **The weekly snapshot:** the AH week starts on Monday; after it starts, run `fetch-deals` and
  upload (later `publish-deals`). Until then the API falls back to the old snapshot's last day.
- **The budget** stays at zero spend with credits excluded; check Cost Explorer after each step
  that adds a service.

### 9.2 Full roadmap (phased)

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
- Deploy: the AWS setup from §9.3 is the starting point. With a database and a second chain, revisit
  whether a scheduled ingestion job on AWS is acceptable (see §9.3 on the snapshot decision).
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
