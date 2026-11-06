import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

/** JSON import: choose a file, show the preview (IMP-07), then import. Errors are
 * listed with their JSON path (IMP-06); nothing is stored before confirming.
 * `onDone` receives the import result, to show what was imported. */
export function FileImport<P, R>({
  title,
  description,
  preview,
  run,
  renderPreview,
  onClose,
  onDone,
}: {
  title: string;
  description: string;
  preview: (text: string) => Promise<P>;
  run: (text: string) => Promise<R>;
  renderPreview: (preview: P) => ReactNode;
  onClose: () => void;
  onDone: (result: R) => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState<string | null>(null);
  const [result, setResult] = useState<P | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const choose = async (file: File | undefined) => {
    setResult(null);
    setError(null);
    if (!file) return;
    const content = await file.text();
    setText(content);
    setBusy(true);
    try {
      setResult(await preview(content));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (text === null) return;
    setBusy(true);
    try {
      onDone(await run(text));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
        <div className="mt-4 grid gap-4">
          <Input
            type="file"
            accept="application/json,.json"
            aria-label={t("components.fileImport.file")}
            onChange={(e) => choose(e.target.files?.[0])}
          />
          {error instanceof ApiError && error.problems.length > 0 ? (
            <Alert variant="destructive">
              <p className="font-medium">{t("components.fileImport.cannotImport")}</p>
              <ul className="mt-1 list-disc pl-5">
                {error.problems.map((p) => (
                  <li key={p.path + p.message}>
                    <code>{p.path}</code>: {p.message}
                  </li>
                ))}
              </ul>
            </Alert>
          ) : error ? (
            <Alert variant="destructive">
              {error instanceof ApiError ? error.message : t("components.fileImport.failed")}
            </Alert>
          ) : null}
          {result !== null && <div className="max-h-96 overflow-auto">{renderPreview(result)}</div>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button onClick={confirm} disabled={busy || result === null}>
              {t("components.fileImport.import")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
