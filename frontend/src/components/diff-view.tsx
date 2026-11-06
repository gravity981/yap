import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

/** A unified diff with added and removed lines highlighted (THS-02). */
export function DiffView({ diff }: { diff: string }) {
  const { t } = useTranslation();
  if (!diff.trim())
    return <p className="text-sm text-muted-foreground">{t("components.diff.none")}</p>;
  return (
    <pre
      className="overflow-x-auto rounded-md border p-3 text-xs leading-5"
      aria-label={t("components.diff.label")}
    >
      {diff.split("\n").map((line, i) => (
        <div
          key={i}
          className={cn(
            line.startsWith("+") && !line.startsWith("+++") && "bg-success/15",
            line.startsWith("-") && !line.startsWith("---") && "bg-destructive/15",
            line.startsWith("@@") && "text-muted-foreground",
          )}
        >
          {line || " "}
        </div>
      ))}
    </pre>
  );
}
