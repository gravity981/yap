import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { admin, json, mockApi, renderApp } from "@/test/utils";

const alice = {
  id: 1,
  username: "alice",
  is_admin: false,
  is_investor: true,
  base_currency: "CHF",
  active: true,
  must_change_password: true,
  created_at: "2026-01-15T09:00:00+00:00",
};
const root = {
  ...alice,
  id: 9,
  username: "root",
  is_admin: true,
  is_investor: false,
  base_currency: null,
  must_change_password: false,
};

function setup(extra: Parameters<typeof mockApi>[0] = {}) {
  let accounts = [alice, root];
  const calls = mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(admin),
    "GET /api/admin/accounts": () => json(accounts),
    "POST /api/admin/accounts": (_, body) => {
      const created = { ...alice, id: 2, username: (body as { username: string }).username };
      accounts = [...accounts, created];
      return json(created, 201);
    },
    "POST /api/admin/accounts/1/deactivate": () => {
      accounts = [{ ...alice, active: false }, root];
      return json(accounts[0]);
    },
    "POST /api/admin/accounts/1/reset-password": () => json(alice),
    "PUT /api/admin/accounts/1/base-currency": () => json(alice),
    "PUT /api/admin/accounts/9/roles": (_, body) => {
      accounts = [alice, { ...root, ...(body as object), base_currency: "CHF" }];
      return json(accounts[1]);
    },
    "DELETE /api/admin/accounts/1": () => {
      accounts = [root];
      return new Response(null, { status: 204 });
    },
    ...extra,
  });
  renderApp("/accounts");
  return calls;
}

async function row(username: string) {
  return (await screen.findByRole("cell", { name: username })).closest("tr")!;
}

describe("account management", () => {
  it("[USR-02] [USR-09] lists accounts with roles and status; only roles on the own account", async () => {
    setup();
    const aliceRow = await row("alice");
    expect(within(aliceRow).getByText("temporary password")).toBeInTheDocument();
    expect(within(aliceRow).getByText("CHF")).toBeInTheDocument();
    expect(within(aliceRow).getByRole("cell", { name: "investor" })).toBeInTheDocument();
    const rootRow = await row("root");
    expect(within(rootRow).getByRole("cell", { name: "admin" })).toBeInTheDocument();
    expect(
      within(rootRow)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["Roles"]);
  });

  it("[USR-02] [USR-06] creates an investor with a temporary password", async () => {
    const calls = setup();
    await userEvent.click(await screen.findByRole("button", { name: "New account" }));
    await userEvent.type(screen.getByLabelText("Username"), "bob");
    await userEvent.type(screen.getByLabelText("Temporary password"), "temporary password 1");
    expect(screen.getByLabelText(/^Investor/)).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await row("bob")).toBeInTheDocument();
    expect(
      calls.find((c) => c.method === "POST" && c.path === "/api/admin/accounts")?.body,
    ).toEqual({
      username: "bob",
      temporary_password: "temporary password 1",
      is_admin: false,
      is_investor: true,
      base_currency: "CHF",
    });
  });

  it("[USR-09] creates an admin without investor data", async () => {
    const calls = setup();
    await userEvent.click(await screen.findByRole("button", { name: "New account" }));
    await userEvent.type(screen.getByLabelText("Username"), "carol");
    await userEvent.type(screen.getByLabelText("Temporary password"), "temporary password 1");
    await userEvent.click(screen.getByLabelText(/^Investor/));
    await userEvent.click(screen.getByLabelText(/^Admin/));
    expect(screen.queryByLabelText("Base currency")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    await vi.waitFor(() =>
      expect(
        calls.find((c) => c.method === "POST" && c.path === "/api/admin/accounts")?.body,
      ).toEqual({
        username: "carol",
        temporary_password: "temporary password 1",
        is_admin: true,
        is_investor: false,
      }),
    );
  });

  it("[USR-09] gives the own admin account the investor role", async () => {
    const calls = setup();
    await userEvent.click(within(await row("root")).getByRole("button", { name: "Roles" }));
    expect(screen.getByLabelText(/^Admin/)).toBeChecked();
    expect(screen.queryByLabelText("Base currency")).not.toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/^Investor/));
    expect(screen.getByLabelText("Base currency")).toHaveValue("CHF");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await within(await row("root")).findByText("admin, investor")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/admin/accounts/9/roles")?.body).toEqual({
      is_admin: true,
      is_investor: true,
      base_currency: "CHF",
    });
    // The own roles decide the navigation, so the account is loaded again
    expect(calls.filter((c) => c.path === "/api/auth/me").length).toBeGreaterThan(1);
  });

  it("[USR-09] reports why the investor role cannot be removed", async () => {
    const message =
      "The investor role cannot be removed while the account owns theses, policies or portfolios";
    setup({ "PUT /api/admin/accounts/1/roles": () => json({ detail: message }, 409) });
    await userEvent.click(within(await row("alice")).getByRole("button", { name: "Roles" }));
    await userEvent.click(screen.getByLabelText(/^Admin/));
    await userEvent.click(screen.getByLabelText(/^Investor/));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("[USR-02] shows validation errors at the field", async () => {
    setup({
      "POST /api/admin/accounts": () =>
        json(
          {
            detail: "x",
            problems: [{ path: "password", message: "Passwords need at least 12 characters" }],
          },
          422,
        ),
    });
    await userEvent.click(await screen.findByRole("button", { name: "New account" }));
    await userEvent.type(screen.getByLabelText("Username"), "bob");
    await userEvent.type(screen.getByLabelText("Temporary password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("Passwords need at least 12 characters")).toBeInTheDocument();
  });

  it("[USR-02] deactivates, resets the password and deletes", async () => {
    const calls = setup();
    await userEvent.click(within(await row("alice")).getByRole("button", { name: "Deactivate" }));
    expect(await within(await row("alice")).findByText("deactivated")).toBeInTheDocument();

    await userEvent.click(
      within(await row("alice")).getByRole("button", { name: "Reset password" }),
    );
    await userEvent.type(screen.getByLabelText("Temporary password"), "temporary password 2");
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(calls.some((c) => c.path === "/api/admin/accounts/1/reset-password")).toBe(true);

    await userEvent.click(within(await row("alice")).getByRole("button", { name: "Delete" }));
    const confirm = screen.getByRole("button", { name: "Delete account" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Type "alice" to confirm'), "alice");
    await userEvent.click(confirm);
    expect(await screen.findByRole("cell", { name: "root" })).toBeInTheDocument();
    expect(screen.queryByRole("cell", { name: "alice" })).not.toBeInTheDocument();
  });

  it("[USR-06] changes the base currency or reports why not", async () => {
    setup({
      "PUT /api/admin/accounts/1/base-currency": () =>
        json({ detail: "The base currency cannot change once snapshots exist" }, 409),
    });
    await userEvent.click(within(await row("alice")).getByRole("button", { name: "Currency" }));
    const input = screen.getByLabelText("Base currency");
    await userEvent.clear(input);
    await userEvent.type(input, "EUR");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText("The base currency cannot change once snapshots exist"),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
