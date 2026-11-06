import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.SCREENSHOT_PORT ?? 8791);

// Screenshots for docs/features.md: the real app with fictional demo data and the fake
// LLM. Not part of CI. Build first: npm run build, then npm run screenshots.
export default defineConfig({
  testDir: "./screenshots",
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://localhost:${port}`,
    viewport: { width: 1280, height: 800 },
    colorScheme: "light",
  },
  webServer: {
    command: "bash ./e2e/start-server.sh",
    url: `http://localhost:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
    env: { E2E_PORT: String(port) },
  },
});
