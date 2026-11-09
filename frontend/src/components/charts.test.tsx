import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AllocationBars, TypePie } from "./charts";

const rows = [
  {
    ticker: "XUS",
    name: "US Equity",
    allocation: 38,
    target: 40,
    buyAbs: 32,
    sellAbs: 50,
    status: "within_band",
  },
  {
    ticker: "ETH",
    name: "Ethereum",
    allocation: 31,
    target: 18,
    buyAbs: 12.6,
    sellAbs: 30.6,
    status: "above_sell_threshold",
  },
  {
    ticker: "OLD",
    name: "Legacy",
    allocation: 2,
    target: null,
    buyAbs: null,
    sellAbs: null,
    status: "not_in_policy",
  },
];

describe("charts", () => {
  it("[CMP-07] shows one bar per position with target and band", () => {
    render(<AllocationBars rows={rows} />);
    expect(
      screen.getByRole("img", {
        name: "ETH: 31.0\u00a0% of the portfolio, target 18.0\u00a0%, band 12.6\u00a0% to 30.6\u00a0%, above sell threshold",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "OLD: 2.0\u00a0% of the portfolio, not in policy" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("target-XUS")).toBeInTheDocument();
    expect(screen.getByTestId("band-XUS")).toBeInTheDocument();
    expect(screen.queryByTestId("target-OLD")).not.toBeInTheDocument();
    expect(screen.getByText("38.0 %")).toBeInTheDocument(); // value at the tip
  });

  it("[CMP-07] shows details on focus and hover", () => {
    render(<AllocationBars rows={rows} />);
    const bar = screen.getByRole("img", { name: /^XUS/ });
    fireEvent.focus(bar);
    expect(screen.getByRole("tooltip")).toHaveTextContent("target 40.0 %");
    fireEvent.blur(bar);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.pointerEnter(bar);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    fireEvent.pointerLeave(bar);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("[CMP-07] shows the allocation by type as a pie with legend", () => {
    render(
      <TypePie
        shares={[
          { type: "crypto", value: 250 },
          { type: "ETF", value: 750 },
          { type: "stock", value: 0 },
        ]}
      />,
    );
    // fixed order by type, not by size; zero shares are left out
    const slices = screen.getAllByRole("img");
    expect(slices.map((s) => s.getAttribute("aria-label"))).toEqual([
      "ETF: 75.0\u00a0%",
      "Crypto: 25.0\u00a0%",
    ]);
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "ETF75.0\u00a0%",
      "Crypto25.0\u00a0%",
    ]);
    fireEvent.pointerEnter(slices[1]!);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Crypto: 25.0 %");
  });

  it("[CMP-07] draws a single type as a full circle and handles empty portfolios", () => {
    const { container, rerender } = render(<TypePie shares={[{ type: "ETF", value: 5 }]} />);
    expect(container.querySelector("circle")).toHaveAttribute("aria-label", "ETF: 100.0\u00a0%");
    rerender(<TypePie shares={[]} />);
    expect(screen.getByText("No values yet.")).toBeInTheDocument();
  });
});
