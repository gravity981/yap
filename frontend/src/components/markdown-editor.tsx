import { markdown } from "@codemirror/lang-markdown";
import CodeMirror, { EditorView } from "@uiw/react-codemirror";

import { useTheme } from "@/lib/theme";

function useDark(): boolean {
  const { theme } = useTheme();
  return (
    theme === "dark" ||
    (theme === "system" && (window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false))
  );
}

/** THS-01: the markdown source; the stored markdown is exactly what is typed. The live
 * preview is laid out by the page (e.g. the draft editor, POL-15). */
export function MarkdownSource({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
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
