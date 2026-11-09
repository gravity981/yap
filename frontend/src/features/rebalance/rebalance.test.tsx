import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { investor, json, mockApi, renderApp, type Handler } from "@/test/utils";

const position = (ticker: string, extra: Record<string, unknown> = {}) => ({
  ticker,
  name: ticker,
  type: "ETF",
  broker: null,
  in_policy: true,
  exit: false,
  target_pct: "50",
  value_before: "500",
  allocation_before_pct: "50",
  buffer_buy: "0",
  buffer_deployed: "0",
  sell_amount: "0",
  phase1_action: "Hold",
  value_after_phase1: "500",
  allocation_after_phase1_pct: "50",
  buy_amount: "0",
  withdrawal_sell: "0",
  phase3_action: "Hold",
  value_after: "500",
  allocation_after_pct: "50",
  difference_to_target_pct: "0",
  units_before: null,
  price: null,
  whole_units: null,
  buffer_buy_units: null,
  sell_units: null,
  buy_units: null,
  withdrawal_sell_units: null,
  units_after: null,
  ...extra,
});

const result = (extra: Record<string, unknown> = {}) => ({
  total_value_before: "1000",
  total_buffer_used: "0",
  total_sell_proceeds: "150.4",
  available_cash: "650.4",
  total_withdrawal_sells: "0",
  unallocated_cash: "0",
  rounding_cash: "0",
  total_value_after: "1500",
  buys_by_broker: { Northbank: "650.4" },
  positions: [
    position("AAA", {
      broker: "Southbank",
      sell_amount: "150.4",
      phase1_action: "Sell",
      value_after: "549.6",
      allocation_after_pct: "55",
      difference_to_target_pct: "5",
    }),
    position("BBB", {
      broker: "Northbank",
      buy_amount: "650.4",
      phase3_action: "Buy (Below Target)",
      difference_to_target_pct: "-3.2",
    }),
  ],
  ...extra,
});

const plan = (extra: Record<string, unknown> = {}) => ({
  snapshot_id: 41,
  snapshot_taken_at: new Date().toISOString(),
  policy_version_id: 202,
  policy_version_label: "core-v2",
  policy_id: 9,
  policy_name: "core",
  mode: "normal",
  semaphore: null,
  semaphore_reason: null,
  contribution: "500",
  withdrawal: "0",
  precise_amounts: false,
  instructions: [
    {
      phase: "1B",
      ticker: "AAA",
      action: "Sell",
      broker: "Southbank",
      amount: "150.4",
      units: null,
      whole_units: null,
    },
    {
      phase: "3",
      ticker: "BBB",
      action: "Buy (Below Target)",
      broker: "Northbank",
      amount: "650.4",
      units: null,
      whole_units: null,
    },
  ],
  result: result(),
  ...extra,
});

function setup(handlers: Record<string, Handler> = {}) {
  return mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(investor),
    "GET /api/portfolios/5": () => json({ id: 5, name: "Main" }),
    "GET /api/portfolios/5/rebalance": () => json(plan()),
    ...handlers,
  });
}

describe("rebalancing", () => {
  it("[RB-03] [RB-12] [RB-13] [RB-15] [NFR-15] shows instructions, cash and buys per broker, rounded", async () => {
    setup();
    renderApp("/portfolios/5/rebalance?snapshot=41");
    const sells = await screen.findByRole("list", { name: "Sell" });
    expect(within(sells).getByText("150")).toBeInTheDocument(); // 150.4 rounded
    // NFR-15: with every set of instructions, also in the printed report
    const notes = screen.getAllByRole("note", { name: "Not financial advice" });
    expect(notes.some((n) => /only apply the rules of your policy/.test(n.textContent ?? ""))).toBe(
      true,
    );
    const buys = screen.getByRole("list", { name: "Buy" });
    expect(within(buys).getByText(/Buy \(Below Target\) · Northbank/)).toBeInTheDocument();
    expect(screen.getByText("Nothing to do.")).toBeInTheDocument(); // no dip buys
    const cash = screen.getByLabelText("Cash calculation");
    expect(within(cash).getByText("Available for buys").nextSibling).toHaveTextContent("650");
    expect(
      within(screen.getByLabelText("Buys per broker")).getByText("Northbank"),
    ).toBeInTheDocument();
  });

  it("[RB-15] shows precise amounts when the portfolio asks for them", async () => {
    setup({ "GET /api/portfolios/5/rebalance": () => json(plan({ precise_amounts: true })) });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    const sells = await screen.findByRole("list", { name: "Sell" });
    expect(within(sells).getByText("150.40")).toBeInTheDocument();
  });

  it("[RB-02] warns, without blocking, when the values are older than 3 days", async () => {
    const days = (n: number) => new Date(Date.now() - n * 24 * 60 * 60 * 1000).toISOString();
    setup({
      "GET /api/portfolios/5/rebalance": () => json(plan({ snapshot_taken_at: days(4) })),
    });
    renderApp("/portfolios/5/rebalance");
    expect(await screen.findByText(/Values outdated/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Enter values" })).toHaveAttribute(
      "href",
      "/portfolios/5/values",
    );
    expect(screen.getByRole("list", { name: "Sell" })).toBeInTheDocument();
  });

  it("[RB-02] does not warn when the values are at most 3 days old", async () => {
    const days = (n: number) => new Date(Date.now() - n * 24 * 60 * 60 * 1000).toISOString();
    setup({
      "GET /api/portfolios/5/rebalance": () => json(plan({ snapshot_taken_at: days(2) })),
    });
    renderApp("/portfolios/5/rebalance");
    await screen.findByRole("list", { name: "Sell" });
    expect(screen.queryByText(/Values outdated/)).not.toBeInTheDocument();
  });

  it("[RB-01] recalculates with another contribution and uses a chosen snapshot", async () => {
    const calls = setup();
    renderApp("/portfolios/5/rebalance?snapshot=40");
    await screen.findByRole("list", { name: "Sell" });
    await userEvent.type(screen.getByLabelText("Contribution"), "0");
    await userEvent.click(screen.getByRole("button", { name: "Recalculate" }));
    await waitFor(() => expect(calls.some((c) => c.path.includes("contribution=0"))).toBe(true));
    expect(
      calls.every(
        (c) =>
          !c.path.startsWith("/api/portfolios/5/rebalance") || c.path.includes("snapshot_id=40"),
      ),
    ).toBe(true);
  });

  it("[RB-01] [RB-09] [RB-13] [RB-22] recalculates with a withdrawal and shows the sells for it", async () => {
    const withdrawing = plan({
      withdrawal: "300",
      instructions: [
        {
          phase: "3",
          ticker: "BBB",
          action: "Sell (Withdrawal)",
          broker: "Northbank",
          amount: "200",
        },
      ],
      result: result({
        total_sell_proceeds: "0",
        available_cash: "0",
        total_withdrawal_sells: "200",
        buys_by_broker: {},
        positions: [
          position("AAA"),
          position("BBB", {
            broker: "Northbank",
            withdrawal_sell: "200",
            phase3_action: "Sell (Withdrawal)",
          }),
        ],
      }),
    });
    const calls = setup({
      "GET /api/portfolios/5/rebalance": (request) =>
        json(request.url.includes("withdrawal=300") ? withdrawing : plan()),
    });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    await screen.findByRole("list", { name: "Sell" });
    await userEvent.type(screen.getByLabelText("Withdrawal"), "300");
    await userEvent.click(screen.getByRole("button", { name: "Recalculate" }));
    const sells = await screen.findByRole("list", { name: "Sell for the withdrawal" });
    expect(within(sells).getByText(/Sell \(Withdrawal\) · Northbank/)).toBeInTheDocument();
    expect(calls.some((c) => c.path.includes("withdrawal=300"))).toBe(true);
    const cash = screen.getByLabelText("Cash calculation");
    expect(within(cash).getByText("Withdrawal").nextSibling).toHaveTextContent("−300");
    expect(within(cash).getByText("To sell for the withdrawal").nextSibling).toHaveTextContent(
      "200",
    );
    const brokers = screen.getByLabelText("Withdrawal sells per broker");
    expect(within(brokers).getByText("Northbank")).toBeInTheDocument();
  });

  it("[RB-23] explains the calculation step by step with the amounts of this plan", async () => {
    setup();
    renderApp("/portfolios/5/rebalance?snapshot=41");
    const summary = await screen.findByText("How this was calculated");
    expect(summary.closest("details")).not.toHaveAttribute("open");
    await userEvent.click(summary);
    const steps = summary.closest("details")!;
    expect(steps).toHaveTextContent(
      "Final value of the portfolio: 1,000 + contribution 500 − withdrawal 0 = 1,500.",
    );
    expect(steps).toHaveTextContent(/Dip buys from the cash buffer\s*Nothing to do/);
    expect(steps).toHaveTextContent(
      "AAA at 50.0 %, above its sell threshold: sold down to its midband of 55.0 %, −150",
    );
    expect(steps).toHaveTextContent(
      "Contribution 500 + sell proceeds 150 − withdrawal 0 = 650. This is invested in step 4.",
    );
    expect(steps).toHaveTextContent("BBB +650, now 50.0 % (target 50.0 %)");
  });

  it("[RB-23] explains the sells for a withdrawal instead of buys", async () => {
    setup({
      "GET /api/portfolios/5/rebalance": () =>
        json(
          plan({
            contribution: "0",
            withdrawal: "700",
            result: result({
              total_sell_proceeds: "500",
              available_cash: "0",
              total_withdrawal_sells: "200",
              buys_by_broker: {},
              positions: [
                position("AAA", {
                  withdrawal_sell: "200",
                  phase3_action: "Sell (Withdrawal)",
                  allocation_after_pct: "37.5",
                }),
                position("BBB", {
                  exit: true,
                  sell_amount: "500",
                  phase1_action: "Sell All (Exit)",
                }),
              ],
            }),
          }),
        ),
    });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    await userEvent.click(await screen.findByText("How this was calculated"));
    const steps = screen.getByText("How this was calculated").closest("details")!;
    expect(steps).toHaveTextContent("BBB has the exit flag: sold completely, −500");
    expect(steps).toHaveTextContent("200 is missing for the withdrawal; it is sold in step 4.");
    expect(steps).toHaveTextContent("Sells for the withdrawal");
    expect(steps).toHaveTextContent("AAA −200, now 37.5 % (target 50.0 %)");
    expect(steps).not.toHaveTextContent("Nothing to buy");
  });

  it("[RB-02] rebalances from the latest snapshot and has no value entry", async () => {
    const calls = setup();
    renderApp("/portfolios/5/rebalance");
    expect(await screen.findByRole("list", { name: "Sell" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Price of AAA")).not.toBeInTheDocument();
    expect(screen.queryByText(/corrects the last entry/)).not.toBeInTheDocument();
    expect(calls.every((c) => c.method === "GET")).toBe(true);
  });

  it("[RB-24] [RB-16] shows units and cash left over by rounding", async () => {
    const withUnits = plan({
      instructions: [
        {
          phase: "1B",
          ticker: "AAA",
          action: "Sell",
          broker: "Southbank",
          amount: "200",
          units: "2",
          whole_units: true,
        },
      ],
      result: result({ unallocated_cash: "60", rounding_cash: "49.6" }),
    });
    setup({
      "GET /api/portfolios/5/rebalance": () => json(withUnits),
    });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    const sells = await screen.findByRole("list", { name: "Sell" });
    expect(within(sells).getByText(/2 units/)).toBeInTheDocument();
    const cash = screen.getByLabelText("Cash calculation");
    expect(within(cash).getByText("Left over by whole units").nextSibling).toHaveTextContent("50");
    // The rest is cash no position can take
    expect(within(cash).getByText("Unallocated (no position can take it)")).toBeInTheDocument();
  });

  it("[RB-10] shows cash that no position can take", async () => {
    setup({
      "GET /api/portfolios/5/rebalance": () =>
        json(plan({ result: result({ unallocated_cash: "500" }) })),
    });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    expect(await screen.findByText("Unallocated (no position can take it)")).toBeInTheDocument();
  });

  it("[RB-11] [RB-14] shows every position through all phases with its distance to target", async () => {
    setup();
    renderApp("/portfolios/5/rebalance?snapshot=41");
    await userEvent.click(await screen.findByText("All positions in detail"));
    const aaa = screen.getByRole("cell", { name: /AAA/ }).closest("tr")!;
    expect(within(aaa).getByText(/Sell −150/)).toBeInTheDocument();
    expect(within(aaa).getByLabelText("above target by 5.0 %")).toHaveTextContent("▲ 5.0 %");
    const bbb = screen.getByRole("cell", { name: /BBB/ }).closest("tr")!;
    expect(within(bbb).getByLabelText("below target by 3.2 %")).toHaveTextContent("▼ 3.2 %");
  });

  it("[RB-16] confirms the trades as calculated, without adjusting anything", async () => {
    const calls = setup({
      "POST /api/portfolios/5/rebalances": () =>
        json(
          {
            id: 77,
            portfolio_id: 5,
            confirmed_at: "2026-03-01T10:00:00+00:00",
            input_snapshot_id: 41,
            result_snapshot_id: null,
            policy_version_id: 202,
            contribution: "500",
            withdrawal: "0",
            precise_amounts: false,
            actions: [],
          },
          201,
        ),
      "GET /api/rebalances/77": () =>
        json({
          id: 77,
          portfolio_id: 5,
          confirmed_at: "2026-03-01T10:00:00+00:00",
          input_snapshot_id: 41,
          result_snapshot_id: null,
          policy_version_id: 202,
          contribution: "500",
          withdrawal: "0",
          precise_amounts: false,
          actions: [
            {
              phase: "1B",
              ticker: "AAA",
              action: "Sell",
              broker: "Southbank",
              calculated_amount: "150.4",
              calculated_units: null,
              whole_units: null,
            },
          ],
        }),
    });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    expect(await screen.findByText(/not that they have been/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Executed/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Carry out as calculated" }));
    expect(await screen.findByRole("heading", { name: /Rebalance of/ })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      snapshot_id: 41,
      contribution: "500",
      withdrawal: "0",
      mode: "normal",
      policy_version_id: 202,
    });
    const row = screen.getByRole("cell", { name: "AAA" }).closest("tr")!;
    expect(within(row).getByText("150")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "values after" })).not.toBeInTheDocument();
  });

  it("[RB-16] shows why a confirmation was refused", async () => {
    setup({
      "POST /api/portfolios/5/rebalances": () =>
        json(
          { detail: "The policy changed since the preview; calculate the rebalance again" },
          409,
        ),
    });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    await userEvent.click(await screen.findByRole("button", { name: "Carry out as calculated" }));
    expect(await screen.findByText(/changed since the preview/)).toBeInTheDocument();
  });

  it("[RB-03] has nothing to confirm when nothing needs to change", async () => {
    setup({ "GET /api/portfolios/5/rebalance": () => json(plan({ instructions: [] })) });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    expect(await screen.findByText(/Nothing to rebalance/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Carry out as calculated" }),
    ).not.toBeInTheDocument();
  });

  it("[RB-20] simulates several cycles", async () => {
    const calls = setup({
      "POST /api/portfolios/5/simulate": () =>
        json([result(), result({ total_value_after: "2000" })]),
    });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    await userEvent.click(await screen.findByText("Simulate several cycles"));
    await userEvent.clear(screen.getByLabelText("Cycles"));
    await userEvent.type(screen.getByLabelText("Cycles"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Simulate" }));
    const table = await screen.findByRole("table", { name: "Simulated cycles" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("2,000")).toBeInTheDocument();
    expect(screen.getByText("After cycle 2")).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/simulate"))?.body).toEqual({
      cycles: 2,
      contribution: "500",
      withdrawal: "0",
      snapshot_id: 41,
    });
  });

  it("[RB-26] shows an amber hint with the reason and a link for a thesis warning", async () => {
    setup({
      "GET /api/portfolios/5/rebalance": () =>
        json(plan({ semaphore: "warning", semaphore_reason: "Rates rose faster than assumed." })),
    });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    const hint = await screen.findByRole("alert", { name: "" });
    expect(hint).toHaveTextContent("The thesis of core needs attention");
    expect(hint).toHaveTextContent("Rates rose faster than assumed.");
    expect(within(hint).getByRole("link", { name: "Open the policy" })).toHaveAttribute(
      "href",
      "/policies/9",
    );
    expect(within(hint).queryByRole("radio")).toBeNull(); // the calculation is the usual one
    expect(screen.getByRole("list", { name: "Buy" })).toBeInTheDocument();
  });

  it("[RB-25] offers to sell the whole portfolio, preselected, or to rebalance as usual", async () => {
    const sellAll = plan({
      mode: "sell_all",
      semaphore: "broken",
      semaphore_reason: "The company lost its main customer.",
      instructions: [
        {
          phase: "1B",
          ticker: "AAA",
          action: "Sell All (Exit)",
          broker: "Southbank",
          amount: "500",
          units: null,
          whole_units: null,
        },
      ],
    });
    const usual = plan({
      semaphore: "broken",
      semaphore_reason: "The company lost its main customer.",
    });
    const calls = setup({
      "GET /api/portfolios/5/rebalance": (request) =>
        json(new URL(request.url).searchParams.get("mode") === "normal" ? usual : sellAll),
    });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    const alert = await screen.findByRole("alert", { name: "" });
    expect(alert).toHaveTextContent("The thesis of core is broken");
    expect(alert).toHaveTextContent("The company lost its main customer.");
    expect(screen.getByRole("radio", { name: /Sell the whole portfolio/ })).toBeChecked();
    expect(screen.getByRole("list", { name: "Sell" })).toHaveTextContent("Sell All (Exit)");

    await userEvent.click(screen.getByRole("radio", { name: /Rebalance as usual/ }));
    expect(await screen.findByRole("list", { name: "Buy" })).toHaveTextContent("BBB");
    expect(screen.getByRole("radio", { name: /Rebalance as usual/ })).toBeChecked();
    const modes = calls.filter((c) => c.method === "GET" && c.path.includes("/rebalance?"));
    expect(modes[0]?.path).not.toContain("mode=");
    expect(modes.at(-1)?.path).toContain("mode=normal");
  });

  it("[RB-25] confirms the sale of the whole portfolio with its mode", async () => {
    const calls = setup({
      "GET /api/portfolios/5/rebalance": () =>
        json(plan({ mode: "sell_all", semaphore: "broken", semaphore_reason: null })),
      "POST /api/portfolios/5/rebalances": () => json({ id: 78 }, 201),
      "GET /api/rebalances/78": () =>
        json({
          id: 78,
          portfolio_id: 5,
          confirmed_at: "2026-03-01T10:00:00+00:00",
          input_snapshot_id: 41,
          result_snapshot_id: null,
          policy_version_id: 202,
          contribution: "500",
          withdrawal: "0",
          mode: "sell_all",
          precise_amounts: false,
          actions: [],
        }),
    });
    renderApp("/portfolios/5/rebalance?snapshot=41");
    await screen.findByText("The latest review gave no reason.", { exact: false });
    await userEvent.click(await screen.findByRole("button", { name: "Carry out as calculated" }));
    expect(await screen.findByText("Sold completely, thesis broken")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ mode: "sell_all" });
  });
});
