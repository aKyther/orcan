import { readFile } from "node:fs/promises";
import { defineConfig } from "vite";

// Dev server only: serves the read-only host snapshot written by
// `scripts/dev/orcan-studio-preview snapshot`. It is never part of a build.
const previewSnapshot = {
  name: "orcan-preview-snapshot",
  apply: "serve",
  configureServer(server) {
    server.middlewares.use("/preview-probe.json", async (_request, response) => {
      try {
        const body = await readFile(new URL("./.preview/probe.json", import.meta.url));
        response.setHeader("Content-Type", "application/json");
        response.setHeader("Cache-Control", "no-store");
        response.end(body);
      } catch {
        response.statusCode = 404;
        response.end();
      }
    });
  },
};

export default defineConfig({ plugins: [previewSnapshot] });
