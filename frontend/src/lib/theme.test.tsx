import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThemeProvider, useTheme } from "./theme";

function Probe() {
  const { theme, setTheme } = useTheme();
  return (
    <>
      <span>{theme}</span>
      <button onClick={() => setTheme("dark")}>dark</button>
      <button onClick={() => setTheme("system")}>system</button>
    </>
  );
}

function prefersDark(dark: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: dark && query.includes("dark"),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

describe("theme", () => {
  it("follows the system setting by default", () => {
    prefersDark(true);
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByText("system", { selector: "span" })).toBeInTheDocument();
    expect(document.documentElement).toHaveClass("dark");
  });

  it("remembers a manual choice", () => {
    prefersDark(false);
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(document.documentElement).not.toHaveClass("dark");
    act(() => screen.getByRole("button", { name: "dark" }).click());
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("itk-theme")).toBe("dark");
    act(() => screen.getByRole("button", { name: "system" }).click());
    expect(localStorage.getItem("itk-theme")).toBeNull();
  });

  it("works without storage", () => {
    prefersDark(false);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    act(() => screen.getByRole("button", { name: "dark" }).click());
    expect(document.documentElement).toHaveClass("dark");
    vi.restoreAllMocks();
  });

  it("fails outside the provider", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow("useTheme outside ThemeProvider");
    vi.restoreAllMocks();
  });
});
