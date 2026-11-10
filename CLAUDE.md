# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Koopjeskompas ("deals compass") is a web app that ranks nearby Dutch supermarkets by how good their
current deals are for a given user's food preferences (e.g. "vegetarian, Middle Eastern inspired"),
weighing deal relevance, discount depth, and distance.

The project is a learning vehicle for software engineering best practices — clean architecture,
unit testing, CI, typed code, documentation — on a system with real-world messiness. The user does
not need to implement it by hand: Claude writes the code, and the user learns by reading and
reviewing it. So favour code that is idiomatic and easy to learn from, and explain non-obvious design
choices. The full design doc and phased roadmap live in `PLAN.md` (concept, architecture, tech stack,
data sources, scoring formula, API design, MVP roadmap in §9.1). Read it before making architectural
decisions. Current status: **the MVP (steps 1–4) is done** — the pure domain core
(`koopjeskompas/domain/`), real AH bonus deals fetched and cached as JSON
(`koopjeskompas/ingestion/`), a store list (`koopjeskompas/stores/`; every store of every registered chain in NL) and a
`koopjeskompas` CLI that prints a ranking. Step 2b is done too: range deals are looked up product by
product and per-weight deals are scored. Step 3 added the web API (`koopjeskompas/api/`:
`POST /api/rank`, `GET /api/health`). Step 4 added the web page (`frontend/`). The AWS demo (PLAN.md §9.3) is in
live, first built by hand in the console by the user to learn it (the user does the AWS steps
themselves; Claude explains and checks read-only). PLAN.md §9.4 steps 1 (CDK in `infra/`,
`scripts/deploy.sh`, `publish-deals`) and 2 (every AH in NL via `fetch-stores`, postcode and place
search with PDOK in the page) are done. Step 3 adds Jumbo and Lidl next to AH, in four parts
(3a multi-chain foundations, 3b Jumbo, 3c Lidl, 3d page and weekly routine); the `DealSource`
interface (`ingestion/source.py`, `ingestion/ah/source.py`) is built. Follow the scraping policy
in PLAN.md §9.4 step 3: a browser identity is allowed when an honest one is blocked, but deal
pages only, a fixed pause, one request at a time, and no CAPTCHA solving, proxies or forged
bot-detection data. Step 4 is continuous deployment inside AWS.

## Commands

This project uses `uv` for packaging/dependency management (Python >=3.14, pinned via `.python-version`).

```bash
uv sync --dev              # install dependencies (including dev group: pytest, ruff, mypy, pre-commit)
uv run pytest              # run the full test suite
uv run pytest tests/domain/test_scoring.py::test_name   # run a single test
uv run ruff check .        # lint
uv run ruff format --check .   # format check (use `uv run ruff format .` to fix)
uv run mypy .              # type check

uv run koopjeskompas fetch-deals               # this week's deals of every chain (live: AH ~65, Jumbo ~100 requests)
uv run koopjeskompas fetch-deals --from-raw    # re-parse the saved raw responses, no network
uv run koopjeskompas rank --diet vegetarian --cuisine middle_eastern
uv run koopjeskompas serve                     # web API on 127.0.0.1:8000, Swagger UI at /docs
uv run koopjeskompas openapi                   # write the API schema to frontend/openapi.json
uv run koopjeskompas fetch-stores              # every chain's stores in NL from OpenStreetMap (Overpass); now and then
uv run koopjeskompas fetch-deals --chain ah    # one chain only (default: every chain with a source)

cd frontend                # Node 24 (.nvmrc), npm
npm ci                     # install
npm run dev                # page on localhost:5173; proxies /api to 127.0.0.1:8000
npm test                   # Vitest + React Testing Library
npm run lint && npm run format:check && npm run typecheck && npm run build
npm run gen:api            # regenerate src/api/schema.d.ts from openapi.json

scripts/build-lambda.sh    # build/lambda.zip for AWS Lambda (python3.14, arm64); CI runs it too
scripts/deploy.sh          # the user's deploy (needs `aws login`): zip, page, cdk deploy, publish-deals
uv run koopjeskompas publish-deals   # upload data/deals/*.json to the demo's data bucket
cd infra && npx cdk synth  # synthesise the CloudFormation template (no AWS needed); cdk diff to compare
```

`fetch-deals` writes raw AH responses to `data/raw/ah/<date>/` (`metadata.json`, one
`section_<category>.json` per food category and one `range_<segmentId>.json` per looked-up range) and
parsed deals to `data/deals/ah.json` (`data/` is gitignored). It hits AH's unofficial mobile API: run it at most about
once a week, never in tests or CI. `tests/` mirrors the package (`tests/domain/test_scoring.py` tests
`koopjeskompas/domain/scoring.py`; every test folder has an `__init__.py`). Tests replay captured
responses from `tests/fixtures/ah/` (loaded through `tests/ah_fixtures.py`) and mock
HTTP with `respx`. If AH changes its API, use `--from-raw` while fixing the parser rather than
refetching.

CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check`, `mypy` (strict, pydantic
plugin; configured in `pyproject.toml`) and `pytest` on every push/PR to `main`, and in a second
job the frontend's checks (generated types current, ESLint, Prettier, tsc, Vitest, Vite build). Keep changes green
against this pipeline. There is no `.pre-commit-config.yaml` yet despite `pre-commit` being a dev
dependency — if you add one, make it mirror the CI checks rather than diverging from them.

## Architecture (target — see PLAN.md for full detail)

The intended design is a modular monolith with a strict separation between the domain core and I/O
(hexagonal / ports-and-adapters style), not microservices:

- **Domain core (pure Python, no HTTP/DB imports)**: deal-mechanic parsing (e.g. normalizing
  "2e halve prijs" / "2 voor €5" into discount fractions), preference→deal tag matching, the
  store-scoring function, and haversine distance. This layer should be exhaustively unit tested
  (table-driven tests, `hypothesis` property-based tests for the scoring function) because it has no
  external dependencies.
- **Ingestion**: a separate scheduled CLI process (not part of the request cycle) that scrapes/pulls
  deals per supermarket chain behind a common `DealSource` interface (one implementation per chain,
  e.g. `AlbertHeijnSource`, `JumboSource`), and writes to the DB. Raw external payloads must be parsed
  into validated internal `Deal` models immediately at the boundary — never let scraped JSON shapes
  leak into domain code. Failures in one source must not take down others (graceful degradation).
  Jumbo (`ingestion/jumbo/`: the same four modules plus `source.py`) reads jumbo.com's deal
  pages through `PoliteClient` with `BROWSER_HEADERS` (Akamai blocks honest requests): the
  overview (`/aanbiedingen/nu`, this and next week, Wednesday to Tuesday) and, per promotion
  whose discount needs a price, its own page (products with `price` = normal price in cents).
  Only each page's `__NUXT_DATA__` is saved (`data/raw/jumbo/<date>/`). Promotions are
  deduplicated by id with the aisle as category; online-only, non-food and hidden ones are left
  out; product availability is ignored (`DELISTED` means off the webshop, not out of stores).
  Tests use `tests/jumbo_fixtures.py` (real pages from 2026-11-10, and `pack`/`page_with` to build
  pages). AH: as plain modules in `ingestion/ah/`: `client.py` (HTTP,
  saves raw responses; REST for the bonus sections, GraphQL `bonusPromotions` for range products),
  `payloads.py` (Pydantic models of AH's JSON) and `parser.py` (pure, payload → `Deal`); the
  `DealSource` interface (`ingestion/source.py`) now exists, with `AhSource` as its first
  implementation; `fetch-deals` runs each source on its own (`--chain` picks one). A range deal is a `Deal` with
  `products`; scoring values it at the median of its products that pass the diet filters. Deals go to a
  JSON cache (`ingestion/cache.py`) instead of a DB.
- **API (FastAPI)**: read-only against the DB — `/api/rank`, `/api/stores`, `/api/deals`. Never
  scrapes or hits external sources synchronously in a request. Built so far: `api/app.py`
  (`create_app(data_dir)` factory; deals, stores and today are FastAPI dependencies, so tests swap
  them via `dependency_overrides`), `api/lambda_handler.py` (the same app behind Mangum for AWS
  Lambda; downloads every registered chain's snapshot (`deals/<key>.json`) from S3 into `/tmp`
  per cold start, skipping missing ones, configured by `DEALS_BUCKET`) and `api/schemas.py` (the HTTP contract, deliberately separate
  from the domain models; `extra="forbid"` so misspelled fields are a 422). Endpoints are sync
  `def`: scoring is CPU-bound. Tests use `TestClient` (needs the `httpx2` dev dependency).
- **Chains** (`koopjeskompas/chains.py`): the registry of AH, Jumbo and Lidl: the `name` deals
  and stores meet on ("AH"), the `key` for the command line and files ("ah"), and how
  OpenStreetMap knows the brand. Dependency-free, so the Lambda can import it. The API, `rank`
  and the Lambda read every chain's snapshot (`ingestion/cache.load_snapshots`); stores of a
  chain without one aren't offered, and each chain falls back to its own day
  (`domain.scoring.chain_ranking_days`, passed to `rank_stores` as `chain_days`).
- **Web-page sources** share `ingestion/http.py` (`PoliteClient`: fixed pause, raw answers
  saved before parsing, a block (403/429, or a bot-check page) stops that source for the run;
  honest headers by default, `BROWSER_HEADERS` where a site blocks them) and
  `ingestion/nuxt.py` (unpacks `__NUXT_DATA__`, the devalue format).
- **Stores** (`koopjeskompas/stores/`): packaged JSON from OpenStreetMap (`nl_stores.json`).
  `osm.py` builds one Overpass query from the chain registry and converts the answer (chain by
  Wikidata ID, else brand, else name; point or building centre; named by street/branch/town;
  deduplicated within 100 m; sorted). Overpass is often busy and can answer
  200 with a runtime error in `remark`; both are errors, and an empty result never overwrites the
  list. Tests use a hand-built fixture in Overpass's format (`tests/fixtures/osm/`) and respx.
- **Data model**: deals are per-chain (national promotions), not per-store; a store's deal set is its
  chain's active deals. See PLAN.md §4.4 for the schema sketch.
- **Frontend** (`frontend/`): React + TypeScript + Vite, calling the FastAPI backend over HTTP.
  The API types are generated, never hand-written: `koopjeskompas openapi` writes
  `frontend/openapi.json` (a pytest test fails when it's stale) and `npm run gen:api` turns it into
  `src/api/schema.d.ts` (CI fails when that's stale). So after changing `api/schemas.py`, run both
  and commit both. In development Vite proxies `/api` to the API, so the browser sees one origin
  and no CORS is configured (production will be one origin too, via CloudFront). Plain CSS with
  colour tokens; components hold no fetch logic (`src/api/client.ts` does); tests sit next to the
  code (`*.test.ts(x)`) and stub `fetch`. The place search (`src/api/pdok.ts`,
  `components/PlaceSearch.tsx`) calls PDOK Locatieserver straight from the browser
  (`suggest`, then `lookup`; `centroide_ll` is `POINT(lon lat)`, longitude first). TypeScript stays on 5.9 because typescript-eslint and
  openapi-typescript don't support TypeScript 7 yet.
- **Infrastructure** (`infra/`): an AWS CDK app in Python (`stack.py`, `app.py`; the `cdk` CLI is
  pinned in `infra/package.json`). Its libraries are the `infra` dependency group, a default
  group, so `uv sync` installs it, while `build-lambda.sh` exports no groups at all. The group
  also holds `botocore[crt]`: boto3 needs it to use `aws login` credentials (for
  `publish-deals`); the Lambda uses its role and doesn't. `build-lambda.sh` makes a reproducible
  zip (sorted entries, fixed timestamps), so an unchanged build doesn't redeploy the function. The stack
  takes the Lambda code and page files as parameters; `tests/infra/` synthesises it with stand-ins
  and checks the template, with no AWS. Names shared with the app (Region, stack name, `deals/`
  prefix, the bucket output) live in `koopjeskompas/publish.py`; `infra/` imports them, never the
  other way round. Only eu-north-1 (CloudFront is global); no Lambda@Edge.

Key invariant carried through every layer: vegetarian/vegan preference is a **hard filter**, not a
soft relevance score.
