import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// GitHub Pages project path. All data fetches derive from import.meta.env.BASE_URL.
export default defineConfig({
  root: "web",
  publicDir: "../public",
  base: "/art-islands/",
  plugins: [react()],
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
