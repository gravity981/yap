import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { de } from "../src/i18n/de";
import { en } from "../src/i18n/en";

// Fictional demo data for the screenshots in docs/features.md; no real portfolio.
// SCREENSHOT_LANGUAGE=de shows the app in German; SCREENSHOT_DIR changes the folder
const OUT = process.env.SCREENSHOT_DIR ?? "../docs/screenshots";
const LANGUAGE = process.env.SCREENSHOT_LANGUAGE ?? "en";
const M = LANGUAGE === "de" ? de : en; // the texts the script waits for
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "admin password 1";
const TEMPORARY = "temporary password 1";
const PASSWORD = "demo password 123";

const CORE_THESIS = `# Global equities for the long run

## Role in the portfolio
Core holding, about two thirds of the portfolio. Holding period: 15+ years.

## Core thesis
A broadly diversified world equity fund captures the long-term growth of listed companies
worldwide at very low cost. No single country or sector decides the outcome.

## Why this asset and not an alternative
- One fund instead of many regional ones: fewer decisions, lower costs.
- Market-cap weighted, so it follows the market without forecasts.

## Value drivers
- Earnings growth of global companies
- Dividends, reinvested inside the fund

## Risks
- Drawdowns of 40–50 % are possible and can last years.
- The US share is large; a US-specific crisis weighs heavily.
- Currency risk against CHF.

## Break conditions
- The fund's total costs rise above 0.4 % per year.
- The index methodology changes so that the fund is no longer broadly diversified.

## Warning signals
- Tracking difference worse than −0.5 % per year for two years in a row.

## Review checklist
- [x] Costs checked
- [x] Index unchanged
- [ ] Currency hedging reconsidered
`;

// A shorter version of the core thesis for the README teaser: thesis and review on one page.
// Keeps a section for every aspect the fake review comments on (value drivers, two warning signals)
const TEASER_THESIS = `# Global equities for the long run

## Role in the portfolio
Core holding, 65 % of the portfolio. Holding period: 15+ years.

## Core thesis
A broadly diversified world equity fund captures the long-term growth of listed companies
worldwide at very low cost. No single country or sector decides the outcome.

## Why this asset and not an alternative
- One fund instead of many regional ones: fewer decisions, lower costs.

## Value drivers
- Earnings growth of global companies

## Risks
- Drawdowns of 40–50 % are possible and can last years.
- Currency risk against CHF.

## Break conditions
- The fund's total costs rise above 0.4 % per year.

## Warning signals
- Tracking difference worse than −0.5 % per year for two years in a row.
- The fund's assets shrink for several years in a row.
`;

const BONDS_THESIS = `# Bonds as stabiliser

## Role in the portfolio
Stabiliser and source of cash for rebalancing after equity drawdowns.

## Core thesis
High-quality bonds fall less than equities in most crises, so they reduce drawdowns and
provide money to buy equities when they are cheap.

## Risks
- Rising rates lower bond prices.
- In inflation shocks, bonds and equities can fall together.

## Break conditions
- Bonds and equities fall together for more than two years.
`;

const BITCOIN_THESIS = `# Bitcoin as a small satellite

## Role in the portfolio
Speculative satellite, at most 5 %. Can go to zero without hurting the plan.

## Core thesis
A fixed supply and growing adoption may make bitcoin a store of value for part of the
world. The outcome is uncertain, so the position stays small.

## Risks
- Regulation, theft, loss of keys; extreme volatility.

## Break conditions
- A major jurisdiction bans holding it.
`;

/** Seeding only: the answers are used loosely, the app's own types matter in src/. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = any;

async function call(
  request: APIRequestContext,
  method: string,
  path: string,
  data?: unknown,
): Promise<Json> {
  const response = await request.fetch(`/api${path}`, { method, data });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return response.status() === 204 ? null : response.json();
}

async function login(page: Page, username: string, password: string) {
  await page.context().clearCookies();
  await call(page.request, "POST", "/auth/login", { username, password });
}

async function thesis(request: APIRequestContext, title: string, content: string) {
  const created = await call(request, "POST", "/theses", { title, content_md: content });
  await call(request, "POST", `/theses/${created.id}/draft/activate`, {
    change_note: "First version",
  });
  return created.id as number;
}

async function waitForReview(request: APIRequestContext, id: number) {
  await expect.poll(async () => (await call(request, "GET", `/reviews/${id}`)).state).toBe("done");
}

async function shot(page: Page, name: string, height?: number) {
  // No hover effect or focused field in the image; `height` crops or extends the page
  await page.mouse.move(0, 0);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  const width = page.viewportSize()!.width;
  await page.screenshot({
    path: `${OUT}/${name}.png`,
    ...(height && { fullPage: true, clip: { x: 0, y: 0, width, height } }),
  });
}

const positions = (core: string, rationale: string) => [
  {
    ticker: "VT",
    name: "Vanguard Total World Stock ETF",
    type: "ETF",
    target_pct: 65,
    buy_threshold_pct: -10,
    sell_threshold_pct: 10,
    rationale_md: core,
  },
  {
    ticker: "BND",
    name: "Vanguard Total Bond Market ETF",
    type: "ETF",
    target_pct: 25,
    buy_threshold_pct: -20,
    sell_threshold_pct: 20,
    rationale_md: rationale,
  },
  {
    ticker: "BTC",
    name: "Bitcoin",
    type: "crypto",
    target_pct: 5,
    buy_threshold_pct: -40,
    sell_threshold_pct: 60,
    rationale_md: "Small satellite; see the bitcoin thesis.",
  },
  {
    ticker: "CASH",
    name: "Cash buffer",
    type: "cash_buffer",
    target_pct: 5,
    buy_threshold_pct: -40,
    sell_threshold_pct: 40,
    rationale_md: "Buffer for dips and planned expenses.",
  },
];

test("feature screenshots", async ({ page, browser }) => {
  test.setTimeout(180_000);

  await test.step("seed: admin, AI reviewers and accounts", async () => {
    await login(page, "admin", ADMIN_PASSWORD);
    for (const reviewer of [
      {
        name: "Claude (thorough)",
        description: "Careful reasoning with web search; slower.",
        provider: "anthropic",
        model: "claude-opus-5-5",
        monthly_review_limit: 10,
      },
      {
        name: "Gemini (quick)",
        description: "Fast first opinion.",
        provider: "google",
        model: "gemini-3-flash",
        monthly_review_limit: 30,
      },
    ]) {
      await call(page.request, "POST", "/admin/ai-reviewers", {
        ...reviewer,
        api_key: "sk-demo-key-0000",
      });
    }
    await call(page.request, "POST", "/admin/accounts", {
      username: "demo",
      temporary_password: TEMPORARY,
      is_admin: true,
      is_investor: true,
      base_currency: "CHF",
    });
    for (const [username, currency] of [
      ["alice", "EUR"],
      ["bob", "CHF"],
    ]) {
      await call(page.request, "POST", "/admin/accounts", {
        username,
        temporary_password: TEMPORARY,
        base_currency: currency,
      });
    }
    await login(page, "demo", TEMPORARY);
    await call(page.request, "POST", "/auth/password", {
      current_password: TEMPORARY,
      new_password: PASSWORD,
    });
    await login(page, "demo", PASSWORD);
    await call(page.request, "PUT", "/auth/language", { language: LANGUAGE });
    const reviewers = await call(page.request, "GET", "/ai-reviewers");
    await call(page.request, "PUT", "/ai-reviewers/choice", { ai_reviewer_id: reviewers[0].id });
  });

  const ids = await test.step("seed: theses, policy, portfolio and rebalance", async () => {
    const request = page.request;
    const core = await thesis(request, "Global equities for the long run", CORE_THESIS);
    const bonds = await thesis(request, "Bonds as stabiliser", BONDS_THESIS);
    await thesis(request, "Bitcoin as a small satellite", BITCOIN_THESIS);
    await call(request, "PUT", `/theses/${core}/visibility`, { visibility: "shared" });

    // A second revision of the core thesis with a confirmed review
    await call(request, "POST", `/theses/${core}/draft`);
    await call(request, "PUT", `/theses/${core}/draft`, {
      title: "Global equities for the long run",
      content_md: CORE_THESIS.replace("about two thirds", "65 %"),
      status: "intact",
      change_note: "Target share made explicit",
    });
    const review = await call(request, "POST", `/theses/${core}/draft/review`, {
      news_days: 90,
    });
    await waitForReview(request, review.id);
    await call(request, "POST", `/theses/${core}/draft/activate`, {
      change_note: "Reviewed",
    });

    const policy = await call(request, "POST", "/policies", {
      name: "Long-term core",
      thesis_id: core,
    });
    await call(request, "PUT", `/policies/${policy.id}/draft`, {
      positions: positions(
        "Core of the portfolio, see the thesis.",
        "Stabiliser; source of cash after equity drawdowns.",
      ),
    });
    const policyReview = await call(request, "POST", `/policies/${policy.id}/draft/review`, {});
    await waitForReview(request, policyReview.id);
    await call(request, "POST", `/policies/${policy.id}/draft/activate`, {
      change_note: "Initial target structure",
    });
    const detail = await call(request, "GET", `/policies/${policy.id}`);
    const versionId = detail.versions.at(-1).id;

    const portfolio = await call(request, "POST", "/portfolios", {
      name: "Retirement",
      policy_id: policy.id,
      default_contribution: 1500,
    });
    await call(request, "PUT", `/portfolios/${portfolio.id}/positions`, {
      VT: { broker: "Eastbank" },
      BND: { broker: "Eastbank" },
      BTC: { broker: "Kryptobank" },
      CASH: { broker: "Bank" },
    });
    const first = await call(request, "POST", `/portfolios/${portfolio.id}/snapshots`, {
      values: [
        { ticker: "VT", units: 510, price: 120 },
        { ticker: "BND", units: 350, price: 74 },
        { ticker: "BTC", units: 0.05, price: 88000 },
        { ticker: "CASH", value: 5100 },
      ],
    });
    await call(request, "POST", `/portfolios/${portfolio.id}/rebalances`, {
      snapshot_id: first.id,
      contribution: 1500,
      policy_version_id: versionId,
      executed: [],
    });
    // The latest values: bitcoin ran above its band, the cash buffer below
    await call(request, "POST", `/portfolios/${portfolio.id}/snapshots`, {
      values: [
        { ticker: "VT", units: 560, price: 130 },
        { ticker: "BND", units: 335, price: 72 },
        { ticker: "BTC", units: 0.1, price: 95000 },
        { ticker: "CASH", value: 2500 },
      ],
    });
    // An open draft for the editor screenshot
    await call(request, "POST", `/theses/${bonds}/draft`);
    return { core, bonds, policy: policy.id as number, portfolio: portfolio.id as number };
  });

  await test.step("dashboard", async () => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: M.portfolios.dashboard.title })).toBeVisible();
    await expect(page.getByText("Retirement").first()).toBeVisible();
    await shot(page, "dashboard");
  });

  await test.step("theses", async () => {
    await page.goto("/theses");
    await expect(page.getByRole("link", { name: "Bonds as stabiliser" })).toBeVisible();
    await shot(page, "theses");
    await page.goto(`/theses/${ids.core}`);
    await expect(
      page.getByRole("heading", { name: "Global equities for the long run" }).first(),
    ).toBeVisible();
    await shot(page, "thesis");
  });

  await test.step("thesis editor", async () => {
    await page.goto(`/theses/${ids.bonds}/edit`);
    await expect(page.getByText("Bonds as stabiliser").first()).toBeVisible();
    await page.waitForTimeout(500); // the editor chunk loads lazily
    await shot(page, "thesis-editor");
  });

  await test.step("review", async () => {
    await page.goto(`/theses/${ids.core}`);
    const review = page.getByRole("region", { name: M.reviews.section.thesis });
    await expect(review.getByText(`T6 ${M.reviews.aspects.T6}`)).toBeVisible();
    await page.mouse.move(0, 0);
    await review.screenshot({ path: `${OUT}/thesis-review.png` });
  });

  await test.step("policy", async () => {
    await page.goto(`/policies/${ids.policy}`);
    await expect(page.getByText("Long-term core").first()).toBeVisible();
    await shot(page, "policy");
  });

  await test.step("portfolio", async () => {
    await page.goto(`/portfolios/${ids.portfolio}`);
    await expect(page.getByText("Retirement").first()).toBeVisible();
    await shot(page, "portfolio", 620);
  });

  await test.step("rebalance", async () => {
    await page.goto(`/portfolios/${ids.portfolio}/rebalance`);
    // A rebalance starts from a fresh snapshot with the current units and prices
    await page.getByRole("button", { name: M.portfolios.values.saveAndRebalance }).click();
    await expect(page.getByText(M.rebalance.cash.sellProceeds, { exact: true })).toBeVisible();
    // Up to the printable report; the confirmation form below is left out
    await shot(page, "rebalance", 670);
  });

  await test.step("timeline", async () => {
    await page.goto("/timeline");
    await expect(page.getByRole("heading", { name: M.timeline.title })).toBeVisible();
    await shot(page, "timeline");
  });

  await test.step("administration", async () => {
    await page.goto("/ai-reviewers");
    await expect(
      page.getByRole("form", {
        name: M.pages.aiReviewers.form.replace("{{name}}", "Claude (thorough)"),
      }),
    ).toBeVisible();
    await shot(page, "ai-reviewers");
    await page.goto("/accounts");
    await expect(page.getByRole("cell", { name: "alice" })).toBeVisible();
    await shot(page, "accounts");
  });

  await test.step("phone", async () => {
    const phone = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
      colorScheme: "light",
      baseURL: test.info().project.use.baseURL,
    });
    const mobile = await phone.newPage();
    await call(mobile.request, "POST", "/auth/login", { username: "demo", password: PASSWORD });
    await mobile.goto("/");
    await expect(mobile.getByRole("heading", { name: M.portfolios.dashboard.title })).toBeVisible();
    await expect(mobile.getByText(M.timeline.types.rebalance_confirmed)).toBeVisible();
    await shot(mobile, "phone-dashboard");
    await phone.close();
  });

  // Last, so that the extra thesis appears in no other screenshot
  await test.step("README teaser: thesis with its review", async () => {
    const request = page.request;
    const title = "Global equities for the long run";
    const created = await call(request, "POST", "/theses", { title, content_md: TEASER_THESIS });
    await call(request, "PUT", `/theses/${created.id}/draft`, {
      title,
      content_md: TEASER_THESIS,
      status: "intact",
      change_note: "First version",
    });
    const review = await call(request, "POST", `/theses/${created.id}/draft/review`, {
      news_days: 90,
    });
    await waitForReview(request, review.id);
    await call(request, "POST", `/theses/${created.id}/draft/activate`, {
      change_note: "Reviewed",
    });
    await page.goto(`/theses/${created.id}`);
    const section = page.getByRole("region", { name: M.reviews.section.thesis });
    await expect(section.getByText(`T6 ${M.reviews.aspects.T6}`)).toBeVisible();
    await page.mouse.move(0, 0);
    await page.screenshot({ path: `${OUT}/thesis-with-review.png`, fullPage: true });
  });
});
