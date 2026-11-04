# Koopjeskompas

Koopjeskompas ("bargain compass") ranks nearby Dutch supermarkets by how good their current deals
are **for you**. You give a location and food preferences, such as "vegetarian, Italian-inspired".
It weighs each store's deals by relevance and discount depth, subtracts a penalty for distance,
and shows the deals that earned each store its score.

It's also a practice project in software engineering: clean architecture, testing, typed code and
CI, applied to messy real-world data.

## Status

**MVP steps 1 and 2 of 4 are done.** The app works end to end from the command line on real
Albert Heijn data for Leiden. The web API and frontend come next.

| | Feature | Status |
|---|---|---|
| ✅ | Domain core: deal parsing, diet/cuisine tagging, scoring, distance | done, fully unit-tested |
| ✅ | Real Albert Heijn bonus deals, cached as JSON | done (`fetch-deals`) |
| ✅ | Leiden store list (6 AH supermarkets, from OpenStreetMap) | done |
| ✅ | Ranking in the terminal | done (`rank`) |
| ⏳ | Web API (`POST /api/rank`, FastAPI) | next |
| ⏳ | Web page (React + TypeScript) | planned |
| ⏳ | Public demo on AWS | planned |

**Known limitations:**
- **About half of AH's deals can't be scored yet.** Range deals such as "Alle AH Rauwkost: 2 voor
  €4,00" come without a normal price, so there's nothing to compare the deal price against. They
  are kept but score zero.
- **Diet filtering is based on product names.** Vegetarian and vegan are hard filters: a
  non-matching deal is excluded, not just ranked lower. But a range deal whose name doesn't reveal
  its ingredients ("Alle Unox soep in zak") can still slip through the vegan filter.
- **Only one chain.** Every store has the same deals, so for now the ranking comes down to distance.

## How it works

```
AH mobile API ──► fetch-deals ──► data/raw/ah/<date>/*.json   (raw responses, as received)
                      │
                      ▼  parse at the boundary into validated Deal models
                 data/deals/ah.json
                      │
 stores + your preferences + location ──► rank_stores() ──► ranked stores with their top deals
```

For each store, its chain's active deals are scored:

```
deal value   = discount fraction × relevance to your preferences        (0–1)
store score  = (sum of its top-k deal values) / k − weight × distance penalty
```

- **Discount fraction:** Dutch deal mechanics are normalised into a fraction of the price you save,
  e.g. "2e halve prijs" is 0.25 and "3 voor 5,99" depends on the normal price.
- **Top-k deals only:** stores aren't rewarded for simply having a huge promotion folder.
- **Diet as a hard filter:** a great deal on chicken is worth nothing to a vegetarian, not "a bit
  less".

The design is described in detail in [PLAN.md](PLAN.md).

## Installation

Requirements: [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.14 (uv
installs the right Python for you if needed).

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

## Usage

### 1. Fetch this week's deals

```bash
uv run koopjeskompas fetch-deals
```

This fetches this week's national bonus deals from Albert Heijn: about 20 requests, spaced one
second apart. It saves the raw responses under `data/raw/ah/<date>/` and the parsed deals to
`data/deals/ah.json`, then prints a summary of deals it couldn't score.

Run it at most about once a week; AH's bonus changes weekly. To re-parse earlier responses
without contacting AH again (useful after changing the parser), use:

```bash
uv run koopjeskompas fetch-deals --from-raw
```

### 2. Rank the stores

```bash
uv run koopjeskompas rank --diet vegetarian --cuisine italian
```

Example output (top deals shortened):

```
1. AH Breestraat (Breestraat 130, Leiden) | 1.3 km | score 0.063
    35%  Combideal voor 7.50: AH Verspakket fusilli met oesterzwam  [deal price]
    50%  AH Rode druiven pitloos 500 gram  [1 + 1 GRATIS]
    50%  Alle AH Pancakes en poffertjes 24 stuks  [1 + 1 GRATIS]

2. AH Hooigracht (Hooigracht 85, Leiden) | 1.3 km | score 0.061
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

Two options go *before* the subcommand and work for both commands:

- `--data-dir DIR` stores the cache somewhere other than `./data`.
- `--today YYYY-MM-DD` fetches or ranks as if it were that day. Deals only count during their bonus
  week, so ranking with an old cache shows no deals unless you pass a date inside that week:

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

GitHub Actions runs lint, format check, mypy and the tests on every push and pull request to `main`.

Testing approach:
- **Domain code:** table-driven tests with real Dutch product names and deal mechanics, plus
  property-based tests (`hypothesis`) for the scoring. For example: "adding a deal never lowers a
  store's score", "a vegetarian ranking never contains meat or fish".
- **AH integration:** tests replay real AH responses saved in `tests/fixtures/ah/`, with HTTP mocked
  by `respx`. Tests never contact AH.

### Project structure

```
koopjeskompas/
├── domain/        pure logic, no I/O: models, deal mechanics, tagging, scoring, distance
├── ingestion/     getting deals in: the JSON cache, and ah/ (HTTP client, payload models, parser)
├── stores/        the Leiden store list and the OpenStreetMap query that produced it
├── report.py      formats a ranking for the terminal
└── cli.py         the koopjeskompas command; wires the pieces together
tests/             one test module per module, plus captured AH fixtures
```

The domain layer never imports HTTP or file-handling code. External data, such as AH's JSON, is
validated and converted into domain models the moment it enters (`ingestion/ah/parser.py`), so
AH's data format never spreads through the code.

## Roadmap

Following the MVP roadmap in [PLAN.md §9.1](PLAN.md):

1. ✅ **Domain core:** models, deal mechanics, tagging, scoring.
2. ✅ **One real source:** AH deals for Leiden, ranked in the terminal.
3. **Web API:** `POST /api/rank` with FastAPI, reading the cached deals.
4. **Web page:** a React + TypeScript page with location, preferences and the ranked stores.
5. **Public demo on AWS** ([PLAN.md §9.3](PLAN.md)):
   - S3 + CloudFront for the page, Lambda for the API;
   - defined with AWS CDK and deployed from GitHub Actions;
   - designed to stay within the AWS free plan.

After the MVP:
- **Score range deals:** look up each range's products, so the deals currently scoring zero count.
- **Second chain:** add Jumbo behind a common `DealSource` interface, so rankings differ by more
  than distance.
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
