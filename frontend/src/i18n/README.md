# UI texts (NFR-10)

English and German. App-wide texts are in `en.ts` / `de.ts`, the texts of a feature in
`areas/<area>.ts` (English and German next to each other). The German type is derived from
the English texts, so a missing or extra key fails `tsc`; `i18n.test.ts` also checks the
placeholders. Components get their texts with `useTranslation()` and `t("area.key")`;
the lint rule `i18next/no-literal-string` refuses texts written into JSX.

Messages from the backend come with a code (`backend/yap/messages/`, one
catalog per group). `npm run gen:api` exports the English templates to
`src/api/messages.json`; the German texts are in `areas/errors/<group>.ts`, and `tsc` fails
if a code has none. `unwrap` in `src/api/client.ts` translates every error when it arrives.

Timeline entries are stored with their values (`params`); `features/timeline/summary.ts`
writes the sentence in the UI language, with the backend's English as the model.

Not translated: texts written by users (theses, notes, names), AI review texts, the thesis
template, product and provider names, tickers.

## German

- Swiss spelling: _ss_, never _ß_. Numbers and dates come from `lib/format` (de-CH).
- The user is addressed with _du_.
- Keep the English structure of a sentence only where German reads naturally.

| English                            | German                                                                |
| ---------------------------------- | --------------------------------------------------------------------- |
| Dashboard                          | Übersicht                                                             |
| thesis, theses                     | Anlagethese, Anlagethesen                                             |
| policy, policies                   | Anlagestrategie, Anlagestrategien                                     |
| policy version                     | Version der Anlagestrategie                                           |
| target structure                   | Zielstruktur                                                          |
| position                           | Position                                                              |
| target                             | Ziel                                                                  |
| band, buy below / sell above       | Band, Kaufen unter / Verkaufen über (Kaufschwelle / Verkaufsschwelle) |
| midband                            | Mittelband                                                            |
| exit flag                          | Exit-Markierung                                                       |
| cash buffer                        | Liquiditätsreserve                                                    |
| portfolio, snapshot (values)       | Portfolio, Werte (Stand)                                              |
| rebalancing, rebalance             | Rebalancing                                                           |
| contribution, withdrawal           | Einzahlung, Entnahme                                                  |
| units, price, value                | Anzahl, Preis, Wert                                                   |
| whole units only                   | nur ganze Stücke                                                      |
| currency, base currency            | Währung, Basiswährung                                                 |
| time zone                          | Zeitzone                                                              |
| broker                             | Broker                                                                |
| timeline                           | Verlauf                                                               |
| draft, activate, revision          | Entwurf, aktivieren, Revision                                         |
| change note                        | Änderungsnotiz                                                        |
| review (AI)                        | Prüfung                                                               |
| AI reviewer                        | KI-Reviewer                                                           |
| aspect, score, verdict             | Aspekt, Bewertung, Urteil                                             |
| intact / needs adaptation / broken | intakt / Anpassung nötig / gebrochen                                  |
| shared / private                   | geteilt / privat                                                      |
| account, admin, investor           | Konto, Admin, Investor                                                |
| import, export                     | importieren, exportieren                                              |
