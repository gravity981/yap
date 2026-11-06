import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { investor, json, mockApi, renderApp } from "@/test/utils";

const position = (ticker: string, extra: Record<string, unknown> = {}) => ({
  ticker,
  name: ticker,
  type: "ETF",
  broker: "Southbank",
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
  ...extra,
});

const result = {
  total_value_before: "1000",
  total_buffer_used: "0",
  total_sell_proceeds: "150",
  available_cash: "150",
  total_withdrawal_sells: "0",
  unallocated_cash: "0",
  total_value_after: "1000",
  buys_by_broker: { Northbank: "150" },
  positions: [
    position("AAA", { sell_amount: "150", phase1_action: "Sell", allocation_after_pct: "55" }),
    position("BBB", {
      type: "crypto",
      broker: "Northbank",
      buy_amount: "150",
      phase3_action: "Buy (Below Target)",
      allocation_after_pct: "45",
    }),
  ],
};

function setup() {
  return mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(investor),
    "GET /api/portfolios/5": () => json({ id: 5, name: "Main" }),
    "GET /api/portfolios/5/rebalance": () =>
      json({
        snapshot_id: 41,
        snapshot_taken_at: "2026-03-01T10:00:00+00:00",
        policy_version_id: 202,
        policy_version_label: "core-v2",
        contribution: "0",
        withdrawal: "0",
        precise_amounts: false,
        instructions: [
          { phase: "1B", ticker: "AAA", action: "Sell", broker: "Southbank", amount: "150" },
          {
            phase: "3",
            ticker: "BBB",
            action: "Buy (Below Target)",
            broker: "Northbank",
            amount: "150",
          },
        ],
        result,
      }),
    "GET /api/rebalances/77": () =>
      json({
        id: 77,
        portfolio_id: 5,
        confirmed_at: "2026-03-02T10:00:00+00:00",
        input_snapshot_id: 41,
        result_snapshot_id: 42,
        policy_version_id: 202,
        contribution: "0",
        withdrawal: "0",
        precise_amounts: false,
        actions: [
          {
            phase: "1B",
            ticker: "AAA",
            action: "Sell",
            broker: "Southbank",
            calculated_amount: "150",
            executed_amount: "140",
          },
        ],
      }),
    "GET /api/rebalances/77/result": () => json(result),
  });
}

describe("report", () => {
  it("[RB-19] [RB-23] prints the instructions with all tables and charts", async () => {
    const calls = setup();
    const print = vi.fn();
    vi.stubGlobal("print", print);
    renderApp("/portfolios/5/rebalance/report?snapshot=41&contribution=0");
    expect(
      await screen.findByRole("heading", { name: "Rebalancing instructions – Main" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Policy core-v2/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Sell" })).toBeInTheDocument();
    expect(screen.getByLabelText("Buys per broker")).toBeInTheDocument();
    // the detail table is open for printing
    expect(screen.getByText("All positions in detail").closest("details")).toHaveAttribute("open");
    expect(screen.getByText("How this was calculated").closest("details")).toHaveAttribute("open");
    expect(screen.getByRole("figure", { name: "Allocation by position" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "ETF: 50.0\u00a0%" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Print / save as PDF" }));
    expect(print).toHaveBeenCalled();
    expect(
      calls.some((c) => c.path.includes("snapshot_id=41") && c.path.includes("contribution=0")),
    ).toBe(true);
  });

  it("[RB-19] [RB-23] prints a confirmed rebalance with calculated and executed amounts", async () => {
    setup();
    renderApp("/rebalances/77/report");
    expect(await screen.findByRole("heading", { name: "Rebalance – Main" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Calculated and executed" });
    const row = within(table).getByRole("cell", { name: "AAA" }).closest("tr")!;
    expect(within(row).getByText("150")).toBeInTheDocument();
    expect(within(row).getByText("140")).toBeInTheDocument();
    expect(screen.getByLabelText("Cash calculation")).toBeInTheDocument();
    expect(screen.getByText("How this was calculated").closest("details")).toHaveAttribute("open");
  });

  it("[RB-19] ignores invalid report parameters", async () => {
    const calls = setup();
    renderApp("/portfolios/5/rebalance/report?snapshot=abc&contribution=-5");
    await screen.findByRole("heading", { name: /Rebalancing instructions/ });
    const planCall = calls.find((c) => c.path.startsWith("/api/portfolios/5/rebalance"))!;
    expect(planCall.path).toBe("/api/portfolios/5/rebalance");
  });
});
