import { currentLanguage, type Language } from "@/i18n";

/** THS-07: structure of a new thesis, in the account's language. Plain markdown, so it can
 * be copied into other tools and back; its sections match the review aspects T1–T5. */
export const THESIS_TEMPLATES: Record<Language, string> = {
  en: `# Investment Thesis

## 1. Belief — What do I think?
Describe the investment idea in 2–5 sentences. What do I believe, and why is this opportunity attractive?

## 2. Investor Fit — Is this appropriate for me?
- **Investor type:** Conservative / Balanced / Growth / Aggressive
- **Investment horizon:** Short-term / Medium-term / Long-term
- **Risk tolerance:** Low / Moderate / High
- **Risk capacity:** Low / Moderate / High
- **Liquidity needs:** Low / Moderate / High

## 3. Implementation — Which assets express my thesis?
List the selected assets and explain why they are suitable for expressing the investment thesis.

- **Asset name (TICKER):**
- **Role in portfolio:**
- **Selection rationale:**

## 4. Opportunity — What creates value?
Describe the factors that could create value and generate investment returns.

- Value driver 1:
- Value driver 2:

## 5. Downside — What can go wrong?
Identify the risks that could negatively affect the investment thesis.

- Risk 1:
- Risk 2:

## 6. Invalidation — When am I wrong?
Define the conditions that invalidate the investment thesis.

When one of these conditions is met, mark the thesis as *broken* and/or set exit flags in the policy.

- Break condition 1:
- Break condition 2:

## 7. Early Warnings — What should make me reconsider?
Identify signals that weaken the thesis and require attention or adaptation. They trigger nothing by themselves.

- Warning signal 1:
- Warning signal 2:

## 8. Monitoring — Is the thesis still valid?
Define the metrics and signals to monitor to assess whether the thesis remains valid.

- Metric / signal 1:
- Metric / signal 2:
- **Review frequency:**
`,
  de: `# Anlagethese

## 1. Überzeugung — Was denke ich?
Beschreibe die Anlageidee in 2–5 Sätzen. Was glaube ich, und warum ist diese Gelegenheit attraktiv?

## 2. Eignung — Passt das zu mir?
- **Anlegertyp:** Konservativ / Ausgewogen / Wachstum / Offensiv
- **Anlagehorizont:** Kurzfristig / Mittelfristig / Langfristig
- **Risikobereitschaft:** Tief / Mittel / Hoch
- **Risikofähigkeit:** Tief / Mittel / Hoch
- **Liquiditätsbedarf:** Tief / Mittel / Hoch

## 3. Umsetzung — Mit welchen Anlagen setze ich die These um?
Liste die gewählten Anlagen auf und erkläre, warum sie die Anlagethese gut umsetzen.

- **Name der Anlage (TICKER):**
- **Rolle im Portfolio:**
- **Begründung der Auswahl:**

## 4. Chancen — Was schafft Wert?
Beschreibe die Faktoren, die Wert schaffen und Rendite bringen könnten.

- Werttreiber 1:
- Werttreiber 2:

## 5. Risiken — Was kann schiefgehen?
Nenne die Risiken, die der Anlagethese schaden könnten.

- Risiko 1:
- Risiko 2:

## 6. Widerlegung — Wann liege ich falsch?
Lege die Bedingungen fest, die die Anlagethese widerlegen.

Tritt eine dieser Bedingungen ein, setze die Anlagethese auf *gebrochen* und/oder setze in der Anlagestrategie Exit-Markierungen.

- Bruchbedingung 1:
- Bruchbedingung 2:

## 7. Frühwarnungen — Was sollte mich zum Überdenken bringen?
Nenne Signale, die die Anlagethese schwächen und Aufmerksamkeit oder eine Anpassung verlangen. Sie lösen für sich allein nichts aus.

- Warnsignal 1:
- Warnsignal 2:

## 8. Überwachung — Gilt die These noch?
Lege die Kennzahlen und Signale fest, mit denen du prüfst, ob die Anlagethese noch gilt.

- Kennzahl / Signal 1:
- Kennzahl / Signal 2:
- **Prüfrhythmus:**
`,
};

/** The template in the current UI language (USR-10). */
export function thesisTemplate(): string {
  return THESIS_TEMPLATES[currentLanguage()];
}
