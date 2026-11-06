import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import { PageTitle } from "@/components/page-title";
import { FileImport } from "@/components/file-import";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate } from "@/lib/format";

import { thesesKey, thesisImport, useTheses } from "./api";
import { statusLabel, ThesisStatusBadge } from "./status";

/** Own and shared theses (THS-05). */
/** The visibility of a thesis in the current language. */
export function useVisibilityLabel() {
  const { t } = useTranslation();
  return (visibility: string) =>
    visibility === "private" || visibility === "shared"
      ? t(`theses.visibility.${visibility}`)
      : visibility;
}

export function ThesesPage() {
  const { t } = useTranslation();
  const visibilityLabel = useVisibilityLabel();
  const theses = useTheses();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [importing, setImporting] = useState(false);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <PageTitle title={t("theses.list.title")} description={t("theses.list.description")} />
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setImporting(true)}>
            {t("theses.list.import")}
          </Button>
          <Button asChild>
            <Link to="/theses/new">{t("theses.list.new")}</Link>
          </Button>
        </div>
      </div>
      <FormError error={theses.error} />
      {theses.data?.length === 0 && (
        <p className="text-muted-foreground">{t("theses.list.empty")}</p>
      )}
      {theses.data && theses.data.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("theses.list.columnTitle")}</TableHead>
              <TableHead>{t("theses.list.columnStatus")}</TableHead>
              <TableHead>{t("theses.list.columnVisibility")}</TableHead>
              <TableHead>{t("theses.list.columnActiveRevision")}</TableHead>
              <TableHead>{t("theses.list.columnChanged")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {theses.data.map((thesis) => (
              <TableRow key={thesis.id}>
                <TableCell>
                  <Link
                    to="/theses/$thesisId"
                    params={{ thesisId: String(thesis.id) }}
                    className="font-medium hover:underline"
                  >
                    {thesis.latest.title}
                  </Link>{" "}
                  {!thesis.is_own && (
                    <Badge variant="outline">{t("theses.list.sharedWithYou")}</Badge>
                  )}
                  {thesis.has_draft && <Badge variant="outline">{t("theses.list.draft")}</Badge>}
                </TableCell>
                <TableCell>
                  <ThesisStatusBadge status={thesis.latest.status} />
                </TableCell>
                <TableCell>{visibilityLabel(thesis.visibility)}</TableCell>
                <TableCell>{thesis.active_revision_no ?? "–"}</TableCell>
                <TableCell>{formatDate(thesis.latest.created_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {importing && (
        <FileImport
          title={t("theses.list.importTitle")}
          description={t("theses.list.importDescription")}
          preview={(text) => thesisImport.preview(text)}
          run={(text) => thesisImport.run(text)}
          renderPreview={(p) => (
            <p>
              <Trans
                i18nKey="theses.list.importPreview"
                values={{
                  visibility: visibilityLabel(p.visibility ?? "private"),
                  title: p.title,
                  status: statusLabel(p.status),
                }}
                components={{ strong: <strong /> }}
              />
            </p>
          )}
          onClose={() => setImporting(false)}
          onDone={(revision) => {
            setImporting(false);
            client.invalidateQueries({ queryKey: thesesKey });
            navigate({ to: "/theses/$thesisId", params: { thesisId: String(revision.thesis_id) } });
          }}
        />
      )}
    </div>
  );
}
