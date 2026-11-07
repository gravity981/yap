import { markdown } from "@codemirror/lang-markdown";
import CodeMirror, { EditorView } from "@uiw/react-codemirror";
import { useEffect, useState, type ReactNode } from "react";
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

const WIDE = "(min-width: 1024px)"; // Tailwind's lg

/** Whether the wide layout is shown; the aside is rendered in one layout only, so its
 * state (e.g. a typed answer) exists once. */
function useWide(): boolean {
  const [wide, setWide] = useState(() => window.matchMedia?.(WIDE).matches ?? false);
  useEffect(() => {
    const media = window.matchMedia?.(WIDE);
    if (!media) return;
    const update = () => setWide(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return wide;
}

export interface EditorAside {
  label: string; // the tab next to "Preview"
  content: ReactNode;
}

/** THS-01: markdown source next to a live preview; tabs on narrow screens. The stored
 * markdown is exactly what is typed. An `aside` (e.g. the review, REV-01) is a tab next to
 * the preview. */
export function MarkdownEditor({
  value,
  onChange,
  label,
  aside,
}: {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  aside?: EditorAside;
}) {
  const { t } = useTranslation();
  const name = label ?? t("components.markdownEditor.content");
  const wide = useWide();
  const preview = (
    <div
      className="max-h-[40rem] overflow-auto rounded-md border p-4"
      aria-label={t("components.markdownEditor.preview")}
    >
      <Markdown source={value} />
    </div>
  );
  return (
    <>
      <div className="hidden gap-4 lg:grid lg:grid-cols-2">
        <Source value={value} onChange={onChange} label={name} />
        {aside && wide ? (
          <Tabs defaultValue="preview" className="min-w-0">
            <TabsList>
              <TabsTrigger value="preview">{t("components.markdownEditor.preview")}</TabsTrigger>
              <TabsTrigger value="aside">{aside.label}</TabsTrigger>
            </TabsList>
            <TabsContent value="preview">{preview}</TabsContent>
            <TabsContent value="aside" className="max-h-[40rem] overflow-auto">
              {aside.content}
            </TabsContent>
          </Tabs>
        ) : (
          preview
        )}
      </div>
      <Tabs defaultValue="write" className="lg:hidden">
        <TabsList>
          <TabsTrigger value="write">{t("components.markdownEditor.write")}</TabsTrigger>
          <TabsTrigger value="preview">{t("components.markdownEditor.preview")}</TabsTrigger>
          {aside && !wide && <TabsTrigger value="aside">{aside.label}</TabsTrigger>}
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
        {aside && !wide && <TabsContent value="aside">{aside.content}</TabsContent>}
      </Tabs>
    </>
  );
}
