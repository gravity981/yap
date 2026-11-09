# Contributing

Thank you for helping. This project is maintained in spare time, so please be patient
with answers, and keep changes focused.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Security
problems are reported privately, see [SECURITY.md](SECURITY.md).

## Before you start

- **Bugs and ideas** go into an issue first, using the templates. For larger changes,
  wait for a short agreement in the issue before writing code.
- **Behaviour is specified first.** The requirements live in
  [spec/sw-architecture.md](spec/sw-architecture.md), each with an ID (e.g. `RB-08`).
  A change in behaviour changes or adds a requirement in the same pull request.
- **Never include real financial data** (portfolio values, personal strategies, API keys)
  in issues, tests or examples.

## Development

The [README](README.md) explains the devcontainer, running the app, and the checks. In
short, from `backend`: `ruff check .`, `ruff format --check .`, `mypy yap`,
`pytest`; from `frontend`: `npm run lint`, `npm run format:check`, `npm run typecheck`,
`npm test`, and `npm run e2e` for the end-to-end tests.

- **Tests:** every test names the requirements it verifies — `@pytest.mark.req("RB-08")`
  in the backend, `[RB-08]` in the test name in the frontend. Every requirement needs at
  least one passing test ([test strategy](spec/test-strategy.md)).
- **Generated files:** after changing the API or the import formats, regenerate the API
  types (`npm run gen:api`) and the JSON Schemas; CI fails if they are out of date.
- **Database changes** come with an Alembic migration that also works on existing data.
- **Dependencies:** only releases that are at least two weeks old; Dependabot proposes
  updates monthly.

## Commit messages and release notes

The release notes list the commit messages since the previous release, so write each
first line for the people who use the app. Start with `feat:` (or `Add`) for something
new and `fix:` (or `Fix`) for a fix; other commits are listed as changes.
Housekeeping that users don't care about starts with `chore:`, `docs:`, `test:`, `ci:`
or `build:` and is left out. Dependabot's commits are listed separately.

## Pull requests

- Branch from `main`, one topic per pull request, with a description of what and why.
- CI must be green; it runs all checks and tests.
- Contributions are licensed under the project's license, the
  [GNU Affero General Public License v3.0 or later](LICENSE) (inbound = outbound); there
  is no separate contributor agreement.
