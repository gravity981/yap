import i18n from "i18next";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";

export const THESIS_STATUSES = ["intact", "needs_adaptation", "broken"] as const;
type ThesisStatus = (typeof THESIS_STATUSES)[number];

function isStatus(status: string): status is ThesisStatus {
  return (THESIS_STATUSES as readonly string[]).includes(status);
}

/** THS-04: intact, needs adaptation or broken. */
export function ThesisStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const label = isStatus(status) ? t(`domain.thesisStatus.${status}`) : status;
  if (status === "broken") return <Badge variant="destructive">{label}</Badge>;
  if (status === "needs_adaptation") return <Badge variant="warning">{label}</Badge>;
  return <Badge variant="success">{label}</Badge>;
}

/** The status in the current language; also for thesis verdicts of reviews (REV-03). */
export function statusLabel(status: string) {
  return isStatus(status) ? i18n.t(`domain.thesisStatus.${status}`) : status;
}
