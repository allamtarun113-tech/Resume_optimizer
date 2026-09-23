import { defineConfig, devices } from "@playwright/test";
import { config } from "dotenv";

// Credentials for the dedicated test user live in .env.e2e.local (gitignored).
config({ path: ".env.e2e.local" });

export default defineConfig({
  testDir: "./e2e",
  // The backend sleeps when idle (Render free tier) and an analysis runs several LLM calls.
  timeout: 6 * 60_000,
  expect: { timeout: 15_000 },
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL:
      process.env.E2E_BASE_URL ??
      "https://resume-optimizer-ten-virid.vercel.app",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
