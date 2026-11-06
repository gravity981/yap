# YAP – Specification

This folder holds the specification of YAP ("YAP Ain't a Portfolio").

## Purpose

The application supports several investors, each with their own login, in running a rule-based investment strategy. It runs on a server in the home LAN. Theses can be shared between investors; policies and portfolios stay private.

1. **Define policies** – work out investment theses and derive a target structure (target allocations, buy/sell thresholds) from them. Thesis + target structure together form a policy. An investor can have several policies and several portfolios; each portfolio follows exactly one policy, and a policy can be used by several portfolios.
2. **Version the policy** – every change creates a new version; one version is active at a time, and the app records when each version was active and why it changed.
3. **Compare with the policy** – the investor enters current position values when needed; the app compares them against the policy version active on that date, so the history stays consistent across policy changes. The app does not track portfolio value.
4. **Rebalance on demand** – the investor asks for rebalancing instructions (fixed rules, section 3.7); a confirmed rebalance is recorded.
5. **Review theses** – the app looks up current news for the assets and assesses whether each thesis still holds, or suggests changes. Each review is recorded.
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
| Technology stack | Backend decided (FastAPI); frontend, database and deployment proposed |
| Requirements | Drafted; no open points |
| Architecture | Data model drafted (section 4.1) |
| Build, release and deployment | Defined (section 5) |
| Test strategy | Agreed |
