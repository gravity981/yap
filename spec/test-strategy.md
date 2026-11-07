# Test Strategy

Status: **agreed**.

## 1. Goals

- Every requirement in [sw-architecture.md](sw-architecture.md) is verified (NFR-11), and it is visible which test verifies which requirement.
- Code is covered by unit tests (NFR-12).
- All automated tests run with one command and must pass before a merge (NFR-13).
- The rebalancing calculation gives the approved results of the reference cases (RB-21), with money as decimals (NFR-04).

## 2. Test levels

| Level | What | Tools | Runs |
|---|---|---|---|
| Unit – backend | Core library without database or web: rebalancing phases, bands and band status, midband, policy version resolution, scoring input preparation, import validation rules, version string generation | pytest | Every CI run |
| Unit – frontend | Components, hooks, formatting (numbers, dates, UTC → local time), form validation | Vitest + React Testing Library | Every CI run |
| Integration – backend | API endpoints through FastAPI's test client against a temporary SQLite database with all migrations applied: auth, sessions, data isolation, revisions, activation, snapshots, rebalance confirmation, timeline events, imports, review jobs (with mocked LLM) | pytest + httpx | Every CI run |
| End-to-end | Main user flows in a real browser against the running app: login, create policy and activate, create portfolio, enter snapshot, rebalance and confirm, import JSON, start review (mocked LLM) | Playwright | CI on `main` and in the release-candidate workflow |
| Image smoke test | Built image starts, migrations run, `GET /api/version` returns the expected version, `GET /api/health` is healthy | shell script in CI | Every CI run with image build |
| Manual acceptance | Things that cannot be automated meaningfully: usability on phone and desktop (NFR-06), login over plain HTTP from another LAN device and deployment on the server (NFR-02, NFR-09), backup/restore on the server (NFR-08), one live review per configured LLM provider | Checklist (section 9) | On staging, for every release candidate before promotion |

## 3. Requirement traceability

- **Backend:** each test that verifies a requirement carries a marker with the requirement ID(s):

  ```python
  @pytest.mark.req("RB-07", "RB-06")
  def test_buffer_is_split_proportionally_to_deficit(): ...
  ```

- **Frontend and end-to-end:** the requirement IDs are the first part of the test name:

  ```ts
  it("[CMP-05] shows band status per position", () => { ... })
  ```

- **Manual tests:** each checklist item (section 9) lists the requirement IDs it verifies.
- **Report:** a script reads all requirement IDs from the tables in `sw-architecture.md`, collects the IDs from pytest, Vitest and Playwright results and from the manual checklist, and produces a coverage table: requirement → tests → result. CI publishes it as a job summary.
- **Failing rule:** CI fails if a requirement has no passing automated or manual test, unless it is listed in section 8 ("not yet implemented"). Requirements of a planned stage (spec/README.md) are on that list until the stage is delivered; it is empty at the first release.

## 4. Verification method per requirement group

| Group | Method |
|---|---|
| USR (users, access) | Integration; USR-07 session timeouts with controlled time |
| THS (theses) | Unit for revision and status rules, integration for API, Vitest for editor/preview/diff; catalog: integration for listing and visibility (shared, made private, other investors), copy origin, examples in both languages; Playwright for copy from the catalog |
| POL (policies) | Unit for version resolution and validation, integration for activation and immutability |
| PTF (portfolios) | Integration (assignment history, reassignment, archive rules) |
| CMP (comparison) | Unit for allocation, deviation and band status; integration for snapshot ↔ policy version linkage |
| RB (rebalancing) | Unit with reference cases (section 5), including the conversion into units (RB-24); integration for the fresh snapshot, confirmation with executed units and resulting snapshot; Vitest for display and rounding |
| TL (timeline) | Integration: each event type is written in the same transaction as its source |
| REV (reviews) | Unit for scoring (averaging, rounding to 0.5, outdated check incl. prompt ID), prompt building (content per review kind, nothing else sent, NFR-01) and answer validation (valid, malformed JSON, missing aspect, score outside 0–10 or not in 0.5 steps, wrong prompt ID, code fence around the JSON); integration with a mocked LLM (section 6) for both review kinds and both methods, activation blocked without a current review, sharing blocked for not reviewed theses, reviewer stored with the review, migration of modified reviews; Vitest for the review pane (method choice, copy button only for manual, result filling in, outdated mark) and star display; Playwright for a manual thesis review from copy to activation; integration for AI reviewers (choice, disabled and archived ones, limit per reviewer), key encryption (key never returned), and the monthly limit with controlled time; manual live review on staging |
| PRC (prices) | Unit for lookup selection, cache expiry, call counting and the order of the update (oldest first), schedule calculation across daylight saving changes, unit conversion with exchange rates; integration with a fake price provider (section 6) for lookup in policy drafts, import previews and snapshots, `unresolved` and "try auto", unavailable listings, provider disabled/archived, key encryption; Vitest for the price sources settings, candidate choice and stale-price marker; manual live update on staging |
| IMP (import) | Unit for each schema and business rule (valid and invalid files, error paths); integration for all-or-nothing behaviour |
| NFR-01 privacy | Integration: the requests sent to the mocked LLM and the fake price provider are inspected; no amounts, units, names or IDs |
| NFR-02 security | Integration for hashing, cookie flags (with and without `COOKIE_SECURE`), rate limit; manual login over HTTP from another LAN device |
| NFR-03 isolation | Integration: generated test over *all* API routes (section 7) |
| NFR-04 accuracy | Unit: decimal types end-to-end; reference cases (section 5) |
| NFR-05 history | Integration: update/delete attempts on append-only tables are rejected; past snapshots show the same values after later changes |
| NFR-06 usability | Manual |
| NFR-07 performance | Unit benchmark for rebalancing (50 positions < 1 s); page load manual on staging |
| NFR-08 backup | Integration for the backup command; manual restore on staging |
| NFR-09 operations | Image smoke test; manual on staging |
| NFR-11 – NFR-13 | Fulfilled by this strategy and the CI setup; a test checks that CI runs on every change and enforces the coverage targets (`tests/tools/test_ci_setup.py`); branch protection by hand (section 9) |
| NFR-15, NFR-16 notices | Vitest: notices and links on the pages named; image smoke test: licenses file served |
| NFR-14 time | Unit for UTC handling and conversion; tests run with a fixed clock and in a non-UTC time zone to catch local-time bugs |

## 5. Rebalancing reference cases

- Reference cases are JSON files in `backend/tests/reference/`: input (positions, values, targets, thresholds, thesis status, contribution, withdrawal) and expected output per phase and position.
- Each case has a description with the requirements it covers, how its expected values were obtained (`calculation`), and whether the product owner has reviewed and approved it (`approved`). Expected amounts are rounded to cents and compared with a tolerance of 0.01 (RB-21).
- Required cases include: no buffer; buffer covering all dips; buffer too small; multiple dips (because need and weight are both proportional to the dip depth when measured against the total value, either all dips are filled or none is; there is no partial capping); sell above threshold; exit flag; position not in policy; more than one cash buffer (rejected); withdrawal covered by sells; withdrawal larger than contribution + sells (sold from positions above target, then by target); contribution and withdrawal together; contribution 0; all positions at target; empty portfolio (total 0); targets not summing to 100 %; units (RB-24): buys and sells rounded to whole units, fractional units, complete sell of all units, positions without known units, and the unallocated cash left by rounding.

## 6. External services

- **LLM providers** (Anthropic, OpenAI, Google) are never called by automated tests. Each provider adapter is unit-tested against recorded responses of its API (normal result with web search, API error); the review logic is tested through a fake adapter that returns (thesis review per verdict, policy review, malformed response, score outside 0–10 or not in 0.5 steps, timeout, API error). Tests check request content (NFR-01), result parsing, scoring storage, and job states.
- **Price providers** (EODHD, Yahoo Finance, CoinGecko) and the exchange rate source are never called by automated tests either. Each adapter is unit-tested against recorded responses (lookup with one, several and no listings; price; not found; quota used up; API error); everything else uses a fake price provider with configurable listings, prices and failures, also in the e2e tests (like `LLM_FAKE`, refused when `APP_ENV=prod`).
- **Live check:** one manual review per configured LLM provider and one price update per configured price provider on staging per release candidate (checklist items), no live calls in CI.

## 7. Data isolation test (NFR-03)

- Test fixtures create two investors (A, B), an admin and an account with both roles, each with data in every table.
- A generated test iterates over every API route of the app and calls it as B with A's resource IDs; every call must return 404 (not 403, so existence is not revealed). As admin, every investor-data route must return 403/404; an account with both roles gets 404 for A's resources like B.
- A new route without coverage in this test fails CI.

## 8. Test environment and data

- Each test gets a fresh SQLite database (temporary file, all Alembic migrations applied). The dev and prod volumes are never used.
- Test data is created with factory functions in code, not shared fixture files (except the reference cases and import examples).
- Time is controlled with a fixed clock; tests run with `TZ` set to a non-UTC zone.
- **Not yet implemented** (excluded from the failing rule in section 3; must be empty at the first release): THS-02, THS-05, POL-06, REV-01, REV-11, REV-18, REV-19, REV-20, THS-10, THS-11, THS-12, THS-13, THS-14, THS-15

## 9. Manual acceptance checklist (staging, per release candidate)

Done on staging for every release candidate, before it is promoted. The result is noted
in the candidate's GitHub pre-release.

| # | Steps | Expected result | Requirements |
|---|---|---|---|
| 1 | `./deploy.sh staging <version>-rc.N` | Prints "Deployed …"; the footer shows `<version>-rc.N` (5.7) | NFR-09 |
| 2 | Open the app from another device in the LAN over plain HTTP and log in | Login works; the session lasts across page loads | NFR-02, USR-01 |
| 3 | Use it on a phone: dashboard, enter units of a portfolio with 10 positions, rebalance | Usable without zooming; entering the snapshot takes under 2 minutes | NFR-06 |
| 4 | Open the main pages and a rebalance | Each loads in under 1 s | NFR-07 |
| 5 | `docker compose exec -T app python -m yap.cli backup /backups/check.db`, then `./deploy.sh staging <same tag> --restore check.db` | Backup file exists; after the restore the app runs with the same data | NFR-08 |
| 6 | Per configured provider: set the AI reviewer's API key (staging has its own secret), choose it in the investor's settings, Test connection, run a thesis and a policy review on a draft. Once: copy a manual review prompt into an external AI, paste its answer | Connection ok; both reviews finish with six scored aspects, the thesis review with sources; the external AI's answer is accepted | REV-04, REV-05, REV-14, REV-18, REV-19 |
| 7 | GitHub settings: branch protection on `main` requires the CI workflow; tag ruleset protects `v*` | Both active | NFR-13, spec 5.4 |
| 8 | Per configured price provider and for the built-in exchange rate source: Test connection; look up a ticker; run `update-prices` | Connection ok; listings found; prices, exchange rates and update times shown in the price sources settings and on the admin page, the exchange rate source marked as built-in | PRC-01, PRC-02, PRC-07, PRC-10, PRC-11 |

## 10. Coverage targets

| Area | Target |
|---|---|
| Rebalancing, policy version resolution, import validation (NFR-12) | 100 % line and branch coverage |
| Backend overall | ≥ 90 % line coverage |
| Frontend overall | ≥ 80 % line coverage |

CI fails if a target is not met.

## 11. Bugs

Every bug fix starts with a failing test that reproduces it. The test carries the requirement ID it concerns.
