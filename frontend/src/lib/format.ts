// Number and date formatting in the locale of the UI language (NFR-10): de-CH for German,
// the browser's own for English. The backend sends decimals as strings and timestamps in
// UTC (NFR-04, NFR-14); they are shown in the account's time zone (USR-11).

import { currentLocale } from "@/i18n";

type Amount = string | number;

let accountTimeZone: string | undefined;

/** USR-11: the account's time zone; null or undefined follows the browser. */
export function applyTimeZone(timeZone: string | null | undefined): void {
  accountTimeZone = timeZone ?? undefined;
}

/** The time zone dates are shown in; undefined means the browser's. */
export function currentTimeZone(): string | undefined {
  return accountTimeZone;
}

/** The browser's own time zone, e.g. Europe/Zurich. */
export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** Every time zone the browser knows, for the settings (USR-11). */
export function timeZones(): string[] {
  return Intl.supportedValuesOf("timeZone");
}

/** Amounts rounded to whole units unless precise amounts are on (RB-15). */
export function formatAmount(value: Amount, precise = false, locale?: string): string {
  const digits = precise ? 2 : 0;
  return new Intl.NumberFormat(locale ?? currentLocale(), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

/** Decimal text from the API as Intl reads it: the string itself, never via a float, so
 * every digit is kept (NFR-04); 123456789.123456789012345678 has more digits than a
 * JavaScript number. */
type Exact = `${number}`;
const exact = (value: Amount): Exact => String(value) as Exact;

/** Units with every decimal up to 18, like ETH; whole numbers without decimals (CMP-05). */
export function formatUnits(value: Amount, locale?: string): string {
  return new Intl.NumberFormat(locale ?? currentLocale(), { maximumFractionDigits: 18 }).format(
    exact(value),
  );
}

/** A price per unit: 2 to 4 decimals, and up to 10 below 1 (small crypto prices). */
export function formatPrice(value: Amount, locale?: string): string {
  return new Intl.NumberFormat(locale ?? currentLocale(), {
    minimumFractionDigits: 2,
    maximumFractionDigits: Math.abs(Number(value)) < 1 ? 10 : 4,
  }).format(exact(value));
}

/** A percentage; the non-breaking space keeps the "%" on the line of its number. */
export function formatPct(value: Amount, locale?: string, digits = 1): string {
  return `${new Intl.NumberFormat(locale ?? currentLocale(), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value))}\u00a0%`;
}

/** UTC timestamp from the API, shown in the user's time zone (NFR-14). */
export function formatDateTime(
  utc: string,
  locale?: string,
  timeZone: string | undefined = currentTimeZone(),
): string {
  return new Intl.DateTimeFormat(locale ?? currentLocale(), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(new Date(utc));
}

export function formatDate(
  utc: string,
  locale?: string,
  timeZone: string | undefined = currentTimeZone(),
): string {
  return new Intl.DateTimeFormat(locale ?? currentLocale(), {
    dateStyle: "medium",
    timeZone,
  }).format(new Date(utc));
}
