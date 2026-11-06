import { useTranslation } from "react-i18next";

import { PriceSourceControl } from "./price-source";

export interface FilePosition {
  ticker: string;
  name?: string;
  type?: string;
}

const CASH_BUFFER = "cash_buffer";

/** The positions of an import file, read for the preview; the server checks the file. */
export function filePositions(text: string): FilePosition[] {
  try {
    const data: unknown = JSON.parse(text);
    const positions = (data as { positions?: unknown }).positions;
    if (!Array.isArray(positions)) return [];
    return positions.flatMap((p: unknown) => {
      const { ticker, name, type } = (p ?? {}) as Record<string, unknown>;
      return typeof ticker === "string" && ticker.trim()
        ? [
            {
              ticker,
              name: typeof name === "string" ? name : undefined,
              type: typeof type === "string" ? type : undefined,
            },
          ]
        : [];
    });
  } catch {
    return [];
  }
}

/** IMP-07, PRC-02: the price source of each ticker of the file, looked up for the preview. */
export function ImportPriceSources({ positions }: { positions: FilePosition[] }) {
  const { t } = useTranslation();
  const priced = positions.filter((p) => p.type !== CASH_BUFFER);
  if (priced.length === 0) return null;
  return (
    <section className="grid gap-2" aria-label={t("prices.import.title")}>
      <p className="text-sm font-medium">{t("prices.import.title")}</p>
      {priced.map((p) => (
        <div key={p.ticker} className="grid gap-0.5">
          <span className="text-sm">{p.ticker.trim().toUpperCase()}</span>
          <PriceSourceControl ticker={p.ticker} name={p.name} type={p.type} />
        </div>
      ))}
    </section>
  );
}
