import { Link, useNavigate } from "@tanstack/react-router";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { Field, FormError, fieldError } from "@/components/form";
import { MarkdownEditor } from "@/components/lazy-markdown-editor";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { PriceSourceControl } from "@/features/prices/price-source";
import type { ReviewBrief } from "@/features/reviews/api";
import { ReviewPane } from "@/features/reviews/pane";
import { formatPct, formatTime } from "@/lib/format";

import {
  useAssets,
  usePolicy,
  usePolicyActions,
  useVersion,
  type PositionIn,
  type Version,
} from "./api";
import { useAutoSave, type SaveStatus } from "./auto-save";
import { DiscardDraft } from "./discard";
import { assetTypeLabel } from "./positions";

const TYPES = ["ETF", "stock", "crypto", "cash_buffer"] as const;
const TICKER_FIELD = "ticker"; // API field path of a position

interface Row {
  ticker: string;
  name: string;
  type: string;
  target_pct: string;
  buy_threshold_pct: string;
  sell_threshold_pct: string;
  exit: boolean;
  rationale_md: string;
}

const emptyRow = (): Row => ({
  ticker: "",
  name: "",
  type: "ETF",
  target_pct: "0",
  buy_threshold_pct: "-20",
  sell_threshold_pct: "20",
  exit: false,
  rationale_md: "",
});

function rowsOf(version: Version): Row[] {
  return version.positions.map((p) => ({
    ticker: p.ticker,
    name: p.name,
    type: p.type,
    target_pct: p.target_pct,
    buy_threshold_pct: p.buy_threshold_pct,
    sell_threshold_pct: p.sell_threshold_pct,
    exit: p.exit,
    rationale_md: p.rationale_md,
  }));
}

/** Absolute band of a row as the user types (POL-04); display only, the backend decides. */
export function band(row: Pick<Row, "target_pct" | "buy_threshold_pct" | "sell_threshold_pct">) {
  const target = Number(row.target_pct);
  const buy = target * (1 + Number(row.buy_threshold_pct) / 100);
  const sell = target * (1 + Number(row.sell_threshold_pct) / 100);
  return { buy, sell, midband: (target + sell) / 2 };
}

/** POL-02 to POL-05, THS-01: edits the draft's thesis and target structure. */
export function DraftEditorPage({ policyId }: { policyId: number }) {
  const { t } = useTranslation();
  const policy = usePolicy(policyId);
  const draft = policy.data?.versions.find((v) => v.is_draft);
  const version = useVersion(policyId, draft?.version_no);
  if (policy.data && !draft) {
    return <Alert>{t("policies.editor.noDraft")}</Alert>;
  }
  if (!version.data || !policy.data) {
    return <p className="text-muted-foreground">{t("common.loading")}</p>;
  }
  return (
    <DraftForm
      policyId={policyId}
      policyName={policy.data.name}
      version={version.data}
      brief={draft?.review}
      neverActivated={policy.data.versions.every((v) => v.is_draft)}
    />
  );
}

function DraftForm({
  policyId,
  policyName,
  version,
  brief,
  neverActivated,
}: {
  policyId: number;
  policyName: string;
  version: Version;
  brief: ReviewBrief | null | undefined;
  neverActivated: boolean;
}) {
  const { t } = useTranslation();
  const { saveDraft } = usePolicyActions(policyId);
  const assets = useAssets();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Row[]>(() =>
    version.positions.length ? rowsOf(version) : [emptyRow()],
  );
  const [title, setTitle] = useState(version.thesis_title);
  const [content, setContent] = useState(version.thesis_md);
  const known = new Map((assets.data ?? []).map((a) => [a.ticker, a]));

  const total = rows.reduce((sum, r) => sum + (Number(r.target_pct) || 0), 0);
  const cashBuffers = rows.filter(
    (r) => (known.get(r.ticker.trim().toUpperCase())?.type ?? r.type) === "cash_buffer",
  ).length;

  const update = (i: number, patch: Partial<Row>) =>
    setRows((current) => current.map((r, k) => (k === i ? { ...r, ...patch } : r)));

  const problem = (i: number, field: string) =>
    saveDraft.error instanceof ApiError
      ? saveDraft.error.problems.find((p) => p.path === `positions[${i}].${field}`)?.message
      : undefined;

  // A row left completely empty is no position; a new policy may have none yet
  const positions = (rows: Row[]): PositionIn[] =>
    rows
      .filter((r) => r.ticker.trim() !== "")
      .map((r) => {
        const asset = known.get(r.ticker.trim().toUpperCase());
        return {
          ticker: r.ticker,
          name: asset ? null : r.name,
          type: asset ? null : r.type,
          target_pct: r.target_pct,
          buy_threshold_pct: r.buy_threshold_pct,
          sell_threshold_pct: r.sell_threshold_pct,
          exit: r.exit,
          rationale_md: r.rationale_md,
        };
      });
  // POL-14: everything in the editor is saved automatically; there is no save button
  const body = (draft: Content) => ({
    positions: positions(draft.rows),
    thesis: { title: draft.title, content_md: draft.content },
  });
  const autoSave = useAutoSave<Content>(
    { title, content, rows },
    (draft) => saveDraft.mutateAsync(body(draft)),
    (draft) =>
      // Leaving the page: sent without waiting for the answer
      void fetch(`${api_base()}/api/policies/${policyId}/draft`, {
        method: "PUT",
        keepalive: true,
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body(draft)),
      }).catch(() => undefined),
  );
  const finalize = async () => {
    await autoSave.flush();
    await navigate({
      to: "/policies/$policyId/draft/summary",
      params: { policyId: String(policyId) },
    });
  };

  // Not a <form>: the review pane below has forms of its own (REV-18)
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="grid gap-1">
          <Link
            to="/policies/$policyId"
            params={{ policyId: String(policyId) }}
            className="text-sm underline"
          >
            {t("policies.editor.back", { name: policyName })}
          </Link>
          <h1 className="text-2xl font-semibold">
            {t("policies.editor.title", { name: policyName, no: version.version_no })}
          </h1>
        </div>
        <SaveState status={autoSave.status} />
      </div>

      {/* THS-01: the thesis of the draft, with the review of the whole draft next to it
          (REV-01); the thesis has no status, its semaphore comes from the review (THS-04) */}
      <section className="grid gap-3" aria-label={t("policies.detail.tabThesis")}>
        <Field
          id="thesis-title"
          label={t("theses.editor.title")}
          error={fieldError(saveDraft.error, "thesis_title")}
        >
          <Input id="thesis-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <MarkdownEditor
          value={content}
          onChange={setContent}
          aside={{
            label: t("reviews.pane.tab"),
            content: (
              <ReviewPane
                policyId={policyId}
                brief={brief}
                save={autoSave.flush}
                onDraft={(draft) => {
                  // REV-07: a suggestion changed the draft on the server
                  const next = {
                    title: draft.thesis_title,
                    content: draft.thesis_md,
                    rows: draft.positions.length ? rowsOf(draft) : [emptyRow()],
                  };
                  autoSave.markSaved(next);
                  setTitle(next.title);
                  setContent(next.content);
                  setRows(next.rows);
                }}
              />
            ),
          }}
        />
      </section>

      <datalist id="asset-catalog">
        {assets.data?.map((a) => (
          <option key={a.ticker} value={a.ticker}>
            {a.name}
          </option>
        ))}
      </datalist>

      <div className="grid gap-3">
        {rows.map((row, i) => {
          const asset = known.get(row.ticker.trim().toUpperCase());
          const b = band(row);
          const tickerProblem = problem(i, TICKER_FIELD);
          return (
            <fieldset
              key={i}
              className="grid gap-2 rounded-md border p-3"
              aria-label={t("policies.editor.position", { no: i + 1 })}
            >
              <div className="grid gap-2 sm:grid-cols-[8rem_1fr_9rem_auto]">
                <Input
                  aria-label={t("policies.editor.ticker")}
                  list="asset-catalog"
                  value={row.ticker}
                  onChange={(e) => update(i, { ticker: e.target.value })}
                  required
                />
                <Input
                  aria-label={t("policies.editor.name")}
                  value={asset?.name ?? row.name}
                  disabled={asset !== undefined}
                  onChange={(e) => update(i, { name: e.target.value })}
                  placeholder={t("policies.editor.namePlaceholder")}
                />
                <NativeSelect
                  aria-label={t("policies.editor.type")}
                  value={asset?.type ?? row.type}
                  disabled={asset !== undefined}
                  onChange={(e) => update(i, { type: e.target.value })}
                >
                  {TYPES.map((type) => (
                    <option key={type} value={type}>
                      {assetTypeLabel(type)}
                    </option>
                  ))}
                </NativeSelect>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={t("policies.editor.remove", { no: i + 1 })}
                  onClick={() => setRows((r) => r.filter((_, k) => k !== i))}
                >
                  <Trash2 />
                </Button>
              </div>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-[repeat(3,8rem)_auto]">
                <NumberField
                  label={t("policies.editor.target")}
                  value={row.target_pct}
                  error={problem(i, "target_pct")}
                  onChange={(v) => update(i, { target_pct: v })}
                />
                <NumberField
                  label={t("policies.editor.buy")}
                  value={row.buy_threshold_pct}
                  error={problem(i, "buy_threshold_pct")}
                  onChange={(v) => update(i, { buy_threshold_pct: v })}
                />
                <NumberField
                  label={t("policies.editor.sell")}
                  value={row.sell_threshold_pct}
                  error={problem(i, "sell_threshold_pct")}
                  onChange={(v) => update(i, { sell_threshold_pct: v })}
                />
                <label className="col-span-3 flex items-center gap-2 text-sm sm:col-span-1">
                  <input
                    type="checkbox"
                    checked={row.exit}
                    onChange={(e) => update(i, { exit: e.target.checked })}
                  />
                  {t("policies.editor.exit")}
                </label>
              </div>
              <p
                className="text-xs text-muted-foreground"
                aria-label={t("policies.editor.bandLabel", { no: i + 1 })}
              >
                {t("policies.editor.band", {
                  buy: formatPct(b.buy),
                  sell: formatPct(b.sell),
                  midband: formatPct(b.midband),
                })}
              </p>
              {tickerProblem && <p className="text-xs text-destructive">{tickerProblem}</p>}
              {/* PRC-02: a new ticker is looked up as soon as it is entered */}
              {(asset?.type ?? row.type) !== "cash_buffer" && (
                <PriceSourceControl
                  ticker={row.ticker}
                  name={asset?.name ?? row.name}
                  type={asset?.type ?? row.type}
                  onName={(name) => asset === undefined && update(i, { name })}
                />
              )}
              <details>
                <summary className="cursor-pointer text-sm text-muted-foreground">
                  {t("policies.editor.rationale")}
                </summary>
                <Textarea
                  aria-label={t("policies.editor.rationale")}
                  className="mt-2"
                  value={row.rationale_md}
                  onChange={(e) => update(i, { rationale_md: e.target.value })}
                />
              </details>
            </fieldset>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button type="button" variant="outline" onClick={() => setRows((r) => [...r, emptyRow()])}>
          {t("policies.editor.addPosition")}
        </Button>
        <p
          className={total === 100 ? "text-sm" : "text-sm text-destructive"}
          aria-label={t("policies.editor.totalLabel")}
        >
          {t("policies.editor.total", { total: formatPct(total, undefined, 2) })}
          {total !== 100 && t("policies.editor.totalMust")}
        </p>
      </div>
      {cashBuffers > 1 && <Alert variant="destructive">{t("policies.editor.oneCashBuffer")}</Alert>}
      <FormError
        error={saveDraft.error}
        fields={rows.flatMap((_, i) =>
          ["ticker", "target_pct", "buy_threshold_pct", "sell_threshold_pct"].map(
            (f) => `positions[${i}].${f}`,
          ),
        )}
      />
      {/* POL-16, POL-17 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <DiscardDraft policyId={policyId} neverActivated={neverActivated} />
        <Button type="button" onClick={() => void finalize().catch(() => undefined)}>
          {t("policies.editor.finalize")}
        </Button>
      </div>
    </div>
  );
}

interface Content {
  title: string;
  content: string;
  rows: Row[];
}

const api_base = () => globalThis.location?.origin ?? "";

/** POL-14: when the draft was saved last, or that saving failed and is retried. */
function SaveState({ status }: { status: SaveStatus }) {
  const { t } = useTranslation();
  const text =
    status.state === "saving"
      ? t("policies.editor.saving")
      : status.state === "failed"
        ? t("policies.editor.saveFailed")
        : status.state === "invalid"
          ? t("policies.editor.saveInvalid")
          : status.at
            ? t("policies.editor.savedAt", { time: formatTime(status.at.toISOString()) })
            : t("policies.editor.savedAuto");
  return (
    <p
      role="status"
      className={
        status.state === "failed" || status.state === "invalid"
          ? "text-sm text-destructive"
          : "text-sm text-muted-foreground"
      }
    >
      {text}
    </p>
  );
}

function NumberField({
  label,
  value,
  error,
  onChange,
}: {
  label: string;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-xs">
      {label}
      <Input
        inputMode="decimal"
        value={value}
        aria-invalid={error !== undefined}
        onChange={(e) => onChange(e.target.value)}
        required
      />
      {error && <span className="text-destructive">{error}</span>}
    </label>
  );
}
