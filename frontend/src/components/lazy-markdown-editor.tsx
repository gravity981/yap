import { lazy, Suspense, type ComponentProps } from "react";
import { useTranslation } from "react-i18next";

// CodeMirror is large; it is loaded only on pages that edit markdown
const Editor = lazy(() => import("./markdown-editor").then((m) => ({ default: m.MarkdownEditor })));

export function MarkdownEditor(props: ComponentProps<typeof Editor>) {
  const { t } = useTranslation();
  return (
    <Suspense
      fallback={
        <p className="text-sm text-muted-foreground">{t("components.markdownEditor.loading")}</p>
      }
    >
      <Editor {...props} />
    </Suspense>
  );
}
