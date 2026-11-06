import type { MessageCode } from "./index";

// German texts of the backend's price provider messages (backend/yap/messages/prices.py)
export const de = {
  price_provider_unreachable: "{{provider}} ist nicht erreichbar ({{detail}})",
  price_provider_auth: "{{provider}} hat den API-Schlüssel abgelehnt",
  price_provider_quota: "Das Abfragelimit von {{provider}} ist für heute erreicht",
  price_provider_status: "{{provider}} hat mit Status {{status}} geantwortet",
  price_provider_unexpected:
    "{{provider}} hat eine Antwort gesendet, die nicht gelesen werden kann",
  price_not_found: "{{provider}} hat keinen Preis für {{symbol}}",
  price_connection_ok: "Verbindung zu {{provider}} hergestellt",
  price_provider_not_found: "Preisanbieter {{id}} nicht gefunden",
  price_provider_unknown: "Unbekannter Preisanbieter {{provider}}",
  price_provider_exists: "{{provider}} wurde bereits hinzugefügt",
  price_provider_built_in: "Die eingebaute Wechselkursquelle kann nicht geändert werden",
  price_no_provider: "Kein Preisanbieter ist aktiviert; frag den Admin",
  price_source_kind_unknown: "Unbekannte Preisquelle {{kind}}",
  price_listing_unavailable: "Listing {{id}} ist nicht verfügbar",
  time_of_day_invalid: "Gib die Uhrzeit als HH:MM ein",
  interval_invalid: "Das Intervall muss eine dieser Stundenzahlen sein: {{intervals}}",
} satisfies Partial<Record<MessageCode, string>>;
