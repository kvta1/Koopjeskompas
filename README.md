# Koopjeskompas

Koopjeskompas ("bargain compass") ranks nearby Dutch supermarkets by how good their current deals
are **for you**. You give a location and food preferences, such as "vegetarian, Italian-inspired".
It weighs each store's deals by relevance and discount depth, subtracts a penalty for distance,
and shows the deals that earned each store its score.

It's also a practice project in software engineering: clean architecture, testing, typed code and
CI, applied to messy real-world data.

## Status

**The MVP is done.** The app works end to end on real Albert Heijn data, for any postcode or place
in the Netherlands: in the browser, from the command line, through a web API and as a public demo
on AWS.

| | Feature | Status |
|---|---|---|
| ✅ | Domain core: deal parsing, diet/cuisine tagging, scoring, distance | done, fully unit-tested |
| ✅ | Real Albert Heijn bonus deals, cached as JSON | done (`fetch-deals`) |
| ✅ | Every AH, Jumbo and Lidl in the Netherlands (2,138 stores, from OpenStreetMap) | done (`fetch-stores`) |
| ✅ | Postcode and place search (PDOK Locatieserver) | done |
| ✅ | Ranking in the terminal | done (`rank`) |
| ✅ | Range deals priced product by product, per-weight deals | done |
| ✅ | Web API (`POST /api/rank`, FastAPI) | done (`serve`) |
| ✅ | Web page (React + TypeScript) | done (`frontend/`) |
| ✅ | Public demo on AWS | live (S3 + CloudFront + Lambda) |
| ✅ | Infrastructure as code (AWS CDK) and a one-command deploy | done ([infra/aws/](infra/aws/README.md)) |
| ✅ | A second demo on Azure (Container Apps + Static Web Apps), as Terraform | done ([infra/azure/](infra/azure/README.md)) |
| ✅ | Jumbo deals (165 a week, from jumbo.com's deal pages) | done (`fetch-deals --chain jumbo`) |
| ✅ | Lidl deals (about 40 a week, from lidl.nl's deals page) | done (`fetch-deals --chain lidl`) |
| ✅ | The page names each store's chain; the weekly refresh in one command | done (`scripts/refresh-deals.sh`) |
| ✅ | A beer section: crates, cans and bottles by price per litre (AH and Jumbo) | done (`#/beer`, `GET /api/beer`) |
| ⏳ | Continuous deployment | next ([PLAN.md §9.4](PLAN.md)) |

**Known limitations:**
- **Diet filtering is based on product names.** Vegetarian and vegan are hard filters: a
  non-matching deal is excluded, not just ranked lower. But a name that doesn't reveal its
  ingredients can still slip through:
  - ready meals such as "lasagne" or "tikka masala";
  - ranges whose discount doesn't depend on a price ("Alle A-merk diepvriesmaaltijden: 25%
    korting"), because those aren't looked up product by product.
- **A failed range lookup leaves that range unscored.** It's kept, but it scores zero.
- **Only one chain.** Every store has the same deals, so for now the ranking comes down to distance.
- **The store list is as complete as OpenStreetMap.** About 20 AHs are left out because nobody
  mapped their street or town, and the list only changes when `fetch-stores` is run again.

## How it works

```
AH mobile API ──► fetch-deals ──► data/raw/ah/<date>/*.json   (raw responses, as received)
                      │
                      ▼  parse at the boundary into validated Deal models
                 data/deals/ah.json
                      │
 stores + your preferences + location ──► rank_stores() ──► ranked stores with their top deals
                                                         (printed by `rank`, or JSON from
                                                          POST /api/rank via `serve`, shown
                                                          by the web page)
```

For each store, its chain's active deals are scored:

```
deal value   = discount fraction × relevance to your preferences        (0–1)
store score  = (sum of its top-k deal values) / k − weight × distance penalty
```

- **Discount fraction:** Dutch deal mechanics are normalised into a fraction of the price you save,
  e.g. "2e halve prijs" is 0.25 and "3 voor 5,99" depends on the normal price.
- **Top-k deals only:** stores aren't rewarded for simply having a huge promotion folder.
- **Range deals count once:** "2 voor €12 on all fresh pizzas" is valued at the median discount of
  the pizzas that pass your diet filters, not by its single best pizza.
- **Diet as a hard filter:** a great deal on chicken is worth nothing to a vegetarian, not "a bit
  less".

The design is described in detail in [PLAN.md](PLAN.md).

## Installation

Requirements: [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.14 (uv
installs the right Python for you if needed). For the web page, also
[Node.js](https://nodejs.org/) 24 (the version in `frontend/.nvmrc`).

```bash
git clone git@github.com:kvta1/Koopjeskompas.git
cd Koopjeskompas
uv sync --dev
```

This creates a virtual environment in `.venv` with the app and its development tools. Check it
works:

```bash
uv run koopjeskompas --help
```

For the web page, install its packages too:

```bash
cd frontend
npm ci
```

## Usage

### 1. Fetch this week's deals

```bash
uv run koopjeskompas fetch-deals
```

This fetches this week's deals from every chain with a source, each on its own: one chain failing
doesn't stop the others. Requests are spaced one second apart.
- **Albert Heijn**, about 65 requests (roughly a minute): about 20 for the food categories, and
  about 45 lookups for the products of range deals like "Alle AH Verse pizza's: 2 voor €12", which
  AH lists without prices.
- **Jumbo**, about 100 requests (roughly two minutes): the deals page, with this week's and next
  week's deals, and the page of each deal whose discount depends on a price ("2 voor 3,49").
  Jumbo's site blocks requests that identify themselves honestly, so this one presents itself as a
  browser (see the scraping policy in [PLAN.md §9.4](PLAN.md)).

- **Lidl**, one request: the deals page lists every deal with its prices. Lidl Plus prices count
  (they need Lidl's free app) and are named "(met Lidl Plus)".

It saves the raw responses under `data/raw/<chain>/<date>/` and the parsed deals to
`data/deals/<chain>.json`, then prints a summary per chain, including any deals it couldn't score.
`--chain jumbo` fetches one chain only.

Run it at most about once a week; AH's bonus changes weekly. To re-parse earlier responses
without contacting AH again (useful after changing the parser), use:

```bash
uv run koopjeskompas fetch-deals --from-raw
```

### 2. Rank the stores

```bash
uv run koopjeskompas rank --diet vegetarian --cuisine italian
```

Example output (top deals shortened). Deals are ordered by their value to you, the discount
times how well it fits your cuisines, so a 58% soup deal can rank below a 13% pizza deal when
you asked for Italian. "median of 3 products" means three of the eight pizzas in that range are
vegetarian, and the range is scored on those three:

```
1. AH Breestraat (Breestraat 130, Leiden) | 1.3 km | score 0.050
    50%  Alle AH Pizzadeeg  [2e GRATIS]
    17%  AH Ongesneden verspakketten  [1 EURO KORTING]  median of 3 products
    13%  Alle AH Verse pizza's  [2 VOOR 12.00]  median of 3 products
    58%  Unox soep in zak romige of Chinese tomatensoep 570 ml  [VOOR 1.49]  median of 2 products

2. AH Hooigracht (Hooigracht 85, Leiden) | 1.3 km | score 0.048
    ...
```

`rank` options:

| Option | Meaning | Default |
|---|---|---|
| `--lat`, `--lon` | your location | Leiden Centraal |
| `--diet` | `none`, `vegetarian` or `vegan` (hard filter) | `none` |
| `--cuisine` | `middle_eastern`, `italian`, `asian`, `mexican`, `indian`; repeat for several | none |
| `--lactose-free`, `--gluten-free` | exclude deals with lactose or gluten | off |
| `--radius-km` | ignore stores further away than this | 5 |
| `--top-k` | how many deals count towards a store's score | 10 |

### 3. Run the web API

```bash
uv run koopjeskompas serve            # http://127.0.0.1:8000, change with --host and --port
```

Open <http://127.0.0.1:8000/docs> for interactive documentation; the bare address redirects
there. It shows every endpoint, its request and response models, and a "Try it out" button. The
API reads the same deal cache as `rank`; a new `fetch-deals` run is picked up without a restart.
It never contacts AH during a request.

| Endpoint | What it does |
|---|---|
| `GET /api/health` | `{"status": "ok"}` when the server is up |
| `POST /api/rank` | ranks the stores around a location, with the deals behind each score |

```bash
curl -X POST http://127.0.0.1:8000/api/rank \
  -H 'content-type: application/json' \
  -d '{"location": {"lat": 52.1664, "lon": 4.4817}, "diet": "vegetarian", "cuisines": ["italian"]}'
```

The request body has the same options as `rank`: `location` (required), `diet`, `cuisines`,
`gluten_free`, `lactose_free`, `radius_km`, `top_k`, plus `distance_weight` (0 ignores distance).
A response lists `stores` best first. Each store has its `score`, `distance_km` and `top_deals`,
and each deal has its `discount`, `relevance` and `value`.

Error responses:
- **422:** an invalid request, e.g. a latitude of 152 or a misspelled field name. The response
  says what's wrong and where.
- **503:** no deals are cached yet.

### 4. Open the web page

Run the API and the page's development server side by side, each in its own terminal:

```bash
uv run koopjeskompas serve      # terminal 1: the API on port 8000
cd frontend && npm run dev      # terminal 2: the page on http://localhost:5173
```

Open <http://localhost:5173>, type a postcode or place and pick one of the suggestions (or press
"Use my location"), choose a diet and cuisines, and press **Find the best deals**. The stores come back best first; the best store's
deals are shown, and the others open with a click.

The **Beer** link at the top opens the beer section (`#/beer`): this week's beer deals of every
chain as crates, cans and bottles, each cheapest per litre first, the only fair way to compare a
crate with a 6-pack. It needs no location, since a chain's deals are the same in every store.

The development server forwards every `/api` request to the API on port 8000, so to the browser
the page and the API are one site. That's also how the AWS demo will serve them, so the API needs
no CORS settings. The place search is the exception: the browser asks
[PDOK Locatieserver](https://www.pdok.nl/introductie/-/article/pdok-locatieserver-1), the Dutch
government's free geocoder, directly. It needs no key and allows any origin.

### 5. Refresh the store list (now and then)

The stores come from OpenStreetMap, packaged with the code. Stores open and close slowly, so a
refresh every few months is plenty:

```bash
uv run koopjeskompas fetch-stores               # every AH in the Netherlands, via Overpass
uv run koopjeskompas fetch-stores --from-raw    # re-convert the saved answer, no network
```

Overpass is free and often busy. `fetch-stores` asks once: it checks Overpass's status page for a
free query slot first, and stops with a message rather than queue or retry. If it answers 502 or
504, wait and try once more, or use another server with `--server` (a list is on the [OpenStreetMap wiki](https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances)).
A run that finds no stores never overwrites the list.

### Global options

Two options go *before* the subcommand and work for every command:

- `--data-dir DIR` stores the cache somewhere other than `./data`.
- `--today YYYY-MM-DD` fetches, ranks or serves as if it were that day. Deals only count during
  their bonus week, so ranking with an old cache shows no deals unless you pass a date inside that
  week:

  ```bash
  uv run koopjeskompas --today 2026-10-15 rank --diet vegan
  ```

## Development

```bash
uv run pytest                  # run all tests (offline; no network needed)
uv run ruff check .            # lint
uv run ruff format .           # format
uv run mypy .                  # type check (strict)
```

For the web page, in `frontend/`:

```bash
npm test                       # run the tests (Vitest; offline)
npm run lint                   # lint (ESLint)
npm run format                 # format (Prettier)
npm run typecheck              # type check (tsc, strict)
npm run build                  # production build into frontend/dist/
```

GitHub Actions runs all of these on every push and pull request to `main`, in four jobs: the
Python backend, the container image, the Azure Terraform (`fmt`, `validate`, `test`) and the
frontend.

**The API on AWS Lambda** runs the same app behind [Mangum](https://mangum.fastapiexpert.com/)
(`koopjeskompas/cloud/aws/lambda_handler.py`). To build the zip for the function (Python 3.14, arm64):

```bash
scripts/build-lambda.sh                   # writes build/lambda.zip
```

CI builds it too, so a dependency without a Linux arm64 build fails on the pull request.

**The AWS demo** is defined as code with AWS CDK in [`infra/aws/`](infra/aws/README.md), which also
explains bootstrapping and tearing down. Signed in with `aws login`:

```bash
scripts/deploy.sh                         # build the zip and the page, deploy, upload the deals
scripts/refresh-deals.sh                  # weekly: fetch every chain's deals, publish them
```

**The Azure demo** is defined as code with Terraform in [`infra/azure/`](infra/azure/README.md),
which also explains the first-time setup. Signed in with `az login`:

```bash
scripts/deploy-azure.sh                   # image, infrastructure, page and deals
scripts/refresh-deals.sh --azure          # weekly: as above, and publish to Azure too
```

**When the API's request or response models change**, regenerate the page's types and commit
both files (a test and CI fail until you do):

```bash
uv run koopjeskompas openapi              # writes frontend/openapi.json
cd frontend && npm run gen:api            # writes src/api/schema.d.ts from it
```

TypeScript then points at every part of the page that no longer fits the API.

Testing approach:
- **Domain code:** table-driven tests with real Dutch product names and deal mechanics, plus
  property-based tests (`hypothesis`) for the scoring. For example: "adding a deal never lowers a
  store's score", "a vegetarian ranking never contains meat or fish".
- **AH integration:** tests replay real AH responses saved in `tests/fixtures/ah/`, with HTTP mocked
  by `respx`. Tests never contact AH.
- **Web API:** tests send real HTTP requests through FastAPI's `TestClient`, without a running
  server. They swap the deal cache and "today" through FastAPI's dependency overrides.
- **Web page:** tests render the page with React Testing Library and use it the way a person
  would: pick options by their label, click the button, read the result. `fetch` is replaced by a
  stub, so the tests need no server. The page's API types are generated from the API's OpenAPI
  schema, so the two can't drift apart unnoticed.

### Project structure

```
koopjeskompas/
├── domain/        pure logic, no I/O: models, deal mechanics, tagging, scoring, distance
├── ingestion/     getting deals in: the JSON cache, and ah/ (HTTP client, payload models, parser)
├── api/           the web API: request/response models (schemas.py), endpoints (app.py)
│                  and the container entry point for any host (container.py)
├── cloud/         what knows a cloud exists: the snapshot download (snapshots.py),
│                  aws/ (S3, the Lambda entry point) and azure/ (Blob Storage)
├── chains.py      the chains Koopjeskompas knows (AH, Jumbo, Lidl), in one place
├── stores/        every store in NL (nl_stores.json), and osm.py, which asks OpenStreetMap for
│                  them and turns the answer into stores (koopjeskompas fetch-stores)
├── report.py      formats a ranking for the terminal
└── cli.py         the koopjeskompas command; wires the pieces together
tests/             mirrors koopjeskompas/: domain/test_scoring.py tests domain/scoring.py,
                   and so on; fixtures/ah/ holds the captured AH responses
├── publish.py     uploads the deal snapshots to the AWS or Azure demo
infra/             the demos as code, one folder per cloud (README.md compares them):
├── aws/           AWS CDK: stack.py, app.py; tests in tests/infra/aws/
└── azure/         Terraform: *.tf; tests in infra/azure/tests/
scripts/           build-lambda.sh packages the API for Lambda; deploy.sh and deploy-azure.sh
                   deploy everything; refresh-deals.sh is the weekly routine
frontend/          the web page (React + TypeScript + Vite)
├── openapi.json   the API's schema, written by `koopjeskompas openapi`
└── src/
    ├── api/       the API client, and the types generated from openapi.json
    ├── components/  the form, its location picker, and the ranked stores
    └── App.tsx    the page: sends the form to the API and shows the result
```

Frontend tests sit next to the code they test (`format.test.ts` beside `format.ts`), the usual
convention in TypeScript projects.

The domain layer never imports HTTP or file-handling code. External data, such as AH's JSON, is
validated and converted into domain models the moment it enters (`ingestion/ah/parser.py`), so
AH's data format never spreads through the code.

## Roadmap

Following the MVP roadmap in [PLAN.md §9.1](PLAN.md):

1. ✅ **Domain core:** models, deal mechanics, tagging, scoring.
2. ✅ **One real source:** AH deals for Leiden, ranked in the terminal.
3. ✅ **Web API:** `POST /api/rank` with FastAPI, reading the cached deals.
4. ✅ **Web page:** a React + TypeScript page with location, preferences and the ranked stores.
5. ✅ **Public demo on AWS** ([PLAN.md §9.3](PLAN.md)): S3 + CloudFront for the page, Lambda for
   the API, within the AWS free plan.

Next, in this order ([PLAN.md §9.4](PLAN.md)):
1. ✅ **Infrastructure as code:** the AWS setup as a CDK stack, deployed with one command.
2. ✅ **Your own location, anywhere in the Netherlands:** every AH in the country from OpenStreetMap,
   and a place and postcode search in the page with PDOK's free Locatieserver.
3. **More chains:** Jumbo and Lidl next to AH, behind a common `DealSource` interface, so
   rankings differ by more than distance.
4. **Continuous deployment** with AWS CodePipeline, since this AWS project can't use GitHub
   Actions' OIDC login.

Later:
- **Use AH's own diet labels:** AH's product data includes fields like "vegetarisch" and "geen
  gluten". They could replace much of the name-based tagging.
- **Database:** SQLite/PostgreSQL with migrations, replacing the JSON cache.
- **Better matching:** LLM-based tagging at ingestion time, so diet filters can use ingredients
  rather than product names.
- **Stretch goals:** a map view, cycling-time distances, price history and a "what can I cook
  cheaply this week?" mode.

## Data sources and disclaimer

- **Deals:** Albert Heijn's unofficial mobile app API. It isn't a public API and may change or
  stop working at any time. This is a personal, non-commercial learning project. It fetches deals at
  most about once a week, at low volume, and isn't affiliated with or endorsed by Albert Heijn.
- **Store locations:** © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors,
  available under the Open Database License (ODbL).

## License

[Apache License 2.0](LICENSE)
