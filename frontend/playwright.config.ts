import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.E2E_PORT ?? 8790);

// End-to-end tests against the real app (test strategy §2). Build first: npm run build.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  // No retries: the tests build on each other in one database, so a retry starts over on
  // data the first attempt already changed and only adds follow-up failures
  retries: 0,
  // printSteps: every test.step is shown with its result and duration
  reporter: [["list", { printSteps: true }], ["./e2e/req-reporter.ts"]],
  use: {
    baseURL: `http://localhost:${port}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // via bash: the executable bit can get lost (core.fileMode=false on Windows checkouts)
    command: "bash ./e2e/start-server.sh",
    url: `http://localhost:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
