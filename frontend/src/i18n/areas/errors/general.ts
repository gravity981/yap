import type { MessageCode } from "./index";

// German texts of the backend's general messages (backend/yap/messages/general.py)
export const de = {
  not_logged_in: "Nicht angemeldet",
  password_change_required: "Zuerst muss das Passwort geändert werden",
  admins_only: "Nur Admins können Konten verwalten",
  investors_only: "Nur aktive Investoren haben Zugriff auf Anlagedaten",
  invalid_input: "Die Eingabe ist ungültig",
  policy_not_found: "Anlagestrategie {{id}} nicht gefunden",
  portfolio_not_found: "Portfolio {{id}} nicht gefunden",
} satisfies Partial<Record<MessageCode, string>>;
