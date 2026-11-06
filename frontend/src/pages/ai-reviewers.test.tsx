import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { admin, json, mockApi, renderApp } from "@/test/utils";

const deep = {
  id: 1,
  name: "Deep",
  description: "Thorough, slower",
  provider: "anthropic",
  model: "claude-opus-5-5",
  api_key_last4: "1234",
  monthly_review_limit: 30,
  enabled: true,
  updated_at: "2026-10-30T10:00:00+00:00",
};

function setup(extra: Parameters<typeof mockApi>[0] = {}, keysAvailable = true) {
  let reviewers: (typeof deep)[] = [deep];
  const calls = mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(admin),
    "GET /api/admin/ai-reviewers": () => json({ reviewers, keys_available: keysAvailable }),
    "POST /api/admin/ai-reviewers": (_, body) => {
      const created = { ...deep, ...(body as object), id: 2, api_key_last4: "9999" };
      reviewers = [...reviewers, created];
      return json(created, 201);
    },
    "PUT /api/admin/ai-reviewers/1": (_, body) => {
      reviewers = [{ ...deep, ...(body as object) }];
      return json(reviewers[0]);
    },
    "POST /api/admin/ai-reviewers/1/archive": () => {
      reviewers = [];
      return new Response(null, { status: 204 });
    },
    ...extra,
  });
  renderApp("/ai-reviewers");
  return calls;
}

describe("AI reviewers", () => {
  it("[REV-13] [REV-15] shows each reviewer without the stored key", async () => {
    setup();
    const form = await screen.findByRole("form", { name: "AI reviewer Deep" });
    expect(within(form).getByLabelText("Provider")).toHaveValue("anthropic");
    expect(within(form).getByLabelText("Model")).toHaveValue("claude-opus-5-5");
    expect(within(form).getByLabelText(/^Description/)).toHaveValue("Thorough, slower");
    expect(within(form).getByLabelText("API key")).toHaveValue("");
    expect(within(form).getByLabelText("API key")).toHaveAttribute(
      "placeholder",
      expect.stringContaining("ends in 1234"),
    );
    expect(within(form).getByLabelText(/^Enabled/)).toBeChecked();
  });

  it("[REV-13] [REV-15] creates another reviewer with its own key", async () => {
    const calls = setup();
    await userEvent.click(await screen.findByRole("button", { name: "New AI reviewer" }));
    const form = screen.getByRole("form", { name: "AI reviewer New AI reviewer" });
    await userEvent.type(within(form).getByLabelText("Name"), "Quick");
    await userEvent.selectOptions(within(form).getByLabelText("Provider"), "openai");
    await userEvent.type(within(form).getByLabelText("Model"), "gpt-x");
    await userEvent.type(within(form).getByLabelText("API key"), "sk-new-9999");
    await userEvent.clear(within(form).getByLabelText("Reviews per investor and month"));
    await userEvent.type(within(form).getByLabelText("Reviews per investor and month"), "50");
    await userEvent.click(within(form).getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("form", { name: "AI reviewer Quick" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      name: "Quick",
      description: null,
      provider: "openai",
      model: "gpt-x",
      monthly_review_limit: 50,
      enabled: true,
      api_key: "sk-new-9999",
    });
  });

  it("[REV-14] [REV-15] saves changes and keeps the stored key when none is entered", async () => {
    const calls = setup();
    const form = await screen.findByRole("form", { name: "AI reviewer Deep" });
    await userEvent.click(within(form).getByLabelText(/^Enabled/));
    await userEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
        enabled: false,
        api_key: null,
      }),
    );
    expect(await within(form).findByText("disabled")).toBeInTheDocument();
  });

  it("[REV-14] tests the connection and shows the result", async () => {
    setup({
      "POST /api/admin/ai-reviewers/1/test": () =>
        json({ ok: false, message: "Anthropic rejected the API key" }),
    });
    const form = await screen.findByRole("form", { name: "AI reviewer Deep" });
    await userEvent.click(within(form).getByRole("button", { name: "Test connection" }));
    expect(await within(form).findByText("Anthropic rejected the API key")).toBeInTheDocument();
  });

  it("[REV-13] archives a reviewer after confirmation", async () => {
    const calls = setup();
    const form = await screen.findByRole("form", { name: "AI reviewer Deep" });
    await userEvent.click(within(form).getByRole("button", { name: "Archive" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/Past reviews keep its name/);
    await userEvent.click(within(dialog).getByRole("button", { name: "Archive" }));
    expect(await screen.findByText(/No AI reviewers yet/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/admin/ai-reviewers/1/archive")).toBe(true);
  });

  it("[REV-15] warns when the server has no secret for keys", async () => {
    setup({}, false);
    expect(await screen.findByText(/APP_SECRET_KEY is not set/)).toBeInTheDocument();
  });
});
