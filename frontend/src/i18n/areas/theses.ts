import type { Messages } from "../messages";

// The thesis of a policy draft: its fields in the policy editor (features/policies).
export const en = {
  editor: {
    title: "Title",
    status: "Status",
    statusHint:
      "A thesis that needs adaptation or is broken does not change any rebalancing by itself; its policy and portfolios show a warning. Adapt the thesis, or set exit flags to leave positions.",
  },
};

// German in Swiss spelling (ss, no ß), addressing the user with "du"; see src/i18n/README.md
export const de: Messages<typeof en> = {
  editor: {
    title: "Titel",
    status: "Status",
    statusHint:
      "Eine Anlagethese, die angepasst werden muss oder gebrochen ist, ändert für sich allein kein Rebalancing; ihre Anlagestrategie und Portfolios zeigen eine Warnung. Passe die Anlagethese an oder setze Exit-Markierungen, um Positionen aufzulösen.",
  },
};
