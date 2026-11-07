import { expect, test, type Page } from "@playwright/test";

// One investor's way through the app, against the real backend (test strategy §2).
// The tests build on each other and run in order on one fresh database. Every
// test is split into named steps, which the list reporter prints as it goes.
test.describe.configure({ mode: "serial" });

const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "admin password 1";
const TEMPORARY = "temporary password 1";
const PASSWORD = "alice password 123";

async function login(page: Page, username: string, password: string) {
  await test.step(`log in as ${username}`, async () => {
    await page.goto("/login");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Log in" }).click();
  });
}

async function asAlice(page: Page) {
  await login(page, "alice", PASSWORD);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

test("[USR-01] [USR-02] [USR-03] an admin creates an investor who chooses an own password", async ({
  page,
}) => {
  await login(page, "admin", ADMIN_PASSWORD);
  await test.step("admin sees only account management", async () => {
    await expect(page.getByRole("heading", { name: "Accounts" })).toBeVisible();
  });
  await test.step("admin creates investor alice with a temporary password", async () => {
    await page.getByRole("button", { name: "New account" }).click();
    await page.getByLabel("Username").fill("alice");
    await page.getByLabel("Temporary password").fill(TEMPORARY);
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page.getByRole("cell", { name: "alice" })).toBeVisible();
  });
  await test.step("admin logs out", async () => {
    await page.context().clearCookies();
  });
  await login(page, "alice", TEMPORARY);
  await test.step("alice must choose an own password first", async () => {
    await expect(page.getByText(/You logged in with a temporary password/)).toBeVisible();
    await page.getByLabel("Current password").fill(TEMPORARY);
    await page.getByLabel("New password", { exact: true }).fill(PASSWORD);
    await page.getByLabel("Repeat new password").fill(PASSWORD);
    await page.getByRole("button", { name: "Change password" }).click();
  });
  await test.step("alice reaches the dashboard", async () => {
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });
});

test("[THS-01] [THS-02] [THS-07] writes a thesis in the markdown editor", async ({ page }) => {
  await asAlice(page);
  await test.step("open a new thesis, which starts from the template", async () => {
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Theses" })
      .click();
    await page.getByRole("link", { name: "New thesis" }).click();
    await expect(page.locator(".cm-content").first()).toContainText("Investment Thesis");
  });
  await test.step("type markdown and see the live preview", async () => {
    await page.getByLabel("Title").fill("Growth");
    await page.locator(".cm-content").first().click();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("# Global growth\n\nIndex funds follow the economy.");
    await expect(
      page.getByLabel("Preview").getByRole("heading", { name: "Global growth" }),
    ).toBeVisible();
  });
  await test.step("create the thesis; it starts as a draft", async () => {
    await page.getByRole("button", { name: "Create thesis" }).click();
    // Wait for the thesis page: role names match as substrings unless exact, and the
    // editor's preview already shows the heading "Global growth"
    await expect(page).toHaveURL(/\/theses\/\d+$/);
    await expect(page.getByRole("heading", { name: "Growth", exact: true })).toBeVisible();
    await expect(page.getByText("Index funds follow the economy.")).toBeVisible();
    await expect(page.getByText("not activated yet")).toBeVisible();
  });
  await test.step("activate the draft as revision 1", async () => {
    await page.getByRole("button", { name: "Activate draft" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Activate" }).click();
    await expect(page.getByText("revision 1", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "New draft" })).toBeVisible();
  });
});

test("[POL-01] [POL-02] [POL-05] [POL-06] creates and activates a policy", async ({ page }) => {
  await asAlice(page);
  await test.step("create policy core based on the thesis", async () => {
    await page.goto("/policies");
    await page.getByRole("button", { name: "New policy" }).click();
    await page.getByLabel("Name").fill("core");
    await page.getByLabel("Thesis").selectOption({ label: "Growth" });
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page.getByRole("heading", { name: "core", exact: true })).toBeVisible();
  });
  await test.step("edit the draft: XUS 50 %, ETH 50 %", async () => {
    await page.getByRole("button", { name: "Edit draft" }).click();
    const first = page.getByRole("group", { name: "Position 1" });
    await first.getByLabel("Ticker").fill("XUS");
    await first.getByLabel("Name").fill("US Equity ETF");
    await first.getByLabel("Target %").fill("50");
    await page.getByRole("button", { name: "Add position" }).click();
    const second = page.getByRole("group", { name: "Position 2" });
    await second.getByLabel("Ticker").fill("ETH");
    await second.getByLabel("Name").fill("Ethereum");
    await second.getByLabel("Type").selectOption("crypto");
    await second.getByLabel("Target %").fill("50");
    await expect(page.getByLabel("Target total")).toHaveText("Total target: 100.00 %");
    await page.getByRole("button", { name: "Save draft" }).click();
  });
  await test.step("activate the draft as core-v1", async () => {
    await page.getByRole("button", { name: "Activate draft" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Activate" }).click();
    await expect(page.getByText("active: core-v1")).toBeVisible();
  });
});

test("[PTF-01] [CMP-01] [CMP-05] [CMP-07] enters values and compares them with the policy", async ({
  page,
}) => {
  await asAlice(page);
  await test.step("create portfolio Main following core", async () => {
    await page.goto("/portfolios");
    await page.getByRole("button", { name: "New portfolio" }).click();
    await page.getByLabel("Name").fill("Main");
    await page.getByLabel("Policy").selectOption({ label: "core (core-v1)" });
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page.getByRole("heading", { name: "Main", exact: true })).toBeVisible();
  });
  await test.step("enter units and prices: XUS 70 x 100, ETH 1.5 x 2000", async () => {
    await page.getByRole("link", { name: "Enter values" }).click();
    await page.getByLabel("Units of XUS").fill("70");
    await page.getByLabel("Price of XUS").fill("100");
    await expect(page.getByLabel("Value of XUS")).toHaveValue("7000.00");
    await page.getByLabel("Units of ETH").fill("1.5");
    await page.getByLabel("Price of ETH").fill("2000");
    await page.getByRole("button", { name: "Save values" }).click();
    await expect(page.getByRole("heading", { name: "Snapshot" })).toBeVisible();
  });
  await test.step("XUS at 70 % is above its sell threshold of 60 %", async () => {
    const xus = page.getByRole("row").filter({ hasText: "XUS" });
    await expect(xus.getByText("above sell threshold")).toBeVisible();
  });
  await test.step("charts show bars per position and the pie by type", async () => {
    await expect(page.getByRole("img", { name: /^XUS: 70.0 % of the portfolio/ })).toBeVisible();
    await expect(page.getByRole("figure", { name: "Allocation by type" })).toBeVisible();
  });
});

test("[RB-01] [RB-02] [RB-03] [RB-16] [RB-19] [RB-22] [RB-24] rebalances, prints the report and confirms", async ({
  page,
}) => {
  await asAlice(page);
  await test.step("rebalance Main from a fresh snapshot with the current prices", async () => {
    await page.goto("/portfolios");
    await page.getByRole("link", { name: "Main" }).click();
    await page.getByRole("link", { name: "Rebalance" }).click();
    await expect(
      page.getByRole("heading", { name: "Rebalance Main: current values" }),
    ).toBeVisible();
    await expect(page.getByLabel("Units of XUS")).toHaveValue("70");
    await expect(page.getByLabel("Price of XUS")).toHaveValue("100");
    await page.getByRole("button", { name: "Save and rebalance" }).click();
  });
  await test.step("instructions: sell 15 units XUS (1,500) down to the midband of 55 %", async () => {
    const sells = page.getByRole("list", { name: "Sell" });
    await expect(sells).toContainText("XUS");
    await expect(sells).toContainText("15 units");
    await expect(sells).toContainText("1,500");
  });
  await test.step("a withdrawal of 6,000 also sells 1,200 ETH, then back to none", async () => {
    const field = page.getByRole("textbox", { name: "Withdrawal", exact: true });
    await field.fill("6000");
    await page.getByRole("button", { name: "Recalculate" }).click();
    await expect(page.getByRole("list", { name: "Sell", exact: true })).toContainText("4,800");
    const withdrawal = page.getByRole("list", { name: "Sell for the withdrawal" });
    await expect(withdrawal).toContainText("ETH");
    await expect(withdrawal).toContainText("1,200");
    await expect(page.getByLabel("Executed Sell (Withdrawal) ETH")).toHaveValue(/^1200/);
    await field.fill("");
    await page.getByRole("button", { name: "Recalculate" }).click();
    await expect(page.getByRole("list", { name: "Sell", exact: true })).toContainText("1,500");
  });
  await test.step("the print report hides its print button on paper", async () => {
    await page.getByRole("link", { name: "Report for printing / PDF" }).click();
    await expect(
      page.getByRole("heading", { name: "Rebalancing instructions – Main" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Print / save as PDF" })).toBeVisible();
    await page.emulateMedia({ media: "print" });
    await expect(page.getByRole("button", { name: "Print / save as PDF" })).toBeHidden();
    await page.emulateMedia({ media: "screen" });
    await page.goBack();
  });
  await test.step("confirm with 14 units sold for 1,400 instead of 15 for 1,500", async () => {
    await page.getByLabel("Executed units Sell XUS").fill("14");
    await page.getByLabel("Executed Sell XUS").fill("1400");
    await page.getByRole("button", { name: "Confirm rebalance" }).click();
    await expect(page.getByRole("heading", { name: /Rebalance of/ })).toBeVisible();
  });
  await test.step("the values after the rebalance reflect the executed sell", async () => {
    await page.getByRole("link", { name: "values after" }).click();
    await expect(page.getByRole("row").filter({ hasText: "XUS" })).toContainText("5,600");
  });
});

test("[TL-01] [TL-02] shows the decisions in the timeline", async ({ page }) => {
  await asAlice(page);
  await test.step("open the timeline", async () => {
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Timeline" })
      .click();
  });
  await test.step("the confirmed rebalance is listed and opens its details", async () => {
    const rebalance = page.getByText(/Main: rebalanced, sold 1,400/);
    await expect(rebalance).toBeVisible();
    await rebalance.click();
    await expect(page.getByText(/XUS Sell: 1,400/)).toBeVisible();
  });
  await test.step("the policy activation is listed", async () => {
    await expect(page.getByText("core-v1 activated (no portfolios)")).toBeVisible();
  });
});

test("[IMP-01] [IMP-07] [IMP-10] imports a thesis and exports it again", async ({ page }) => {
  await asAlice(page);
  await test.step("choose a thesis file and see the preview", async () => {
    await page.goto("/theses");
    await page.getByRole("button", { name: "Import" }).click();
    await page.getByLabel("Import file").setInputFiles({
      name: "thesis.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({ schema_version: "1.0", title: "Imported view", content_md: "# Imported" }),
      ),
    });
    await expect(page.getByRole("dialog")).toContainText("Imported view");
  });
  await test.step("import it; the imported thesis opens as a draft", async () => {
    await page.getByRole("dialog").getByRole("button", { name: "Import", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Imported view", level: 1 })).toBeVisible();
    await expect(page.getByText("not activated yet")).toBeVisible();
  });
  await test.step("the export gives back the same content", async () => {
    const exportLink = page.getByRole("link", { name: "Export revision 1 as JSON" });
    const response = await page.request.get((await exportLink.getAttribute("href"))!);
    expect(response.ok()).toBe(true);
    expect(await response.json()).toMatchObject({
      schema_version: "1.3",
      title: "Imported view",
      content_md: "# Imported",
    });
  });
});

test("[NFR-06] works on a phone-sized screen", async ({ page }) => {
  await test.step("use a 390 px wide screen", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
  });
  await asAlice(page);
  await test.step("navigate through the menu", async () => {
    await page.getByRole("button", { name: "Open menu" }).click();
    await page.getByRole("dialog").getByRole("link", { name: "Portfolios" }).click();
    await expect(page.getByRole("heading", { name: "Portfolios" })).toBeVisible();
  });
  await test.step("nothing is wider than the screen", async () => {
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);
  });
});

test("[REV-13] [REV-14] [USR-08] [REV-01] [REV-11] [TL-01] reviews a thesis draft and confirms it", async ({
  page,
}) => {
  await login(page, "admin", ADMIN_PASSWORD);
  await test.step("the admin sets up an AI reviewer", async () => {
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "AI reviewers" })
      .click();
    await page.getByRole("button", { name: "New AI reviewer" }).click();
    const created = page.getByRole("form", { name: "AI reviewer New AI reviewer" });
    await created.getByLabel("Name").fill("Standard");
    await created.getByLabel("Provider").selectOption("anthropic");
    await created.getByLabel("Model").fill("fake-model");
    await created.getByLabel("API key").fill("sk-e2e-key-1234");
    await created.getByLabel("Reviews per investor and month").fill("5");
    await created.getByRole("button", { name: "Create" }).click();
    const standard = page.getByRole("form", { name: "AI reviewer Standard" });
    await expect(standard.getByLabel("API key")).toHaveAttribute("placeholder", /ends in 1234/);
    await standard.getByRole("button", { name: "Test connection" }).click();
    await expect(standard.getByRole("alert")).toHaveText(
      "Connected to anthropic, model fake-model",
    );
    await page.context().clearCookies();
  });
  await asAlice(page);
  await test.step("alice chooses the AI reviewer in her settings", async () => {
    await page.goto("/settings");
    await page.getByRole("radio", { name: /^Standard/ }).check();
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Saved.")).toBeVisible();
  });
  await test.step("open a new draft of the thesis Growth", async () => {
    await page.goto("/theses");
    await page.getByRole("link", { name: "Growth" }).click();
    await page.getByRole("button", { name: "New draft" }).click();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByText("draft r2")).toBeVisible();
  });
  const review = page.getByRole("region", { name: "Thesis review" });
  await test.step("start the review and wait for its result", async () => {
    await expect(review.getByText(/0 of 5 reviews with Standard used this month/)).toBeVisible();
    await review.getByRole("button", { name: "Start review" }).click();
    await expect(review.getByRole("img", { name: "Total score: 6.5 of 10" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(review.getByText("not confirmed yet")).toBeVisible();
    // The result cannot be changed (REV-10 dropped)
    await expect(review.getByRole("button", { name: "Change result" })).toHaveCount(0);
  });
  await test.step("activating the draft confirms the review", async () => {
    await page.getByRole("button", { name: "Activate draft" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("alert")).toHaveCount(0); // the review is current
    await dialog.getByLabel("Change note").fill("Reviewed");
    await dialog.getByRole("button", { name: "Activate", exact: true }).click();
    await expect(page.getByText("revision 2", { exact: true })).toBeVisible();
    await expect(review.getByText("confirmed", { exact: true })).toBeVisible();
  });
  await test.step("the confirmed review is in the timeline", async () => {
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Timeline" })
      .click();
    await expect(
      page.getByText("Thesis review of 'Growth' revision 2: intact, 6.5 / 10"),
    ).toBeVisible();
  });
});

test("[USR-09] the admin becomes an investor too", async ({ page }) => {
  await login(page, "admin", ADMIN_PASSWORD);
  await test.step("admin gives the own account the investor role", async () => {
    const own = page.getByRole("row").filter({ has: page.getByRole("cell", { name: "admin" }) });
    await own.first().getByRole("button", { name: "Roles" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel(/^Investor/).check();
    await dialog.getByLabel("Base currency").fill("EUR");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toHaveCount(0);
  });
  await test.step("both navigations; the investment data of alice stays hidden", async () => {
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByText("Administration")).toBeVisible();
    await nav.getByRole("link", { name: "Theses" }).click();
    await expect(page.getByRole("heading", { name: "Theses" })).toBeVisible();
    await expect(page.getByText("Growth")).toHaveCount(0);
    await nav.getByRole("link", { name: "Accounts" }).click();
    await expect(page.getByRole("cell", { name: "alice" })).toBeVisible();
  });
});

test("[PRC-01] [PRC-11] [PRC-02] [PRC-04] [PRC-06] adds a price provider; alice chooses a listing", async ({
  page,
}) => {
  await login(page, "admin", ADMIN_PASSWORD);
  await test.step("open the price providers", async () => {
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Price providers" })
      .click();
    await expect(page.getByText("Frankfurter (ECB)")).toBeVisible();
  });
  await test.step("the built-in exchange rate source answers", async () => {
    await page.getByRole("button", { name: "Test connection" }).first().click();
    await expect(page.getByRole("alert").first()).toHaveText("Connected to Frankfurter (ECB)");
  });
  await test.step("add Yahoo Finance with a daily limit of 100", async () => {
    await page.getByLabel("Add a price provider").selectOption("yahoo");
    const yahoo = page.getByRole("form", { name: "Price provider Yahoo Finance" });
    await yahoo.getByLabel("Calls per day").fill("100");
    await yahoo.getByRole("button", { name: "Add" }).click();
    await expect(
      page
        .getByRole("form", { name: "Price provider Yahoo Finance" })
        .getByText("0 of 100 calls today (UTC)"),
    ).toBeVisible();
    await page.context().clearCookies();
  });
  await asAlice(page);
  await test.step("alice's XUS was unresolved without providers; she chooses a listing", async () => {
    await page.goto("/settings");
    const sources = page.getByRole("table", { name: "Price sources" });
    const xus = sources.getByRole("row").filter({ hasText: "XUS" });
    await expect(xus.getByText("unresolved")).toBeVisible();
    await xus.getByRole("button", { name: "Change the price source of XUS" }).click();
    await xus.getByRole("button", { name: "Try auto" }).click();
    await xus
      .getByLabel("Listing for XUS")
      .selectOption({ label: "XUS.SW · SIX · CHF (Yahoo Finance)" });
    await xus.getByRole("button", { name: "Use" }).click();
    await expect(xus.getByText("XUS.SW · SIX · CHF (Yahoo Finance)")).toBeVisible();
  });
});

test("[USR-10] [NFR-10] switches the account to German", async ({ page }) => {
  await login(page, "admin", ADMIN_PASSWORD);
  await test.step("choose Deutsch in the settings", async () => {
    await expect(page.getByRole("navigation", { name: "Main" }).first()).toBeVisible();
    await page.goto("/settings");
    await page.getByLabel("Language").selectOption("de");
    await expect(page.getByRole("heading", { name: "Einstellungen" })).toBeVisible();
  });
  await test.step("the app is German, also after a new login", async () => {
    await page.context().clearCookies();
    await login(page, "admin", ADMIN_PASSWORD);
    const nav = page.getByRole("navigation", { name: "Hauptnavigation" });
    await expect(nav.getByRole("link", { name: "Übersicht" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Anlagestrategien" })).toBeVisible();
    await nav.getByRole("link", { name: "Portfolios" }).click();
    await expect(page.getByRole("heading", { name: "Portfolios" })).toBeVisible();
  });
});
