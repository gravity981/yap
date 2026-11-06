import { markdown } from "@codemirror/lang-markdown";
import CodeMirror, { EditorView } from "@uiw/react-codemirror";
import { useTranslation } from "react-i18next";

import { Markdown } from "@/components/markdown";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTheme } from "@/lib/theme";

function useDark(): boolean {
  const { theme } = useTheme();
  return (
    theme === "dark" ||
    (theme === "system" && (window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false))
  );
}

function Source({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
}) {
  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      extensions={[markdown(), EditorView.lineWrapping]}
      theme={useDark() ? "dark" : "light"}
      minHeight="24rem"
      aria-label={label}
      className="overflow-hidden rounded-md border text-sm"
    />
  );
}

/** THS-01: markdown source next to a live preview; tabs on narrow screens. The stored
 * markdown is exactly what is typed. */
export function MarkdownEditor({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  label?: string;
}) {
  const { t } = useTranslation();
  const name = label ?? t("components.markdownEditor.content");
  return (
    <>
      <div className="hidden gap-4 lg:grid lg:grid-cols-2">
        <Source value={value} onChange={onChange} label={name} />
        <div
          className="max-h-[40rem] overflow-auto rounded-md border p-4"
          aria-label={t("components.markdownEditor.preview")}
        >
          <Markdown source={value} />
        </div>
      </div>
      <Tabs defaultValue="write" className="lg:hidden">
        <TabsList>
          <TabsTrigger value="write">{t("components.markdownEditor.write")}</TabsTrigger>
          <TabsTrigger value="preview">{t("components.markdownEditor.preview")}</TabsTrigger>
        </TabsList>
        <TabsContent value="write">
          <Source
            value={value}
            onChange={onChange}
            label={t("components.markdownEditor.narrow", { label: name })}
          />
        </TabsContent>
        <TabsContent value="preview" className="rounded-md border p-4">
          <Markdown source={value} />
        </TabsContent>
      </Tabs>
    </>
  );
}
