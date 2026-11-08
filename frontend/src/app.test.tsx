import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { admin, adminInvestor, investor, json, mockApi, renderApp } from "@/test/utils";

const version = { "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }) };

describe("login and navigation", () => {
  it("[USR-01] sends visitors without session to the login page", async () => {
    mockApi({ "GET /api/auth/me": () => json({ detail: "Not logged in" }, 401) });
    renderApp("/portfolios");
    expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
  });

  it("[USR-01] logs in and shows the dashboard", async () => {
    let loggedIn = false;
    const calls = mockApi({
      ...version,
      "GET /api/auth/me": () => (loggedIn ? json(investor) : json({ detail: "x" }, 401)),
      "POST /api/auth/login": () => {
        loggedIn = true;
        return json(investor);
      },
    });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Username"), "alice");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/auth/login")?.body).toEqual({
      username: "alice",
      password: "correct horse battery",
    });
  });

  it.each([
    [401, "Invalid username or password."],
    [429, "Too many failed attempts. Please wait 15 minutes and try again."],
    [500, "Login failed. Please try again."],
  ])("[USR-01] [NFR-02] shows a login failure (%i)", async (status, message) => {
    mockApi({
      "GET /api/auth/me": () => json({ detail: "x" }, 401),
      "POST /api/auth/login": () => json({ detail: "x" }, status),
    });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Username"), "alice");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("[USR-04] [NFR-06] shows the investor navigation and the version", async () => {
    mockApi({ ...version, "GET /api/auth/me": () => json(investor) });
    renderApp("/");
    const nav = await screen.findAllByRole("navigation", { name: "Main" });
    const links = within(nav[0]!)
      .getAllByRole("link")
      .map((l) => l.textContent);
    expect(links).toEqual(["Dashboard", "Portfolios", "Policies", "Timeline"]);
    expect(await screen.findAllByText("Version 1.2.0")).not.toHaveLength(0);
  });

  it("[NFR-15] [NFR-16] shows the notice and links to source and licenses", async () => {
    mockApi({
      "GET /api/version": () => json({ version: "1.2.0", commit: "0123456789abcdef" }),
      "GET /api/auth/me": () => json(investor),
    });
    renderApp("/");
    // The exact commit the running app was built from (AGPL), once the version is loaded
    await waitFor(() =>
      expect(screen.getAllByRole("link", { name: "Source code" })[0]).toHaveAttribute(
        "href",
        "https://github.com/gravity981/yap/tree/0123456789abcdef",
      ),
    );
    expect(screen.getAllByRole("link", { name: "License (AGPL-3.0)" })[0]).toHaveAttribute(
      "href",
      "https://github.com/gravity981/yap/blob/main/LICENSE",
    );
    expect(screen.getAllByRole("link", { name: "Third-party licenses" })[0]).toHaveAttribute(
      "href",
      "/third-party-licenses.txt",
    );
    expect(screen.getAllByRole("note", { name: "Not financial advice" })).not.toHaveLength(0);
  });

  it("[NFR-15] states on the login page that it gives no financial advice", async () => {
    mockApi({ ...version, "GET /api/auth/me": () => json({ detail: "x" }, 401) });
    renderApp("/login");
    expect(await screen.findByRole("note", { name: "Not financial advice" })).toHaveTextContent(
      /no investment, legal or tax advice/,
    );
  });

  it("[USR-05] gives admins account, AI reviewer and price provider management only", async () => {
    mockApi({
      ...version,
      "GET /api/auth/me": () => json(admin),
      "GET /api/admin/accounts": () => json([]),
    });
    renderApp("/portfolios");
    expect(await screen.findByRole("heading", { name: "Accounts" })).toBeInTheDocument();
    const nav = screen.getAllByRole("navigation", { name: "Main" })[0]!;
    expect(
      within(nav)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(["Accounts", "AI reviewers", "Price providers"]);
  });

  it("[USR-09] gives an account with both roles both navigations", async () => {
    mockApi({
      ...version,
      "GET /api/auth/me": () => json(adminInvestor),
      "GET /api/admin/accounts": () => json([]),
      "GET /api/portfolios": () => json([]),
      "GET /api/timeline": () => json([]),
    });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    const nav = screen.getAllByRole("navigation", { name: "Main" })[0]!;
    expect(
      within(nav)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual([
      "Dashboard",
      "Portfolios",
      "Policies",
      "Timeline",
      "Accounts",
      "AI reviewers",
      "Price providers",
    ]);
    expect(within(nav).getByText("Administration")).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole("link", { name: "Accounts" }));
    expect(await screen.findByRole("heading", { name: "Accounts" })).toBeInTheDocument();
  });

  it("[USR-05] keeps investors away from the AI reviewer configuration", async () => {
    mockApi({ ...version, "GET /api/auth/me": () => json(investor) });
    renderApp("/ai-reviewers");
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("[USR-05] keeps investors away from account management", async () => {
    mockApi({ ...version, "GET /api/auth/me": () => json(investor) });
    renderApp("/accounts");
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("[NFR-06] opens the navigation as a menu on phones", async () => {
    mockApi({ ...version, "GET /api/auth/me": () => json(investor) });
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Open menu" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("link", { name: "Policies" }));
    expect(await screen.findByRole("heading", { name: "Policies" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("[USR-01] logs out", async () => {
    let loggedIn = true;
    mockApi({
      ...version,
      "GET /api/auth/me": () => (loggedIn ? json(investor) : json({ detail: "x" }, 401)),
      "POST /api/auth/logout": () => {
        loggedIn = false;
        return new Response(null, { status: 204 });
      },
    });
    renderApp("/");
    await userEvent.click((await screen.findAllByRole("button", { name: "alice" }))[0]!);
    await userEvent.click(await screen.findByRole("menuitem", { name: "Log out" }));
    expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
  });
});

describe("password change", () => {
  it("[USR-02] [USR-03] forces a new password after a reset", async () => {
    let mustChange = true;
    const calls = mockApi({
      ...version,
      "GET /api/auth/me": () => json({ ...investor, must_change_password: mustChange }),
      "POST /api/auth/password": () => {
        mustChange = false;
        return new Response(null, { status: 204 });
      },
    });
    renderApp("/portfolios");
    expect(await screen.findByText(/temporary password/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Current password"), "temporary password 1");
    await userEvent.type(screen.getByLabelText("New password"), "short");
    await userEvent.type(screen.getByLabelText("Repeat new password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(screen.getByText(/at least 12 characters/)).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("New password"));
    await userEvent.type(screen.getByLabelText("New password"), "my own long password");
    await userEvent.clear(screen.getByLabelText("Repeat new password"));
    await userEvent.type(screen.getByLabelText("Repeat new password"), "another long password");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(screen.getByText("The new passwords do not match.")).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("Repeat new password"));
    await userEvent.type(screen.getByLabelText("Repeat new password"), "my own long password");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/auth/password")?.body).toEqual({
      current_password: "temporary password 1",
      new_password: "my own long password",
    });
  });

  it("[USR-03] shows the server's message at the field", async () => {
    mockApi({
      ...version,
      "GET /api/auth/me": () => json(investor),
      "POST /api/auth/password": () =>
        json(
          {
            detail: "x",
            problems: [{ path: "current_password", message: "The current password is wrong" }],
          },
          422,
        ),
    });
    renderApp("/password");
    await userEvent.type(await screen.findByLabelText("Current password"), "wrong password");
    await userEvent.type(screen.getByLabelText("New password"), "my own long password");
    await userEvent.type(screen.getByLabelText("Repeat new password"), "my own long password");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("The current password is wrong")).toBeInTheDocument();
  });
});
