# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Koopjeskompas ("deals compass") is a web app that ranks nearby Dutch supermarkets by how good their
current deals are for a given user's food preferences (e.g. "vegetarian, Middle Eastern inspired"),
weighing deal relevance, discount depth, and distance.

The primary goal of the project is to practice software engineering best practices — clean
architecture, unit testing, CI, typed code, documentation — on a system with real-world messiness.
The full design doc and phased roadmap live in `PLAN.md` (concept, architecture, tech stack, data
sources, scoring formula, API design, and an 8-phase build order). Read it before making
architectural decisions — this repo is currently at **Phase 0 (foundations)**: tooling is wired up
but no domain code exists yet beyond a placeholder `main.py`.

## Commands

This project uses `uv` for packaging/dependency management (Python >=3.14, pinned via `.python-version`).

```bash
uv sync --dev              # install dependencies (including dev group: pytest, ruff, mypy, pre-commit)
uv run pytest              # run the full test suite
uv run pytest path/to/test_file.py::test_name   # run a single test
uv run ruff check .        # lint
uv run ruff format --check .   # format check (use `uv run ruff format .` to fix)
uv run mypy .              # type check
```

CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check`, and `pytest` on every push/PR
to `main`. Keep changes green against this pipeline; there is no ruff/mypy config section in
`pyproject.toml` yet and no `.pre-commit-config.yaml`, despite `pre-commit` being a listed dependency —
if you add one, make sure it mirrors the CI checks rather than diverging from them.

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
- **API (FastAPI)**: read-only against the DB — `/api/rank`, `/api/stores`, `/api/deals`. Never
  scrapes or hits external sources synchronously in a request.
- **Data model**: deals are per-chain (national promotions), not per-store; a store's deal set is its
  chain's active deals. See PLAN.md §4.4 for the schema sketch.
- **Frontend**: React + TypeScript + Vite, calling the FastAPI backend over HTTP.

Key invariant carried through every layer: vegetarian/vegan preference is a **hard filter**, not a
soft relevance score.
