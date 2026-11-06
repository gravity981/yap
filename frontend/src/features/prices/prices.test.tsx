import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { investor, json, mockApi, renderApp } from "@/test/utils";

import { filePositions } from "./import-price-sources";
import { PriceSourceControl } from "./price-source";

const listing = (id: number, symbol: string, exchange: string, currency: string) => ({
  id,
  provider: "yahoo",
  provider_name: "Yahoo Finance",
  symbol,
  exchange,
  currency,
  name: "Vanguard FTSE All-World",
  available: true,
  price: null,
  price_date: null,
  price_updated_at: null,
});
const SIX = listing(11, "VWRL.SW", "SIX", "CHF");
const LSE = listing(12, "VWRL.L", "London", "USD");

type Source = {
  ticker: string;
  name: string;
  type: string;
  kind: string | null;
  listing: ReturnType<typeof listing> | null;
  updated_at: string | null;
};

function setup(lookups: Record<string, object>, initial: Source[] = []) {
  let sources = initial;
  const calls = mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(investor),
    "GET /api/ai-reviewers": () => json([]),
    "GET /api/reviews/usage": () =>
      json({ ai_reviewer_id: null, ai_reviewer_name: null, used: 0, limit: 0, left: 0 }),
    "GET /api/price-sources": () => json(sources),
    "POST /api/price-sources/lookup": (_, body) => {
      const { ticker } = body as { ticker: string };
      const found = sources.find((s) => s.ticker === ticker.toUpperCase());
      return json({
        ticker: ticker.toUpperCase(),
        problems: [],
        source: found ?? null,
        ...lookups[ticker.toUpperCase()],
      });
    },
    "PUT /api/price-sources/VWRL": (_, body) => {
      const b = body as { kind: string; listing_id: number | null };
      const chosen: Source = {
        ticker: "VWRL",
        name: "Vanguard FTSE All-World",
        type: "ETF",
        kind: b.kind,
        listing: [SIX, LSE].find((l) => l.id === b.listing_id) ?? null,
        updated_at: "2026-11-04T10:00:00+00:00",
      };
      sources = [...sources.filter((s) => s.ticker !== "VWRL"), chosen];
      return json(chosen);
    },
    "PUT /api/price-sources/NEW": (_, body) => {
      const chosen = {
        ticker: "NEW",
        name: "NEW",
        type: "stock",
        ...(body as object),
        listing: null,
      };
      sources = [...sources, chosen as Source];
      return json(chosen);
    },
  });
  return calls;
}

const vwrl: Source = {
  ticker: "VWRL",
  name: "Vanguard FTSE All-World",
  type: "ETF",
  kind: null,
  listing: null,
  updated_at: null,
};

describe("price sources", () => {
  it("[PRC-02] [PRC-05] chooses one of several listings in the settings", async () => {
    const calls = setup({ VWRL: { status: "found", listings: [SIX, LSE] } }, [vwrl]);
    renderApp("/settings");
    const table = await screen.findByRole("table", { name: "Price sources" });
    expect(within(table).getByText("not looked up yet")).toBeInTheDocument();
    await userEvent.click(within(table).getByRole("button", { name: /Change the price source/ }));
    // A ticker without a price source is looked up at once; several listings: choose
    const choose = await screen.findByLabelText("Listing for VWRL");
    await userEvent.selectOptions(choose, "12");
    await userEvent.click(screen.getByRole("button", { name: "Use" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
        kind: "auto",
        listing_id: 12,
      }),
    );
    expect(await within(table).findByText("VWRL.L · London · USD (Yahoo Finance)")).toBeVisible();
  });

  it("[PRC-02] [PRC-06] takes a single listing at once; none means manual, then try auto", async () => {
    const calls = setup({
      VWRL: { status: "found", listings: [SIX] },
      NEW: { status: "not_found", listings: [] },
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PriceSourceControl ticker="vwrl" name="" type="ETF" />
        <PriceSourceControl ticker="new" name="New one" type="stock" />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(calls.filter((c) => c.method === "PUT").map((c) => [c.path, c.body])).toEqual(
        expect.arrayContaining([
          ["/api/price-sources/VWRL", expect.objectContaining({ kind: "auto", listing_id: 11 })],
          ["/api/price-sources/NEW", expect.objectContaining({ kind: "manual", name: "New one" })],
        ]),
      ),
    );
    // NEW is manual now; "try auto" asks the providers again
    const tryAuto = await screen.findByRole("button", { name: "Try auto" });
    await userEvent.click(tryAuto);
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && (c.body as { retry: boolean }).retry)).toBe(
        true,
      ),
    );
  });

  it("[IMP-07] shows the price sources of the file's tickers in an import preview", async () => {
    expect(
      filePositions(
        '{"positions": [{"ticker": "VWRL", "name": "V", "type": "ETF"}, {"ticker": "CASH", "type": "cash_buffer"}, {"x": 1}]}',
      ),
    ).toEqual([
      { ticker: "VWRL", name: "V", type: "ETF" },
      { ticker: "CASH", name: undefined, type: "cash_buffer" },
    ]);
    expect(filePositions("not json")).toEqual([]);
  });
});

const auto = {
  listing_id: 11,
  symbol: "XUS.US",
  exchange: "NYSE",
  provider_name: "Yahoo Finance",
  listing_price: "100",
  listing_currency: "USD",
  fx_rate: "0.8",
  price_date: "2020-01-02", // more than 3 days ago
};

function valuesSetup() {
  return mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(investor),
    "GET /api/portfolios/5": () => json({ id: 5, name: "Main", currency: "CHF" }),
    "GET /api/portfolios/5/snapshots": () => json([]),
    "GET /api/price-sources": () => json([]),
    "POST /api/price-sources/lookup": () =>
      json({ status: "not_found", listings: [], problems: [] }),
    "GET /api/portfolios/5/prefill": () =>
      json([
        {
          ticker: "XUS",
          name: "US Equity",
          type: "ETF",
          units: "10",
          price: "80.0",
          value: "800",
          in_policy: true,
          price_kind: "auto",
          auto,
          notice: null,
          listing_symbol: "XUS.US",
        },
        {
          ticker: "ETH",
          name: "Ethereum",
          type: "crypto",
          units: "1",
          price: "2000",
          value: "2000",
          in_policy: true,
          price_kind: "auto",
          auto: null,
          notice: "no_rate",
          listing_symbol: "ethereum",
        },
      ]),
    "POST /api/portfolios/5/snapshots": () => json({ id: 42 }, 201),
    "GET /api/snapshots/42": () => json({}),
  });
}

describe("auto prices", () => {
  it("[CMP-01] [CMP-10] [PRC-11] [PRC-12] pre-fills the auto price and sends it as auto", async () => {
    const calls = valuesSetup();
    renderApp("/portfolios/5/values");
    expect(await screen.findByLabelText("Price of XUS")).toHaveValue("80.0");
    expect(screen.getByLabelText("Value of XUS")).toHaveValue("800.00");
    expect(screen.getByText(/auto: XUS\.US 100\.00 USD × 0\.8 → CHF/)).toBeInTheDocument();
    // PRC-12: a small marker, no dialog
    expect(screen.getByRole("img", { name: /more than 3 days old/ })).toBeInTheDocument();
    // PRC-11: no rate, so ETH is entered by hand
    expect(screen.getByText(/no exchange rate for ethereum yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save values" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path.endsWith("/snapshots"))?.body).toEqual(
        {
          values: [
            { ticker: "XUS", units: "10" }, // no price: the auto price is taken and kept
            { ticker: "ETH", units: "1", price: "2000" },
          ],
          corrects_snapshot_id: null,
        },
      ),
    );
  });

  it("[CMP-01] a price changed by hand is manual; the auto price can come back", async () => {
    const calls = valuesSetup();
    renderApp("/portfolios/5/values");
    const price = await screen.findByLabelText("Price of XUS");
    await userEvent.clear(price);
    await userEvent.type(price, "81");
    expect(screen.getByText("Changed by hand: saved as a manual price.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use the auto price again" }));
    expect(screen.getByLabelText("Price of XUS")).toHaveValue("80.0");
    await userEvent.clear(screen.getByLabelText("Price of XUS"));
    await userEvent.type(screen.getByLabelText("Price of XUS"), "82");
    await userEvent.click(screen.getByRole("button", { name: "Save values" }));
    await waitFor(() =>
      expect(
        (
          calls.find((c) => c.method === "POST" && c.path.endsWith("/snapshots"))?.body as {
            values: object[];
          }
        ).values[0],
      ).toEqual({ ticker: "XUS", units: "10", price: "82" }),
    );
  });
});
