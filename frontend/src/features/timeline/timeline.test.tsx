import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { investor, json, mockApi, renderApp, type Handler } from "@/test/utils";

import { localDayEnd, localDayStart } from "./timeline";

const event = (id: number, type: string, summary: string, extra: Record<string, unknown> = {}) => ({
  id,
  occurred_at: `2026-0${id}-01T10:00:00+00:00`,
  type,
  summary,
  portfolio_id: null,
  policy_version_id: null,
  rebalance_id: null,
  review_id: null,
  ...extra,
});

const events = [
  event(1, "policy_activated", "core-v1 activated (no portfolios)", { policy_version_id: 201 }),
  event(2, "policy_activated", "core-v2 activated (Main): less ETH", { policy_version_id: 202 }),
  event(3, "rebalance_confirmed", "Main: rebalanced, sold 140, bought 150", {
    portfolio_id: 5,
    rebalance_id: 77,
  }),
  // From before policies held their thesis: shown with its summary only
  event(4, "thesis_revised", "Thesis 'Core' has a new revision 2"),
];

const policies = [
  {
    id: 3,
    name: "core",
    archived_at: null,
    active_version_label: "core-v2",
    has_draft: false,
    thesis_warning: false,
    semaphore: "good",
  },
  {
    id: 4,
    name: "growth",
    archived_at: null,
    active_version_label: "growth-v1",
    has_draft: false,
    thesis_warning: true,
    semaphore: "warning",
  },
];

function setup(handlers: Record<string, Handler> = {}) {
  return mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(investor),
    "GET /api/timeline": () => json(events),
    "GET /api/portfolios": () =>
      json([
        {
          id: 5,
          name: "Main",
          policy_id: 3,
          policy_name: "core",
          policy_semaphore: "broken",
          policy_semaphore_reason: "A break condition is met.",
          archived_at: null,
          latest_snapshot: null,
        },
      ]),
    "GET /api/policies": () => json(policies),
    "GET /api/policy-versions/202": () =>
      json({
        id: 202,
        version_no: 2,
        label: "core-v2",
        change_note: "less ETH",
        policy_id: 3,
        policy_name: "core",
        positions: [],
      }),
    "GET /api/policies/3/compare": () =>
      json({
        positions: [{ ticker: "ETH", change: "changed", fields: { target_pct: ["20", "18"] } }],
        thesis_changed: false,
        thesis_diff: "",
      }),
    "GET /api/rebalances/77": () =>
      json({
        id: 77,
        precise_amounts: false,
        actions: [
          {
            phase: "1B",
            ticker: "AAA",
            action: "Sell",
            broker: null,
            calculated_amount: "150",
            executed_amount: "140",
          },
        ],
      }),
    ...handlers,
  });
}

describe("timeline", () => {
  it("[NFR-14] turns local days into UTC instants", () => {
    expect(new Date(localDayStart("2026-07-01")).getDate()).toBe(1);
    expect(new Date(localDayEnd("2026-07-01")).getDate()).toBe(2);
    expect(new Date(localDayEnd("2026-12-31")).getFullYear()).toBe(2027);
  });

  it("[TL-01] lists events, newest first", async () => {
    setup();
    renderApp("/timeline");
    const items = await screen.findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Thesis 'Core' has a new revision 2");
    expect(items[3]).toHaveTextContent("core-v1 activated");
  });

  it("[TL-03] filters by portfolio, policy, type and period", async () => {
    const calls = setup();
    renderApp("/timeline");
    await screen.findAllByRole("listitem");
    await userEvent.selectOptions(screen.getByLabelText("Portfolio"), "5");
    await userEvent.selectOptions(screen.getByLabelText("Policy"), "3");
    await userEvent.click(screen.getByLabelText("Rebalance confirmed"));
    await userEvent.type(screen.getByLabelText("From"), "2026-03-01");
    await waitFor(() => {
      const last = calls.filter((c) => c.path.startsWith("/api/timeline")).at(-1)!.path;
      const query = new URLSearchParams(last.split("?")[1]);
      expect(query.get("portfolio_id")).toBe("5");
      expect(query.get("policy_id")).toBe("3");
      expect(query.getAll("type")).toEqual(["rebalance_confirmed"]);
      expect(query.get("start")).toBe(localDayStart("2026-03-01"));
    });
  });

  it("[TL-02] opens the details of an activation and a rebalance", async () => {
    setup();
    renderApp("/timeline");
    await userEvent.click(await screen.findByText("core-v2 activated (Main): less ETH"));
    expect(await screen.findByText(/target: 20 → 18/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "core-v2" })).toHaveAttribute("href", "/policies/3");

    await userEvent.click(screen.getByText("Main: rebalanced, sold 140, bought 150"));
    expect(await screen.findByText(/AAA Sell: 140/)).toBeInTheDocument();
    expect(screen.getByText(/calculated 150/)).toBeInTheDocument();
    expect(screen.getByText("Thesis 'Core' has a new revision 2")).toBeInTheDocument();
  });

  it("[TL-02] [REV-12] opens the result of a confirmed review", async () => {
    const aspect = (n: number, score: number) => ({
      code: `T${n}`,
      name: `Aspect ${n}`,
      score,
      reasoning_md: "",
    });
    setup({
      "GET /api/timeline": () =>
        json([
          event(5, "thesis_review_confirmed", "Thesis review of core-v2: intact, 7 / 10", {
            review_id: 30,
            policy_version_id: 202,
          }),
        ]),
      "GET /api/reviews/30": () =>
        json({
          id: 30,
          kind: "thesis",
          state: "done",
          aspects: [
            aspect(1, 7),
            aspect(2, 6),
            aspect(3, 8),
            aspect(4, 5),
            aspect(5, 7),
            aspect(6, 7),
          ],
          total: 6.5,
          thesis_score: 6.5,
          structure_score: null,
          semaphore: "good",
          verdict: "intact",
          verdict_reason: null,
          scoring_version: "2",
          method: "manual",
          model: "Gemini 3",
          ai_reviewer_name: null,
          legacy_modification: null,
          confirmed: true,
        }),
    });
    renderApp("/timeline");
    await userEvent.click(await screen.findByText(/Thesis review of core-v2/));
    expect(await screen.findByRole("img", { name: "Score: 6.5 of 10" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Aspect 1: 7.0 of 10" })).toBeInTheDocument();
    expect(screen.getByText("manual review with Gemini 3")).toBeInTheDocument(); // REV-17
    expect(screen.getByText("good")).toBeInTheDocument(); // REV-06: intact
    expect(await screen.findByRole("link", { name: "core-v2" })).toHaveAttribute(
      "href",
      "/policies/3",
    );
  });

  it("[TL-02] [REV-02] [REV-17] opens the result of a confirmed review of the whole policy", async () => {
    setup({
      "GET /api/timeline": () =>
        json([
          event(6, "review_confirmed", "Review of core-v3: warning, 7 / 10", {
            review_id: 31,
            policy_version_id: 202,
            params: { version: "core-v3", verdict: "warning", total: 7 },
          }),
        ]),
      "GET /api/reviews/31": () =>
        json({
          id: 31,
          kind: "full",
          state: "done",
          aspects: [
            { code: "T1", name: "Belief", score: 6.5, reasoning_md: "" },
            { code: "P1", name: "Coverage", score: 7.5, reasoning_md: "" },
          ],
          total: 7,
          thesis_score: 6.5,
          structure_score: 7.5,
          semaphore: "warning",
          verdict: "warning",
          verdict_reason: "Warning signals",
          scoring_version: "3",
          method: "manual",
          model: null,
          ai_reviewer_name: null,
          provider: "manual",
          news_from: "2026-01-01T10:00:00+00:00",
          news_to: "2026-03-01T10:00:00+00:00",
          started_at: "2026-03-01T10:00:00+00:00",
          completed_at: "2026-03-01T10:05:00+00:00",
          legacy_modification: null,
          outdated: false,
          sources: [],
          suggestions: [],
          confirmed: true,
        }),
    });
    renderApp("/timeline");
    await userEvent.click(await screen.findByText("Review of core-v3: warning, 7 / 10"));
    expect(await screen.findByRole("img", { name: "Score: 7.0 of 10" })).toBeInTheDocument();
    expect(screen.getByText("Thesis · 6.5 · Target structure · 7.5")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Coverage: 7.5 of 10" })).toBeInTheDocument();
    expect(screen.getByText("manual review")).toBeInTheDocument();
    // REV-24: the full review is a click away
    await userEvent.click(screen.getByRole("button", { name: "Read the full review →" }));
    const dialog = await screen.findByRole("dialog", { name: "The full review" });
    expect(within(dialog).getByText("Warning signals")).toBeInTheDocument();
  });

  it("[CMP-09] [POL-11] [THS-04] [PTF-07] shows portfolios, warnings and recent events on the dashboard", async () => {
    setup();
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Main" })).toBeInTheDocument();
    // PTF-07: the semaphore of the portfolio's policy with a link; the verdict text is on the
    // policy and portfolio pages, not on the cards
    expect(screen.getByText("broken")).toBeInTheDocument();
    expect(screen.queryByText("A break condition is met.")).toBeNull();
    expect(screen.getByRole("link", { name: "Open the policy" })).toHaveAttribute(
      "href",
      "/policies/3",
    );
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.map((a) => a.textContent)).toEqual([
      "growth: the semaphore of its thesis is warning.",
    ]);
    const recent = screen.getByRole("heading", { name: "Recent events" }).closest("section")!;
    expect(within(recent).getAllByRole("listitem")).toHaveLength(4);
  });
});

describe("export links", () => {
  it("[IMP-10] offers JSON exports for theses, versions and snapshots", async () => {
    setup({
      "GET /api/policies/3": () =>
        json({
          id: 3,
          name: "core",
          archived_at: null,
          created_at: "2026-01-01T10:00:00+00:00",
          versions: [
            {
              id: 201,
              version_no: 1,
              label: "core-v1",
              thesis_title: "T",
              change_note: null,
              active_from: "2026-01-01T10:00:00+00:00",
              active_until: null,
              is_draft: false,
              review: null,
              reviews: [],
            },
          ],
          portfolios: [],
          thesis_warning: false,
          semaphore: null,
        }),
      "GET /api/policies/3/versions/1": () =>
        json({
          id: 201,
          version_no: 1,
          label: "core-v1",
          thesis_title: "T",
          thesis_md: "x",
          positions: [],
        }),
      "GET /api/snapshots/41": () =>
        json({
          id: 41,
          portfolio_id: 5,
          taken_at: "2026-03-01T10:00:00+00:00",
          source: "manual",
          corrects_snapshot_id: null,
          policy_version_id: 202,
          policy_version_label: "core-v2",
          total_value: "0",
          rows: [],
        }),
    });
    const { unmount } = renderApp("/policies/3");
    expect(await screen.findByRole("link", { name: "Export as JSON" })).toHaveAttribute(
      "href",
      "/api/policies/3/versions/1/thesis/export",
    );
    unmount();
    renderApp("/snapshots/41");
    expect(await screen.findByRole("link", { name: "Export values" })).toHaveAttribute(
      "href",
      "/api/snapshots/41/export",
    );
  });
});
