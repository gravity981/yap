import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { investor, json, mockApi, renderApp, type Handler } from "@/test/utils";

export const snapshot = (extra: Record<string, unknown> = {}) => ({
  id: 41,
  portfolio_id: 5,
  taken_at: "2026-03-01T10:00:00+00:00",
  source: "manual",
  corrects_snapshot_id: null,
  policy_version_id: 202,
  policy_version_label: "core-v2",
  total_value: "1000",
  currency: "CHF",
  rows: [
    {
      ticker: "XUS",
      name: "US Equity",
      type: "ETF",
      units: "6.5",
      price: "100",
      price_kind: "manual",
      value: "650",
      allocation_pct: "65",
      target_pct: "50",
      buy_abs_pct: "40",
      sell_abs_pct: "60",
      deviation_pct: "15",
      exit: false,
      status: "above_sell_threshold",
    },
    {
      ticker: "ETH",
      name: "Ethereum",
      type: "crypto",
      units: "0.125",
      price: "2400",
      price_kind: "manual",
      value: "300",
      allocation_pct: "30",
      target_pct: "50",
      buy_abs_pct: "40",
      sell_abs_pct: "60",
      deviation_pct: "-20",
      exit: false,
      status: "below_buy_threshold",
    },
    {
      ticker: "OLD",
      name: "Legacy",
      type: "stock",
      units: null,
      price: null,
      price_kind: null,
      value: "50",
      allocation_pct: "5",
      target_pct: null,
      buy_abs_pct: null,
      sell_abs_pct: null,
      deviation_pct: null,
      exit: false,
      status: "not_in_policy",
    },
  ],
  ...extra,
});

const portfolio = (extra: Record<string, unknown> = {}) => ({
  id: 5,
  name: "Main",
  currency: "CHF",
  policy_id: 3,
  policy_name: "core",
  policy_semaphore: "good",
  policy_semaphore_reason: "Recent news supports the thesis.",
  archived_at: null,
  latest_snapshot: snapshot(),
  default_contribution: "500",
  precise_amounts: false,
  currency_locked: true,
  active_version_label: "core-v2",
  brokers: { XUS: "Southbank" },
  positions: [
    { ticker: "XUS", name: "US Equity", type: "ETF", broker: "Southbank", whole_units: true },
    { ticker: "ETH", name: "Ethereum", type: "crypto", broker: null, whole_units: false },
    { ticker: "CSH", name: "Cash", type: "cash_buffer", broker: null, whole_units: null },
  ],
  assignments: [{ policy_id: 3, policy_name: "core", valid_from: "2026-01-01T10:00:00+00:00" }],
  ...extra,
});

function setup(handlers: Record<string, Handler> = {}) {
  return mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(investor),
    "GET /api/portfolios": () =>
      json([portfolio(), { ...portfolio({ id: 6, name: "Extra", latest_snapshot: null }) }]),
    "GET /api/portfolios/5": () => json(portfolio()),
    "GET /api/portfolios/5/snapshots": () =>
      json([
        {
          ...snapshot(),
          rows: undefined,
          allocations: [
            { ticker: "XUS", allocation_pct: "60" },
            { ticker: "BTC", allocation_pct: "40" },
          ],
        },
        {
          ...snapshot({
            id: 40,
            taken_at: "2026-02-01T10:00:00+00:00",
            policy_version_label: "core-v1",
          }),
          rows: undefined,
          allocations: [
            { ticker: "XUS", allocation_pct: "70" },
            { ticker: "BTC", allocation_pct: "30" },
          ],
        },
      ]),
    "GET /api/portfolios/5/prefill": () =>
      json([
        {
          ticker: "XUS",
          name: "US Equity",
          type: "ETF",
          units: "6.5",
          price: "100",
          value: "650",
          in_policy: true,
        },
        // Units unknown: the previous snapshot is from before price tracking (CMP-10)
        {
          ticker: "ETH",
          name: "Ethereum",
          type: "crypto",
          units: null,
          price: null,
          value: "300",
          in_policy: true,
        },
        {
          ticker: "CSH",
          name: "Cash",
          type: "cash_buffer",
          units: "200",
          price: "1",
          value: "200",
          in_policy: true,
        },
      ]),
    "GET /api/snapshots/41": () => json(snapshot()),
    "GET /api/policies": () =>
      json([
        {
          id: 3,
          name: "core",
          archived_at: null,
          active_version_label: "core-v2",
          has_draft: false,
          thesis_warning: false,
        },
        {
          id: 4,
          name: "growth",
          archived_at: null,
          active_version_label: "growth-v1",
          has_draft: false,
          thesis_warning: false,
        },
        {
          id: 9,
          name: "draft only",
          archived_at: null,
          active_version_label: null,
          has_draft: true,
          thesis_warning: false,
        },
      ]),
    ...handlers,
  });
}

describe("portfolios", () => {
  it("[CMP-09] gives an overview of all portfolios with band status", async () => {
    setup();
    renderApp("/portfolios");
    const main = (await screen.findByRole("link", { name: "Main" })).closest("div.rounded-lg")!;
    expect(within(main as HTMLElement).getByText("2 positions outside band")).toBeInTheDocument();
    expect(screen.getByText("no values entered yet")).toBeInTheDocument();
  });

  it("[PTF-07] shows the semaphore of the policy on the overview and the portfolio page", async () => {
    setup({
      "GET /api/portfolios": () =>
        json([
          portfolio({
            policy_semaphore: "warning",
            policy_semaphore_reason: "Two warning signals are observed.",
          }),
          portfolio({ id: 6, name: "Extra", latest_snapshot: null }),
        ]),
      "GET /api/portfolios/5": () =>
        json(
          portfolio({
            policy_semaphore: "broken",
            policy_semaphore_reason: "A break condition is met.",
          }),
        ),
    });
    renderApp("/portfolios");
    const main = (await screen.findByRole("link", { name: "Main" })).closest("div.rounded-lg")!;
    // warning in amber with a link to the policy, without the verdict text
    expect(within(main as HTMLElement).getByText("warning")).toBeInTheDocument();
    expect(within(main as HTMLElement).queryByText("Two warning signals are observed.")).toBeNull();
    expect(
      within(main as HTMLElement).getByRole("link", { name: "Open the policy" }),
    ).toBeInTheDocument();
    const extra = screen.getByRole("link", { name: "Extra" }).closest("div.rounded-lg")!;
    // good: the semaphore only, no reason and no link
    expect(within(extra as HTMLElement).getByText("good")).toBeInTheDocument();
    expect(within(extra as HTMLElement).queryByText("Recent news supports the thesis.")).toBeNull();
    expect(
      within(extra as HTMLElement).queryByRole("link", { name: "Open the policy" }),
    ).toBeNull();
    await userEvent.click(screen.getByRole("link", { name: "Main" }));
    expect(await screen.findByText("A break condition is met.")).toBeInTheDocument();
    expect(screen.getByText("broken")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the policy" })).toHaveAttribute(
      "href",
      "/policies/3",
    );
  });

  it("[PTF-01] [PTF-02] creates a portfolio for a policy with an active version", async () => {
    const calls = setup({ "POST /api/portfolios": () => json(portfolio(), 201) });
    renderApp("/portfolios");
    await userEvent.click(await screen.findByRole("button", { name: "New portfolio" }));
    const options = within(screen.getByLabelText("Policy"))
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual(["Choose a policy", "core (core-v2)", "growth (growth-v1)"]);
    await userEvent.type(screen.getByLabelText("Name"), "Main");
    await userEvent.selectOptions(screen.getByLabelText("Policy"), "3");
    await userEvent.clear(screen.getByLabelText("Default contribution"));
    await userEvent.type(screen.getByLabelText("Default contribution"), "500");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("heading", { name: /Main/ })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/portfolios" && c.method === "POST")?.body).toEqual({
      name: "Main",
      policy_id: 3,
      currency: "CHF", // preset with the base currency (PTF-03)
      default_contribution: "500",
      precise_amounts: false,
    });
  });

  it("[PTF-05] [CMP-02] [CMP-05] shows the latest values against the policy", async () => {
    setup();
    renderApp("/portfolios/5");
    expect(await screen.findByText(/active core-v2/)).toBeInTheDocument();
    const xus = screen.getByRole("cell", { name: /XUS/ }).closest("tr")!;
    expect(within(xus).getByText("above sell threshold")).toBeInTheDocument();
    expect(within(xus).getByText("+15.0 %")).toBeInTheDocument();
    expect(within(xus).getByText("40.0 % – 60.0 %")).toBeInTheDocument();
    const old = screen.getByRole("cell", { name: /OLD/ }).closest("tr")!;
    expect(within(old).getByText("not in policy")).toBeInTheDocument();
    // CMP-05, CMP-10: units and price; unknown for a row from before price tracking
    expect(within(xus).getByText("6.5")).toBeInTheDocument();
    expect(within(xus).getByText("100.00")).toBeInTheDocument();
    expect(within(old).getAllByText("–").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("columnheader", { name: "Value (CHF)" })).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: "Allocation by type" })).toBeInTheDocument();
  });

  it("[CMP-08] lists past snapshots and assignments", async () => {
    setup();
    renderApp("/portfolios/5");
    await userEvent.click(await screen.findByRole("tab", { name: "History" }));
    expect(await screen.findByText(/core-v1 · manual/)).toBeInTheDocument();
    expect(screen.getByText(/from 1 Jan 2026|from Jan 1, 2026/)).toBeInTheDocument();
  });

  it("[CMP-08] shows the allocation over the snapshots as a line chart", async () => {
    setup();
    renderApp("/portfolios/5");
    await userEvent.click(await screen.findByRole("tab", { name: "History" }));
    const figure = await screen.findByRole("figure", { name: "Allocation over the snapshots" });
    expect(
      within(figure)
        .getAllByRole("img")
        .map((e) => e.getAttribute("aria-label")),
    ).toEqual([
      expect.stringMatching(/XUS 70\.0\s?%, BTC 30\.0\s?%/),
      expect.stringMatching(/XUS 60\.0\s?%, BTC 40\.0\s?%/),
    ]);
    expect(within(figure).getByText("BTC")).toBeVisible();
  });

  it("[PTF-03] [PTF-04] saves settings, positions and a new policy", async () => {
    const calls = setup({
      "PUT /api/portfolios/5/settings": () => json(portfolio()),
      "PUT /api/portfolios/5/positions": () => json(portfolio()),
      "POST /api/portfolios/5/reassign": () => json(portfolio({ policy_id: 4 })),
    });
    renderApp("/portfolios/5");
    await userEvent.click(await screen.findByRole("button", { name: "Settings" }));
    const dialog = await screen.findByRole("dialog");
    // The portfolio has snapshots, so its currency is fixed
    expect(within(dialog).getByLabelText("Currency")).toBeDisabled();
    expect(within(dialog).getByText("Fixed, because the portfolio has snapshots.")).toBeVisible();
    await userEvent.click(within(dialog).getByLabelText(/precise amounts/));
    await userEvent.type(within(dialog).getByLabelText("Broker of ETH"), "Bitexchange");
    await userEvent.click(within(dialog).getByLabelText("ETH: traded in whole units only"));
    // The cash buffer has only an amount: no whole-units choice
    expect(within(dialog).queryByLabelText("CSH: traded in whole units only")).toBeNull();
    await userEvent.selectOptions(within(dialog).getByLabelText("Policy"), "4");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls.find((c) => c.path.endsWith("/settings"))?.body).toEqual({
      default_contribution: "500",
      precise_amounts: true,
      currency: "CHF",
    });
    expect(calls.find((c) => c.path.endsWith("/positions"))?.body).toEqual({
      XUS: { broker: "Southbank", whole_units: true },
      ETH: { broker: "Bitexchange", whole_units: true },
      CSH: { broker: "", whole_units: null },
    });
    expect(calls.find((c) => c.path.endsWith("/reassign"))?.body).toEqual({ policy_id: 4 });
  });

  it("[PTF-06] archives a portfolio", async () => {
    const calls = setup({
      "POST /api/portfolios/5/archive": () =>
        json(portfolio({ archived_at: "2026-04-01T10:00:00+00:00" })),
    });
    renderApp("/portfolios/5");
    await userEvent.click(await screen.findByRole("button", { name: "Settings" }));
    await userEvent.click(await screen.findByRole("button", { name: "Archive portfolio" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/archive"))).toBe(true));
  });

  it("[CMP-01] [CMP-02] [CMP-06] enters values pre-filled, with an extra position and as a correction", async () => {
    const calls = setup({
      "POST /api/portfolios/5/snapshots": () => json(snapshot({ id: 41 }), 201),
    });
    renderApp("/portfolios/5/values");
    // Units of the last entry and the price last entered; the value follows
    expect(await screen.findByLabelText("Units of XUS")).toHaveValue("6.5");
    expect(screen.getByLabelText("Price of XUS")).toHaveValue("100");
    expect(screen.getByLabelText("Value of XUS")).toHaveValue("650.00");
    await userEvent.clear(screen.getByLabelText("Price of XUS"));
    await userEvent.type(screen.getByLabelText("Price of XUS"), "102.5");
    expect(screen.getByLabelText("Value of XUS")).toHaveValue("666.25");
    // ETH's units are not known yet; entering the value gives the price
    expect(screen.getByText("Units unknown so far; previously 300.00.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Units of ETH"), "0.25");
    await userEvent.type(screen.getByLabelText("Value of ETH"), "640");
    expect(screen.getByLabelText("Price of ETH")).toHaveValue("2560");
    // Many decimals in the units, e.g. one satoshi less: the price still shows
    await userEvent.clear(screen.getByLabelText("Units of ETH"));
    await userEvent.type(screen.getByLabelText("Units of ETH"), "123456.12345678");
    expect(screen.getByLabelText("Price of ETH")).toHaveValue("0.005184027994");
    await userEvent.clear(screen.getByLabelText("Units of ETH"));
    await userEvent.type(screen.getByLabelText("Units of ETH"), "0.25");
    // The cash buffer has only its amount
    expect(screen.queryByLabelText("Units of CSH")).toBeNull();
    expect(screen.getByLabelText("Value of CSH")).toHaveValue("200");
    await userEvent.click(screen.getByRole("button", { name: "Add position not in the policy" }));
    await userEvent.type(screen.getByLabelText("New ticker"), "OLD");
    await userEvent.type(screen.getByLabelText("New name"), "Legacy");
    await userEvent.type(screen.getByLabelText("Units of OLD"), "2");
    await userEvent.type(screen.getByLabelText("Price of OLD"), "25");
    await userEvent.click(await screen.findByLabelText(/corrects the last entry/));
    await userEvent.click(screen.getByRole("button", { name: "Save values" }));
    expect(await screen.findByRole("heading", { name: "Snapshot" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      values: [
        { ticker: "XUS", units: "6.5", price: "102.5" },
        { ticker: "ETH", units: "0.25", value: "640" },
        { ticker: "CSH", value: "200" },
        { ticker: "OLD", units: "2", price: "25", name: "Legacy", type: "stock" },
      ],
      corrects_snapshot_id: 41,
    });
  });

  it("[CMP-01] shows value errors at the position", async () => {
    setup({
      "POST /api/portfolios/5/snapshots": () =>
        json(
          {
            detail: "x",
            problems: [{ path: "values[1].value", message: "Value must be 0 or more" }],
          },
          422,
        ),
    });
    renderApp("/portfolios/5/values");
    await userEvent.type(await screen.findByLabelText("Value of ETH"), "-1");
    await userEvent.click(screen.getByRole("button", { name: "Save values" }));
    expect(await screen.findByText("Value must be 0 or more")).toBeInTheDocument();
  });

  it("[IMP-03] imports current values", async () => {
    const calls = setup({
      "POST /api/portfolios/5/import/preview": () =>
        json({
          values: [
            ["XUS", "1"],
            ["NEW", "2"],
          ],
          new_tickers: ["NEW"],
        }),
      "POST /api/portfolios/5/import": () => json(snapshot(), 201),
    });
    renderApp("/portfolios/5");
    await userEvent.click(await screen.findByRole("tab", { name: "History" }));
    await userEvent.click(screen.getByRole("button", { name: "Import values" }));
    await userEvent.upload(screen.getByLabelText("Import file"), new File(['{"x":1}'], "v.json"));
    expect(await screen.findByText("2 values will be saved.")).toBeInTheDocument();
    expect(screen.getByText("New in the asset catalog: NEW")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() =>
      expect(calls.some((c) => c.path === "/api/portfolios/5/import")).toBe(true),
    );
    // Back on the current values, which show the imported snapshot
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Current" })).toHaveAttribute("aria-selected", "true"),
    );
  });

  it("[CMP-03] [CMP-04] shows a past snapshot against its own version", async () => {
    setup();
    renderApp("/snapshots/41");
    expect(await screen.findByText(/compared with core-v2/)).toBeInTheDocument();
    // RB-02: a rebalance starts from the latest snapshot, not necessarily from this one
    expect(screen.getByRole("link", { name: "Rebalance" })).toHaveAttribute(
      "href",
      "/portfolios/5/rebalance",
    );
  });
});
