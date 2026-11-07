import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { browserTimeZone, currentTimeZone, formatDateTime } from "@/lib/format";
import { admin, investor, json, mockApi, renderApp } from "@/test/utils";

const options = [
  {
    id: 1,
    name: "Deep",
    description: "Thorough, slower",
    provider: "anthropic",
    model: "claude-x",
    monthly_review_limit: 5,
  },
  {
    id: 2,
    name: "Quick",
    description: null,
    provider: "openai",
    model: "gpt-x",
    monthly_review_limit: 50,
  },
];

function setup(me: object = investor, extra: Parameters<typeof mockApi>[0] = {}) {
  let chosen = (me as { ai_reviewer_id: number | null }).ai_reviewer_id;
  let manual = false;
  const calls = mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () =>
      json({ ...me, ai_reviewer_id: chosen, manual_review_default: manual }),
    "GET /api/ai-reviewers": () => json(options),
    "GET /api/reviews/usage": () => {
      const option = options.find((o) => o.id === chosen);
      return json({
        ai_reviewer_id: option?.id ?? null,
        ai_reviewer_name: option?.name ?? null,
        used: 2,
        limit: option?.monthly_review_limit ?? 0,
        left: 0,
        unavailable_reason: option ? null : "Choose an AI reviewer",
      });
    },
    "PUT /api/ai-reviewers/choice": (_, body) => {
      ({ ai_reviewer_id: chosen, manual } = body as { ai_reviewer_id: number; manual: boolean });
      return json(body);
    },
    "GET /api/portfolios": () => json([]),
    "GET /api/timeline": () => json([]),
    ...extra,
  });
  renderApp("/settings");
  return calls;
}

describe("settings", () => {
  it("[USR-08] shows the enabled reviewers with the current choice and its usage", async () => {
    setup();
    const form = await screen.findByRole("form", { name: "Default review method" });
    expect(await within(form).findByRole("radio", { name: /^Deep/ })).toBeChecked();
    expect(within(form).getByRole("radio", { name: /^Quick/ })).not.toBeChecked();
    expect(within(form).getByText("Thorough, slower")).toBeInTheDocument();
    expect(
      await within(form).findByText("2 of 5 reviews with Deep used this month."),
    ).toBeInTheDocument();
    expect(within(form).getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("[USR-08] [REV-16] chooses another reviewer", async () => {
    const calls = setup();
    const form = await screen.findByRole("form", { name: "Default review method" });
    await userEvent.click(await within(form).findByRole("radio", { name: /^Quick/ }));
    await userEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await within(form).findByText("Saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      ai_reviewer_id: 2,
      manual: false,
    });
    await waitFor(() =>
      expect(
        within(form).getByText("2 of 50 reviews with Quick used this month."),
      ).toBeInTheDocument(),
    );
  });

  it("[USR-08] [REV-18] chooses manual reviews as the default", async () => {
    const calls = setup();
    const form = await screen.findByRole("form", { name: "Default review method" });
    const manual = within(form).getByRole("radio", { name: /^Manual/ });
    expect(manual).not.toBeChecked();
    expect(
      within(form).getByText(/paste its answer back. Counts towards no limit/),
    ).toBeInTheDocument();
    await userEvent.click(manual);
    await userEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await within(form).findByText("Saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      ai_reviewer_id: null,
      manual: true,
    });
    await waitFor(() => expect(within(form).getByRole("radio", { name: /^Manual/ })).toBeChecked());
    expect(within(form).getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("[USR-08] asks to choose again when the reviewer is gone", async () => {
    setup({ ...investor, ai_reviewer_id: 7 });
    expect(await screen.findByText(/no longer available/)).toBeInTheDocument();
  });

  it("[USR-10] [USR-05] gives admin-only accounts the language but no AI reviewer", async () => {
    setup(admin);
    expect(await screen.findByLabelText("Language")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Default review method" })).not.toBeInTheDocument();
  });

  it("[USR-10] switches the language of the account", async () => {
    let language: string | null = null;
    const calls = setup(investor, {
      "GET /api/auth/me": () => json({ ...investor, language }),
      "PUT /api/auth/language": (_, body) => {
        language = (body as { language: string | null }).language;
        return json({ ...investor, language });
      },
    });
    await userEvent.selectOptions(await screen.findByLabelText("Language"), "de");
    expect(await screen.findByRole("heading", { name: "Einstellungen" })).toBeInTheDocument();
    expect(screen.getByLabelText("Sprache")).toHaveValue("de");
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ language: "de" });
    await userEvent.selectOptions(screen.getByLabelText("Sprache"), "");
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
  });

  it("[USR-11] [NFR-14] switches the time zone of the account", async () => {
    let timeZone: string | null = null;
    const calls = setup(admin, {
      "GET /api/auth/me": () => json({ ...admin, time_zone: timeZone }),
      "PUT /api/auth/time-zone": (_, body) => {
        timeZone = (body as { time_zone: string | null }).time_zone;
        return json({ ...admin, time_zone: timeZone });
      },
    });
    const select = await screen.findByLabelText("Time zone");
    expect(select).toHaveValue("");
    expect(
      within(select).getByRole("option", { name: `Like the browser (${browserTimeZone()})` }),
    ).toBeInTheDocument();
    await userEvent.selectOptions(select, "Asia/Tokyo");
    await waitFor(() => expect(screen.getByLabelText("Time zone")).toHaveValue("Asia/Tokyo"));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ time_zone: "Asia/Tokyo" });
    // Dates everywhere follow the account's time zone
    expect(currentTimeZone()).toBe("Asia/Tokyo");
    expect(formatDateTime("2026-07-01T10:00:00+00:00", "en-GB")).toBe("1 Jul 2026, 19:00");
    await userEvent.selectOptions(screen.getByLabelText("Time zone"), "");
    await waitFor(() => expect(currentTimeZone()).toBeUndefined());
  });
});
