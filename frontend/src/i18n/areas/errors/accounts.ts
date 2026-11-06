import type { MessageCode } from "./index";

// German texts of the backend's accounts messages (backend/yap/messages/accounts.py)
export const de = {
  login_locked: "Zu viele fehlgeschlagene Anmeldungen; versuche es nach {{until}} wieder",
  login_invalid: "Benutzername oder Passwort ist falsch",
  session_expired: "Die Sitzung ist abgelaufen",
  password_too_short: "Passwörter brauchen mindestens {{min}} Zeichen",
  password_wrong: "Das aktuelle Passwort ist falsch",
  password_unchanged: "Das neue Passwort muss sich vom aktuellen unterscheiden",
  language_unknown: "Unbekannte Sprache {{language}}; wähle eine von {{languages}}",
  time_zone_unknown: "Unbekannte Zeitzone {{time_zone}}",
  currency_invalid: "Die Währung muss ein dreistelliger ISO-4217-Code sein",
  username_empty: "Der Benutzername darf nicht leer sein",
  username_reserved: "Benutzernamen dürfen nicht mit «deleted-» beginnen",
  username_taken: "Der Benutzername {{username}} ist bereits vergeben",
  roles_required: "Ein Konto braucht mindestens eine Rolle",
  base_currency_required: "Investoren brauchen eine Basiswährung",
  last_admin_keeps_role: "Der letzte aktive Admin behält die Admin-Rolle",
  investor_role_in_use:
    "Die Investor-Rolle kann nicht entfernt werden, solange das Konto Anlagethesen, Anlagestrategien oder Portfolios besitzt",
  account_not_found: "Konto {{id}} nicht gefunden",
  own_account_status: "Admins können den Status ihres eigenen Kontos nicht ändern",
  base_currency_investors_only: "Nur Investoren haben eine Basiswährung",
  ai_reviewer_not_found: "KI-Reviewer {{id}} nicht gefunden",
  ai_reviewer_name_required: "Ein Name ist erforderlich",
  ai_reviewer_name_taken: "Es gibt bereits einen KI-Reviewer mit dem Namen {{name}}",
  provider_unknown: "Unbekannter Anbieter {{provider}}",
  model_required: "Ein Modell ist erforderlich",
  limit_negative: "Das Limit muss 0 oder mehr sein",
  api_key_required: "Ein API-Schlüssel ist erforderlich",
  api_key_no_secret:
    "APP_SECRET_KEY ist nicht gesetzt, daher können keine Schlüssel gespeichert werden",
  ai_reviewer_disabled: "Der KI-Reviewer {{name}} ist deaktiviert",
  connection_ok: "Verbunden mit {{provider}}, Modell {{model}}",
  test_failed_unexpectedly: "Der Test ist unerwartet fehlgeschlagen ({{detail}})",
  secret_missing:
    "APP_SECRET_KEY ist auf dem Server nicht gesetzt; API-Schlüssel können nicht verwendet werden",
  secret_cannot_decrypt:
    "Der gespeicherte API-Schlüssel kann nicht entschlüsselt werden (APP_SECRET_KEY geändert?); gib ihn erneut ein",
} satisfies Partial<Record<MessageCode, string>>;
