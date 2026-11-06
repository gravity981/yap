import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

/** NFR-15: the app manages the investor's own strategy and gives no advice. */
export function NotAdvice({ className, short }: { className?: string; short?: string }) {
  const { t } = useTranslation();
  return (
    <p
      role="note"
      aria-label={t("notAdvice.label")}
      className={cn("text-xs text-muted-foreground", className)}
    >
      {short ?? t("notAdvice.long")}
    </p>
  );
}

export const REPOSITORY = "https://github.com/gravity981/yap";

/** NFR-16: source code of exactly the running build (AGPL), or the repository. */
export function sourceUrl(commit: string | undefined) {
  return commit && /^[0-9a-f]{7,40}$/.test(commit) ? `${REPOSITORY}/tree/${commit}` : REPOSITORY;
}
