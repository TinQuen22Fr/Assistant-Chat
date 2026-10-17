import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, root, "");
  const port = Number(env.PORT || 3000);
  const hmrPort = env.WDS_SOCKET_PORT ? Number(env.WDS_SOCKET_PORT) : undefined;
  // Cible du proxy : backend FastAPI local. En dev comme en preview, le
  // navigateur n'appelle que des chemins relatifs `/api/...` ; c'est le
  // serveur Vite qui relaie vers uvicorn. Plus aucune URL absolue cote client.
  const backendTarget = env.BACKEND_PROXY_TARGET || "http://127.0.0.1:8010";
  const proxy = {
    "/api": {
      target: backendTarget,
      changeOrigin: true,
      ws: true,
    },
  };
  return {
    plugins: [react()],
    envPrefix: ["VITE_", "REACT_APP_"],
    resolve: { alias: { "@": path.resolve(root, "src") } },
    server: {
      host: "0.0.0.0",
      port,
      strictPort: true,
      allowedHosts: true,
      hmr: hmrPort ? { clientPort: hmrPort, protocol: "wss" } : undefined,
      watch: { ignored: ["**/node_modules/**", "**/build/**"] },
      proxy,
    },
    preview: { host: "0.0.0.0", port, strictPort: true, allowedHosts: true, proxy },
    build: {
      outDir: "build",
      // Decoupage des dependances en chunks stables. Sans cela, tout le
      // node_modules se retrouve dans un unique bundle (~715 kB) et Rollup
      // emet l'avertissement "chunks are larger than 500 kB". Separer les
      // grosses librairies (React, charts, markdown, primitives Radix) reduit
      // ce chunk principal et ameliore la mise en cache navigateur : une
      // modification du code applicatif n'invalide plus le cache des vendored.
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) return undefined;
            if (
              id.includes("recharts") ||
              id.includes("/d3-") ||
              id.includes("victory") ||
              id.includes("react-smooth") ||
              id.includes("decimal.js") ||
              id.includes("tiny-invariant") && id.includes("recharts")
            ) {
              return "vendor-charts";
            }
            if (
              id.includes("react-markdown") ||
              id.includes("remark") ||
              id.includes("rehype") ||
              id.includes("micromark") ||
              id.includes("mdast") ||
              id.includes("hast") ||
              id.includes("unified") ||
              id.includes("/vfile")
            ) {
              return "vendor-markdown";
            }
            if (id.includes("@radix-ui")) return "vendor-radix";
            if (id.includes("react-router") || id.includes("@remix-run")) {
              return "vendor-router";
            }
            // Note : on ne separe PAS React dans son propre chunk. Ses
            // consommateurs restants (clsx, date-fns, cmdk, sonner, vaul...)
            // finissaient aussi dans "vendor", ce qui creait un cycle
            // "vendor <-> vendor-react" signale par Rollup. React reste donc
            // dans "vendor", ces chunks n'important que "vendor" (sens unique).
            return "vendor";
          },
        },
      },
    },
  };
});
