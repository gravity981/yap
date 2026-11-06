import { useNavigate } from "@tanstack/react-router";
import { Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { FormError } from "@/components/form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { PriceSourceControl } from "@/features/prices/price-source";
import { useThesis } from "@/features/theses/api";
import { statusLabel } from "@/features/theses/status";
import { api, unwrap } from "@/api/client";
import { formatPct } from "@/lib/format";

import {
  useAssets,
  usePolicy,
  usePolicyActions,
  useVersion,
  type PositionIn,
  type Version,
} from "./api";
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

/** POL-02 to POL-05: edits the draft's target structure. */
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
      thesisId={policy.data.thesis_id}
      version={version.data}
    />
  );
}

function DraftForm({
  policyId,
  policyName,
  thesisId,
  version,
}: {
  policyId: number;
  policyName: string;
  thesisId: number;
  version: Version;
}) {
  const { t } = useTranslation();
  const { saveDraft } = usePolicyActions(policyId);
  const assets = useAssets();
  const thesis = useThesis(thesisId);
  const navigate = useNavigate();
  const [rows, setRows] = useState<Row[]>(() =>
    version.positions.length ? rowsOf(version) : [emptyRow()],
  );
  const [revisionId, setRevisionId] = useState(version.thesis_revision_id);
  const [revisionError, setRevisionError] = useState<unknown>(null);
  const known = new Map((assets.data ?? []).map((a) => [a.ticker, a]));

  const total = rows.reduce((sum, r) => sum + (Number(r.target_pct) || 0), 0);
  const cashBuffers = rows.filter(
    (r) => (known.get(r.ticker.trim().toUpperCase())?.type ?? r.type) === "cash_buffer",
  ).length;
  const back = () =>
    navigate({ to: "/policies/$policyId", params: { policyId: String(policyId) } });

  const update = (i: number, patch: Partial<Row>) =>
    setRows((current) => current.map((r, k) => (k === i ? { ...r, ...patch } : r)));

  const problem = (i: number, field: string) =>
    saveDraft.error instanceof ApiError
      ? saveDraft.error.problems.find((p) => p.path === `positions[${i}].${field}`)?.message
      : undefined;

  const changeRevision = async (id: number) => {
    setRevisionError(null);
    try {
      await unwrap(
        api.PUT("/api/policies/{policy_id}/draft/thesis-revision", {
          params: { path: { policy_id: policyId } },
          body: { thesis_revision_id: id },
        }),
      );
      setRevisionId(id);
    } catch (error) {
      setRevisionError(error);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const positions: PositionIn[] = rows.map((r) => {
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
    saveDraft.mutate({ positions }, { onSuccess: back });
  };

  return (
    <form className="grid gap-4" onSubmit={submit}>
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold">
          {t("policies.editor.title", { name: policyName, no: version.version_no })}
        </h1>
        <p className="text-sm text-muted-foreground">{t("policies.editor.hint")}</p>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          {t("policies.editor.thesisRevision")}
          <NativeSelect
            className="w-auto"
            aria-label={t("policies.editor.thesisRevision")}
            value={revisionId}
            onChange={(e) => changeRevision(Number(e.target.value))}
          >
            {thesis.data?.revisions.map((r) => (
              <option key={r.id} value={r.id}>
                {r.revision_no} ({statusLabel(r.status)})
              </option>
            ))}
          </NativeSelect>
        </label>
      </div>
      <FormError error={revisionError} />

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
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={back}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={saveDraft.isPending}>
          {t("policies.editor.saveDraft")}
        </Button>
      </div>
    </form>
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
