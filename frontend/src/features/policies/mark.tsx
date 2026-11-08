import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";

const MARKS = ["not_reviewed", "review_did_not_match"] as const;

/** REV-20: a version activated without a review, or with one that no longer matched. */
export function MarkBadge({ mark }: { mark: string | null | undefined }) {
  const { t } = useTranslation();
  if (!mark) return null;
  const label = (MARKS as readonly string[]).includes(mark)
    ? t(`policies.marks.${mark as (typeof MARKS)[number]}`)
    : mark;
  const hint = (MARKS as readonly string[]).includes(mark)
    ? t(`policies.marks.hint.${mark as (typeof MARKS)[number]}`)
    : undefined;
  return (
    <Badge variant="warning" title={hint}>
      {label}
    </Badge>
  );
}
