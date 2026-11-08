import i18n from "i18next";
import { useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import { Markdown } from "@/components/markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Version } from "@/features/policies/api";
import { assetTypeLabel } from "@/features/policies/positions";
import { formatPct } from "@/lib/format";

import { useSuggestionAction, type Review, type Suggestion, type SuggestionAction } from "./api";

/** What the draft editor gives the review pane, so suggestions can change the draft:
 * `save` stores what is in the editor first, `onDraft` takes the changed draft back. */
export interface SuggestionActions {
  save: () => Promise<unknown>;
  onDraft: (draft: Version) => void;
}

type Row = Record<string, unknown>;

// Suggestions of reviews before scoring version 3: text only, nothing to take over
const LEGACY_KINDS = ["thesis_text", "thesis_status", "policy_position"] as const;
const FIELDS = [
  "target_pct",
  "buy_threshold_pct",
  "sell_threshold_pct",
  "exit",
  "rationale_md",
] as const;

const text = (value: unknown) => String(value ?? "");

/** A relative threshold or a target, e.g. "+30 %" or "−20 %". */
function signedPct(value: unknown, signed: boolean) {
  const n = Number(value);
  const formatted = formatPct(Math.abs(n), undefined, Number.isInteger(n) ? 0 : 1);
  if (!signed || n === 0) return formatted;
  return `${n > 0 ? "+" : "−"}${formatted}`;
}

function fieldLabel(field: string) {
  return (FIELDS as readonly string[]).includes(field)
    ? i18n.t(`reviews.suggestions.fields.${field as (typeof FIELDS)[number]}`)
    : field;
}

function fieldValue(field: string, value: unknown) {
  if (field === "exit") {
    return value ? i18n.t("reviews.suggestions.exitYes") : i18n.t("reviews.suggestions.exitNo");
  }
  if (field === "rationale_md") return text(value);
  return signedPct(value, field !== "target_pct");
}

function band(row: Row) {
  if (row.type === "cash_buffer") return assetTypeLabel("cash_buffer");
  return i18n.t("reviews.suggestions.band", {
    buy: signedPct(row.buy_threshold_pct, true),
    sell: signedPct(row.sell_threshold_pct, true),
  });
}

/** The heading of a suggestion, e.g. "Thesis · section 7" or "BTC · sell threshold". */
function title(s: Suggestion) {
  const change = (s.change ?? {}) as Row;
  switch (s.kind) {
    case "thesis_section":
      return i18n.t("reviews.suggestions.section", { section: text(change.section) });
    case "position_change":
      return `${text(change.ticker)} · ${fieldLabel(text(change.field))}`;
    case "position_add": {
      const row = (change.position ?? {}) as Row;
      return i18n.t("reviews.suggestions.add", { ticker: text(row.ticker), name: text(row.name) });
    }
    case "position_remove":
      return i18n.t("reviews.suggestions.remove", { ticker: text(change.ticker) });
    default:
      return (LEGACY_KINDS as readonly string[]).includes(s.kind)
        ? i18n.t(`reviews.suggestions.${s.kind as (typeof LEGACY_KINDS)[number]}`)
        : s.kind;
  }
}

/** What the suggestion changes, e.g. "+25 % → +30 %" once its old value is known. */
function ChangeDetail({ s }: { s: Suggestion }) {
  const change = (s.change ?? {}) as Row;
  if (s.kind === "thesis_section") {
    return (
      <div className="rounded-md bg-muted p-2 font-mono text-xs whitespace-pre-wrap">
        {text(change.text)}
      </div>
    );
  }
  if (s.kind === "position_change") {
    const field = text(change.field);
    const previous = s.previous as Row | null;
    if (field === "rationale_md") {
      return (
        <div className="rounded-md bg-muted p-2 text-xs">
          <Markdown source={text(change.value)} />
        </div>
      );
    }
    return (
      <p className="tabular-nums">
        {previous ? `${fieldValue(field, previous.value)} → ` : "→ "}
        {fieldValue(field, change.value)}
      </p>
    );
  }
  if (s.kind === "position_add") {
    const row = (change.position ?? {}) as Row;
    return (
      <p className="tabular-nums">
        {i18n.t("reviews.suggestions.addDetail", {
          type: assetTypeLabel(text(row.type)),
          target: signedPct(row.target_pct, false),
          band: band(row),
        })}
      </p>
    );
  }
  return null;
}

function useAct(review: Review, actions: SuggestionActions | undefined) {
  const mutation = useSuggestionAction(review.id);
  const act = async (action: SuggestionAction, suggestionId: number) => {
    if (!actions) return;
    await actions.save(); // nothing typed in the editor gets lost (POL-14)
    const result = await mutation.mutateAsync({ action, suggestionId });
    actions.onDraft(result.draft);
  };
  return {
    act: (a: SuggestionAction, id: number) => void act(a, id).catch(() => undefined),
    mutation,
  };
}

function StateLine({
  s,
  canAct,
  onUndo,
  pending,
}: {
  s: Suggestion;
  canAct: boolean;
  onUndo: () => void;
  pending: boolean;
}) {
  const { t } = useTranslation();
  if (s.state === "open") return null;
  return (
    <p
      className={
        s.state === "taken_over"
          ? "flex flex-wrap items-center gap-2 font-medium text-green-700 dark:text-green-400"
          : "flex flex-wrap items-center gap-2 text-muted-foreground"
      }
    >
      {s.state === "taken_over"
        ? t("reviews.suggestions.takenOver")
        : t("reviews.suggestions.dismissed")}
      {canAct && (
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto p-0"
          onClick={onUndo}
          disabled={pending}
        >
          {t("reviews.suggestions.undo")}
        </Button>
      )}
    </p>
  );
}

function OpenButtons({
  onTakeOver,
  onDismiss,
  pending,
}: {
  onTakeOver: () => void;
  onDismiss?: () => void;
  pending: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-2">
      <Button type="button" size="sm" onClick={onTakeOver} disabled={pending}>
        {t("reviews.suggestions.takeOver")}
      </Button>
      {onDismiss && (
        <Button type="button" size="sm" variant="outline" onClick={onDismiss} disabled={pending}>
          {t("reviews.suggestions.dismiss")}
        </Button>
      )}
    </div>
  );
}

/** REV-07: suggestions are never applied without a click; in the draft editor they can be
 * taken over, dismissed and undone, elsewhere they are read-only. */
export function Suggestions({ review, actions }: { review: Review; actions?: SuggestionActions }) {
  const { t } = useTranslation();
  const { act, mutation } = useAct(review, actions);
  const editable = !!actions && review.state === "done" && !review.confirmed;
  const suggestions = review.suggestions.filter((s) => s.kind !== "proposal");
  const proposals = review.suggestions.filter((s) => s.kind === "proposal");
  if (review.suggestions.length === 0) return null;
  return (
    <div className="grid gap-4">
      {suggestions.length > 0 && (
        <div className="grid gap-2">
          <h3 className="font-medium">{t("reviews.suggestions.title")}</h3>
          <p className="text-sm text-muted-foreground">{t("reviews.suggestions.note")}</p>
          <ul className="grid gap-2">
            {suggestions.map((s) => {
              const canAct = editable && s.change !== null;
              return (
                <li
                  key={s.id}
                  aria-label={title(s)}
                  className={
                    s.state === "taken_over"
                      ? "grid gap-2 rounded-md border border-green-200 bg-green-50 p-3 text-sm dark:border-green-900 dark:bg-green-950"
                      : "grid gap-2 rounded-md border p-3 text-sm"
                  }
                >
                  {s.change === null ? (
                    <Badge variant="outline" className="justify-self-start">
                      {title(s)}
                    </Badge>
                  ) : (
                    <p>
                      <span className="font-medium">{title(s)}</span>
                    </p>
                  )}
                  <Markdown source={s.content_md} />
                  {s.change !== null && <ChangeDetail s={s} />}
                  {canAct && s.state === "open" && (
                    <OpenButtons
                      pending={mutation.isPending}
                      onTakeOver={() => act("take-over", s.id)}
                      onDismiss={() => act("dismiss", s.id)}
                    />
                  )}
                  <StateLine
                    s={s}
                    canAct={canAct}
                    pending={mutation.isPending}
                    onUndo={() => act("undo", s.id)}
                  />
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {proposals.length > 0 && (
        <div className="grid gap-2">
          <h3 className="font-medium">{t("reviews.suggestions.proposals")}</h3>
          <p className="text-sm text-muted-foreground">{t("reviews.suggestions.proposalsNote")}</p>
          <ul className="grid gap-2">
            {proposals.map((s, i) => (
              <Proposal
                key={s.id}
                s={s}
                letter={String.fromCharCode(65 + i)}
                canAct={editable}
                pending={mutation.isPending}
                onAct={(action) => act(action, s.id)}
              />
            ))}
          </ul>
        </div>
      )}
      <FormError error={mutation.error} />
    </div>
  );
}

/** REV-22: a proposed target structure; taking it over fills the draft's positions. */
function Proposal({
  s,
  letter,
  canAct,
  pending,
  onAct,
}: {
  s: Suggestion;
  letter: string;
  canAct: boolean;
  pending: boolean;
  onAct: (action: SuggestionAction) => void;
}) {
  const { t } = useTranslation();
  const change = (s.change ?? {}) as Row;
  const rows = (change.positions ?? []) as Row[];
  const name = `${letter} · ${text(change.name)}`;
  return (
    <li aria-label={name} className="grid gap-2 rounded-md border p-3 text-sm">
      <p>
        <span className="font-medium">{name}</span>
        {s.content_md && ` · ${s.content_md}`}
      </p>
      <div className="overflow-x-auto">
        <table className="text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th scope="col" className="pr-4 font-medium">
                {t("reviews.suggestions.ticker")}
              </th>
              <th scope="col" className="pr-4 font-medium">
                {t("reviews.suggestions.target")}
              </th>
              <th scope="col" className="font-medium">
                {t("reviews.suggestions.bandHeader")}
              </th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {rows.map((row) => (
              <tr key={text(row.ticker)}>
                <td className="pr-4" title={text(row.name)}>
                  {text(row.ticker)}
                </td>
                <td className="pr-4">{signedPct(row.target_pct, false)}</td>
                <td>{band(row)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canAct && s.state === "open" && (
        <OpenButtons pending={pending} onTakeOver={() => onAct("take-over")} />
      )}
      <StateLine s={s} canAct={canAct} pending={pending} onUndo={() => onAct("undo")} />
    </li>
  );
}
