import { lazy, Suspense, type ComponentProps } from "react";
import { useTranslation } from "react-i18next";

// CodeMirror is large; it is loaded only on pages that edit markdown
const Source = lazy(() => import("./markdown-editor").then((m) => ({ default: m.MarkdownSource })));

export function MarkdownSource(props: ComponentProps<typeof Source>) {
  const { t } = useTranslation();
  return (
    <Suspense
      fallback={
        <p className="text-sm text-muted-foreground">{t("components.markdownEditor.loading")}</p>
      }
    >
      <Source {...props} />
    </Suspense>
  );
}
