import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Stars } from "@/components/stars";
import { investor, json, mockApi, renderApp, type Handler } from "@/test/utils";

const version = (n: number, extra: Record<string, unknown> = {}) => ({
  id: 200 + n,
  version_no: n,
  label: `core-v${n}`,
  thesis_title: "Core thesis",
  change_note: n === 1 ? null : `change ${n}`,
  is_draft: false,
  active_from: `2026-0${n}-01T10:00:00+00:00`,
  active_until: n === 1 ? "2026-02-01T10:00:00+00:00" : null,
  review: null,
  reviews: [],
  ...extra,
});

/** A version's review, which also is its only one (REV-21). */
const reviewed = (b: unknown) => ({ review: b, reviews: b ? [b] : [] });

const brief = (id: number, total: number, extra: Record<string, unknown> = {}) => ({
  id,
  kind: "full",
  state: "done",
  total,
  thesis_score: total,
  structure_score: total,
  semaphore: "good",
  scoring_version: "3",
  method: "ai",
  model: "claude-x",
  ai_reviewer_name: "Standard",
  outdated: false,
  ...extra,
});

const NAMES = [
  "Belief",
  "Fit and implementation",
  "Opportunity",
  "Downside",
  "Invalidation, warnings and monitoring",
  "Current evidence",
];
const NAMES_V1 = ["Core claim", "Value drivers", "Risks", "Break conditions", "Fit", "Evidence"];
const P_NAMES = ["Coverage", "Weighting", "Bands", "Exits", "Concentration", "Rationales"];

const aspect = (n: number, score: number, extra: Record<string, unknown> = {}) => ({
  code: `T${n}`,
  name: NAMES[n - 1],
  score,
  reasoning_md: `Reasoning ${n} [1]`,
  ...extra,
});

const pAspect = (n: number, score: number) => ({
  code: `P${n}`,
  name: P_NAMES[n - 1],
  score,
  reasoning_md: `Structure reasoning ${n}`,
});

const review = (extra: Record<string, unknown> = {}) => ({
  id: 30,
  kind: "full",
  state: "done",
  error: null,
  policy_version_id: 203,
  provider: "anthropic",
  model: "claude-x",
  ai_reviewer_name: null,
  scoring_version: "3",
  method: "ai",
  prompt_id: null,
  news_from: "2025-12-01T10:00:00+00:00",
  news_to: "2026-03-01T10:00:00+00:00",
  started_at: "2026-03-01T10:00:00+00:00",
  completed_at: "2026-03-01T10:05:00+00:00",
  aspects: [
    ...[7, 6, 8, 5, 7, 6.5].map((s, i) => aspect(i + 1, s)),
    ...[8, 7, 6, 9, 7.5, 8].map((s, i) => pAspect(i + 1, s)),
  ],
  total: 7,
  thesis_score: 6.5,
  structure_score: 7.5,
  semaphore: "warning",
  verdict: "warning",
  verdict_reason: "Two warning signals are observed [1].",
  legacy_modification: null,
  outdated: false,
  confirmed: false,
  sources: [
    { title: "ETF inflows rise", published_on: "2026-02-10", url: "https://news.example/etf" },
  ],
  suggestions: [
    {
      id: 1,
      kind: "thesis_text",
      content_md: "Add a time horizon.",
      change: null,
      previous: null,
      state: "open",
    },
  ],
  ...extra,
});

type Sugg = { id: number; state: string; previous: unknown; [key: string]: unknown };
type Current = { suggestions: Sugg[]; [key: string]: unknown };

const suggestion = (id: number, kind: string, change: unknown, extra: object = {}) => ({
  id,
  kind,
  content_md: `Reason ${id}.`,
  change,
  previous: null,
  state: "open",
  ...extra,
});

const proposalRows = [
  {
    ticker: "VWRL",
    name: "All-World",
    type: "ETF",
    target_pct: "85",
    buy_threshold_pct: "-20",
    sell_threshold_pct: "20",
    exit: false,
    rationale_md: "Core.",
  },
  {
    ticker: "CASH",
    name: "Cash buffer",
    type: "cash_buffer",
    target_pct: "15",
    buy_threshold_pct: "0",
    sell_threshold_pct: "0",
    exit: false,
    rationale_md: "",
  },
];

const usage = (extra: Record<string, unknown> = {}) => ({
  ai_reviewer_id: 1,
  ai_reviewer_name: "Standard",
  used: 1,
  limit: 3,
  left: 2,
  unavailable_reason: null,
  ...extra,
});

const reviewers = [
  {
    id: 1,
    name: "Standard",
    description: null,
    provider: "openai",
    model: "gpt-x",
    monthly_review_limit: 3,
  },
  {
    id: 2,
    name: "Deep",
    description: "Thorough, slower",
    provider: "anthropic",
    model: "claude-x",
    monthly_review_limit: 5,
  },
];

/** Usage of the reviewer in the query, or of the default (Standard). */
const usageOf: Handler = (request) => {
  const id = Number(new URL(request.url).searchParams.get("ai_reviewer_id") ?? 1);
  const reviewer = reviewers.find((r) => r.id === id)!;
  return json(
    usage({
      ai_reviewer_id: id,
      ai_reviewer_name: reviewer.name,
      limit: reviewer.monthly_review_limit,
    }),
  );
};

function policy(draftReview: unknown = null) {
  // REV-06: a thesis review from before stage 2, with an old verdict mapped to its semaphore
  const v1Review = brief(10, 6, {
    kind: "thesis",
    scoring_version: "1",
    method: "manual",
    model: "GPT 5",
    structure_score: null,
  });
  return {
    id: 7,
    name: "core",
    archived_at: null,
    created_at: "2026-01-01T10:00:00+00:00",
    portfolios: [],
    thesis_warning: true,
    semaphore: "warning",
    versions: [
      version(1, reviewed(v1Review)),
      version(2, reviewed(brief(20, 7.5, { semaphore: "warning" }))),
      version(3, {
        is_draft: true,
        active_from: null,
        change_note: null,
        ...reviewed(draftReview),
      }),
    ],
  };
}

const draftVersion = { ...version(3, { is_draft: true }), thesis_md: "# Draft", positions: [] };

function setup(handlers: Record<string, Handler> = {}, draftReview: unknown = null) {
  return mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(investor),
    "GET /api/policies/7": () => json(policy(draftReview)),
    "GET /api/policies/7/versions/2": () =>
      json({ ...version(2), thesis_md: "# Active", positions: [] }),
    "GET /api/policies/7/versions/3": () => json(draftVersion),
    "GET /api/assets": () => json([]),
    "GET /api/reviews/usage": usageOf,
    "GET /api/ai-reviewers": () => json(reviewers),
    "GET /api/reviews/30": () => json(review()),
    "PUT /api/policies/7/draft": () => json(draftVersion),
    ...handlers,
  });
}

/** The draft on the policy page: its thesis with the review, read-only. */
async function draftOnPage() {
  const result = renderApp("/policies/7");
  await userEvent.selectOptions(await screen.findByLabelText("Version"), "3");
  return result;
}

/** REV-01: the review is a tab of the draft editor (narrow layout in jsdom). */
async function openPane() {
  renderApp("/policies/7/draft");
  await userEvent.click(await screen.findByRole("tab", { name: "Review" }));
  return screen.findByRole("region", { name: "Review" });
}

describe("reviews", () => {
  it("[REV-02] shows a score as ten stars with half stars", () => {
    render(<Stars score={6.5} label="Total" />);
    const stars = screen.getByRole("img", { name: "Total: 6.5 of 10" });
    expect(stars.querySelectorAll("svg")).toHaveLength(11); // 10 stars + one half overlay
  });

  it("[REV-01] [REV-04] [REV-05] [REV-16] [NFR-01] [NFR-15] starts one review of the whole draft with a news period", async () => {
    const calls = setup({
      "POST /api/policies/7/draft/review": () =>
        json(review({ state: "queued", aspects: [] }), 202),
    });
    const section = await openPane();
    expect(within(section).getByText(/Not reviewed yet. You can activate/)).toBeInTheDocument();
    expect(
      await within(section).findByText(/1 of 3 reviews with Standard used this month/),
    ).toBeInTheDocument();
    // NFR-01: says what is sent before anything is sent
    expect(
      within(section).getByText(
        /the title, the thesis text and the target structure .* are sent to the provider of your AI reviewer/,
      ),
    ).toHaveTextContent(/No amounts, portfolios or personal data are sent/);
    const days = within(section).getByLabelText("News of the last … days");
    expect(days).toHaveValue(90);
    await userEvent.clear(days);
    await userEvent.type(days, "30");
    await userEvent.click(within(section).getByRole("button", { name: "Start review" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/policies/7/draft/review")?.body).toEqual({
        ai_reviewer_id: 1,
        news_days: 30,
      }),
    );
    // The draft is saved first, so the review sees what is in the editor
    const order = calls.map((c) => `${c.method} ${c.path}`);
    expect(order.indexOf("PUT /api/policies/7/draft")).toBeLessThan(
      order.indexOf("POST /api/policies/7/draft/review"),
    );
    expect(within(section).queryByRole("button", { name: "Copy review prompt" })).toBeNull();
  });

  it("[USR-08] [REV-16] chooses another AI reviewer than the default for one review", async () => {
    const calls = setup({
      "POST /api/policies/7/draft/review": () =>
        json(review({ state: "queued", aspects: [] }), 202),
    });
    const section = await openPane();
    const select = await within(section).findByLabelText("Review method");
    await waitFor(() => expect(select).toHaveValue("1"));
    expect(within(select).getByRole("option", { name: "Standard (default)" })).toBeInTheDocument();
    await userEvent.selectOptions(select, "2");
    expect(
      await within(section).findByText(/1 of 5 reviews with Deep used this month/),
    ).toBeInTheDocument();
    expect(within(section).getByText("Thorough, slower")).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Start review" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/policies/7/draft/review")?.body).toEqual({
        ai_reviewer_id: 2,
        news_days: 90,
      }),
    );
  });

  it("[REV-16] explains why no review can be started", async () => {
    setup({
      "GET /api/reviews/usage": () =>
        json(
          usage({
            used: 3,
            left: 0,
            unavailable_reason: "All 3 reviews with Standard of this month are used",
          }),
        ),
    });
    const section = await openPane();
    expect(
      await within(section).findByText("All 3 reviews with Standard of this month are used"),
    ).toBeInTheDocument();
    expect(within(section).getByRole("button", { name: "Start review" })).toBeDisabled();
  });

  it("[REV-08] shows that the review is running and that the page can be left", async () => {
    setup(
      { "GET /api/reviews/30": () => json(review({ state: "running", aspects: [] })) },
      brief(30, 0, { state: "running", total: null }),
    );
    await openPane();
    expect(await screen.findByRole("status")).toHaveTextContent(/you can leave the page/);
  });

  it("[REV-08] shows why a review failed and offers to start it again", async () => {
    setup(
      {
        "GET /api/reviews/30": () =>
          json(review({ state: "failed", error: "OpenAI did not answer in time", aspects: [] })),
      },
      brief(30, 0, { state: "failed", total: null }),
    );
    const section = await openPane();
    expect(await within(section).findByText(/OpenAI did not answer in time/)).toBeInTheDocument();
    expect(within(section).getByRole("button", { name: "Run review again" })).toBeInTheDocument();
  });

  it("[REV-02] [REV-03] [REV-04] [REV-07] [REV-17] [NFR-15] shows the result of a draft review", async () => {
    setup({}, brief(30, 7));
    await draftOnPage();
    const section = await screen.findByRole("region", { name: "Review" });
    expect(
      await within(section).findByRole("img", { name: "Score: 7.0 of 10" }),
    ).toBeInTheDocument();
    // REV-02: the thesis and target-structure scores, the aspects grouped by both
    expect(within(section).getByText("Thesis · 6.5 · Target structure · 7.5")).toBeInTheDocument();
    expect(within(section).getByRole("heading", { name: "Thesis" })).toBeInTheDocument();
    expect(within(section).getByRole("heading", { name: "Target structure" })).toBeInTheDocument();
    expect(within(section).getByRole("img", { name: "Bands: 6.0 of 10" })).toBeInTheDocument();
    // REV-03: the semaphore with the reason for the verdict
    expect(within(section).getByText("warning")).toBeInTheDocument();
    expect(within(section).getByText(/Two warning signals are observed/)).toBeInTheDocument();
    expect(within(section).getByText("not confirmed yet")).toBeInTheDocument();
    expect(within(section).getByText(/anthropic claude-x · scoring v3/)).toBeInTheDocument();
    expect(within(section).getByRole("img", { name: "Belief: 7.0 of 10" })).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "ETF inflows rise" })).toHaveAttribute(
      "href",
      "https://news.example/etf",
    );
    expect(within(section).getByText("Add a time horizon.")).toBeInTheDocument();
    expect(within(section).getByText(/Nothing is changed automatically/)).toBeInTheDocument();
    expect(within(section).getByRole("note", { name: "Not financial advice" })).toHaveTextContent(
      /AI reviews can be wrong/,
    );
  });

  it("[REV-02] shows the changes of a review from before reviews became read-only", async () => {
    setup(
      {
        "GET /api/reviews/30": () =>
          json(
            review({
              kind: "thesis",
              confirmed: true,
              scoring_version: "1",
              aspects: [7, 6, 8, 5, 7, 6.5].map((s, i) => aspect(i + 1, s, { name: NAMES_V1[i] })),
              total: 6.5,
              thesis_score: 6.5,
              structure_score: null,
              verdict: "needs_adaptation",
              verdict_reason: null,
              legacy_modification: { note: "Too strict", verdict: "intact", scores: { T1: 9 } },
            }),
          ),
      },
      brief(30, 6.5, { kind: "thesis" }),
    );
    await draftOnPage();
    const section = await screen.findByRole("region", { name: "Thesis review" });
    expect(
      await within(section).findByText(/You changed this result when reviews could still/),
    ).toBeInTheDocument();
    // REV-06: old verdicts are shown as semaphores
    expect(within(section).getByText("Your verdict: good")).toBeInTheDocument();
    expect(within(section).getByText("warning")).toBeInTheDocument();
    expect(within(section).getByText("T1 Core claim: 9.0")).toBeInTheDocument();
    expect(within(section).getByText("Why: Too strict")).toBeInTheDocument();
    // The AI's values are the result
    expect(within(section).getByRole("img", { name: "Score: 6.5 of 10" })).toBeInTheDocument();
    expect(
      within(section).queryByRole("button", { name: "Change result" }),
    ).not.toBeInTheDocument();
  });

  it("[REV-06] [NFR-10] names the aspects by the scoring version of the review", async () => {
    const german = async (version: string) => {
      setup(
        {
          "GET /api/auth/me": () => json({ ...investor, language: "de" }),
          "GET /api/reviews/30": () =>
            json(
              review({
                kind: "thesis",
                scoring_version: version,
                aspects: [7, 6, 8, 5, 7, 6.5].map((s, i) =>
                  aspect(i + 1, s, { name: (version === "1" ? NAMES_V1 : NAMES)[i] }),
                ),
              }),
            ),
        },
        brief(30, 6.5, { kind: "thesis", scoring_version: version }),
      );
      return draftOnPage();
    };
    const current = await german("2");
    const section = await screen.findByRole("region", { name: "Prüfung der Anlagethese" });
    expect(await within(section).findByText("T1 Überzeugung")).toBeInTheDocument();
    expect(
      within(section).getByText("T5 Widerlegung, Frühwarnungen und Überwachung"),
    ).toBeInTheDocument();
    current.unmount();
    await german("1");
    const old = await screen.findByRole("region", { name: "Prüfung der Anlagethese" });
    expect(await within(old).findByText("T1 Kernaussage")).toBeInTheDocument();
  });

  it("[REV-17] [REV-18] shows a manual review without a model, older ones with theirs", async () => {
    const show = (extra: Record<string, unknown>) => {
      setup(
        {
          "GET /api/reviews/30": () =>
            json(review({ method: "manual", provider: "manual", ...extra })),
        },
        brief(30, 7),
      );
      return draftOnPage();
    };
    const current = await show({ model: null });
    const section = await screen.findByRole("region", { name: "Review" });
    expect(await within(section).findByText(/manual review · scoring v3/)).toBeInTheDocument();
    current.unmount();
    await show({ model: "ChatGPT 5", scoring_version: "2" });
    const old = await screen.findByRole("region", { name: "Review" });
    expect(
      await within(old).findByText(/manual review with ChatGPT 5 · scoring v2/),
    ).toBeInTheDocument();
  });

  it("[REV-09] marks a review as outdated when the draft changed", async () => {
    setup(
      { "GET /api/reviews/30": () => json(review({ outdated: true })) },
      brief(30, 6.5, { outdated: true }),
    );
    const section = await openPane();
    expect(
      await within(section).findByText(/outdated: the draft changed since/),
    ).toBeInTheDocument();
    // The result stays visible while the investor works through it
    expect(within(section).getByText("Add a time horizon.")).toBeInTheDocument();
    expect(within(section).getByRole("button", { name: "Run review again" })).toBeInTheDocument();
  });

  it("[REV-18] [REV-19] [NFR-01] reviews manually: copy the prompt, paste the answer", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    const manual = review({ method: "manual", provider: "manual", model: null });
    let draftReview: unknown = null;
    const calls = setup({
      "GET /api/policies/7": () => json(policy(draftReview)),
      "GET /api/policies/7/draft/review-prompt": () =>
        json({ prompt_id: "R203-20260301T100000Z-30-abcdef", text: "THE PROMPT" }),
      "POST /api/policies/7/draft/review/manual": () => {
        draftReview = brief(30, 7);
        return json(manual, 201);
      },
      "GET /api/reviews/30": () => json(manual),
    });
    const section = await openPane();
    await userEvent.selectOptions(within(section).getByLabelText("Review method"), "manual");
    // REV-19: what the prompt contains, before it is copied; no AI reviewer is used
    expect(
      within(section).getByText(
        /The prompt contains the review instructions, the title, the thesis text and the target structure/,
      ),
    ).toBeInTheDocument();
    expect(within(section).queryByRole("button", { name: "Start review" })).toBeNull();
    const days = within(section).getByLabelText("News of the last … days");
    await userEvent.clear(days);
    await userEvent.type(days, "30");
    await userEvent.click(within(section).getByRole("button", { name: "Copy review prompt" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("THE PROMPT"));
    expect(await within(section).findByRole("status")).toHaveTextContent(/Copied/);
    const order = calls.map((c) => `${c.method} ${c.path}`);
    expect(order.indexOf("PUT /api/policies/7/draft")).toBeLessThan(
      order.indexOf("GET /api/policies/7/draft/review-prompt?news_days=30"),
    );
    // REV-17: no model is asked for
    expect(within(section).queryByLabelText("AI model used")).toBeNull();
    fireEvent.change(within(section).getByLabelText("Paste its whole answer"), {
      target: { value: '{"prompt_id": "R203-20260301T100000Z-30-abcdef"}' },
    });
    await userEvent.click(within(section).getByRole("button", { name: "Save review" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/policies/7/draft/review/manual")?.body).toEqual({
        answer: '{"prompt_id": "R203-20260301T100000Z-30-abcdef"}',
      }),
    );
    expect(await screen.findByText(/manual review · scoring v3/)).toBeInTheDocument();
  });

  it("[REV-18] lists every problem of a pasted answer", async () => {
    const calls = setup({
      "POST /api/policies/7/draft/review/manual": () =>
        json(
          {
            detail: "invalid",
            problems: [
              {
                path: "answer",
                message: "The answer contains no JSON object",
                code: "answer_no_json",
              },
              {
                path: "answer",
                message: "Score 11 is not between 0 and 10 in steps of 0.5",
                code: "score_invalid",
                params: { score: 11 },
              },
            ],
          },
          422,
        ),
    });
    const section = await openPane();
    await userEvent.selectOptions(within(section).getByLabelText("Review method"), "manual");
    await userEvent.type(within(section).getByLabelText("Paste its whole answer"), "nonsense");
    await userEvent.click(within(section).getByRole("button", { name: "Save review" }));
    expect(calls.some((c) => c.method === "PUT")).toBe(false); // the editor stays open
    expect(await within(section).findByText("The answer cannot be used:")).toBeInTheDocument();
    expect(within(section).getByText("The answer contains no JSON object")).toBeInTheDocument();
    expect(within(section).getByText(/Score 11 is not between 0 and 10/)).toBeInTheDocument();
  });

  it("[REV-19] shows the prompt to copy by hand when the browser does not allow copying", async () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      clipboard: { writeText: () => Promise.reject(new Error("not allowed")) },
    });
    setup({
      "GET /api/policies/7/draft/review-prompt": () =>
        json({ prompt_id: "R1-20260301T100000Z-90-abcdef", text: "THE PROMPT" }),
    });
    const section = await openPane();
    await userEvent.selectOptions(within(section).getByLabelText("Review method"), "manual");
    await userEvent.click(within(section).getByRole("button", { name: "Copy review prompt" }));
    expect(
      await within(section).findByLabelText(/did not allow copying; copy the prompt from here/),
    ).toHaveValue("THE PROMPT");
  });

  it("[USR-08] [REV-16] [REV-18] preselects manual as default, and when there is no AI reviewer", async () => {
    setup({ "GET /api/auth/me": () => json({ ...investor, manual_review_default: true }) });
    const section = await openPane();
    const select = within(section).getByLabelText("Review method");
    await waitFor(() => expect(select).toHaveValue("manual"));
    expect(
      within(select).getByRole("option", { name: /^Manual.*\(default\)$/ }),
    ).toBeInTheDocument();
    cleanup();
    setup({ "GET /api/ai-reviewers": () => json([]) });
    const none = await openPane();
    await waitFor(() => expect(within(none).getByLabelText("Review method")).toHaveValue("manual"));
    expect(within(none).getByRole("button", { name: "Copy review prompt" })).toBeEnabled();
  });

  it("[USR-08] links to the settings for the default method", async () => {
    setup();
    const section = await openPane();
    expect(within(section).getByRole("link", { name: "settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("[REV-01] points from the policy page to the editor for reviews", async () => {
    setup();
    await draftOnPage();
    expect(await screen.findByRole("link", { name: "editor" })).toHaveAttribute(
      "href",
      "/policies/7/draft",
    );
    const section = screen.getByRole("region", { name: "Review" });
    expect(within(section).queryByRole("button")).toBeNull();
  });

  it("[REV-12] [THS-08] shows confirmed reviews read-only in the history, with the score course", async () => {
    setup({ "GET /api/reviews/20": () => json(review({ id: 20, confirmed: true })) });
    renderApp("/policies/7");
    await userEvent.click(await screen.findByRole("tab", { name: "Versions" }));
    const course = screen.getByRole("figure", { name: "Review score over the versions" });
    expect(within(course).getByRole("img", { name: "core-v1: 6.0 of 10" })).toBeInTheDocument();
    expect(within(course).getByRole("img", { name: "core-v2: 7.5 of 10" })).toBeInTheDocument();
    // REV-06: v1 was scored with scoring version 1, v2 with scoring version 3
    expect(within(course).getByTestId("version-change")).toHaveTextContent("v3");
    expect(
      within(course).getByText(/scores before and after are not directly comparable/),
    ).toBeInTheDocument();
    const second = screen.getByText("core-v2").closest("li")!;
    expect(within(second).getByRole("img", { name: "Review: 7.5 of 10" })).toBeInTheDocument();
    expect(within(second).getByText("warning")).toBeInTheDocument();
    // REV-17: who made each review
    expect(within(second).getByText("Standard (claude-x)")).toBeInTheDocument();
    const first = screen.getByText("core-v1").closest("li")!;
    expect(within(first).getByText("manual review with GPT 5")).toBeInTheDocument();
    expect(within(first).getByText("Thesis review:")).toBeInTheDocument();
    expect(within(first).getByText("good")).toBeInTheDocument();
    // An activated version's review cannot be changed or run again
    await userEvent.click(screen.getByRole("tab", { name: "Thesis" }));
    await userEvent.selectOptions(await screen.findByLabelText("Version"), "2");
    const section = await screen.findByRole("region", { name: "Review" });
    expect(await within(section).findByText("confirmed")).toBeInTheDocument();
    expect(within(section).queryByRole("button")).not.toBeInTheDocument();
  });

  it("[REV-07] takes over, dismisses and undoes suggestions in the editor, saving first", async () => {
    const section = suggestion(2, "thesis_section", { section: 7, text: "- GDP below 2 %" });
    const change = suggestion(3, "position_change", {
      ticker: "BTC",
      field: "sell_threshold_pct",
      value: "50",
    });
    const add = suggestion(4, "position_add", {
      position: { ...proposalRows[0], ticker: "EMIM", name: "Emerging", target_pct: "10" },
    });
    const remove = suggestion(5, "position_remove", { ticker: "XUS" });
    let current: Current = review({ suggestions: [section, change, add, remove] });
    const changed = {
      ...draftVersion,
      thesis_md: "# Draft\n\n## 7. Early Warnings\n- GDP below 2 %\n",
    };
    const act =
      (state: string, previous: unknown = null): Handler =>
      (request) => {
        const id = Number(request.url.split("/suggestions/")[1]!.split("/")[0]);
        current = {
          ...current,
          outdated: true,
          suggestions: current.suggestions.map((s) =>
            s.id === id ? { ...s, state, previous: state === "open" ? null : previous } : s,
          ),
        };
        return json({ review: current, draft: changed });
      };
    const calls = setup(
      {
        "GET /api/reviews/30": () => json(current),
        "POST /api/reviews/30/suggestions/3/take-over": act("taken_over", {
          ticker: "BTC",
          field: "sell_threshold_pct",
          value: "25",
        }),
        "POST /api/reviews/30/suggestions/2/take-over": act("taken_over", {
          section: 7,
          text: null,
        }),
        "POST /api/reviews/30/suggestions/2/undo": act("open"),
        "POST /api/reviews/30/suggestions/5/dismiss": act("dismissed"),
      },
      brief(30, 7),
    );
    const pane = await openPane();
    // Each kind says what it changes
    const sectionCard = await within(pane).findByRole("listitem", { name: "Thesis · section 7" });
    expect(within(sectionCard).getByText("- GDP below 2 %")).toBeInTheDocument();
    const changeCard = within(pane).getByRole("listitem", { name: "BTC · sell threshold" });
    expect(within(changeCard).getByText("→ +50 %")).toBeInTheDocument();
    expect(within(pane).getByRole("listitem", { name: "Add EMIM (Emerging)" })).toHaveTextContent(
      "ETF, target 10 %, band −20 % / +20 %",
    );
    expect(within(pane).getByRole("listitem", { name: "Remove XUS" })).toBeInTheDocument();
    expect(within(pane).getAllByRole("button", { name: "Take over" })).toHaveLength(4);

    // Take over: the editor is saved first, then the change is applied on the server
    await userEvent.click(within(changeCard).getByRole("button", { name: "Take over" }));
    expect(await within(changeCard).findByText("Taken over")).toBeInTheDocument();
    expect(within(changeCard).getByText("+25 % → +50 %")).toBeInTheDocument();
    const order = calls.map((c) => `${c.method} ${c.path}`);
    const put = order.lastIndexOf("PUT /api/policies/7/draft");
    expect(put).toBeGreaterThan(-1);
    expect(put).toBeLessThan(order.indexOf("POST /api/reviews/30/suggestions/3/take-over"));

    // The editor shows the draft as the server changed it
    await userEvent.click(within(sectionCard).getByRole("button", { name: "Take over" }));
    await userEvent.click(screen.getByRole("tab", { name: "Preview" }));
    expect(
      (await screen.findAllByRole("heading", { name: "7. Early Warnings" })).length,
    ).toBeGreaterThan(0);

    // Undo reopens it
    await userEvent.click(screen.getByRole("tab", { name: "Review" }));
    const again = await screen.findByRole("listitem", { name: "Thesis · section 7" });
    await userEvent.click(within(again).getByRole("button", { name: "Undo" }));
    await waitFor(() =>
      expect(calls.map((c) => c.path)).toContain("/api/reviews/30/suggestions/2/undo"),
    );

    // Dismiss
    const removeCard = screen.getByRole("listitem", { name: "Remove XUS" });
    await userEvent.click(within(removeCard).getByRole("button", { name: "Dismiss" }));
    expect(await within(removeCard).findByText("Dismissed")).toBeInTheDocument();
  });

  it("[REV-07] shows suggestions of a confirmed review read-only", async () => {
    setup(
      {
        "GET /api/reviews/30": () =>
          json(
            review({
              confirmed: true,
              suggestions: [
                suggestion(2, "thesis_section", { section: 1, text: "New." }),
                suggestion(3, "position_remove", { ticker: "XUS" }, { state: "taken_over" }),
              ],
            }),
          ),
      },
      brief(30, 7),
    );
    await draftOnPage();
    const section = await screen.findByRole("region", { name: "Review" });
    expect(await within(section).findByText("Thesis · section 1")).toBeInTheDocument();
    expect(within(section).getByText("Taken over")).toBeInTheDocument();
    expect(within(section).queryByRole("button", { name: "Take over" })).toBeNull();
    expect(within(section).queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("[REV-22] proposes target structures for a thesis without positions and takes one over", async () => {
    let current: Current = review({
      aspects: [7, 6, 8, 5, 7, 6.5].map((s, i) => aspect(i + 1, s)),
      structure_score: null,
      total: 6.5,
      suggestions: [
        suggestion(
          6,
          "proposal",
          { name: "Focused", positions: proposalRows },
          { content_md: "Close to the thesis." },
        ),
        suggestion(
          7,
          "proposal",
          { name: "Broader", positions: proposalRows },
          { content_md: "A world core." },
        ),
      ],
    });
    const filled = {
      ...draftVersion,
      positions: proposalRows.map((r) => ({
        ...r,
        buy_abs_pct: "68",
        sell_abs_pct: "102",
        midband_pct: "93.5",
      })),
    };
    setup(
      {
        "GET /api/reviews/30": () => json(current),
        "POST /api/reviews/30/suggestions/6/take-over": () => {
          current = {
            ...current,
            suggestions: current.suggestions.map((s) =>
              s.id === 6 ? { ...s, state: "taken_over", previous: { positions: [] } } : s,
            ),
          };
          return json({ review: current, draft: filled });
        },
      },
      brief(30, 6.5),
    );
    const pane = await openPane();
    expect(
      await within(pane).findByRole("heading", { name: "Proposed target structures" }),
    ).toBeInTheDocument();
    expect(
      within(pane).getByText(/Taking one over fills the target structure/),
    ).toBeInTheDocument();
    const focused = within(pane).getByRole("listitem", { name: "A · Focused" });
    expect(within(pane).getByRole("listitem", { name: "B · Broader" })).toBeInTheDocument();
    expect(within(focused).getByText("Close to the thesis.", { exact: false })).toBeInTheDocument();
    expect(within(focused).getByText("85 %")).toBeInTheDocument();
    expect(within(focused).getByText("−20 % / +20 %")).toBeInTheDocument();
    expect(within(focused).getByText("Cash buffer")).toBeInTheDocument();
    // A proposal can only be taken over, not dismissed
    expect(within(focused).queryByRole("button", { name: "Dismiss" })).toBeNull();
    await userEvent.click(within(focused).getByRole("button", { name: "Take over" }));
    expect(await within(focused).findByText("Taken over")).toBeInTheDocument();
    // The editor's target structure is filled with the proposal
    expect(await screen.findByDisplayValue("VWRL")).toBeInTheDocument();
    expect(screen.getByDisplayValue("CASH")).toBeInTheDocument();
  });
});
