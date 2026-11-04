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
decisions. Current status: **MVP steps 1–2 are done** — the pure domain core
(`koopjeskompas/domain/`), real AH bonus deals fetched and cached as JSON
(`koopjeskompas/ingestion/`), a hardcoded Leiden store list (`koopjeskompas/stores/`) and a
`koopjeskompas` CLI that prints a ranking. Next is MVP step 3 (a minimal `POST /api/rank`).

## Commands

This project uses `uv` for packaging/dependency management (Python >=3.14, pinned via `.python-version`).

```bash
uv sync --dev              # install dependencies (including dev group: pytest, ruff, mypy, pre-commit)
uv run pytest              # run the full test suite
uv run pytest path/to/test_file.py::test_name   # run a single test
uv run ruff check .        # lint
uv run ruff format --check .   # format check (use `uv run ruff format .` to fix)
uv run mypy .              # type check

uv run koopjeskompas fetch-deals               # fetch this week's AH bonus (live, ~20 requests)
uv run koopjeskompas fetch-deals --from-raw    # re-parse the saved raw responses, no network
uv run koopjeskompas rank --diet vegetarian --cuisine middle_eastern
```

`fetch-deals` writes raw AH responses to `data/raw/ah/<date>/` and parsed deals to
`data/deals/ah.json` (`data/` is gitignored). It hits AH's unofficial mobile API: run it at most about
once a week, never in tests or CI. Tests replay captured responses from `tests/fixtures/ah/` and mock
HTTP with `respx`. If AH changes its API, use `--from-raw` while fixing the parser rather than
refetching.

CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check`, `mypy` (strict, pydantic
plugin; configured in `pyproject.toml`) and `pytest` on every push/PR to `main`. Keep changes green
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
  For now (MVP) there is one source, AH, as plain modules in `ingestion/ah/`: `client.py` (HTTP,
  saves raw responses), `payloads.py` (Pydantic models of AH's JSON) and `parser.py` (pure,
  payload → `Deal`); the `DealSource` interface waits until a second chain exists. Deals go to a
  JSON cache (`ingestion/cache.py`) instead of a DB.
- **API (FastAPI)**: read-only against the DB — `/api/rank`, `/api/stores`, `/api/deals`. Never
  scrapes or hits external sources synchronously in a request.
- **Data model**: deals are per-chain (national promotions), not per-store; a store's deal set is its
  chain's active deals. See PLAN.md §4.4 for the schema sketch.
- **Frontend**: React + TypeScript + Vite, calling the FastAPI backend over HTTP.

Key invariant carried through every layer: vegetarian/vegan preference is a **hard filter**, not a
soft relevance score.
