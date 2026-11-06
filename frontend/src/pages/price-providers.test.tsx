import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { admin, json, mockApi, renderApp } from "@/test/utils";

const ecb = {
  id: 1,
  provider: "frankfurter",
  name: "Frankfurter (ECB)",
  built_in: true,
  key_possible: false,
  key_required: false,
  api_key_last4: null,
  daily_call_limit: null,
  enabled: true,
  calls_today: 2,
  quota_exhausted: false,
  updated_at: "2026-11-01T10:00:00+00:00",
};
const eodhd = {
  ...ecb,
  id: 2,
  provider: "eodhd",
  name: "EODHD",
  built_in: false,
  key_possible: true,
  key_required: true,
  api_key_last4: "5678",
  daily_call_limit: 20,
  calls_today: 20,
  quota_exhausted: true,
};
const addable = [
  { provider: "yahoo", name: "Yahoo Finance", key_possible: false, key_required: false },
  { provider: "coingecko", name: "CoinGecko", key_possible: true, key_required: false },
];

function setup() {
  let providers: object[] = [ecb, eodhd];
  const calls = mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(admin),
    "GET /api/admin/price-providers": () => json({ providers, addable, keys_available: true }),
    "POST /api/admin/price-providers": (_, body) => {
      const created = { ...eodhd, ...(body as object), id: 3, name: "Yahoo Finance" };
      providers = [...providers, created];
      return json(created, 201);
    },
    "PUT /api/admin/price-providers/2": (_, body) => json({ ...eodhd, ...(body as object) }),
    "POST /api/admin/price-providers/1/test": () =>
      json({
        ok: true,
        message: "Connected to Frankfurter (ECB)",
        code: "price_connection_ok",
        params: { provider: "Frankfurter (ECB)" },
      }),
  });
  renderApp("/price-providers");
  return calls;
}

describe("price providers", () => {
  it("[PRC-11] [PRC-10] lists the built-in exchange rate source with a test only", async () => {
    setup();
    const builtIn = (await screen.findByText("built in")).closest("div.rounded-lg")!;
    const card = within(builtIn as HTMLElement);
    expect(card.getByText("2 calls today (UTC)")).toBeInTheDocument();
    expect(card.queryByRole("button", { name: "Save" })).toBeNull();
    await userEvent.click(card.getByRole("button", { name: "Test connection" }));
    expect(await card.findByText("Connected to Frankfurter (ECB)")).toBeInTheDocument();
  });

  it("[PRC-01] [PRC-08] [PRC-10] changes a provider; shows its calls and limit", async () => {
    const calls = setup();
    const form = await screen.findByRole("form", { name: "Price provider EODHD" });
    expect(within(form).getByText("20 of 20 calls today (UTC)")).toBeInTheDocument();
    expect(within(form).getByText("limit reached today")).toBeInTheDocument();
    const key = within(form).getByLabelText("API key");
    expect(key).toHaveAttribute("placeholder", expect.stringContaining("5678"));
    await userEvent.clear(within(form).getByLabelText("Calls per day"));
    await userEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
        provider: "eodhd",
        daily_call_limit: null, // empty: no limit
        enabled: true,
        api_key: null, // the stored key stays
      }),
    );
  });

  it("[PRC-01] adds a provider not added yet; Yahoo is marked unofficial", async () => {
    const calls = setup();
    await userEvent.selectOptions(await screen.findByLabelText("Add a price provider"), "yahoo");
    const form = screen.getByRole("form", { name: "Price provider Yahoo Finance" });
    expect(within(form).getByText(/unofficial interface/)).toBeInTheDocument();
    expect(within(form).queryByLabelText(/API key/)).toBeNull(); // Yahoo takes no key
    await userEvent.click(within(form).getByRole("button", { name: "Add" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        provider: "yahoo",
        daily_call_limit: null,
        enabled: true,
        api_key: null,
      }),
    );
  });
});

describe("price update schedule", () => {
  it("[PRC-07] [PRC-10] sets the schedule and shows the last run", async () => {
    const update = {
      time_of_day: "22:00",
      time_zone: "UTC",
      interval_hours: 24,
      intervals: [1, 2, 3, 4, 6, 8, 12, 24],
      next_run_at: "2026-11-04T22:00:00+00:00",
      last_run: {
        trigger: "schedule",
        started_at: "2026-11-03T22:00:00+00:00",
        finished_at: "2026-11-03T22:00:05+00:00",
        result: { "Yahoo Finance": { updated: 12, skipped: 1, failed: 0, not_found: 1 } },
      },
    };
    const calls = mockApi({
      "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
      "GET /api/auth/me": () => json(admin),
      "GET /api/admin/price-providers": () =>
        json({ providers: [], addable: [], keys_available: true }),
      "GET /api/admin/price-update": () => json(update),
      "PUT /api/admin/price-update": (_, body) => json({ ...update, ...(body as object) }),
    });
    renderApp("/price-providers");
    const form = await screen.findByRole("form", { name: "Price update" });
    expect(
      await within(form).findByText(
        "Yahoo Finance: last update: 12 updated, 1 skipped (limit), 1 failed",
      ),
    ).toBeInTheDocument();
    expect(within(form).getByText(/Last run: .* \(scheduled\)/)).toBeInTheDocument();
    await userEvent.selectOptions(within(form).getByLabelText("Time zone"), "Europe/Zurich");
    await userEvent.selectOptions(within(form).getByLabelText("Interval"), "12");
    await userEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
        time_of_day: "22:00",
        time_zone: "Europe/Zurich",
        interval_hours: 12,
      }),
    );
  });
});
