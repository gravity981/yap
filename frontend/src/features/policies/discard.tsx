import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

import { usePolicyActions } from "./api";

/** POL-16: discards the draft after a confirmation. The policy is back to its active
 * version; a policy that was never activated is deleted with its draft. */
export function DiscardDraft({
  policyId,
  neverActivated,
  onDiscarded,
}: {
  policyId: number;
  neverActivated: boolean;
  onDiscarded?: () => void;
}) {
  const { t } = useTranslation();
  const { deleteDraft } = usePolicyActions(policyId);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const discard = () =>
    deleteDraft.mutate(undefined, {
      onSuccess: (result) => {
        setOpen(false);
        onDiscarded?.();
        if (result.policy_deleted) void navigate({ to: "/policies" });
        else void navigate({ to: "/policies/$policyId", params: { policyId: String(policyId) } });
      },
    });
  return (
    <>
      <Button
        type="button"
        variant="outline"
        className="border-destructive/40 text-destructive"
        onClick={() => setOpen(true)}
      >
        {t("policies.discard.button")}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogTitle>{t("policies.discard.title")}</DialogTitle>
          <DialogDescription>
            {neverActivated
              ? t("policies.discard.deletesPolicy")
              : t("policies.discard.backToActive")}
          </DialogDescription>
          <FormError error={deleteDraft.error} />
          <div className="mt-4 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={discard}
              disabled={deleteDraft.isPending}
            >
              {t("policies.discard.confirm")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
