import type { Messages } from "../messages";

// Price sources and lookup (PRC-02 to PRC-06)
export const en = {
  stale: "Price from {{date}}, more than 3 days old",
  auto: {
    same: "auto: {{symbol}} {{price}} {{currency}} on {{date}}",
    converted: "auto: {{symbol}} {{price}} {{currency}} × {{rate}} → {{target}}, on {{date}}",
    changed: "Changed by hand: saved as a manual price.",
    useAuto: "Use the auto price again",
  },
  notice: {
    noPrice: "{{symbol}} has no price yet; the next update fetches it. Enter the price for now.",
    noRate: "There is no exchange rate for {{symbol}} yet. Enter the price for now.",
    unavailable:
      "{{symbol}} is no longer available, so prices are entered by hand. You can try auto in your settings.",
  },
  source: {
    none: "not looked up yet",
    manual: "manual",
    unresolved: "unresolved",
    retired: "manual: {{symbol}} no longer available",
  },
  control: {
    label: "Price source of {{ticker}}",
    source: "Prices:",
    lookingUp: "looking up …",
    tryAuto: "Try auto",
    another: "Choose another listing",
    choose: "Listing for {{ticker}}",
    manual: "Enter prices manually",
    use: "Use",
  },
  import: {
    title: "Price sources of the file's tickers",
  },
  settings: {
    title: "Price sources",
    description:
      "Where the prices of your assets come from: a listing of a price provider, updated regularly, or prices you enter yourself. A change applies to new snapshots only; earlier ones keep their prices.",
    none: "No assets yet.",
    asset: "Asset",
    source: "Price source",
    price: "Latest price",
    updated: "Updated",
    change: "Change the price source of {{ticker}}",
  },
};

export const de: Messages<typeof en> = {
  stale: "Preis vom {{date}}, älter als 3 Tage",
  auto: {
    same: "automatisch: {{symbol}} {{price}} {{currency}} am {{date}}",
    converted:
      "automatisch: {{symbol}} {{price}} {{currency}} × {{rate}} → {{target}}, am {{date}}",
    changed: "Von Hand geändert: wird als manueller Preis gespeichert.",
    useAuto: "Automatischen Preis wieder verwenden",
  },
  notice: {
    noPrice:
      "{{symbol}} hat noch keinen Preis; die nächste Aktualisierung holt ihn. Gib den Preis vorerst selbst ein.",
    noRate: "Für {{symbol}} gibt es noch keinen Wechselkurs. Gib den Preis vorerst selbst ein.",
    unavailable:
      "{{symbol}} ist nicht mehr verfügbar, daher werden die Preise von Hand erfasst. In deinen Einstellungen kannst du es automatisch versuchen.",
  },
  source: {
    none: "noch nicht gesucht",
    manual: "manuell",
    unresolved: "ungeklärt",
    retired: "manuell: {{symbol}} nicht mehr verfügbar",
  },
  control: {
    label: "Preisquelle von {{ticker}}",
    source: "Preise:",
    lookingUp: "wird gesucht …",
    tryAuto: "Automatisch versuchen",
    another: "Anderes Listing wählen",
    choose: "Listing für {{ticker}}",
    manual: "Preise manuell erfassen",
    use: "Übernehmen",
  },
  import: {
    title: "Preisquellen der Ticker in der Datei",
  },
  settings: {
    title: "Preisquellen",
    description:
      "Woher die Preise deiner Anlagen kommen: ein Listing eines Preisanbieters, regelmässig aktualisiert, oder Preise, die du selbst erfasst. Eine Änderung gilt nur für neue Stände; frühere behalten ihre Preise.",
    none: "Noch keine Anlagen.",
    asset: "Anlage",
    source: "Preisquelle",
    price: "Letzter Preis",
    updated: "Aktualisiert",
    change: "Preisquelle von {{ticker}} ändern",
  },
};
