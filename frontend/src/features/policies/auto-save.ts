import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/api/client";

/** POL-14: saved (with the time of the last save), saving, failed and retried, or not
 * savable as it is (e.g. a threshold out of range, shown at its field). */
export interface SaveStatus {
  state: "saved" | "saving" | "failed" | "invalid";
  at: Date | null;
}

const RETRY_MS = 5000;

/**
 * POL-14: saves `value` shortly after it stops changing; `flush` saves at once and is
 * awaited before a review starts, a prompt is copied or the draft is finalized. Saves
 * run one after the other. A failed save is retried; when the page is left with
 * unsaved changes, `keepalive` sends them without waiting for an answer.
 */
export function useAutoSave<T>(
  value: T,
  save: (value: T) => Promise<unknown>,
  keepalive: (value: T) => void,
  delay = 800,
) {
  const serialized = JSON.stringify(value);
  const saved = useRef(serialized); // the content as it is on the server
  const latest = useRef({ value, serialized });
  const saveRef = useRef(save);
  const keepaliveRef = useRef(keepalive);
  const chain = useRef<Promise<unknown>>(Promise.resolve());
  const retry = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [status, setStatus] = useState<SaveStatus>({ state: "saved", at: null });
  const flushRef = useRef<() => Promise<unknown>>(() => Promise.resolve());

  useEffect(() => {
    latest.current = { value, serialized };
    saveRef.current = save;
    keepaliveRef.current = keepalive;
  });

  const flush = useCallback((): Promise<unknown> => {
    const run = async () => {
      clearTimeout(retry.current);
      const current = latest.current;
      if (current.serialized === saved.current) return;
      setStatus((s) => ({ ...s, state: "saving" }));
      try {
        await saveRef.current(current.value);
        saved.current = current.serialized;
        setStatus({ state: "saved", at: new Date() });
      } catch (error) {
        const invalid = error instanceof ApiError && error.status === 422;
        setStatus((s) => ({ ...s, state: invalid ? "invalid" : "failed" }));
        if (!invalid) {
          retry.current = setTimeout(
            () => void flushRef.current().catch(() => undefined),
            RETRY_MS,
          );
        }
        throw error;
      }
    };
    const next = chain.current.then(run, run);
    chain.current = next.catch(() => undefined);
    return next;
  }, []);

  useEffect(() => {
    flushRef.current = flush;
  }, [flush]);

  /** The content as the server has it now, e.g. after a suggestion was taken over. */
  const markSaved = useCallback((value: T) => {
    saved.current = JSON.stringify(value);
  }, []);

  useEffect(() => {
    if (serialized === saved.current) return;
    const timer = setTimeout(() => void flush().catch(() => undefined), delay);
    return () => clearTimeout(timer);
  }, [serialized, delay, flush]);

  useEffect(() => {
    const leave = () => {
      if (latest.current.serialized !== saved.current) keepaliveRef.current(latest.current.value);
    };
    window.addEventListener("beforeunload", leave);
    return () => {
      window.removeEventListener("beforeunload", leave);
      clearTimeout(retry.current);
      leave(); // the editor is left inside the app
    };
  }, []);

  return { status, flush, markSaved };
}
