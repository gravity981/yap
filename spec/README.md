# YAP – Specification

This folder holds the specification of YAP ("YAP Ain't a Portfolio").

## Purpose

The application supports several investors, each with their own login, in running a rule-based investment strategy. It runs on a server in the home LAN. A policy's thesis, or its thesis and target structure, can be shared with the other investors; portfolios stay private.

1. **Define policies** – write an investment thesis and derive a target structure (target allocations, buy/sell thresholds) from it, in one editor. Thesis + target structure together form a policy. An investor can have several policies and several portfolios; each portfolio follows exactly one policy, and a policy can be used by several portfolios.
2. **Version the policy** – every change creates a new version; one version is active at a time, and the app records when each version was active and why it changed.
3. **Compare with the policy** – the investor enters current position values when needed; the app compares them against the policy version active on that date, so the history stays consistent across policy changes. The app does not track portfolio value.
4. **Rebalance on demand** – the investor asks for rebalancing instructions (fixed rules, section 3.7); a confirmed rebalance is recorded.
5. **Review the policy** – while editing, and again later, an AI reviewer (or an external AI, manually) scores thesis and target structure, checks current news for the assets, gives the thesis a semaphore (good, warning, broken), suggests changes that can be taken over with a click, and proposes target structures when there are none. Missing or outdated reviews are pointed out, never enforced; reviews are kept in a log and can be compared.
6. **Timeline** – policy activations, confirmed rebalances and reviews form a timeline of the investor's strategy decisions.

Theses are written as markdown and target structures in a table, or both are imported as JSON files. The rebalancing rules are hardcoded in the app; the thesis template gives theses their structure.

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

Each stage is one branch, each step one commit; the investor creates branches and commits. Every step leaves CI green: a step takes its requirement IDs off the "not yet implemented" list once they are tested.

| Stage | Goal | Status |
|---|---|---|
| First release | Everything in section 3 of sw-architecture.md as of the first release | Implemented, not yet released |
| 1 Review rework | Simpler thesis template, new review aspects, review in the draft editor with an AI reviewer or manually, per-aspect modification (REV-10) dropped | Done with steps 1.1–1.7; the planned steps 1.8–1.10 are replaced by stage 2 |
| 2 Merged policies | Policy = thesis + target structure in one editor with auto-save, discard and Finalize; one review of everything with take-over suggestions and proposals; reviews that warn, never block; re-reviews and a review log; semaphore instead of thesis status; sharing levels; selling a portfolio with a broken thesis | Done with steps 2.1–2.8 (UX mockups: "YAP policy workflow", https://claude.ai/artifact/4aSR83yFceaCZ3KUwEo6Wu) |
| 3 Catalog | Example policies and shared policies in one catalog, copied into own policies | Specified (THS-10 to THS-15); after stage 2 |

### Stage 2: merged policies

| Step | Content | Requirements |
|---|---|---|
| 2.1 | **Data model and migration.** Thesis title and text on the policy version; reviews per version (one of each kind until the review log of step 2.6); theses and thesis revisions removed (migration as in sw-architecture.md §4.1). Backend API and frontend follow: the separate theses pages go, the policy page and its editor show the thesis. Dropped requirements (THS-02, THS-03, THS-05, POL-10) removed with their tests. | POL-01, POL-02, THS-01, IMP-02, IMP-10 |
| 2.2 | **One review of everything.** One prompt and answer format with T1–T6, P1–P6 and the verdict (scoring version 3: semaphore verdicts with a reason, old verdicts mapped); thesis, target-structure and review scores; thesis status removed; manual reviews without a model. | THS-04, THS-07, REV-01, REV-02, REV-03, REV-05, REV-06, REV-17, REV-19 |
| 2.3 | **Suggestions and proposals.** Structured suggestions (thesis section, position change, add, remove) with Take over, Dismiss and undo; proposed target structures without positions. | REV-07, REV-22 |
| 2.4 | **Drafts.** Auto-save, discard (also of a never activated policy), fingerprints and matching, the summary with Finalize, activation that confirms and never blocks, marks. | POL-06, POL-14, POL-16, POL-17, REV-09, REV-11, REV-20 |
| 2.5 | **Draft editor.** One page with title, thesis and target structure on the left and the review pane on the right; the full review dialog; phone layout. | POL-15, REV-18, REV-24 |
| 2.6 | **Policy page and list.** Review again without a new version, review log and comparison of reviews and versions, the latest review on cards (stars, semaphore, date), semaphore on portfolios and dashboard, sharing levels. | THS-08, POL-09, POL-11, POL-18, POL-19, POL-20, PTF-07, REV-12, REV-21, REV-23 |
| 2.7 | **Rebalancing with a broken or warning thesis.** The choice to sell the whole portfolio (preselected), reference case (k), mode stored, timeline summary; the amber hint. | RB-21, RB-25, RB-26, TL-02 |
| 2.8 | **Wrap-up.** End-to-end flows (write a policy with a review and take-overs, finalize and activate, re-review a year later and compare, sell a portfolio with a broken thesis), docs/features.md and screenshots; no stage 2 IDs left on the list. | – |

### Stage 3: catalog

| Step | Content | Requirements |
|---|---|---|
| 3.1 | Example policies (thesis in English and German, new template) and their loader | THS-13 |
| 3.2 | Catalog API: examples and shared policies with level, search and filter | THS-11, THS-12 |
| 3.3 | Copy into a new policy, with origin | THS-10, THS-14 |
| 3.4 | Catalog page and empty states | THS-11, THS-12, THS-15 |
| 3.5 | Wrap-up: end-to-end copy flow, docs and screenshots | – |
