# yap

Guidance for Claude Code in this repository. [CONTRIBUTING.md](CONTRIBUTING.md) and
[README.md](README.md) are the full references; the spec is in [spec/](spec/).

## Commit messages

The release notes are built from the first line of the commit messages since the last
release (`scripts/release.sh changelog`), so write it for the people who use the app:

- `feat: …` (or `Add …`) for something new, `fix: …` (or `Fix …`) for a fix.
- `chore:`, `docs:`, `test:`, `ci:` or `build:` for housekeeping; these are left out of the
  release notes.
- Anything else is listed under "Changed". Don't prefix commits that users won't notice
  with `feat:` or `fix:`.
- Commit or push only when asked.

## Working rules

- Behaviour changes change or add a requirement in `spec/sw-architecture.md` (and the
  user-facing text in `docs/features.md`) in the same change.
- Every test names the requirements it verifies: `@pytest.mark.req("RB-08")` in the
  backend, `[RB-08]` in the test name in the frontend.
- After changing the API, run `npm run gen:api` (frontend); after changing the import
  formats, regenerate the JSON Schemas. CI fails if they are out of date.
- Database changes need an Alembic migration that also works on existing data.
- All UI text exists in English and German (`frontend/src/i18n/`); a missing translation
  fails the checks.

## Checks

- Backend (from `backend`): `ruff check .`, `ruff format --check .`, `mypy yap`, `pytest`.
- Frontend (from `frontend`): `npm run lint`, `npm run format:check`, `npm run build`
  (`tsc -b`; plain `tsc --noEmit` does not catch type errors here), `npm test`,
  `npm run e2e`. `npm run screenshots` regenerates the screenshots in `docs/`.
