import type { Messages } from "../messages";

// Timeline (features/timeline).
export const en = {
  title: "Timeline",
  description:
    "The history of your decisions: thesis revisions, policy activations, policy changes of portfolios and confirmed rebalances.",
  filter: {
    label: "Filters",
    portfolio: "Portfolio",
    policy: "Policy",
    all: "all",
    from: "From",
    to: "To",
    types: "Event types",
  },
  types: {
    policy_activated: "Policy activated",
    portfolio_assigned: "Portfolio assigned",
    rebalance_confirmed: "Rebalance confirmed",
    thesis_review_confirmed: "Thesis review",
    policy_review_confirmed: "Policy review",
    review_confirmed: "Review",
    review_saved: "Review again",
    thesis_revised: "Thesis revised",
  },
  noEvents: "No events.",
  noDetails: "No further details.",
  firstVersion: "First version of the policy.",
  portfolio: "Portfolio",
  follows: " follows ",
  calculated: "(calculated {{amount}})",
  openRebalance: "Open rebalance",
  revision: "revision {{no}} ({{status}})",
  // The entries, written from their stored values; the English ones are the backend's
  summary: {
    policyActivated: "{{version}} activated ({{portfolios}})",
    policyActivatedNote: "{{version}} activated ({{portfolios}}): {{note}}",
    noPortfolios: "no portfolios",
    portfolioCreated: "Portfolio {{portfolio}} created with policy {{policy}} ({{version}})",
    portfolioReassigned: "Portfolio {{portfolio}} reassigned to policy {{policy}} ({{version}})",
    rebalance: "{{portfolio}}: rebalanced, sold {{sold}}, bought {{bought}}",
    rebalanceWithdrawal:
      "{{portfolio}}: rebalanced, sold {{sold}}, bought {{bought}}, withdrew {{withdrawal}}",
    soldCompletely: "{{portfolio}}: sold completely, thesis broken",
    soldCompletelyWithdrawal:
      "{{portfolio}}: sold completely, thesis broken, withdrew {{withdrawal}}",
    thesisReview: "Thesis review of '{{title}}' revision {{revision}}: {{result}}",
    thesisReviewOfVersion: "Thesis review of {{version}}: {{result}}",
    policyReview: "Policy review of {{version}}: {{result}}",
    review: "Review of {{version}}: {{result}}",
    reviewAgain: "Review of {{version}} (again): {{result}}",
    score: "{{total}} / 10",
    modified: "modified",
    thesisRevised:
      "Thesis '{{title}}' has a new revision {{revision}} (policy {{version}} uses revision {{used}})",
  },
};

// German in Swiss spelling (ss, no ß), addressing the user with "du"; see src/i18n/README.md
export const de: Messages<typeof en> = {
  title: "Verlauf",
  description:
    "Der Verlauf deiner Entscheidungen: Revisionen von Anlagethesen, aktivierte Anlagestrategien, Wechsel der Anlagestrategie von Portfolios und bestätigte Rebalancings.",
  filter: {
    label: "Filter",
    portfolio: "Portfolio",
    policy: "Anlagestrategie",
    all: "alle",
    from: "Von",
    to: "Bis",
    types: "Ereignistypen",
  },
  types: {
    policy_activated: "Anlagestrategie aktiviert",
    portfolio_assigned: "Portfolio zugewiesen",
    rebalance_confirmed: "Rebalancing bestätigt",
    thesis_review_confirmed: "Prüfung der Anlagethese",
    policy_review_confirmed: "Prüfung der Anlagestrategie",
    review_confirmed: "Prüfung",
    review_saved: "Erneute Prüfung",
    thesis_revised: "Anlagethese überarbeitet",
  },
  noEvents: "Keine Ereignisse.",
  noDetails: "Keine weiteren Details.",
  firstVersion: "Erste Version der Anlagestrategie.",
  portfolio: "Portfolio",
  follows: " folgt ",
  calculated: "(berechnet {{amount}})",
  openRebalance: "Rebalancing öffnen",
  revision: "Revision {{no}} ({{status}})",
  summary: {
    policyActivated: "{{version}} aktiviert ({{portfolios}})",
    policyActivatedNote: "{{version}} aktiviert ({{portfolios}}): {{note}}",
    noPortfolios: "keine Portfolios",
    portfolioCreated:
      "Portfolio {{portfolio}} mit der Anlagestrategie {{policy}} ({{version}}) erstellt",
    portfolioReassigned:
      "Portfolio {{portfolio}} der Anlagestrategie {{policy}} ({{version}}) zugewiesen",
    rebalance: "{{portfolio}}: Rebalancing, verkauft {{sold}}, gekauft {{bought}}",
    rebalanceWithdrawal:
      "{{portfolio}}: Rebalancing, verkauft {{sold}}, gekauft {{bought}}, entnommen {{withdrawal}}",
    soldCompletely: "{{portfolio}}: vollständig verkauft, Anlagethese gebrochen",
    soldCompletelyWithdrawal:
      "{{portfolio}}: vollständig verkauft, Anlagethese gebrochen, entnommen {{withdrawal}}",
    thesisReview: "Prüfung der Anlagethese «{{title}}» Revision {{revision}}: {{result}}",
    thesisReviewOfVersion: "Prüfung der Anlagethese von {{version}}: {{result}}",
    policyReview: "Prüfung der Anlagestrategie {{version}}: {{result}}",
    review: "Prüfung von {{version}}: {{result}}",
    reviewAgain: "Prüfung von {{version}} (erneut): {{result}}",
    score: "{{total}} / 10",
    modified: "geändert",
    thesisRevised:
      "Anlagethese «{{title}}» hat eine neue Revision {{revision}} (Anlagestrategie {{version}} verwendet Revision {{used}})",
  },
};
