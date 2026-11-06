import "@testing-library/jest-dom/vitest";
import "@/i18n";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// findBy… waits up to 3 s instead of 1 s: with all test files in parallel, the first
// render of a lazily loaded page can take longer than a second
configure({ asyncUtilTimeout: 3000 });

// jsdom has no scrolling; the router scrolls to the top on every navigation
window.scrollTo = () => {};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});
