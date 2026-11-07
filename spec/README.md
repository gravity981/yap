# YAP – Specification

This folder holds the specification of YAP ("YAP Ain't a Portfolio").

## Purpose

The application supports several investors, each with their own login, in running a rule-based investment strategy. It runs on a server in the home LAN. Theses can be shared between investors; policies and portfolios stay private.

1. **Define policies** – work out investment theses and derive a target structure (target allocations, buy/sell thresholds) from them. Thesis + target structure together form a policy. An investor can have several policies and several portfolios; each portfolio follows exactly one policy, and a policy can be used by several portfolios.
2. **Version the policy** – every change creates a new version; one version is active at a time, and the app records when each version was active and why it changed.
3. **Compare with the policy** – the investor enters current position values when needed; the app compares them against the policy version active on that date, so the history stays consistent across policy changes. The app does not track portfolio value.
4. **Rebalance on demand** – the investor asks for rebalancing instructions (fixed rules, section 3.7); a confirmed rebalance is recorded.
5. **Review theses and policies** – while editing, an AI reviewer (or an external AI, manually) scores the draft, checks current news for the assets and suggests changes. Every activation needs a review, and each review is recorded.
6. **Timeline** – policy activations, confirmed rebalances and thesis reviews form a timeline of the investor's strategy decisions.

Theses and target structures are written as markdown, or imported as JSON files. The rebalancing rules are hardcoded in the app; the thesis template gives theses their structure.

## Documents

| Document | Content |
|---|---|
| [sw-architecture.md](sw-architecture.md) | Application type, requirements, architecture and technology choices |
| [test-strategy.md](test-strategy.md) | How requirements and code are tested |

## Status

| Topic | Status |
|---|---|
| Application type | Decided: multi-investor web app on a LAN server |
| Technology stack | Decided and implemented: FastAPI, React + Vite, SQLite, single Docker image |
| Requirements | Drafted; no open points |
| Architecture | Data model drafted (section 4.1) |
| Build, release and deployment | Defined (section 5) |
| Test strategy | Agreed |
| Implementation | First release: all requirements implemented and covered by tests; not yet released |

## Stages

Work after the first release is planned in stages. A stage's new or changed requirements are written into [sw-architecture.md](sw-architecture.md) and listed as "not yet implemented" in [test-strategy.md](test-strategy.md) §8 until the stage is delivered.

| Stage | Goal | Requirements | Status |
|---|---|---|---|
| First release | Everything in section 3 of sw-architecture.md | All except those below | Implemented, not yet released |
| Review rework | Simpler thesis template; review in the draft editor with an AI reviewer or manually with an external AI; every activation needs a review; per-aspect modification (REV-10) dropped | Changed: THS-02, THS-05, THS-07, POL-06, USR-08, TL-02, REV-01, REV-02, REV-08, REV-09, REV-11, REV-16, REV-17. New: REV-18 to REV-20 | Specified |
| Thesis catalog | New investors find example theses (in the new template); shared theses are found in one catalog and can be copied | THS-10 (changed), THS-11 to THS-15 | Specified; after the review rework |
