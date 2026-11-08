import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { investor, json, mockApi, renderApp, type Handler } from "@/test/utils";

import { THESIS_TEMPLATES } from "@/features/theses/template";

import { band } from "./draft-editor";

const version = (n: number, extra: Record<string, unknown> = {}) => ({
  id: 200 + n,
  version_no: n,
  label: `core-v${n}`,
  thesis_title: "Core thesis",
  change_note: n === 1 ? null : `note ${n}`,
  active_from: `2026-0${n}-01T10:00:00+00:00`,
  active_until: null,
  is_draft: false,
  review: null,
  reviews: [],
  ...extra,
});

/** A review brief of the whole policy (REV-02). */
const reviewBrief = (extra: Record<string, unknown> = {}) => ({
  id: 9,
  kind: "full",
  state: "done",
  total: 7,
  thesis_score: 6.5,
  structure_score: 7.5,
  semaphore: "good",
  scoring_version: "3",
  method: "ai",
  model: "m",
  ai_reviewer_name: null,
  outdated: false,
  ...extra,
});

const position = (ticker: string, target: string, extra: Record<string, unknown> = {}) => ({
  ticker,
  name: `${ticker} name`,
  type: "ETF",
  target_pct: target,
  buy_threshold_pct: "-20",
  sell_threshold_pct: "25",
  buy_abs_pct: String(Number(target) * 0.8),
  sell_abs_pct: String(Number(target) * 1.25),
  midband_pct: String(Number(target) * 1.125),
  exit: false,
  rationale_md: "",
  ...extra,
});

const policy = (extra: Record<string, unknown> = {}) => ({
  id: 3,
  name: "core",
  archived_at: null,
  created_at: "2026-01-01T10:00:00+00:00",
  versions: [
    version(1, { active_until: "2026-02-01T10:00:00+00:00" }),
    version(2),
    version(3, { is_draft: true, active_from: null, change_note: null }),
  ],
  portfolios: [{ id: 5, name: "Main" }],
  thesis_warning: false,
  semaphore: null,
  ...extra,
});

function setup(handlers: Record<string, Handler> = {}) {
  return mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(investor),
    "GET /api/policies": () =>
      json([
        {
          id: 3,
          name: "core",
          archived_at: null,
          active_version_label: "core-v2",
          has_draft: true,
        },
      ]),
    "GET /api/policies/3": () => json(policy()),
    "GET /api/policies/3/versions/2": () =>
      json({
        ...version(2),
        thesis_md: "# Global growth\n\nIndex funds follow the economy.",
        positions: [position("XUS", "40"), position("ETH", "60", { exit: true })],
      }),
    "GET /api/policies/3/versions/3": () =>
      json({
        ...version(3, { is_draft: true }),
        thesis_md: "# Draft thesis",
        positions: [position("XUS", "40"), position("ETH", "60")],
      }),
    "GET /api/policies/3/compare": () =>
      json({
        positions: [
          { ticker: "XUS", change: "changed", fields: { target_pct: ["50", "40"] } },
          { ticker: "BTC", change: "removed", fields: {} },
        ],
        thesis_changed: true,
        thesis_diff: "--- v1\n+++ v2\n@@ -1 +1 @@\n-# Old\n+# New\n",
      }),
    "GET /api/assets": () =>
      json([
        { ticker: "XUS", name: "XUS name", type: "ETF" },
        { ticker: "ETH", name: "Ethereum", type: "crypto" },
      ]),
    ...handlers,
  });
}

describe("policies", () => {
  it("[POL-04] computes absolute bands from relative thresholds", () => {
    expect(band({ target_pct: "40", buy_threshold_pct: "-20", sell_threshold_pct: "25" })).toEqual({
      buy: 32,
      sell: 50,
      midband: 45,
    });
  });

  it("[POL-01] [THS-07] creates a policy whose draft starts with the thesis template", async () => {
    const calls = setup({ "POST /api/policies": () => json(policy(), 201) });
    renderApp("/policies");
    await userEvent.click(await screen.findByRole("button", { name: "New policy" }));
    await userEvent.type(screen.getByLabelText("Name"), "core");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    // The editor of the new draft opens right away
    expect(await screen.findByRole("heading", { name: "core-v3 (draft)" })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/policies" && c.method === "POST")?.body).toEqual({
      name: "core",
      thesis_md: THESIS_TEMPLATES.en,
    });
  });

  it("[THS-07] uses the template in the account's language", async () => {
    const calls = setup({
      "GET /api/auth/me": () => json({ ...investor, language: "de" }),
      "POST /api/policies": () => json(policy(), 201),
    });
    renderApp("/policies");
    await userEvent.click(await screen.findByRole("button", { name: "Neue Anlagestrategie" }));
    await userEvent.type(screen.getByLabelText("Name"), "Kern");
    await userEvent.click(screen.getByRole("button", { name: "Erstellen" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/policies" && c.method === "POST")?.body).toEqual({
        name: "Kern",
        thesis_md: THESIS_TEMPLATES.de,
      }),
    );
  });

  it("[THS-01] [POL-02] [THS-04] shows the thesis of a version with its semaphore", async () => {
    setup();
    renderApp("/policies/3");
    expect(await screen.findByRole("heading", { name: "Global growth" })).toBeInTheDocument();
    const heading = screen.getByRole("heading", { name: "Core thesis" });
    // THS-04: a version without a review shows "not reviewed" instead of a semaphore
    expect(within(heading.parentElement!).getByText("not reviewed")).toBeInTheDocument();
    expect(screen.getByText("Index funds follow the economy.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export as JSON" })).toHaveAttribute(
      "href",
      "/api/policies/3/versions/2/thesis/export",
    );
  });

  it("[POL-02] [POL-04] [POL-11] shows the active target structure with bands and exit flags", async () => {
    setup();
    renderApp("/policies/3");
    await userEvent.click(await screen.findByRole("tab", { name: "Target structure" }));
    const row = (await screen.findByText("ETH")).closest("tr")!;
    expect(within(row).getByText("exit")).toBeInTheDocument();
    const xus = screen.getByText("XUS").closest("tr")!;
    expect(within(xus).getByText("32.0 %")).toBeInTheDocument();
    expect(within(xus).getByText("50.0 %")).toBeInTheDocument();
  });

  it("[POL-12] lists versions with activation periods and the portfolios using it", async () => {
    setup();
    renderApp("/policies/3");
    await userEvent.click(await screen.findByRole("tab", { name: "Versions" }));
    const versions = await screen.findAllByRole("listitem");
    expect(versions[0]).toHaveTextContent("core-v3draft");
    expect(versions[1]).toHaveTextContent("core-v2active");
    expect(versions[1]).toHaveTextContent("note 2");
    expect(screen.getByText("Main")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive policy" })).not.toBeInTheDocument();
  });

  it("[POL-13] archives a policy without portfolios", async () => {
    const calls = setup({
      "GET /api/policies/3": () => json(policy({ portfolios: [] })),
      "POST /api/policies/3/archive": () =>
        json(policy({ portfolios: [], archived_at: "2026-03-01T10:00:00+00:00" })),
    });
    renderApp("/policies/3");
    await userEvent.click(await screen.findByRole("tab", { name: "Versions" }));
    await userEvent.click(await screen.findByRole("button", { name: "Archive policy" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/policies/3/archive")).toBe(true));
  });

  it("[POL-09] compares two versions", async () => {
    setup();
    renderApp("/policies/3");
    await userEvent.click(await screen.findByRole("tab", { name: "Compare" }));
    expect(await screen.findByText(/target: 50 → 40/)).toBeInTheDocument();
    expect(screen.getByText("removed")).toBeInTheDocument();
    expect(screen.getByText("The thesis changed:")).toBeInTheDocument();
    expect(screen.getByText("+# New")).toBeInTheDocument();
  });

  it("[POL-11] [THS-04] warns about a broken thesis of the active version, from its review", async () => {
    const broken = reviewBrief({ semaphore: "broken" });
    setup({
      "GET /api/policies/3": () =>
        json(
          policy({
            thesis_warning: true,
            semaphore: "broken",
            versions: [
              version(1, { active_until: "2026-02-01T10:00:00+00:00" }),
              version(2, { review: broken, reviews: [broken] }),
              version(3, { is_draft: true, active_from: null, change_note: null }),
            ],
          }),
        ),
    });
    renderApp("/policies/3");
    expect(
      await screen.findByText(/The review of the active version rates its thesis/),
    ).toHaveTextContent("broken");
    const heading = await screen.findByRole("heading", { name: "Core thesis" });
    expect(within(heading.parentElement!).getByText("broken")).toBeInTheDocument();
  });

  it("[POL-06] [POL-17] [POL-08] [REV-11] finalizes the draft: summary, change note, activate anyway", async () => {
    const calls = setup({
      "PUT /api/policies/3/draft/change-note": () => json({ ...version(3), positions: [] }),
      "POST /api/policies/3/draft/activate": () => json({ ...version(3), positions: [] }),
    });
    renderApp("/policies/3");
    // POL-17: activation goes through the summary of the draft
    await userEvent.click(await screen.findByRole("button", { name: "Finalize draft" }));
    expect(await screen.findByRole("heading", { name: "core-v3: summary" })).toBeInTheDocument();
    // REV-11: no review is pointed out, never required
    expect(screen.getByText(/Not reviewed. You can activate the draft anyway/)).toBeInTheDocument();
    expect(screen.getByText("Total of the targets: 100.00 %")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Changes against v2" })).toBeInTheDocument();
    expect(await screen.findByText("BTC")).toBeInTheDocument();
    expect(screen.getByText(/It applies to: Main/)).toBeInTheDocument();
    // POL-06, POL-14: from v2 on a change note is asked for; it is saved automatically
    const note = screen.getByLabelText("Change note");
    expect(note).toHaveValue("note 3"); // as saved with the draft
    await userEvent.clear(note);
    await userEvent.type(note, "Less ETH");
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/policies/3/draft/change-note")?.body).toEqual({
        change_note: "Less ETH",
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Activate anyway" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/policies/3/draft/activate")?.body).toEqual({
        change_note: "Less ETH",
      }),
    );
    expect(await screen.findByRole("heading", { name: "core" })).toBeInTheDocument();
  });

  it("[POL-17] [REV-09] [REV-11] shows whether the review matches the draft", async () => {
    const withReview = (brief: unknown) =>
      setup({
        "GET /api/policies/3": () =>
          json(
            policy({
              versions: [
                version(2),
                version(3, {
                  is_draft: true,
                  active_from: null,
                  change_note: null,
                  review: brief,
                  reviews: [brief],
                }),
              ],
            }),
          ),
      });
    withReview(reviewBrief({ outdated: false }));
    const first = renderApp("/policies/3/draft/summary");
    expect(await screen.findByText("matches the draft")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Score: 7.0 of 10" })).toBeInTheDocument();
    expect(screen.getByText("good")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Activate" })).toBeEnabled();
    first.unmount();

    withReview(reviewBrief({ outdated: true, semaphore: "broken" }));
    renderApp("/policies/3/draft/summary");
    expect(await screen.findByText("no longer matches the draft")).toBeInTheDocument();
    expect(screen.getByText(/changed after its review/)).toBeInTheDocument();
    // A broken thesis is recorded as broken and sells nothing (POL-17, RB-25)
    expect(
      screen.getByText(/Activating records it as broken and sells nothing/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Activate anyway" })).toBeEnabled();
  });

  it("[POL-17] [POL-05] blocks only an incomplete target structure, and leads back to the editor", async () => {
    setup({
      "GET /api/policies/3/versions/3": () =>
        json({
          ...version(3, { is_draft: true }),
          thesis_md: "# Draft thesis",
          positions: [position("XUS", "40")],
        }),
    });
    renderApp("/policies/3/draft/summary");
    expect(await screen.findByText("Total of the targets: 40.00 %")).toBeInTheDocument();
    expect(screen.getByText(/must sum to 100 %/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Activate anyway" })).toBeDisabled();
    await userEvent.click(screen.getByRole("link", { name: "Back to the editor" }));
    expect(await screen.findByRole("group", { name: "Position 1" })).toBeInTheDocument();
  });

  it("[POL-17] waits for a running review before activating", async () => {
    const brief = reviewBrief({ state: "running", total: null });
    setup({
      "GET /api/policies/3": () =>
        json(
          policy({
            versions: [
              version(2),
              version(3, { is_draft: true, active_from: null, review: brief, reviews: [brief] }),
            ],
          }),
        ),
    });
    renderApp("/policies/3/draft/summary");
    expect((await screen.findAllByText(/review is still running/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Activate" })).toBeDisabled();
  });

  it("[POL-16] discards a draft after a confirmation, back to the active version", async () => {
    const calls = setup({
      "DELETE /api/policies/3/draft": () => json({ policy_deleted: false }),
    });
    renderApp("/policies/3/draft");
    await userEvent.click(await screen.findByRole("button", { name: "Discard draft" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/stays at its active version/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Discard" }),
    );
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(await screen.findByRole("tab", { name: "Versions" })).toBeInTheDocument();
  });

  it("[POL-16] deletes a never activated policy with its draft", async () => {
    setup({
      "GET /api/policies/3": () =>
        json(policy({ versions: [version(1, { is_draft: true, active_from: null })] })),
      "GET /api/policies/3/versions/1": () =>
        json({ ...version(1, { is_draft: true }), thesis_md: "# New", positions: [] }),
      "DELETE /api/policies/3/draft": () => json({ policy_deleted: true }),
    });
    renderApp("/policies/3/draft");
    await userEvent.click(await screen.findByRole("button", { name: "Discard draft" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/never activated, so it is deleted/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Discard" }));
    expect(await screen.findByRole("heading", { name: "Policies" })).toBeInTheDocument();
  });

  it("[REV-20] marks a version activated without a matching review", async () => {
    setup({
      "GET /api/policies": () =>
        json([
          {
            id: 3,
            name: "core",
            archived_at: null,
            active_version_label: "core-v2",
            has_draft: false,
            thesis_warning: false,
            semaphore: null,
            mark: "not_reviewed",
          },
        ]),
      "GET /api/policies/3": () => json(policy({ mark: "review_did_not_match" })),
    });
    renderApp("/policies");
    expect(await screen.findByText("not reviewed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "core" }));
    expect(await screen.findByText("review did not match")).toBeInTheDocument();
  });

  it("[POL-14] saves the draft automatically, before finalizing, and shows when", async () => {
    const calls = setup({
      "PUT /api/policies/3/draft": () => json({ ...version(3, { is_draft: true }), positions: [] }),
    });
    renderApp("/policies/3/draft");
    const title = await screen.findByLabelText("Title");
    expect(screen.getByRole("status")).toHaveTextContent("Saved automatically");
    // Nothing is saved without a change; there is no save button
    expect(screen.queryByRole("button", { name: /^Save/ })).toBeNull();
    await userEvent.type(title, " 2");
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/Saved automatically · \d/),
    );
    // Finalize saves what was typed just before
    await userEvent.type(title, "3");
    await userEvent.click(screen.getByRole("button", { name: "Finalize →" }));
    expect(await screen.findByRole("heading", { name: "core-v3: summary" })).toBeInTheDocument();
    const puts = calls.filter((c) => c.method === "PUT");
    expect((puts.at(-1)?.body as { thesis: { title: string } }).thesis.title).toBe(
      "Core thesis 23",
    );
  });

  it("[POL-14] retries a failed save", async () => {
    let failing = true;
    const calls = setup({
      "PUT /api/policies/3/draft": () =>
        failing
          ? json({ detail: "down" }, 503)
          : json({ ...version(3, { is_draft: true }), positions: [] }),
    });
    renderApp("/policies/3/draft");
    await userEvent.type(await screen.findByLabelText("Title"), "!");
    expect(await screen.findByText("Saving failed; it is retried")).toBeInTheDocument();
    failing = false;
    await waitFor(
      () => expect(screen.getByRole("status")).toHaveTextContent(/Saved automatically · /),
      { timeout: 8000 },
    );
    expect(calls.filter((c) => c.method === "PUT").length).toBeGreaterThanOrEqual(2);
  }, 15_000);

  it("[POL-02] [POL-05] edits the draft: bands, total, known tickers, exit flag", async () => {
    const calls = setup({
      "PUT /api/policies/3/draft": () => json({ ...version(3, { is_draft: true }), positions: [] }),
    });
    renderApp("/policies/3/draft");
    const first = await screen.findByRole("group", { name: "Position 1" });
    // known ticker: name and type come from the asset catalog
    await waitFor(() => expect(within(first).getByLabelText("Name")).toBeDisabled());
    expect(screen.getByLabelText("Band of position 1")).toHaveTextContent(
      "Buy below 32.0 % · sell above 50.0 % · midband 45.0 %",
    );
    expect(screen.getByLabelText("Target total")).toHaveTextContent("Total target: 100.00 %");

    await userEvent.click(screen.getByRole("button", { name: "Add position" }));
    const added = screen.getByRole("group", { name: "Position 3" });
    await userEvent.type(within(added).getByLabelText("Ticker"), "GOLD");
    await userEvent.type(within(added).getByLabelText("Name"), "Gold ETF");
    await userEvent.clear(within(added).getByLabelText("Target %"));
    await userEvent.type(within(added).getByLabelText("Target %"), "10");
    expect(screen.getByLabelText("Target total")).toHaveTextContent("must be 100 % to activate");
    await userEvent.clear(within(first).getByLabelText("Target %"));
    await userEvent.type(within(first).getByLabelText("Target %"), "30");
    await userEvent.click(
      within(screen.getByRole("group", { name: "Position 2" })).getByLabelText(
        "Exit (sell completely)",
      ),
    );
    // POL-14: saved automatically
    const last = () =>
      calls.filter((c) => c.method === "PUT").at(-1)?.body as
        { positions: Record<string, unknown>[] } | undefined;
    await waitFor(() =>
      expect(
        last()?.positions.map((p) => [p.ticker, p.name, p.type, p.target_pct, p.exit]),
      ).toEqual([
        ["XUS", null, null, "30", false],
        ["ETH", null, null, "60", true],
        ["GOLD", "Gold ETF", "ETF", "10", false],
      ]),
    );
    expect(last()).not.toHaveProperty("reinvest_sells");
  });

  it("[REV-01] [REV-05] [REV-19] reviews the whole draft in its editor, saving it first", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    const calls = setup({
      "PUT /api/policies/3/draft": () => json({ ...version(3, { is_draft: true }), positions: [] }),
      "GET /api/ai-reviewers": () => json([]),
      "GET /api/policies/3/draft/review-prompt": () =>
        json({ prompt_id: "R203-20260301T100000Z-90-abcdef", text: "POLICY PROMPT" }),
    });
    renderApp("/policies/3/draft");
    // POL-14: what was just typed is saved before the prompt is made
    await userEvent.type(await screen.findByLabelText("Title"), " 2");
    await userEvent.click(await screen.findByRole("tab", { name: "Review" }));
    // One review of thesis and target structure; no separate policy review below
    expect(screen.getAllByRole("region", { name: /review/i })).toHaveLength(1);
    const section = screen.getByRole("region", { name: "Review" });
    expect(within(section).getByText(/Not reviewed yet/)).toBeInTheDocument();
    // Without AI reviewers, manual is preselected (REV-16); the news period applies (REV-04)
    await waitFor(() =>
      expect(within(section).getByLabelText("Review method")).toHaveValue("manual"),
    );
    expect(within(section).getByLabelText("News of the last … days")).toHaveValue(90);
    expect(within(section).getByText(/and the target structure \(percentages/)).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Copy review prompt" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("POLICY PROMPT"));
    const order = calls.map((c) => `${c.method} ${c.path}`);
    expect(order.indexOf("PUT /api/policies/3/draft")).toBeLessThan(
      order.indexOf("GET /api/policies/3/draft/review-prompt?news_days=90"),
    );
    expect(screen.getByRole("heading", { name: /core/ })).toBeInTheDocument(); // still editing
  });

  it("[REV-01] points from the policy page to the editor for reviews", async () => {
    setup();
    renderApp("/policies/3");
    await userEvent.selectOptions(await screen.findByLabelText("Version"), "3"); // the draft
    expect(await screen.findByRole("link", { name: "editor" })).toHaveAttribute(
      "href",
      "/policies/3/draft",
    );
  });

  it("[POL-04] [IMP-06] shows the server's errors at the position", async () => {
    setup({
      "PUT /api/policies/3/draft": () =>
        json(
          {
            detail: "x",
            problems: [
              {
                path: "positions[1].buy_threshold_pct",
                message: "Buy threshold must be between -100 and 0",
              },
            ],
          },
          422,
        ),
    });
    renderApp("/policies/3/draft");
    const second = await screen.findByRole("group", { name: "Position 2" });
    await userEvent.clear(within(second).getByLabelText("Buy %"));
    await userEvent.type(within(second).getByLabelText("Buy %"), "5");
    expect(
      await within(second).findByText("Buy threshold must be between -100 and 0"),
    ).toBeInTheDocument();
    // POL-14: a save the server refuses is not retried; the fields say why
    expect(screen.getByText("Not saved yet: correct the marked fields")).toBeInTheDocument();
  });

  it("[POL-05] warns about more than one cash buffer", async () => {
    setup();
    renderApp("/policies/3/draft");
    await screen.findByRole("group", { name: "Position 1" });
    for (const n of [3, 4]) {
      await userEvent.click(screen.getByRole("button", { name: "Add position" }));
      const row = screen.getByRole("group", { name: `Position ${n}` });
      await userEvent.type(within(row).getByLabelText("Ticker"), `C${n}`);
      await userEvent.selectOptions(within(row).getByLabelText("Type"), "cash_buffer");
    }
    expect(screen.getByText("At most one cash buffer position is allowed.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove position 4" }));
    expect(
      screen.queryByText("At most one cash buffer position is allowed."),
    ).not.toBeInTheDocument();
  });

  it("[IMP-02] [IMP-07] imports a target structure after showing the changes", async () => {
    const calls = setup({
      "POST /api/policies/3/import/preview": () =>
        json({
          positions: [{ ticker: "BTC", change: "added", fields: {} }],
          thesis_changed: false,
          thesis_diff: "",
        }),
      "POST /api/policies/3/import": () =>
        json({ ...version(3, { is_draft: true }), positions: [] }, 201),
    });
    renderApp("/policies/3");
    await userEvent.click(await screen.findByRole("tab", { name: "Versions" }));
    await userEvent.click(screen.getByRole("button", { name: "Import target structure" }));
    await userEvent.upload(screen.getByLabelText("Import file"), new File(['{"a":1}'], "s.json"));
    expect(await screen.findByText("added")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    // Back on the policy overview, showing the imported draft, not the draft editor
    await waitFor(() => expect(screen.getByLabelText("Version")).toHaveValue("3"));
    expect(screen.getByRole("tab", { name: "Target structure" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("heading", { name: "core" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "core-v3 (draft)" })).not.toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/policies/3/import")?.body).toEqual({ a: 1 });
  });

  it("[THS-01] [THS-04] edits the thesis of the draft next to its review and saves it with the positions", async () => {
    const calls = setup({
      "PUT /api/policies/3/draft": () => json({ ...version(3, { is_draft: true }), positions: [] }),
      "GET /api/ai-reviewers": () => json([]),
    });
    renderApp("/policies/3/draft");
    const title = await screen.findByLabelText("Title");
    expect(title).toHaveValue("Core thesis");
    await userEvent.clear(title);
    await userEvent.type(title, "Growth");
    // THS-04: a thesis has no status set by the investor
    expect(screen.queryByLabelText("Status")).toBeNull();
    // The review is a tab next to the editor (REV-01)
    await userEvent.click(screen.getByRole("tab", { name: "Review" }));
    expect(screen.getByRole("region", { name: "Review" })).toBeInTheDocument();
    // POL-14: saved automatically
    await waitFor(() =>
      expect(
        (calls.filter((c) => c.method === "PUT").at(-1)?.body as { thesis: unknown })?.thesis,
      ).toEqual({ title: "Growth", content_md: "# Draft thesis" }),
    );
  });

  it("[IMP-01] [IMP-07] imports a thesis as a new policy, or into the draft of a policy", async () => {
    const calls = setup({
      "POST /api/policies/import-thesis/preview": () =>
        json({ creates_new_policy: true, version_no: 1, title: "Imported" }),
      "POST /api/policies/import-thesis": () => json(policy(), 201),
      "POST /api/policies/3/import-thesis/preview": () =>
        json({ creates_new_policy: false, version_no: 3, title: "Imported" }),
      "POST /api/policies/3/import-thesis": () =>
        json({ ...version(3, { is_draft: true }), thesis_md: "x", positions: [] }, 201),
    });
    const { unmount } = renderApp("/policies");
    await userEvent.click(await screen.findByRole("button", { name: "Import thesis" }));
    await userEvent.upload(screen.getByLabelText("Import file"), new File(['{"a":1}'], "t.json"));
    expect(await screen.findByText(/Creates the policy/)).toHaveTextContent("Imported");
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByRole("heading", { name: "core" })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/policies/import-thesis")?.body).toEqual({ a: 1 });
    unmount();

    renderApp("/policies/3");
    await userEvent.click(await screen.findByRole("button", { name: "Import thesis" }));
    await userEvent.upload(screen.getByLabelText("Import file"), new File(['{"b":2}'], "t.json"));
    expect(await screen.findByText(/Replaces the thesis of the draft v3/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/policies/3/import-thesis")?.body).toEqual({ b: 2 }),
    );
  });
});
