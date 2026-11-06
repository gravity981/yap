import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { investor, json, mockApi, renderApp, type Handler } from "@/test/utils";

import { THESIS_TEMPLATE } from "./template";

// CodeMirror needs a real browser; the page logic is tested with a plain text field
vi.mock("@uiw/react-codemirror", () => ({
  default: (props: { value: string; onChange: (v: string) => void; "aria-label": string }) => (
    <textarea
      aria-label={props["aria-label"]}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    />
  ),
  EditorView: { lineWrapping: [] },
}));

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

const draft = (n: number, extra: Record<string, unknown> = {}) =>
  rev(n, { is_draft: true, activated_at: null, change_note: null, ...extra });

const thesis = {
  id: 7,
  is_own: true,
  visibility: "private",
  created_at: "2026-01-01T10:00:00+00:00",
  revisions: [rev(1), rev(2, { status: "broken" })],
};

function setup(handlers: Record<string, Handler> = {}) {
  return mockApi({
    "GET /api/version": () => json({ version: "1.2.0", commit: "abc" }),
    "GET /api/auth/me": () => json(investor),
    "GET /api/theses": () =>
      json([
        {
          id: 7,
          is_own: true,
          visibility: "private",
          latest: rev(2, { status: "broken" }),
          has_draft: false,
          active_revision_no: 2,
        },
        {
          id: 8,
          is_own: false,
          visibility: "shared",
          latest: rev(1, { title: "Shared idea" }),
          has_draft: false,
          active_revision_no: 1,
        },
      ]),
    "GET /api/theses/7": () => json(thesis),
    "GET /api/theses/7/revisions/1": () =>
      json({ ...rev(1), thesis_id: 7, content_md: "# First\n\nold text" }),
    "GET /api/theses/7/revisions/2": () =>
      json({ ...rev(2, { status: "broken" }), thesis_id: 7, content_md: "# Second\n\nnew text" }),
    "GET /api/theses/7/diff": () =>
      json({
        from_revision_no: 1,
        to_revision_no: 2,
        unified_diff: "@@ -1 +1 @@\n-old text\n+new text",
      }),
    ...handlers,
  });
}

describe("theses", () => {
  it("[THS-05] lists own and shared theses", async () => {
    setup();
    renderApp("/theses");
    const shared = (await screen.findByRole("link", { name: "Shared idea" })).closest("tr")!;
    expect(within(shared).getByText("shared with you")).toBeInTheDocument();
    const own = screen.getByRole("link", { name: "Core thesis" }).closest("tr")!;
    expect(within(own).getByText("broken")).toBeInTheDocument();
  });

  it("[THS-01] [THS-07] creates a thesis from the template with live preview", async () => {
    const calls = setup({ "POST /api/theses": () => json({ ...thesis, id: 7 }, 201) });
    renderApp("/theses/new");
    const editor = (
      await screen.findAllByLabelText("Content", {}, { timeout: 5000 })
    )[0] as HTMLTextAreaElement;
    expect(editor.value).toBe(THESIS_TEMPLATE);
    await userEvent.clear(editor);
    await userEvent.type(editor, "# My view");
    expect(
      within(screen.getByLabelText("Preview", { selector: "div[aria-label=Preview]" })).getByRole(
        "heading",
        { name: "My view" },
      ),
    ).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Title"), "Growth");
    await userEvent.selectOptions(screen.getByLabelText("Visibility"), "shared");
    await userEvent.click(screen.getByRole("button", { name: "Create thesis" }));
    expect(await screen.findByRole("heading", { name: "Core thesis" })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/theses" && c.method === "POST")?.body).toEqual({
      title: "Growth",
      content_md: "# My view",
      visibility: "shared",
    });
  });

  it("[THS-02] [THS-04] saves the draft with status and change note", async () => {
    const withDraft = { ...thesis, revisions: [...thesis.revisions, draft(3)] };
    const calls = setup({
      "GET /api/theses/7": () => json(withDraft),
      "GET /api/theses/7/revisions/3": () =>
        json({ ...draft(3), thesis_id: 7, content_md: "# Third\n\ndraft text" }),
      "PUT /api/theses/7/draft": () => json({ ...draft(3), thesis_id: 7, content_md: "" }),
    });
    renderApp("/theses/7/edit");
    expect(
      await screen.findByRole("heading", { name: "Edit draft (revision 3)" }),
    ).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Status"), "needs_adaptation");
    await userEvent.type(screen.getByLabelText("Change note"), "Recovered");
    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/theses/7/draft")).toBe(true));
    expect(calls.find((c) => c.path === "/api/theses/7/draft")?.body).toEqual({
      title: "Core thesis",
      content_md: "# Third\n\ndraft text",
      status: "needs_adaptation",
      change_note: "Recovered",
    });
  });

  it("[THS-02] offers to create a draft when there is none", async () => {
    setup();
    renderApp("/theses/7/edit");
    expect(await screen.findByText(/This thesis has no draft/)).toBeInTheDocument();
  });

  it("[THS-04] explains that a status other than intact changes no rebalancing", async () => {
    setup({
      "GET /api/theses/7": () => json({ ...thesis, revisions: [rev(1), draft(2)] }),
      "GET /api/theses/7/revisions/2": () =>
        json({ ...draft(2), thesis_id: 7, content_md: "# Draft" }),
    });
    renderApp("/theses/7/edit");
    await userEvent.selectOptions(await screen.findByLabelText("Status"), "broken");
    expect(screen.getByText(/does not change any rebalancing by itself/)).toBeInTheDocument();
  });

  it("[THS-02] creates a new draft and opens the editor", async () => {
    let created = false;
    const calls = setup({
      "GET /api/theses/7": () =>
        json(created ? { ...thesis, revisions: [...thesis.revisions, draft(3)] } : thesis),
      "GET /api/theses/7/revisions/3": () =>
        json({ ...draft(3), thesis_id: 7, content_md: "# Second\n\nnew text" }),
      "POST /api/theses/7/draft": () => {
        created = true;
        return json({ ...draft(3), thesis_id: 7, content_md: "" }, 201);
      },
    });
    renderApp("/theses/7");
    expect(screen.queryByRole("button", { name: "Activate draft" })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "New draft" }));
    expect(
      await screen.findByRole("heading", { name: "Edit draft (revision 3)" }),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/theses/7/draft" && c.method === "POST")).toBe(true);
  });

  it("[THS-02] [THS-03] activates the draft with a change note", async () => {
    const calls = setup({
      "GET /api/theses/7": () => json({ ...thesis, revisions: [...thesis.revisions, draft(3)] }),
      "POST /api/theses/7/draft/activate": () => json({ ...rev(3), thesis_id: 7, content_md: "" }),
    });
    renderApp("/theses/7");
    expect(await screen.findByText("draft r3")).toBeInTheDocument();
    expect(screen.getByText("revision 2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Activate draft" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Change note")).toBeRequired();
    await userEvent.type(within(dialog).getByLabelText("Change note"), "New drivers");
    expect(within(dialog).getByText(/no review/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Activate anyway" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/theses/7/draft/activate")?.body).toEqual({
        change_note: "New drivers",
      }),
    );
  });

  it("[THS-02] the first revision of a new thesis cannot be deleted", async () => {
    setup({ "GET /api/theses/7": () => json({ ...thesis, revisions: [draft(1)] }) });
    renderApp("/theses/7");
    expect(await screen.findByText("not activated yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete draft" })).toBeDisabled();
  });

  it("[THS-08] [THS-02] shows content per revision, history and a comparison", async () => {
    setup();
    renderApp("/theses/7");
    expect(await screen.findByRole("heading", { name: "Second" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Revision"), "1");
    expect(await screen.findByRole("heading", { name: "First" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "History" }));
    expect(await screen.findByText("change 2")).toBeInTheDocument();
    expect(screen.getByText("First revision")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Compare" }));
    const diff = await screen.findByLabelText("Differences");
    expect(within(diff).getByText("+new text")).toHaveClass("bg-success/15");
    expect(within(diff).getByText("-old text")).toHaveClass("bg-destructive/15");
  });

  it("[THS-05] shares and unshares an own thesis", async () => {
    const calls = setup({
      "PUT /api/theses/7/visibility": () => json({ ...thesis, visibility: "shared" }),
    });
    renderApp("/theses/7");
    await userEvent.click(await screen.findByRole("button", { name: "Share" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/theses/7/visibility")?.body).toEqual({
        visibility: "shared",
      }),
    );
  });

  it("[THS-10] copies a shared thesis", async () => {
    const calls = setup({
      "GET /api/theses/7": () => json({ ...thesis, is_own: false, visibility: "shared" }),
      "POST /api/theses/7/copy": () => json({ ...thesis, id: 7 }, 201),
    });
    renderApp("/theses/7");
    expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Copy to my theses" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/theses/7/copy")).toBe(true));
  });

  it("[IMP-01] [IMP-07] imports a thesis after a preview", async () => {
    const calls = setup({
      "POST /api/theses/import/preview": () =>
        json({
          creates_new_thesis: true,
          revision_no: 1,
          title: "Imported",
          status: "intact",
          visibility: "private",
        }),
      "POST /api/theses/import": () => json({ ...rev(1), thesis_id: 7, content_md: "" }, 201),
    });
    renderApp("/theses");
    await userEvent.click(await screen.findByRole("button", { name: "Import" }));
    const importButton = screen.getByRole("button", { name: "Import" });
    expect(importButton).toBeDisabled();
    const file = new File(['{"schema_version": "1.0"}'], "thesis.json", {
      type: "application/json",
    });
    await userEvent.upload(screen.getByLabelText("Import file"), file);
    expect(await screen.findByText("Imported")).toBeInTheDocument();
    await userEvent.click(importButton);
    // Opens the imported thesis
    expect(
      await screen.findByRole("heading", { name: "Core thesis", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/theses/import")?.body).toEqual({
      schema_version: "1.0",
    });
  });

  it("[IMP-01] shows the imported draft", async () => {
    let imported = false;
    setup({
      "GET /api/theses/7": () =>
        json(imported ? { ...thesis, revisions: [...thesis.revisions, draft(3)] } : thesis),
      "GET /api/theses/7/revisions/3": () =>
        json({ ...draft(3), thesis_id: 7, content_md: "# Third\n\nimported text" }),
      "POST /api/theses/7/import/preview": () =>
        json({
          creates_new_thesis: false,
          revision_no: 3,
          title: "Core thesis",
          status: "intact",
          visibility: "private",
        }),
      "POST /api/theses/7/import": () => {
        imported = true;
        return json({ ...draft(3), thesis_id: 7, content_md: "# Third\n\nimported text" }, 201);
      },
    });
    renderApp("/theses/7");
    await userEvent.selectOptions(await screen.findByLabelText("Revision"), "1");
    await userEvent.click(screen.getByRole("tab", { name: "History" }));
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    await userEvent.upload(screen.getByLabelText("Import file"), new File(["{}"], "t.json"));
    await userEvent.click(await screen.findByRole("button", { name: "Import" }));
    expect(await screen.findByText("imported text")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Content" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("Revision")).toHaveValue("3");
  });

  it("[IMP-06] lists import errors with their JSON path", async () => {
    setup({
      "POST /api/theses/7/import/preview": () =>
        json(
          {
            detail: "x",
            problems: [{ path: "$.change_note", message: "A change note is required" }],
          },
          422,
        ),
    });
    renderApp("/theses/7");
    await userEvent.click(await screen.findByRole("button", { name: "Import" }));
    await userEvent.upload(screen.getByLabelText("Import file"), new File(["{}"], "t.json"));
    expect(await screen.findByText("$.change_note")).toBeInTheDocument();
    expect(screen.getByText(/A change note is required/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
  });

  it("shows not found for invalid IDs", async () => {
    setup();
    renderApp("/theses/abc");
    expect(await screen.findByText("Not found.")).toBeInTheDocument();
  });
});
