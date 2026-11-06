import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Stars } from "@/components/stars";
import { investor, json, mockApi, renderApp, type Handler } from "@/test/utils";

const rev = (n: number, extra: Record<string, unknown> = {}) => ({
  id: 100 + n,
  revision_no: n,
  title: "Core thesis",
  status: "intact",
  change_note: n === 1 ? null : `change ${n}`,
  is_draft: false,
  activated_at: `2026-0${n}-01T10:00:00+00:00`,
  created_at: `2026-0${n}-01T10:00:00+00:00`,
  review: null,
  ...extra,
});

const brief = (id: number, total: number, extra: Record<string, unknown> = {}) => ({
  id,
  state: "done",
  total,
  verdict: "intact",
  modified: false,
  outdated: false,
  ...extra,
});

const aspect = (n: number, ai: number, extra: Record<string, unknown> = {}) => ({
  code: `T${n}`,
  name: ["Core claim", "Value drivers", "Risks", "Break conditions", "Fit", "Evidence"][n - 1],
  ai_score: ai,
  score: ai,
  modified: false,
  reasoning_md: `Reasoning ${n} [1]`,
  ...extra,
});

const review = (extra: Record<string, unknown> = {}) => ({
  id: 30,
  kind: "thesis",
  state: "done",
  error: null,
  thesis_revision_id: 103,
  policy_version_id: null,
  provider: "anthropic",
  model: "claude-x",
  scoring_version: "1",
  news_from: "2025-12-01T10:00:00+00:00",
  news_to: "2026-03-01T10:00:00+00:00",
  started_at: "2026-03-01T10:00:00+00:00",
  completed_at: "2026-03-01T10:05:00+00:00",
  aspects: [7, 6, 8, 5, 7, 6.5].map((s, i) => aspect(i + 1, s)),
  ai_total: 6.5,
  total: 6.5,
  ai_verdict: "needs_adaptation",
  verdict: "needs_adaptation",
  modified: false,
  modification_note: null,
  outdated: false,
  confirmed: false,
  sources: [
    { title: "ETF inflows rise", published_on: "2026-02-10", url: "https://news.example/etf" },
  ],
  suggestions: [{ kind: "thesis_text", content_md: "Add a time horizon." }],
  ...extra,
});

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

function thesis(draftReview: unknown = null) {
  return {
    id: 7,
    is_own: true,
    visibility: "private",
    created_at: "2026-01-01T10:00:00+00:00",
    revisions: [
      rev(1, { review: brief(10, 6) }),
      rev(2, { review: brief(20, 7.5, { modified: true, verdict: "needs_adaptation" }) }),
      rev(3, { is_draft: true, activated_at: null, change_note: null, review: draftReview }),
    ],
  };
}

function setup(handlers: Record<string, Handler> = {}, draftReview: unknown = null) {
  return mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(investor),
    "GET /api/theses/7": () => json(thesis(draftReview)),
    "GET /api/theses/7/revisions/3": () =>
      json({ ...rev(3, { is_draft: true }), thesis_id: 7, content_md: "# Draft" }),
    "GET /api/reviews/usage": usageOf,
    "GET /api/ai-reviewers": () => json(reviewers),
    "GET /api/reviews/30": () => json(review()),
    ...handlers,
  });
}

describe("reviews", () => {
  it("[REV-02] shows a score as ten stars with half stars", () => {
    render(<Stars score={6.5} label="Total" />);
    const stars = screen.getByRole("img", { name: "Total: 6.5 of 10" });
    expect(stars.querySelectorAll("svg")).toHaveLength(11); // 10 stars + one half overlay
  });

  it("[REV-01] [REV-04] [REV-16] [NFR-01] [NFR-15] starts a thesis review of the draft with a news period", async () => {
    const calls = setup({
      "POST /api/theses/7/draft/review": () => json(review({ state: "queued", aspects: [] }), 202),
    });
    renderApp("/theses/7");
    const section = await screen.findByRole("region", { name: "Thesis review" });
    expect(
      await within(section).findByText(/1 of 3 reviews with Standard used this month/),
    ).toBeInTheDocument();
    // NFR-01: says what is sent before anything is sent
    expect(
      within(section).getByText(/the thesis text is sent to the provider of your AI reviewer/),
    ).toHaveTextContent(/No amounts, portfolios or personal data are sent/);
    const days = within(section).getByLabelText("News of the last … days");
    expect(days).toHaveValue(90);
    await userEvent.clear(days);
    await userEvent.type(days, "30");
    await userEvent.click(within(section).getByRole("button", { name: "Start review" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/theses/7/draft/review")?.body).toEqual({
        ai_reviewer_id: 1,
        news_days: 30,
      }),
    );
  });

  it("[USR-08] [REV-16] chooses another AI reviewer than the default for one review", async () => {
    const calls = setup({
      "POST /api/theses/7/draft/review": () => json(review({ state: "queued", aspects: [] }), 202),
    });
    renderApp("/theses/7");
    const section = await screen.findByRole("region", { name: "Thesis review" });
    const select = await within(section).findByLabelText("AI reviewer");
    expect(select).toHaveValue("1");
    expect(within(select).getByRole("option", { name: "Standard (default)" })).toBeInTheDocument();
    await userEvent.selectOptions(select, "2");
    expect(
      await within(section).findByText(/1 of 5 reviews with Deep used this month/),
    ).toBeInTheDocument();
    expect(within(section).getByText("Thorough, slower")).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Start review" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/theses/7/draft/review")?.body).toEqual({
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
    renderApp("/theses/7");
    const section = await screen.findByRole("region", { name: "Thesis review" });
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
    renderApp("/theses/7");
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
    renderApp("/theses/7");
    expect(await screen.findByText(/OpenAI did not answer in time/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run review again" })).toBeInTheDocument();
  });

  it("[REV-02] [REV-03] [REV-04] [REV-07] [REV-17] [NFR-15] shows the result of a draft review", async () => {
    setup({}, brief(30, 6.5));
    renderApp("/theses/7");
    const section = await screen.findByRole("region", { name: "Thesis review" });
    expect(
      await within(section).findByRole("img", { name: "Total, AI: 6.5 of 10" }),
    ).toBeInTheDocument();
    expect(within(section).getByText("needs adaptation")).toBeInTheDocument();
    expect(within(section).getByText("not confirmed yet")).toBeInTheDocument();
    expect(within(section).getByText(/anthropic claude-x · scoring v1/)).toBeInTheDocument();
    expect(
      within(section).getByRole("img", { name: "Core claim, AI: 7.0 of 10" }),
    ).toBeInTheDocument();
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

  it("[REV-10] changes scores and verdict with a note; the AI's values stay visible", async () => {
    const changed = review({
      aspects: [
        aspect(1, 7, { score: 9, modified: true }),
        ...[6, 8, 5, 7, 6.5].map((s, i) => aspect(i + 2, s)),
      ],
      total: 7,
      verdict: "intact",
      modified: true,
      modification_note: "Too strict",
    });
    let current = review();
    const calls = setup(
      {
        "GET /api/reviews/30": () => json(current),
        "PUT /api/reviews/30": () => {
          current = changed;
          return json(changed);
        },
      },
      brief(30, 6.5),
    );
    renderApp("/theses/7");
    await userEvent.click(await screen.findByRole("button", { name: "Change result" }));
    const form = screen.getByRole("form", { name: "Change result" });
    expect(within(form).getByLabelText("T1 Core claim")).toHaveValue("");
    await userEvent.selectOptions(within(form).getByLabelText("T1 Core claim"), "9");
    await userEvent.selectOptions(within(form).getByLabelText("Verdict"), "intact");
    await userEvent.type(
      within(form).getByLabelText("Why do you change the result?"),
      "Too strict",
    );
    await userEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
        scores: { T1: 9, T2: null, T3: null, T4: null, T5: null, T6: null },
        verdict: "intact",
        note: "Too strict",
      }),
    );
    const section = screen.getByRole("region", { name: "Thesis review" });
    expect(
      await within(section).findByRole("img", { name: "Total, Yours: 7.0 of 10" }),
    ).toBeInTheDocument();
    expect(within(section).getByRole("img", { name: "Total, AI: 6.5 of 10" })).toBeInTheDocument();
    expect(
      within(section).getByRole("img", { name: "Core claim, yours: 9.0 of 10" }),
    ).toBeInTheDocument();
    expect(
      within(section).getByRole("img", { name: "Core claim, AI: 7.0 of 10" }),
    ).toBeInTheDocument();
    expect(within(section).getByText("modified")).toBeInTheDocument();
    expect(within(section).getByText(/Too strict/)).toBeInTheDocument();
  });

  it("[REV-09] marks a review as outdated when the draft changed", async () => {
    setup(
      { "GET /api/reviews/30": () => json(review({ outdated: true })) },
      brief(30, 6.5, { outdated: true }),
    );
    renderApp("/theses/7");
    expect(await screen.findByText(/outdated: the draft changed since/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run review again" })).toBeInTheDocument();
  });

  it("[REV-12] [THS-08] shows confirmed reviews read-only in the history, with the score course", async () => {
    setup({ "GET /api/reviews/20": () => json(review({ id: 20, confirmed: true })) });
    renderApp("/theses/7");
    await userEvent.click(await screen.findByRole("tab", { name: "History" }));
    const course = screen.getByRole("figure", { name: "Review score over the revisions" });
    expect(within(course).getByRole("img", { name: "Revision 1: 6.0 of 10" })).toBeInTheDocument();
    expect(within(course).getByRole("img", { name: "Revision 2: 7.5 of 10" })).toBeInTheDocument();
    const second = screen.getByText("Revision 2").closest("li")!;
    expect(within(second).getByRole("img", { name: "Review: 7.5 of 10" })).toBeInTheDocument();
    expect(within(second).getByText("modified")).toBeInTheDocument();
    // An activated revision's review cannot be changed or run again
    await userEvent.click(screen.getByRole("tab", { name: "Content" }));
    await userEvent.selectOptions(screen.getByLabelText("Revision"), "2");
    const section = await screen.findByRole("region", { name: "Thesis review" });
    expect(await within(section).findByText("confirmed")).toBeInTheDocument();
    expect(within(section).queryByRole("button")).not.toBeInTheDocument();
  });
});
