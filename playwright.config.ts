import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";

const PORT = 4317;
const HAS_LOCAL_CHROME = existsSync("/opt/google/chrome/chrome");

// Tests run against the production build served under the GitHub Pages
// project path, so base-path behavior is exercised on every run.
// Run `npm run build` before `npm run test:e2e`.
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: "chromium",
      use: {
        browserName: "chromium",
        // Locally reuse the installed Google Chrome; CI installs the
        // Playwright chromium build.
        channel: process.env.CI || !HAS_LOCAL_CHROME ? undefined : "chrome",
      },
    },
  ],
  webServer: {
    command: `npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}/art-islands/`,
    reuseExistingServer: !process.env.CI,
  },
});
