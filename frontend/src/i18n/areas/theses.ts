import type { Messages } from "../messages";

// The thesis of a policy draft: its fields in the policy editor (features/policies).
export const en = {
  editor: {
    title: "Title",
  },
};

// German in Swiss spelling (ss, no ß), addressing the user with "du"; see src/i18n/README.md
export const de: Messages<typeof en> = {
  editor: {
    title: "Titel",
  },
};
