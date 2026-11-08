import type { MessageCode } from "./index";

// German texts of the backend's investment messages
// (backend/yap/messages/investments.py)
export const de = {
  // Theses
  title_required: "Der Titel darf nicht leer sein",
  thesis_status_unknown: "Unbekannter Status {{status}}",
  // Policies
  name_required: "Der Name darf nicht leer sein",
  policy_name_taken: "Es gibt bereits eine Anlagestrategie namens {{name}}",
  policy_has_no_draft: "Die Anlagestrategie {{name}} hat keinen Entwurf",
  policy_has_draft: "Die Anlagestrategie {{name}} hat bereits einen Entwurf",
  ticker_duplicate: "Der Ticker {{ticker}} kommt mehrfach vor",
  target_range: "Das Ziel muss zwischen 0 und 100 liegen",
  buy_threshold_range: "Die Kaufschwelle muss zwischen -100 und 0 liegen",
  sell_threshold_min: "Die Verkaufsschwelle muss 0 oder mehr sein",
  one_cash_buffer: "Es ist höchstens eine Liquiditätsreserve erlaubt",
  policy_first_version_kept:
    "Die erste Version kann nicht gelöscht werden; sie ist die einzige der Anlagestrategie",
  target_sum:
    "Die Ziele ergeben zusammen {{sum}} %, das weicht um {{difference}} Prozentpunkte von 100 % ab",
  multiple_cash_buffers: "Die Anlagestrategie enthält mehr als eine Liquiditätsreserve",
  change_note_required_v2: "Ab v2 ist eine Änderungsnotiz nötig",
  policy_has_portfolios:
    "Eine Anlagestrategie mit zugewiesenen Portfolios kann nicht archiviert werden",
  policy_archived: "Die Anlagestrategie {{name}} ist archiviert",
  policy_version_not_found: "Version {{id}} der Anlagestrategie nicht gefunden",
  policy_version_no_not_found: "Version {{number}} der Anlagestrategie {{name}} nicht gefunden",
  policy_no_active_version: "Die Anlagestrategie {{name}} hat keine aktive Version",
  policy_not_active_yet: "Die Anlagestrategie {{name}} hat noch keine aktive Version",
  // Portfolios and snapshots
  portfolio_name_taken: "Es gibt bereits ein Portfolio namens {{name}}",
  portfolio_already_follows:
    "Das Portfolio {{portfolio}} folgt bereits der Anlagestrategie {{policy}}",
  contribution_min: "Die Einzahlung muss 0 oder mehr sein",
  value_min: "Der Wert muss 0 oder mehr sein",
  units_min: "Die Anzahl muss 0 oder mehr sein",
  price_min: "Der Preis muss 0 oder mehr sein",
  units_required: "Gib die Anzahl von {{ticker}} ein",
  price_required: "Gib den Preis oder den Wert von {{ticker}} ein; es gibt keinen früheren Preis",
  value_without_units: "Eine Position mit Anzahl 0 hat den Wert 0",
  portfolio_currency_locked:
    "Die Währung kann nicht mehr geändert werden, sobald das Portfolio Stände hat",
  position_units_or_value: "Eine Position braucht ihre Anzahl oder ihren Wert",
  snapshot_not_found: "Stand {{id}} nicht gefunden",
  // Rebalancing inputs
  withdrawal_min: "Die Entnahme muss 0 oder mehr sein",
  withdrawal_too_large:
    "Die Entnahme darf den Wert des Portfolios plus die Einzahlung nicht übersteigen ({{maximum}})",
  // Asset catalog
  ticker_required: "Der Ticker darf nicht leer sein",
  ticker_unknown_add: "Unbekannter Ticker {{ticker}}: Um ihn hinzuzufügen, sind Name und Typ nötig",
  asset_type_unknown: "Unbekannter Anlagetyp {{type}}",
  // Import
  schema_not_found: "Kein Schema für {{type}}",
  invalid_json: "Ungültiges JSON: {{message}} (Zeile {{line}}, Spalte {{column}})",
  schema_version_unsupported:
    "Schema-Version {{version}} wird nicht unterstützt; diese App liest Version {{major}}.x",
  schema_error: "{{detail}}",
  import_ticker_unknown: "Unbekannter Ticker {{ticker}}: Name und Typ sind nötig",
  asset_type_mismatch:
    "{{ticker}} ist im Anlagekatalog bereits als {{catalog_type}} erfasst, nicht als {{type}}",
  import_target_sum: "Die Ziele ergeben zusammen {{sum}} %, das weicht von 100 % ab",
} satisfies Partial<Record<MessageCode, string>>;
